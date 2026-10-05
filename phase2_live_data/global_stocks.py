"""Near-live quote helpers for US and Indian Yahoo Finance symbols.

Yahoo Finance is a best-effort, unofficial data source. Prices can be delayed
or unavailable; use an exchange-licensed feed for production trading.
"""

from __future__ import annotations

import os
import math
from datetime import datetime, timezone
from typing import Mapping, Sequence

import yfinance as yf


DEFAULT_GLOBAL_SYMBOLS = ("AAPL", "MSFT", "RELIANCE.NS", "TCS.NS")
DEFAULT_GLOBAL_DUMMY = {
    "AAPL": 190.25,
    "MSFT": 420.10,
    "RELIANCE.NS": 2_850.0,
    "TCS.NS": 3_950.0,
}


def symbols_from_env(name: str, default: Sequence[str]) -> tuple[str, ...]:
    """Read a comma-separated list of symbols, preserving order and uniqueness."""
    raw = os.getenv(name, ",".join(default))
    return tuple(dict.fromkeys(item.strip().upper() for item in raw.split(",") if item.strip()))


def _timestamp_ms(index_value: object) -> int:
    try:
        return int(index_value.timestamp() * 1000)  # pandas Timestamp / datetime
    except (AttributeError, TypeError, ValueError, OverflowError):
        return int(datetime.now(timezone.utc).timestamp() * 1000)


def _change_percent(history) -> float:
    if history is None or history.empty:
        return 0.0
    if len(history) > 1:
        base = float(history.iloc[0]["Open"])
    else:
        base = float(history.iloc[0]["Open"])
    latest = float(history.iloc[-1]["Close"])
    if not math.isfinite(base) or not math.isfinite(latest) or base <= 0:
        return 0.0
    return (latest - base) / base * 100.0


def fetch_yfinance_quotes(
    symbols: Sequence[str],
    *,
    market: str,
    dummy_prices: Mapping[str, float] | None = None,
) -> list[dict[str, object]]:
    """Fetch the latest available quote per Yahoo symbol with a labeled fallback."""
    fallbacks = dummy_prices or {}
    quotes: list[dict[str, object]] = []
    for symbol in symbols:
        ticker_symbol = symbol.strip().upper()
        try:
            ticker = yf.Ticker(ticker_symbol)
            history = ticker.history(period="1d", interval="1m", auto_adjust=False, timeout=10)
            if history is None or history.empty:
                history = ticker.history(period="5d", interval="1d", auto_adjust=False, timeout=10)
            if history is None or history.empty:
                raise ValueError("No quote rows returned by Yahoo Finance.")

            row = history.iloc[-1]
            price = float(row["Close"])
            if not math.isfinite(price) or price <= 0:
                raise ValueError("Provider returned a non-positive close price.")
            quotes.append({
                "market": market,
                "symbol": ticker_symbol,
                "price": price,
                "change_pct": round(_change_percent(history), 3),
                "timestamp_ms": _timestamp_ms(history.index[-1]),
                "source": "Yahoo Finance via yfinance",
                "is_live": True,
                "status": "ok",
            })
        except Exception as exc:
            quotes.append({
                "market": market,
                "symbol": ticker_symbol,
                "price": float(fallbacks.get(ticker_symbol, 0.0)),
                "change_pct": 0.0,
                "timestamp_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
                "source": "Sample placeholder",
                "is_live": False,
                "status": f"sample: {type(exc).__name__}",
            })
    return quotes


def fetch_global_stock_data(symbols: Sequence[str] | None = None) -> list[dict[str, object]]:
    """Fetch configured US and Indian stock symbols (Yahoo suffixes included)."""
    configured = tuple(symbols) if symbols is not None else symbols_from_env(
        "OMNI_GLOBAL_SYMBOLS", DEFAULT_GLOBAL_SYMBOLS
    )
    return fetch_yfinance_quotes(
        configured,
        market="global_stocks",
        dummy_prices=DEFAULT_GLOBAL_DUMMY,
    )
