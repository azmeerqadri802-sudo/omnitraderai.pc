"""Async public Binance Spot ticker stream, normalized for the dashboard."""

from __future__ import annotations

import asyncio
import inspect
import json
import math
from datetime import datetime, timezone
from typing import Awaitable, Callable, Sequence
from urllib.parse import quote

import websockets


DEFAULT_CRYPTO_SYMBOLS = ("btcusdt", "ethusdt", "solusdt", "bnbusdt")
PriceCallback = Callable[[dict[str, object]], object | Awaitable[object]]
BINANCE_STREAM_BASE = "wss://stream.binance.com:9443/stream?streams="


def _normalize_ticker(payload: dict[str, object]) -> dict[str, object] | None:
    try:
        symbol = str(payload["s"]).upper()
        price = float(payload["c"])
        change_pct = float(payload.get("P", 0.0))
        timestamp_ms = int(payload.get("E", datetime.now(timezone.utc).timestamp() * 1000))
    except (KeyError, TypeError, ValueError):
        return None
    if not math.isfinite(price) or price <= 0:
        return None
    if not math.isfinite(change_pct):
        change_pct = 0.0
    return {
        "market": "crypto",
        "symbol": symbol,
        "price": price,
        "change_pct": change_pct,
        "timestamp_ms": timestamp_ms,
        "source": "Binance Spot WebSocket",
        "is_live": True,
        "status": "ok",
    }


async def stream_crypto_prices(
    callback: PriceCallback,
    *,
    symbols: Sequence[str] = DEFAULT_CRYPTO_SYMBOLS,
    stop_event: asyncio.Event | None = None,
    reconnect_delay: float = 3.0,
) -> None:
    """Call ``callback`` for each ticker; reconnect with backoff until stopped.

    `callback` may be synchronous or async. A single combined stream is used
    for the configured symbols; Binance connections are expected to rotate
    periodically, so reconnect behavior is part of the normal lifecycle.
    """
    stop = stop_event or asyncio.Event()
    normalized_symbols = tuple(dict.fromkeys(item.lower().replace("/", "") for item in symbols))
    if not normalized_symbols:
        raise ValueError("At least one Binance symbol is required.")
    streams = "/".join(f"{symbol}@ticker" for symbol in normalized_symbols)
    uri = BINANCE_STREAM_BASE + quote(streams, safe="/@")

    while not stop.is_set():
        try:
            async with websockets.connect(
                uri,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=5,
                max_size=1_000_000,
            ) as socket:
                while not stop.is_set():
                    try:
                        raw_message = await asyncio.wait_for(socket.recv(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue
                    envelope = json.loads(raw_message)
                    payload = envelope.get("data", envelope)
                    if not isinstance(payload, dict):
                        continue
                    quote_row = _normalize_ticker(payload)
                    if quote_row is not None:
                        result = callback(quote_row)
                        if inspect.isawaitable(result):
                            await result
        except asyncio.CancelledError:
            raise
        except Exception:
            if stop.is_set():
                return
            try:
                await asyncio.wait_for(stop.wait(), timeout=max(0.5, reconnect_delay))
            except asyncio.TimeoutError:
                pass
