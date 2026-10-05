"""Centralized Binance client construction and credential loading."""

from __future__ import annotations

import os

from binance.client import Client
from .credential_store import get_secret


def create_binance_client(*, testnet: bool = True) -> Client:
    """Create a client only on explicit use; do not log credentials."""
    if not testnet and os.getenv("OMNI_LIVE_TRADING", "").strip() != "YES":
        raise RuntimeError("Live execution is locked. Set OMNI_LIVE_TRADING=YES to unlock it.")
    api_key = (get_secret("BINANCE_API_KEY") or "").strip()
    api_secret = (get_secret("BINANCE_SECRET_KEY") or "").strip()
    if not api_key or not api_secret:
        raise RuntimeError("Save both Binance API credentials in Settings before using this feature.")
    return Client(
        api_key=api_key,
        api_secret=api_secret,
        testnet=testnet,
        requests_params={"timeout": 10},
    )
