"""Read Binance Spot balances without returning credentials or raw account data."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from .client_factory import create_binance_client


def get_account_balance(*, testnet: bool = True, include_zero: bool = False) -> list[dict[str, str]]:
    """Return asset/free/locked strings; Testnet is the default environment."""
    client = create_binance_client(testnet=testnet)
    account: dict[str, Any] = client.get_account()
    balances = []
    for row in account.get("balances", []):
        free = Decimal(str(row.get("free", "0")))
        locked = Decimal(str(row.get("locked", "0")))
        if not include_zero and free == 0 and locked == 0:
            continue
        balances.append({
            "asset": str(row.get("asset", "")),
            "free": format(free, "f"),
            "locked": format(locked, "f"),
        })
    return balances


def get_asset_balance(asset: str, *, testnet: bool = True) -> dict[str, str]:
    """Return one asset balance, or zeroes if it is not present in the account."""
    normalized = asset.strip().upper()
    if not normalized:
        raise ValueError("asset must not be empty")
    for row in get_account_balance(testnet=testnet, include_zero=True):
        if row["asset"].upper() == normalized:
            return row
    return {"asset": normalized, "free": "0", "locked": "0"}
