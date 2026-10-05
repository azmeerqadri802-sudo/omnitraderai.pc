"""Omni Trader desktop entry point; providers run outside the GUI thread."""

from __future__ import annotations

import asyncio
import os
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Sequence

from PyQt5.QtCore import QThread, QTimer, pyqtSignal
from PyQt5.QtWidgets import QApplication


from phase1_ui.app_ui import DashboardWindow  # noqa: E402
from phase2_live_data.crypto_sockets import DEFAULT_CRYPTO_SYMBOLS, stream_crypto_prices  # noqa: E402
from phase2_live_data.forex_data import fetch_forex_data  # noqa: E402
from phase2_live_data.global_stocks import fetch_global_stock_data  # noqa: E402
from phase2_live_data.psx_data import fetch_psx_data  # noqa: E402
from phase4_binance_engine.credential_store import (  # noqa: E402
    check_secure_store,
    delete_secret,
    get_secret,
    has_secret,
    save_secret,
)


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return min(max(value, minimum), maximum)


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _redact_stored_secrets(message: str, names: Sequence[str]) -> str:
    """Remove stored key values from provider errors before showing them in the UI."""
    for name in names:
        try:
            secret = get_secret(name)
        except Exception:
            continue
        if secret:
            message = message.replace(secret, "[redacted]")
    return message


class MarketDataWorker(QThread):
    """Poll slower Yahoo feeds and consume Binance WebSocket updates off-UI."""

    quotes_ready = pyqtSignal(str, object)
    crypto_update = pyqtSignal(object)
    status_changed = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._stop_requested = threading.Event()
        self._poll_seconds = _int_env("OMNI_STOCK_POLL_SECONDS", 60, 30, 3_600)
        raw_symbols = os.getenv("OMNI_CRYPTO_SYMBOLS", ",".join(DEFAULT_CRYPTO_SYMBOLS))
        self._crypto_symbols: Sequence[str] = tuple(
            dict.fromkeys(item.strip().lower().replace("/", "") for item in raw_symbols.split(",") if item.strip())
        )

    def stop(self) -> None:
        self._stop_requested.set()

    def run(self) -> None:
        try:
            asyncio.run(self._run_async())
        except Exception as exc:
            self.status_changed.emit(f"DATA WORKER ERROR: {type(exc).__name__}")

    async def _run_async(self) -> None:
        async_stop = asyncio.Event()
        crypto_task = asyncio.create_task(
            stream_crypto_prices(
                self.crypto_update.emit,
                symbols=self._crypto_symbols,
                stop_event=async_stop,
            )
        )
        try:
            self._emit_crypto_sample()
            while not self._stop_requested.is_set():
                jobs = (
                    asyncio.to_thread(fetch_psx_data),
                    asyncio.to_thread(fetch_global_stock_data),
                    asyncio.to_thread(fetch_forex_data),
                )
                markets = ("psx", "global_stocks", "forex")
                results = await asyncio.gather(*jobs, return_exceptions=True)
                for market, result in zip(markets, results):
                    if isinstance(result, Exception):
                        self.status_changed.emit(f"{market.upper()} PROVIDER ERROR")
                        self.quotes_ready.emit(market, [])
                    else:
                        self.quotes_ready.emit(market, result)
                self.status_changed.emit("MARKET SNAPSHOT UPDATED  ·  CRYPTO STREAM CONNECTING")

                for _ in range(self._poll_seconds):
                    if self._stop_requested.is_set():
                        break
                    await asyncio.sleep(1)
        finally:
            async_stop.set()
            try:
                await asyncio.wait_for(crypto_task, timeout=4)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                crypto_task.cancel()
                await asyncio.gather(crypto_task, return_exceptions=True)

    def _emit_crypto_sample(self) -> None:
        samples = {
            "BTCUSDT": (67_200.0, 0.8),
            "ETHUSDT": (3_450.0, 0.4),
            "SOLUSDT": (152.4, -0.3),
            "BNBUSDT": (590.0, 0.2),
        }
        timestamp_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        for symbol in self._crypto_symbols:
            upper = symbol.upper()
            price, change = samples.get(upper, (0.0, 0.0))
            self.crypto_update.emit({
                "market": "crypto",
                "symbol": upper,
                "price": price,
                "change_pct": change,
                "timestamp_ms": timestamp_ms,
                "source": "Sample placeholder",
                "is_live": False,
                "status": "sample",
            })


class ChartAnalysisWorker(QThread):
    result_ready = pyqtSignal(object)
    error_ready = pyqtSignal(str)

    def __init__(self, image_path: str, parent=None) -> None:
        super().__init__(parent)
        self.image_path = image_path

    def run(self) -> None:
        try:
            from phase3_omni_ai.gemini_vision import GeminiVisionAnalyzer
            from phase3_omni_ai.image_processor import process_chart_image

            image = process_chart_image(self.image_path)
            result = GeminiVisionAnalyzer().analyze_image(image)
            self.result_ready.emit(result)
        except Exception as exc:
            message = _redact_stored_secrets(
                f"{type(exc).__name__}: {exc}",
                ("GEMINI_API_KEY", "BINANCE_API_KEY", "BINANCE_SECRET_KEY"),
            )
            self.error_ready.emit(message)


