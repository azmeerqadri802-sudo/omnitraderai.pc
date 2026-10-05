"""Dark PyQt5 dashboard widgets for Omni Trader."""

from __future__ import annotations

from typing import Sequence

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PyQt5.QtWidgets import (
    QFileDialog,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


NEON_GREEN = "#39FF88"
ELECTRIC_BLUE = "#168CFF"
BG_BLACK = "#030507"
PANEL_BLACK = "#0A0F14"
WHITE = "#F3F7FA"
MUTED = "#82919D"


class PriceChart(QWidget):
    """Lightweight, dependency-free sparkline/chart placeholder widget."""

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(240)
        self.values: list[float] = []
        self.caption = "Waiting for market data"

    def add_value(self, value: float, caption: str) -> None:
        if value > 0:
            self.values.append(float(value))
            self.values = self.values[-90:]
        self.caption = caption
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt callback API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(PANEL_BLACK))
        plot = self.rect().adjusted(46, 22, -20, -30)
        painter.setPen(QPen(QColor("#14212C"), 1))
        for index in range(5):
            y = plot.top() + int(index * plot.height() / 4)
            painter.drawLine(plot.left(), y, plot.right(), y)
        for index in range(7):
            x = plot.left() + int(index * plot.width() / 6)
            painter.drawLine(x, plot.top(), x, plot.bottom())

        painter.setPen(QColor(MUTED))
        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(18, 22, self.caption)
        if len(self.values) < 2:
            painter.setPen(QColor(ELECTRIC_BLUE))
            painter.drawText(plot, Qt.AlignCenter, "LIVE CHART CANVAS  ·  AWAITING PRICE HISTORY")
            return

        low, high = min(self.values), max(self.values)
        spread = high - low or max(abs(high) * 0.001, 0.01)
        path = QPainterPath()
        for index, value in enumerate(self.values):
            x = plot.left() + index * plot.width() / (len(self.values) - 1)
            y = plot.bottom() - ((value - low) / spread) * plot.height()
            if index == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        painter.setPen(QPen(QColor(NEON_GREEN), 2.2))
        painter.drawPath(path)
        painter.setPen(QColor(MUTED))
        painter.drawText(8, plot.top() + 5, f"{high:,.4g}")
        painter.drawText(8, plot.bottom(), f"{low:,.4g}")


