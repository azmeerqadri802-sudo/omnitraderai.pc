"""Optional loopback-only FastAPI endpoints for market quote snapshots."""

from __future__ import annotations

from fastapi import FastAPI

from .forex_data import fetch_forex_data
from .global_stocks import fetch_global_stock_data
from .psx_data import fetch_psx_data


app = FastAPI(title="Omni Trader Local Market API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "omni-trader-market-api"}


@app.get("/market/psx")
def psx_quotes() -> list[dict[str, object]]:
    return fetch_psx_data()


@app.get("/market/global-stocks")
def global_stock_quotes() -> list[dict[str, object]]:
    return fetch_global_stock_data()


@app.get("/market/forex")
def forex_quotes() -> list[dict[str, object]]:
    return fetch_forex_data()
