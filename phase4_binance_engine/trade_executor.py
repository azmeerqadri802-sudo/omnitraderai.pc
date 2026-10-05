"""Guarded Binance Spot market-order helpers.

Orders default to dry-run and Spot Testnet. The AI chart output is not accepted
as an order size or executable limit price. Call these functions explicitly.
"""

from __future__ import annotations

import os
import hashlib
import json
import re
import threading
import time
import uuid
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Any, Mapping

from .client_factory import create_binance_client

_SIGNAL_FIELDS = {"Action", "Open_Price", "Close_Price", "Reason"}
_PRICE_RE = re.compile(r"^\d+(?:\.\d+)?$")
_GUARD_LOCK = threading.Lock()
_RECENT_SIGNALS: dict[str, float] = {}
_SYMBOL_COOLDOWNS: dict[str, float] = {}


def _decimal(value: Decimal | str | float, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{field} must be a decimal number") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError(f"{field} must be a positive finite number")
    return parsed


def _decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _validate_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    allowed = {
        item.strip().upper()
        for item in os.getenv("BINANCE_ALLOWED_SYMBOLS", "BTCUSDT").split(",")
        if item.strip()
    }
    if normalized not in allowed:
        raise ValueError("Symbol must be included in BINANCE_ALLOWED_SYMBOLS (BTCUSDT by default).")
    return normalized


def _mode(dry_run: bool, testnet: bool) -> str:
    if not dry_run and not testnet and os.getenv("OMNI_LIVE_TRADING", "").strip() != "YES":
        raise RuntimeError("Production orders are locked; set OMNI_LIVE_TRADING=YES explicitly.")
    return "dry_run" if dry_run else ("testnet" if testnet else "live")


def place_buy_order(
    symbol: str,
    quote_amount: Decimal | str | float,
    *,
    dry_run: bool = True,
    testnet: bool = True,
) -> dict[str, Any]:
    """Buy at market, capped by a quote-currency amount (USDT pairs only)."""
    mode = _mode(dry_run, testnet)
    normalized = _validate_symbol(symbol)
    amount = _decimal(quote_amount, "quote_amount")
    maximum = _decimal(os.getenv("OMNI_MAX_BUY_USDT", "25"), "OMNI_MAX_BUY_USDT")
    if amount > maximum:
        raise ValueError(f"Buy amount exceeds configured cap ({_decimal_text(maximum)} USDT).")
    if dry_run:
        return {
            "status": "dry_run", "mode": mode, "symbol": normalized,
            "side": "BUY", "type": "MARKET", "quoteOrderQty": _decimal_text(amount),
        }

    client = create_binance_client(testnet=testnet)
    info = client.get_symbol_info(normalized)
    if not info or info.get("status") != "TRADING":
        raise RuntimeError(f"{normalized} is not currently trading on Binance Spot.")
    if info.get("quoteAsset") != "USDT":
        raise ValueError("OMNI_MAX_BUY_USDT is denominated in USDT; use a USDT-quoted symbol.")
    minimum = Decimal("0")
    for rule in info.get("filters", []):
        if rule.get("filterType") in {"MIN_NOTIONAL", "NOTIONAL"}:
            applies = rule.get("applyToMarket", rule.get("applyMinToMarket", True))
            if applies:
                minimum = Decimal(str(rule.get("minNotional", "0")))
            break
    if minimum and amount < minimum:
        raise ValueError("Buy amount is below Binance's minimum market notional for this symbol.")
    balance = client.get_asset_balance(asset="USDT") or {}
    if amount > Decimal(str(balance.get("free", "0"))):
        raise ValueError("Insufficient free USDT balance for this buy.")

    response = client.order_market_buy(
        symbol=normalized,
        quoteOrderQty=_decimal_text(amount),
        newClientOrderId="OMNI" + uuid.uuid4().hex[:28],
        recvWindow=5_000,
    )
    return _order_summary(response, mode, normalized, "BUY")


def place_sell_order(
    symbol: str,
    base_quantity: Decimal | str | float,
    *,
    dry_run: bool = True,
    testnet: bool = True,
) -> dict[str, Any]:
    """Sell a configured bounded base quantity; never liquidate the full balance."""
    mode = _mode(dry_run, testnet)
    normalized = _validate_symbol(symbol)
    requested = _decimal(base_quantity, "base_quantity")
    maximum = _decimal(os.getenv("OMNI_MAX_SELL_BASE", "0.0001"), "OMNI_MAX_SELL_BASE")
    if requested > maximum:
        raise ValueError(f"Sell quantity exceeds configured cap ({_decimal_text(maximum)} base units).")
    if dry_run:
        return {
            "status": "dry_run", "mode": mode, "symbol": normalized,
            "side": "SELL", "type": "MARKET", "quantity": _decimal_text(requested),
        }

    client = create_binance_client(testnet=testnet)
    info = client.get_symbol_info(normalized)
    if not info or info.get("status") != "TRADING":
        raise RuntimeError(f"{normalized} is not currently trading on Binance Spot.")
    rules = {rule.get("filterType"): rule for rule in info.get("filters", [])}
    market_lot = rules.get("MARKET_LOT_SIZE") or rules.get("LOT_SIZE")
    if not market_lot:
        raise RuntimeError("Binance did not return a quantity filter for this symbol.")
    step = Decimal(str(market_lot.get("stepSize", "0")))
    if step <= 0:
        market_lot = rules.get("LOT_SIZE")
        step = Decimal(str((market_lot or {}).get("stepSize", "0")))
    if step <= 0:
        raise RuntimeError("Binance returned an invalid quantity step size.")
    quantity = (requested / step).to_integral_value(rounding=ROUND_DOWN) * step
    minimum_quantity = Decimal(str(market_lot.get("minQty", "0")))
    maximum_quantity = Decimal(str(market_lot.get("maxQty", "0")))
    if quantity < minimum_quantity or (maximum_quantity > 0 and quantity > maximum_quantity):
        raise ValueError("Sell quantity is outside Binance's current market quantity limits.")

    base_asset = str(info["baseAsset"])
    balance = client.get_asset_balance(asset=base_asset) or {}
    if quantity > Decimal(str(balance.get("free", "0"))):
        raise ValueError(f"Insufficient free {base_asset} balance for this sell.")
    response = client.order_market_sell(
        symbol=normalized,
        quantity=_decimal_text(quantity),
        newClientOrderId="OMNI" + uuid.uuid4().hex[:28],
        recvWindow=5_000,
    )
    return _order_summary(response, mode, normalized, "SELL")


def execute_ai_signal(signal_payload: str | Mapping[str, Any]) -> dict[str, Any]:
    """Route a validated Omni AI Buy/Sell signal to a bounded market order.

    Call explicitly from a worker thread. Dry-run and Testnet are the defaults;
    chart levels are sanity-checked but do not set market order prices.
    """
    if isinstance(signal_payload, str):
        try:
            signal = json.loads(signal_payload)
        except json.JSONDecodeError as exc:
            raise ValueError("Omni AI signal must be valid JSON.") from exc
    else:
        signal = dict(signal_payload)
    if not isinstance(signal, dict) or set(signal) != _SIGNAL_FIELDS:
        raise ValueError("Signal must contain exactly Action, Open_Price, Close_Price, and Reason.")
    if any(not isinstance(signal[key], str) for key in _SIGNAL_FIELDS):
        raise ValueError("All Omni AI signal values must be strings.")
    action = signal["Action"]
    if action not in {"Buy", "Sell", "Hold"}:
        raise ValueError("Action must be Buy, Sell, or Hold.")
    if action == "Hold":
        return {"status": "held", "action": action, "message": signal["Reason"]}

    prices: dict[str, Decimal] = {}
    for field in ("Open_Price", "Close_Price"):
        text = signal[field].strip()
        if not _PRICE_RE.fullmatch(text):
            raise ValueError(f"{field} must be a positive decimal for Buy/Sell.")
        prices[field] = _decimal(text, field)
    if action == "Buy" and prices["Close_Price"] <= prices["Open_Price"]:
        raise ValueError("Buy signal target must be above entry.")
    if action == "Sell" and prices["Close_Price"] >= prices["Open_Price"]:
        raise ValueError("Sell signal target must be below entry.")

    symbol = os.getenv("BINANCE_SYMBOL", "BTCUSDT").strip().upper()
    canonical = json.dumps(signal, sort_keys=True, separators=(",", ":"))
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    now = time.time()
    cooldown = int(os.getenv("OMNI_MIN_ORDER_INTERVAL_SECONDS", "10"))
    dedupe_seconds = int(os.getenv("OMNI_SIGNAL_DEDUPE_SECONDS", "90"))
    with _GUARD_LOCK:
        for key, expiry in list(_RECENT_SIGNALS.items()):
            if expiry <= now:
                _RECENT_SIGNALS.pop(key, None)
        if fingerprint in _RECENT_SIGNALS:
            return {"status": "duplicate_ignored", "symbol": symbol}
        if _SYMBOL_COOLDOWNS.get(symbol, 0) > now:
            return {"status": "cooldown", "symbol": symbol}
        # Reserve before the request so concurrent callbacks cannot double-submit.
        _RECENT_SIGNALS[fingerprint] = now + max(1, dedupe_seconds)
        _SYMBOL_COOLDOWNS[symbol] = now + max(1, cooldown)

    dry_run = os.getenv("OMNI_DRY_RUN", "true").strip().lower() in {"1", "true", "yes", "on"}
    testnet = os.getenv("BINANCE_TESTNET", "true").strip().lower() not in {"0", "false", "no", "off"}
    if action == "Buy":
        amount = os.getenv("OMNI_BUY_QUOTE_QTY_USDT", "25")
        return place_buy_order(symbol, amount, dry_run=dry_run, testnet=testnet)
    quantity = os.getenv("OMNI_SELL_BASE_QTY", "0.0001")
    return place_sell_order(symbol, quantity, dry_run=dry_run, testnet=testnet)


def _order_summary(
    response: dict[str, Any], mode: str, symbol: str, side: str
) -> dict[str, Any]:
    """Return only safe, useful order fields; never print credentials or raw requests."""
    return {
        "status": "submitted",
        "mode": mode,
        "symbol": symbol,
        "side": side,
        "order_id": response.get("orderId"),
        "client_order_id": response.get("clientOrderId"),
        "order_status": response.get("status"),
        "executed_qty": response.get("executedQty"),
        "quote_qty": response.get("cummulativeQuoteQty"),
    }
