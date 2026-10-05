"""Pakistan Stock Exchange quote scaffold with Yahoo/dummy fallback."""

from __future__ import annotations

from typing import Sequence

from .global_stocks import fetch_yfinance_quotes, symbols_from_env


# Yahoo's Pakistan listings commonly use the .KA suffix; check provider coverage
# for each instrument before relying on it. These are only starter examples.
DEFAULT_PSX_SYMBOLS = ("OGDC.KA", "HBL.KA", "LUCK.KA")
DEFAULT_PSX_DUMMY = {"OGDC.KA": 245.0, "HBL.KA": 128.5, "LUCK.KA": 615.0}


def fetch_psx_data(symbols: Sequence[str] | None = None) -> list[dict[str, object]]:
    """Fetch best-effort PSX quotes; return clearly labeled placeholders on failure."""
    configured = tuple(symbols) if symbols is not None else symbols_from_env(
        "OMNI_PSX_SYMBOLS", DEFAULT_PSX_SYMBOLS
    )
    return fetch_yfinance_quotes(
        configured,
        market="psx",
        dummy_prices=DEFAULT_PSX_DUMMY,
    )
