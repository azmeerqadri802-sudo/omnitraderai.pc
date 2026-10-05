# Omni Trader

Omni Trader is a Python desktop dashboard scaffold with market data, chart-image analysis, and guarded Binance Spot integration.

## Run locally

Requires Python 3.10 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

Open **Settings** in the dashboard to save Binance and Gemini API credentials. The app uses the operating system credential store (Windows Credential Manager on Windows) and rejects insecure plaintext, null, or file backends. No `.env` file is used for credentials. On Linux or macOS, unlock and configure the desktop system keyring before saving keys.

For Binance, use the narrowest permissions required and keep withdrawals disabled. Order routing is opt-in, dry-run and Spot Testnet are the defaults, and production execution has a separate explicit lock. Review `phase4_binance_engine/trade_executor.py` before enabling any order routing.

## Market data and AI

- Public Binance Spot WebSocket streams provide crypto quotes without credentials.
- Yahoo Finance quotes can be delayed; provider coverage for PSX symbols varies.
- Omni AI uploads a chart screenshot to the configured Gemini model and validates the returned JSON.
- Optional market polling and local API settings can be supplied as process environment variables; API secrets belong in the Settings page.

## Windows executable

Every push triggers `.github/workflows/build.yml`. After the workflow completes, download `OmniTrader.exe` from the run's **Artifacts** section. The artifact is retained for 30 days.

## Project layout

```text
main.py
phase1_ui/
phase2_live_data/
phase3_omni_ai/
phase4_binance_engine/
.github/workflows/build.yml
```

Market feeds can be delayed, stale, or unavailable. AI chart analysis is not a live quote or verified order instruction. Use licensed feeds and appropriate controls for production trading.