class TradeExecutionWorker(QThread):
    result_ready = pyqtSignal(object)
    error_ready = pyqtSignal(str)

    def __init__(self, signal: dict[str, str], parent=None) -> None:
        super().__init__(parent)
        self.signal = signal

    def run(self) -> None:
        try:
            from phase4_binance_engine.trade_executor import execute_ai_signal

            self.result_ready.emit(execute_ai_signal(self.signal))
        except Exception as exc:
            message = _redact_stored_secrets(
                f"{type(exc).__name__}: {exc}",
                ("BINANCE_API_KEY", "BINANCE_SECRET_KEY"),
            )
            self.error_ready.emit(message)


def _start_local_api() -> None:
    """Run optional unauthenticated development API on loopback only."""
    from uvicorn import run
    from phase2_live_data.api_server import app as api_app

    host = os.getenv("OMNI_API_HOST", "127.0.0.1")
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("The unauthenticated starter API can only bind to loopback.")
    port = _int_env("OMNI_API_PORT", 8765, 1, 65_535)
    run(api_app, host=host, port=port, log_level="warning")


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Omni Trader")
    app.setStyle("Fusion")
    window = DashboardWindow()

    def save_credential(name: str, value: str) -> None:
        try:
            save_secret(name, value)
            window.settings_page.clear_field(name)
            window.settings_page.set_key_status(name, "Saved in system keyring", success=True)
        except Exception as exc:
            window.settings_page.set_key_status(
                name,
                f"Secure save failed ({type(exc).__name__}); check OS keyring availability.",
                success=False,
            )

    def remove_credential(name: str) -> None:
        try:
            delete_secret(name)
            window.settings_page.clear_field(name)
            window.settings_page.set_key_status(name, "Removed from system keyring", success=False)
        except Exception as exc:
            window.settings_page.set_key_status(
                name,
                f"Secure removal failed ({type(exc).__name__}).",
                success=False,
            )

    window.credential_save_requested.connect(save_credential)
    window.credential_delete_requested.connect(remove_credential)
    try:
        check_secure_store()
        for name, _, _ in window.settings_page.CREDENTIALS:
            saved = has_secret(name)
            window.settings_page.set_key_status(
                name,
                "Saved in system keyring" if saved else "Not saved",
                success=saved,
            )
    except Exception as exc:
        for name, _, _ in window.settings_page.CREDENTIALS:
            window.settings_page.set_key_status(
                name,
                f"Secure store unavailable ({type(exc).__name__})",
                success=False,
            )

    market_worker = MarketDataWorker()
    market_worker.quotes_ready.connect(window.update_market)
    market_worker.crypto_update.connect(window.update_crypto)
    market_worker.status_changed.connect(window.set_connection_status)
    market_worker.start()

    active_workers: list[QThread] = []

    def analyze_chart(path: str) -> None:
        window.set_ai_busy(True)
        worker = ChartAnalysisWorker(path, window)
        active_workers.append(worker)
        worker.result_ready.connect(on_analysis_result)
        worker.error_ready.connect(window.update_ai_error)
        worker.finished.connect(lambda: active_workers.remove(worker) if worker in active_workers else None)
        worker.start()

    def on_trade_result(result: dict[str, object]) -> None:
        status = str(result.get("status", "unknown"))
        mode = str(result.get("mode", ""))
        order_id = result.get("order_id")
        detail = f"{status} / {mode}" if mode else status
        if order_id:
            detail += f" / order {order_id}"
        window.ai_page.show_execution_status(detail)

    def on_analysis_result(signal: dict[str, str]) -> None:
        window.update_ai_result(signal)
        if signal.get("Action") == "Hold":
            window.ai_page.show_execution_status("No order: Omni AI returned Hold.")
            return
        if not _bool_env("OMNI_AUTO_EXECUTE"):
            window.ai_page.show_execution_status(
                "off; set OMNI_AUTO_EXECUTE=true to route signals (dry-run remains the default)."
            )
            return
        trade_worker = TradeExecutionWorker(signal, window)
        active_workers.append(trade_worker)
        trade_worker.result_ready.connect(on_trade_result)
        trade_worker.error_ready.connect(window.ai_page.show_execution_status)
        trade_worker.finished.connect(
            lambda: active_workers.remove(trade_worker) if trade_worker in active_workers else None
        )
        trade_worker.start()

    window.analyze_requested.connect(analyze_chart)

    if _bool_env("OMNI_START_API"):
        api_thread = threading.Thread(target=_start_local_api, name="omni-local-api", daemon=True)
        api_thread.start()

    clock_timer = QTimer(window)
    clock_timer.timeout.connect(
        lambda: window.clock.setText(f"LOCAL SNAPSHOT: {time.strftime('%H:%M:%S')}")
    )
    clock_timer.start(1_000)

    def shutdown_workers() -> None:
        market_worker.stop()
        market_worker.wait(10_000)
        for worker in tuple(active_workers):
            worker.wait(65_000)

    app.aboutToQuit.connect(shutdown_workers)
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
