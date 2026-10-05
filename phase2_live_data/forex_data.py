"""Best-effort Yahoo Finance forex quote helper."""

from __future__ import annotations

from typing import Sequence

from .global_stocks import fetch_yfinance_quotes, symbols_from_env


DEFAULT_FOREX_SYMBOLS = ("EURUSD=X", "GBPUSD=X", "USDJPY=X", "USDCHF=X")
DEFAULT_FOREX_DUMMY = {
    "EURUSD=X": 1.085,
    "GBPUSD=X": 1.275,
    "USDJPY=X": 149.5,
    "USDCHF=X": 0.885,
}


def fetch_forex_data(symbols: Sequence[str] | None = None) -> list[dict[str, object]]:
    configured = tuple(symbols) if symbols is not None else symbols_from_env(
        "OMNI_FOREX_SYMBOLS", DEFAULT_FOREX_SYMBOLS
    )
    return fetch_yfinance_quotes(
        configured,
        market="forex",
        dummy_prices=DEFAULT_FOREX_DUMMY,
    )