class MarketPage(QWidget):
    def __init__(self, market_title: str) -> None:
        super().__init__()
        self.market_title = market_title
        self._last_symbol = ""
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 18)
        root.setSpacing(14)

        heading = QHBoxLayout()
        self.title = QLabel(market_title.upper())
        self.title.setObjectName("sectionTitle")
        self.feed_status = QLabel("CONNECTING")
        self.feed_status.setObjectName("statusPill")
        heading.addWidget(self.title)
        heading.addStretch(1)
        heading.addWidget(self.feed_status)
        root.addLayout(heading)

        self.chart = PriceChart()
        root.addWidget(self.chart, 1)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["SYMBOL", "LAST PRICE", "CHANGE", "FEED"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setDefaultSectionSize(150)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(False)
        root.addWidget(self.table, 1)

    def update_quotes(self, quotes: Sequence[dict[str, object]]) -> None:
        self._quotes = list(quotes)
        self.table.setRowCount(len(quotes))
        live_count = 0
        for row_index, quote in enumerate(quotes):
            symbol = str(quote.get("symbol", "—"))
            price = float(quote.get("price", 0.0) or 0.0)
            change = float(quote.get("change_pct", 0.0) or 0.0)
            is_live = bool(quote.get("is_live", False))
            live_count += int(is_live)
            values = [symbol, f"{price:,.6g}" if price else "—", f"{change:+.2f}%", "LIVE" if is_live else "SAMPLE"]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                if column == 2:
                    cell.setForeground(QColor(NEON_GREEN if change >= 0 else "#FF5570"))
                elif column == 3:
                    cell.setForeground(QColor(NEON_GREEN if is_live else MUTED))
                else:
                    cell.setForeground(QColor(WHITE))
                self.table.setItem(row_index, column, cell)
            if row_index == 0:
                self.chart.add_value(price, f"{symbol}   •   {quote.get('source', 'sample')}")
        total = len(quotes)
        self.feed_status.setText(f"{live_count}/{total} LIVE" if live_count else "SAMPLE DATA")
        self.feed_status.setProperty("live", live_count > 0)
        self.feed_status.style().unpolish(self.feed_status)
        self.feed_status.style().polish(self.feed_status)


class OmniAIPage(QWidget):
    analyze_requested = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.image_path = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(16)

        eyebrow = QLabel("OMNI AI  /  CHART VISION")
        eyebrow.setObjectName("sectionTitle")
        layout.addWidget(eyebrow)
        intro = QLabel("Upload a chart screenshot for a structured, image-based market read.")
        intro.setObjectName("muted")
        layout.addWidget(intro)

        controls = QHBoxLayout()
        self.upload_button = QPushButton("Choose Chart Image")
        self.upload_button.setObjectName("secondaryButton")
        self.analyze_button = QPushButton("Analyze Screenshot")
        self.analyze_button.setObjectName("primaryButton")
        self.analyze_button.setEnabled(False)
        self.upload_button.clicked.connect(self._choose_image)
        self.analyze_button.clicked.connect(self._analyze)
        controls.addWidget(self.upload_button)
        controls.addWidget(self.analyze_button)
        controls.addStretch(1)
        layout.addLayout(controls)

        preview_frame = QFrame()
        preview_frame.setObjectName("panel")
        preview_layout = QVBoxLayout(preview_frame)
        self.preview = QLabel("Chart preview appears here")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(280)
        self.preview.setObjectName("muted")
        preview_layout.addWidget(self.preview)
        layout.addWidget(preview_frame, 2)

        self.result = QLabel("Action: —\nOpen price: —\nClose price: —\nReason: Upload a chart to begin.")
        self.result.setObjectName("aiResult")
        self.result.setWordWrap(True)
        self.result.setMinimumHeight(112)
        layout.addWidget(self.result)

        disclaimer = QLabel("Static chart analysis only. Recommendations are not live quotes or trading instructions.")
        disclaimer.setObjectName("muted")
        layout.addWidget(disclaimer)
        self.execution_status = QLabel("Order routing: disabled")
        self.execution_status.setObjectName("muted")
        layout.addWidget(self.execution_status)

    def _choose_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose chart screenshot",
            "",
            "Chart images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff);;All files (*.*)",
        )
        if not path:
            return
        self.image_path = path
        pixmap = QPixmap(path)
        if pixmap.isNull():
            self.preview.setText("Could not preview this image. Choose another file.")
            self.analyze_button.setEnabled(False)
            return
        self.preview.setPixmap(pixmap.scaled(1000, 420, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.analyze_button.setEnabled(True)
        self.result.setText("Ready to analyze. No order will be placed.")

    def _analyze(self) -> None:
        if self.image_path:
            self.analyze_button.setEnabled(False)
            self.result.setText("Analyzing chart…")
            self.analyze_requested.emit(self.image_path)

    def show_result(self, signal: dict[str, str]) -> None:
        self.result.setText(
            f"Action: {signal['Action']}\nOpen price: {signal['Open_Price']}\n"
            f"Close price: {signal['Close_Price']}\nReason: {signal['Reason']}"
        )
        self.analyze_button.setEnabled(bool(self.image_path))

    def show_error(self, message: str) -> None:
        self.result.setText(f"Analysis unavailable: {message}")
        self.analyze_button.setEnabled(bool(self.image_path))

    def show_execution_status(self, message: str) -> None:
        self.execution_status.setText(f"Order routing: {message}")


class SettingsPage(QWidget):
    """Credential settings; raw keys are masked and sent directly to keyring."""

    save_requested = pyqtSignal(str, str)
    delete_requested = pyqtSignal(str)

    CREDENTIALS = (
        ("BINANCE_API_KEY", "Binance API key", "Used for account access and Spot orders."),
        ("BINANCE_SECRET_KEY", "Binance secret key", "Paired with your Binance API key."),
        ("GEMINI_API_KEY", "Gemini API key", "Used to analyze uploaded chart images."),
    )

    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(14)

        title = QLabel("SECURE API SETTINGS")
        title.setObjectName("sectionTitle")
        root.addWidget(title)
        intro = QLabel(
            "Credentials are saved in your operating system's secure credential store. "
            "They are never shown again after saving."
        )
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        root.addWidget(intro)

        self.fields: dict[str, QLineEdit] = {}
        self.status_labels: dict[str, QLabel] = {}
        for name, label_text, description in self.CREDENTIALS:
            card = QFrame()
            card.setObjectName("panel")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(18, 14, 18, 14)
            card_layout.setSpacing(8)

            heading = QHBoxLayout()
            label = QLabel(label_text)
            label.setObjectName("sectionTitle")
            status = QLabel("Checking secure store…")
            status.setObjectName("credentialStatus")
            self.status_labels[name] = status
            heading.addWidget(label)
            heading.addStretch(1)
            heading.addWidget(status)
            card_layout.addLayout(heading)

            description_label = QLabel(description)
            description_label.setObjectName("muted")
            card_layout.addWidget(description_label)

            controls = QHBoxLayout()
            field = QLineEdit()
            field.setEchoMode(QLineEdit.Password)
            field.setPlaceholderText("Paste key; input is masked")
            field.setClearButtonEnabled(True)
            self.fields[name] = field
            save_button = QPushButton("Save securely")
            save_button.setObjectName("primaryButton")
            save_button.clicked.connect(lambda checked=False, key=name: self._save(key))
            remove_button = QPushButton("Remove")
            remove_button.setObjectName("secondaryButton")
            remove_button.clicked.connect(lambda checked=False, key=name: self.delete_requested.emit(key))
            controls.addWidget(field, 1)
            controls.addWidget(save_button)
            controls.addWidget(remove_button)
            card_layout.addLayout(controls)
            root.addWidget(card)

        root.addStretch(1)
        note = QLabel(
            "For Binance, use the narrowest required permissions and keep withdrawals disabled. "
            "Live trading remains separately locked behind the existing safety settings."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        root.addWidget(note)

    def _save(self, name: str) -> None:
        value = self.fields[name].text()
        if not value.strip():
            self.set_key_status(name, "Enter a key to save.", success=False)
            return
        self.save_requested.emit(name, value)

    def clear_field(self, name: str) -> None:
        self.fields[name].clear()

    def set_key_status(self, name: str, message: str, *, success: bool) -> None:
        label = self.status_labels[name]
        label.setText(message)
        label.setProperty("success", success)
        label.style().unpolish(label)
        label.style().polish(label)


class DashboardWindow(QMainWindow):
    analyze_requested = pyqtSignal(str)
    credential_save_requested = pyqtSignal(str, str)
    credential_delete_requested = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Omni Trader")
        self.resize(1360, 880)
        self.setMinimumSize(1024, 700)
        self.setStyleSheet(APP_STYLESHEET)

        container = QWidget()
        root = QVBoxLayout(container)
        root.setContentsMargins(22, 16, 22, 18)
        root.setSpacing(12)

        header = QHBoxLayout()
        brand_box = QVBoxLayout()
        brand = QLabel("OMNI TRADER")
        brand.setObjectName("brand")
        tagline = QLabel("MULTI-MARKET TERMINAL  /  PHASE 1")
        tagline.setObjectName("muted")
        brand_box.addWidget(brand)
        brand_box.addWidget(tagline)
        header.addLayout(brand_box)
        header.addStretch(1)
        self.connection_status = QLabel("STARTING FEEDS")
        self.connection_status.setObjectName("statusPill")
        header.addWidget(self.connection_status)
        root.addLayout(header)

        self.ticker_tape = QLabel("PSX  •  waiting   |   GLOBAL  •  waiting   |   CRYPTO  •  connecting   |   FOREX  •  waiting")
        self.ticker_tape.setObjectName("tickerTape")
        root.addWidget(self.ticker_tape)

        self.tabs = QTabWidget()
        self.market_pages = {
            "psx": MarketPage("Pakistan Stock Exchange"),
            "global_stocks": MarketPage("Global Stocks"),
            "crypto": MarketPage("Crypto Markets"),
            "forex": MarketPage("Forex"),
        }
        self.tabs.addTab(self.market_pages["psx"], "PSX")
        self.tabs.addTab(self.market_pages["global_stocks"], "GLOBAL STOCKS")
        self.ai_page = OmniAIPage()
        self.ai_page.analyze_requested.connect(self.analyze_requested.emit)
        self.tabs.addTab(self.ai_page, "✦  OMNI AI  ✦")
        self.tabs.addTab(self.market_pages["crypto"], "CRYPTO")
        self.tabs.addTab(self.market_pages["forex"], "FOREX")
        self.settings_page = SettingsPage()
        self.settings_page.save_requested.connect(self.credential_save_requested.emit)
        self.settings_page.delete_requested.connect(self.credential_delete_requested.emit)
        self.tabs.addTab(self.settings_page, "SETTINGS")
        root.addWidget(self.tabs, 1)

        footer = QHBoxLayout()
        note = QLabel("Feeds may be delayed/sample. Signal routing is opt-in; dry-run is the default.")
        note.setObjectName("muted")
        self.clock = QLabel("LOCAL SNAPSHOT: —")
        self.clock.setObjectName("muted")
        footer.addWidget(note)
        footer.addStretch(1)
        footer.addWidget(self.clock)
        root.addLayout(footer)
        self.setCentralWidget(container)

    def update_market(self, market: str, quotes: Sequence[dict[str, object]]) -> None:
        page = self.market_pages.get(market)
        if page is None:
            return
        page.update_quotes(quotes)
        self._refresh_tape()

    def update_crypto(self, quote: dict[str, object]) -> None:
        page = self.market_pages["crypto"]
        existing = getattr(
            page,
            "_crypto_quotes",
            {str(row.get("symbol", "")): row for row in getattr(page, "_quotes", [])},
        )
        existing[str(quote.get("symbol", ""))] = quote
        page._crypto_quotes = existing
        page._quotes = list(existing.values())
        page.update_quotes(list(existing.values()))
        self._refresh_tape()
        if bool(quote.get("is_live", False)):
            self.connection_status.setText("CRYPTO STREAM LIVE")

    def set_connection_status(self, text: str) -> None:
        self.connection_status.setText(text.upper())

    def set_ai_busy(self, busy: bool) -> None:
        self.ai_page.analyze_button.setEnabled(not busy and bool(self.ai_page.image_path))

    def update_ai_result(self, signal: dict[str, str]) -> None:
        self.ai_page.show_result(signal)

    def update_ai_error(self, message: str) -> None:
        self.ai_page.show_error(message)

    def _refresh_tape(self) -> None:
        parts = []
        for market, label in (("psx", "PSX"), ("global_stocks", "GLOBAL"), ("crypto", "CRYPTO"), ("forex", "FOREX")):
            page = self.market_pages[market]
            if market == "crypto":
                rows = list(getattr(page, "_crypto_quotes", {}).values())
            else:
                rows = getattr(page, "_quotes", [])
            if rows:
                first = rows[0]
                parts.append(f"{label}  {first.get('symbol')}  {float(first.get('price', 0) or 0):,.6g}")
            else:
                parts.append(f"{label}  waiting")
        self.ticker_tape.setText("     │     ".join(parts))


APP_STYLESHEET = f"""
QMainWindow, QWidget {{ background: {BG_BLACK}; color: {WHITE}; font-family: 'Segoe UI'; }}
QLabel#brand {{ color: {WHITE}; font-size: 25px; font-weight: 800; letter-spacing: 2px; }}
QLabel#sectionTitle {{ color: {WHITE}; font-size: 18px; font-weight: 700; letter-spacing: 1px; }}
QLabel#muted {{ color: {MUTED}; font-size: 11px; }}
QLabel#statusPill {{ color: {NEON_GREEN}; background: #0C2118; border: 1px solid #145C3A; border-radius: 10px; padding: 7px 12px; font-weight: 700; }}
QLabel#tickerTape {{ color: {NEON_GREEN}; background: #07120E; border: 1px solid #12261E; border-radius: 8px; padding: 11px; font-weight: 600; }}
QTabWidget::pane {{ border: 1px solid #17232C; border-radius: 12px; background: {BG_BLACK}; top: -1px; }}
QTabBar::tab {{ background: #0B1117; color: #93A3AF; padding: 14px 22px; margin-right: 5px; border: 1px solid #17232C; border-bottom: none; border-top-left-radius: 9px; border-top-right-radius: 9px; font-weight: 700; }}
QTabBar::tab:selected {{ color: {NEON_GREEN}; background: #101A20; border-color: {ELECTRIC_BLUE}; }}
QTabBar::tab:hover {{ color: {WHITE}; }}
QTableWidget {{ background: {PANEL_BLACK}; gridline-color: #18242D; border: 1px solid #17232C; border-radius: 8px; selection-background-color: #10263A; }}
QHeaderView::section {{ color: {ELECTRIC_BLUE}; background: #0D151C; border: none; border-bottom: 1px solid #20303B; padding: 10px; font-weight: 700; }}
QTableWidget::item {{ padding: 8px; border-bottom: 1px solid #141D24; }}
QFrame#panel {{ background: {PANEL_BLACK}; border: 1px solid #17232C; border-radius: 10px; }}
QLabel#aiResult {{ color: {WHITE}; background: #0A1117; border: 1px solid #1B3345; border-left: 3px solid {ELECTRIC_BLUE}; border-radius: 8px; padding: 15px; font-size: 13px; }}
QLabel#credentialStatus {{ color: {MUTED}; font-size: 11px; font-weight: 700; }}
QLabel#credentialStatus[success="true"] {{ color: {NEON_GREEN}; }}
QLineEdit {{ color: {WHITE}; background: #05090D; border: 1px solid #20303B; border-radius: 7px; padding: 10px; selection-background-color: {ELECTRIC_BLUE}; }}
QLineEdit:focus {{ border: 1px solid {ELECTRIC_BLUE}; }}
QPushButton {{ border-radius: 7px; padding: 11px 16px; font-weight: 700; }}
QPushButton#primaryButton {{ background: {NEON_GREEN}; color: #021109; border: none; }}
QPushButton#primaryButton:hover {{ background: #75FFAE; }}
QPushButton#primaryButton:disabled {{ background: #284235; color: #7E9989; }}
QPushButton#secondaryButton {{ background: #0D1C29; color: {ELECTRIC_BLUE}; border: 1px solid #1F5A8B; }}
QPushButton#secondaryButton:hover {{ background: #122A3D; }}
"""
