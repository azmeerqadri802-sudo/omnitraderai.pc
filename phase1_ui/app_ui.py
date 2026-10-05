"""Premium dark PyQt5 dashboard for Omni Trader.

Market feeds, keyring callbacks, chart analysis and trade execution continue to
be driven by the signals and methods exposed by :class:`DashboardWindow`.
"""

from __future__ import annotations

from typing import Sequence

from PyQt5.QtCore import QAbstractAnimation, QPropertyAnimation, QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PyQt5.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


BG_BLACK = "#0B0E14"
PANEL_BLACK = "#111720"
PANEL_RAISED = "#151D28"
NEON_GREEN = "#00FF00"
ELECTRIC_BLUE = "#00E5FF"
WHITE = "#FFFFFF"
MUTED = "#8A94A6"
NEGATIVE = "#FF5C78"
GRID = "#202B38"


class HoverGlowFrame(QFrame):
    """A rounded panel with a short, subtle blue hover-glow animation."""

    def __init__(self, object_name: str = "panel", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        self._glow = QGraphicsDropShadowEffect(self)
        self._glow.setBlurRadius(0)
        self._glow.setColor(QColor(ELECTRIC_BLUE))
        self._glow.setOffset(0, 0)
        self.setGraphicsEffect(self._glow)
        self._glow_animation = QPropertyAnimation(self._glow, b"blurRadius", self)
        self._glow_animation.setDuration(180)

    def _animate_glow(self, radius: float) -> None:
        if self._glow_animation.state() == QAbstractAnimation.Running:
            self._glow_animation.stop()
        self._glow_animation.setStartValue(self._glow.blurRadius())
        self._glow_animation.setEndValue(radius)
        self._glow_animation.start()

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt callback API
        self._animate_glow(15)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt callback API
        self._animate_glow(0)
        super().leaveEvent(event)


class HoverButton(QPushButton):
    """Button with QSS hover colors and an animated, low-key accent glow."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._glow = QGraphicsDropShadowEffect(self)
        self._glow.setBlurRadius(0)
        self._glow.setColor(QColor(ELECTRIC_BLUE))
        self._glow.setOffset(0, 0)
        self.setGraphicsEffect(self._glow)
        self._glow_animation = QPropertyAnimation(self._glow, b"blurRadius", self)
        self._glow_animation.setDuration(150)

    def _animate_glow(self, radius: float) -> None:
        if self._glow_animation.state() == QAbstractAnimation.Running:
            self._glow_animation.stop()
        self._glow_animation.setStartValue(self._glow.blurRadius())
        self._glow_animation.setEndValue(radius)
        self._glow_animation.start()

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt callback API
        self._animate_glow(12)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt callback API
        self._animate_glow(0)
        super().leaveEvent(event)


class PriceChart(QWidget):
    """Responsive, dependency-free chart canvas fed by incoming quote prices."""

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(260)
        self.values: list[float] = []
        self.caption = "Waiting for market data"

    def add_value(self, value: float, caption: str) -> None:
        if value > 0:
            self.values.append(float(value))
            self.values = self.values[-120:]
        self.caption = caption
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt callback API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(PANEL_BLACK))
        plot = self.rect().adjusted(58, 38, -20, -35)

        painter.setPen(QPen(QColor(GRID), 1))
        for index in range(5):
            y = plot.top() + int(index * plot.height() / 4)
            painter.drawLine(plot.left(), y, plot.right(), y)
        for index in range(7):
            x = plot.left() + int(index * plot.width() / 6)
            painter.drawLine(x, plot.top(), x, plot.bottom())

        painter.setPen(QColor(MUTED))
        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(18, 23, self.caption)
        if len(self.values) < 2:
            painter.setPen(QColor(ELECTRIC_BLUE))
            painter.drawText(plot, Qt.AlignCenter, "CHART CANVAS  ·  AWAITING PRICE HISTORY")
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
        color = NEON_GREEN if self.values[-1] >= self.values[0] else NEGATIVE
        painter.setPen(QPen(QColor(color), 2.4))
        painter.drawPath(path)
        painter.setPen(QColor(MUTED))
        painter.drawText(7, plot.top() + 5, f"{high:,.5g}")
        painter.drawText(7, plot.bottom(), f"{low:,.5g}")


class MarketPage(QWidget):
    """One market's chart and quote table, updated by the existing data worker."""

    def __init__(self, market_title: str) -> None:
        super().__init__()
        self.market_title = market_title
        self._quotes: list[dict[str, object]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        heading = QHBoxLayout()
        self.title = QLabel(market_title)
        self.title.setObjectName("sectionTitle")
        self.feed_status = QLabel("CONNECTING")
        self.feed_status.setObjectName("statusPill")
        heading.addWidget(self.title)
        heading.addStretch(1)
        heading.addWidget(self.feed_status)
        root.addLayout(heading)

        chart_panel = HoverGlowFrame("chartCard")
        chart_layout = QVBoxLayout(chart_panel)
        chart_layout.setContentsMargins(16, 14, 16, 12)
        chart_layout.setSpacing(8)
        chart_heading = QHBoxLayout()
        chart_label = QLabel("PRICE ACTION")
        chart_label.setObjectName("eyebrow")
        timeframe = QLabel("LIVE SNAPSHOT  ·  1D")
        timeframe.setObjectName("muted")
        chart_heading.addWidget(chart_label)
        chart_heading.addStretch(1)
        chart_heading.addWidget(timeframe)
        chart_layout.addLayout(chart_heading)
        self.chart = PriceChart()
        chart_layout.addWidget(self.chart, 1)
        root.addWidget(chart_panel, 6)

        table_panel = QFrame()
        table_panel.setObjectName("panel")
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(14, 12, 14, 12)
        table_layout.setSpacing(8)
        table_title = QLabel("WATCHLIST")
        table_title.setObjectName("eyebrow")
        table_layout.addWidget(table_title)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["SYMBOL", "LAST PRICE", "CHANGE", "FEED"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setDefaultSectionSize(130)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.setMinimumHeight(170)
        table_layout.addWidget(self.table)
        root.addWidget(table_panel, 3)

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
            row_values = [
                symbol,
                f"{price:,.6g}" if price else "—",
                f"{change:+.2f}%",
                "LIVE" if is_live else "SAMPLE",
            ]
            for column, value in enumerate(row_values):
                cell = QTableWidgetItem(value)
                cell.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                if column == 2:
                    cell.setForeground(QColor(NEON_GREEN if change >= 0 else NEGATIVE))
                elif column == 3:
                    cell.setForeground(QColor(NEON_GREEN if is_live else MUTED))
                else:
                    cell.setForeground(QColor(WHITE))
                self.table.setItem(row_index, column, cell)
            if row_index == 0:
                self.chart.add_value(price, f"{symbol}   ·   {quote.get('source', 'sample')}")

        total = len(quotes)
        self.feed_status.setText(f"{live_count}/{total} LIVE" if live_count else "SAMPLE FEED")
        self.feed_status.setProperty("live", live_count > 0)
        self.feed_status.style().unpolish(self.feed_status)
        self.feed_status.style().polish(self.feed_status)


class MarketSummaryCard(HoverGlowFrame):
    """Compact live summary card at the top of the dashboard."""

    def __init__(self, title: str) -> None:
        super().__init__("summaryCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(3)
        self.title = QLabel(title)
        self.title.setObjectName("muted")
        self.value = QLabel("—")
        self.value.setObjectName("summaryValue")
        self.detail = QLabel("Waiting for feed")
        self.detail.setObjectName("muted")
        layout.addWidget(self.title)
        layout.addWidget(self.value)
        layout.addWidget(self.detail)

    def update_quote(self, quote: dict[str, object] | None) -> None:
        if not quote:
            return
        price = float(quote.get("price", 0.0) or 0.0)
        change = float(quote.get("change_pct", 0.0) or 0.0)
        symbol = str(quote.get("symbol", "—"))
        is_live = bool(quote.get("is_live", False))
        self.value.setText(f"{price:,.6g}" if price else "—")
        self.value.setStyleSheet(f"color: {NEON_GREEN if change >= 0 else NEGATIVE};")
        self.detail.setText(f"{symbol}   {change:+.2f}%   ·   {'LIVE' if is_live else 'SAMPLE'}")


class OmniAIPage(QWidget):
    """Persistent right-side chart upload and chat-like analysis panel."""

    analyze_requested = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.image_path = ""
        self.setMinimumWidth(285)
        self.setMaximumWidth(370)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        panel = HoverGlowFrame("aiPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(16, 16, 16, 16)
        panel_layout.setSpacing(12)

        title_row = QHBoxLayout()
        self.ai_title = QLabel("✦  OMNI AI")
        self.ai_title.setObjectName("aiTitle")
        self.ai_title.setGraphicsEffect(self._blue_title_glow())
        ai_state = QLabel("VISION")
        ai_state.setObjectName("aiBadge")
        title_row.addWidget(self.ai_title)
        title_row.addStretch(1)
        title_row.addWidget(ai_state)
        panel_layout.addLayout(title_row)

        intro = QLabel("Chart companion  ·  upload a screenshot for an image-based read.")
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        panel_layout.addWidget(intro)

        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setObjectName("chatScroll")
        self.chat_content = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_content)
        self.chat_layout.setContentsMargins(4, 4, 4, 4)
        self.chat_layout.setSpacing(9)
        self.chat_layout.addStretch(1)
        self.chat_scroll.setWidget(self.chat_content)
        panel_layout.addWidget(self.chat_scroll, 1)
        self._append_message("OMNI", "Upload a chart screenshot and I’ll summarize the visible structure.", "assistant")

        self.upload_button = HoverButton("＋   Upload Chart Screenshot")
        self.upload_button.setObjectName("uploadButton")
        self.upload_button.setMinimumHeight(50)
        self.upload_button.clicked.connect(self._choose_image)
        panel_layout.addWidget(self.upload_button)

        self.preview = QLabel("Image preview appears here")
        self.preview.setObjectName("imagePreview")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setFixedHeight(132)
        panel_layout.addWidget(self.preview)

        self.analyze_button = HoverButton("Analyze chart")
        self.analyze_button.setObjectName("primaryButton")
        self.analyze_button.setEnabled(False)
        self.analyze_button.clicked.connect(self._analyze)
        panel_layout.addWidget(self.analyze_button)

        self.result = QLabel("")  # Kept for callers that inspect the structured response.
        self.execution_status = QLabel("Order routing: disabled")
        self.execution_status.setObjectName("muted")
        self.execution_status.setWordWrap(True)
        panel_layout.addWidget(self.execution_status)
        layout.addWidget(panel, 1)

    @staticmethod
    def _blue_title_glow() -> QGraphicsDropShadowEffect:
        effect = QGraphicsDropShadowEffect()
        effect.setBlurRadius(20)
        effect.setColor(QColor(ELECTRIC_BLUE))
        effect.setOffset(0, 0)
        return effect

    def _append_message(self, author: str, message: str, kind: str) -> None:
        bubble = QFrame()
        bubble.setObjectName("chatBubbleUser" if kind == "user" else "chatBubbleAI")
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(11, 9, 11, 9)
        bubble_layout.setSpacing(4)
        heading = QLabel(author.upper())
        heading.setObjectName("chatAuthor")
        body = QLabel(message)
        body.setObjectName("chatText")
        body.setWordWrap(True)
        bubble_layout.addWidget(heading)
        bubble_layout.addWidget(body)
        insertion_index = max(0, self.chat_layout.count() - 1)
        self.chat_layout.insertWidget(insertion_index, bubble)
        QTimer.singleShot(0, lambda: self.chat_scroll.verticalScrollBar().setValue(
            self.chat_scroll.verticalScrollBar().maximum()
        ))

    def focus_upload(self) -> None:
        self.upload_button.setFocus()

    def _choose_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Upload chart screenshot",
            "",
            "Chart images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff);;All files (*.*)",
        )
        if not path:
            return
        pixmap = QPixmap(path)
        if pixmap.isNull():
            self.preview.setText("Could not preview this image. Choose another file.")
            self.analyze_button.setEnabled(False)
            return
        self.image_path = path
        self.preview.setPixmap(pixmap.scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.analyze_button.setEnabled(True)
        self._append_message("YOU", "Chart screenshot attached.", "user")

    def _analyze(self) -> None:
        if self.image_path:
            self.analyze_button.setEnabled(False)
            self._append_message("OMNI", "Reading trend, visible levels and chart patterns…", "assistant")
            self.analyze_requested.emit(self.image_path)

    def show_result(self, signal: dict[str, str]) -> None:
        formatted = (
            f"Action: {signal['Action']}\nOpen: {signal['Open_Price']}\n"
            f"Close: {signal['Close_Price']}\nReason: {signal['Reason']}"
        )
        self.result.setText(formatted)
        self._append_message("OMNI  ·  ANALYSIS", formatted, "assistant")
        self.analyze_button.setEnabled(bool(self.image_path))

    def show_error(self, message: str) -> None:
        self._append_message("OMNI  ·  ERROR", message, "assistant")
        self.analyze_button.setEnabled(bool(self.image_path))

    def show_execution_status(self, message: str) -> None:
        self.execution_status.setText(f"Order routing: {message}")


class SettingsPage(QWidget):
    """Masked, floating-label credential inputs with reveal and keyring actions."""

    save_requested = pyqtSignal(str, str)
    delete_requested = pyqtSignal(str)
    CREDENTIALS = (
        ("BINANCE_API_KEY", "Binance API key", "Account and Spot API access"),
        ("BINANCE_SECRET_KEY", "Binance secret key", "Paired Binance signing secret"),
        ("GEMINI_API_KEY", "Gemini API key", "Omni AI chart analysis"),
    )

    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(2, 2, 2, 2)
        root.setSpacing(14)

        title = QLabel("SECURE CONNECTIONS")
        title.setObjectName("sectionTitle")
        root.addWidget(title)
        intro = QLabel(
            "Keys stay on this device in the operating system credential store. "
            "Saved values are never displayed in the app."
        )
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        root.addWidget(intro)

        self.fields: dict[str, QLineEdit] = {}
        self.eye_buttons: dict[str, QPushButton] = {}
        self.status_labels: dict[str, QLabel] = {}
        for name, label_text, hint in self.CREDENTIALS:
            card = HoverGlowFrame("settingsCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 14, 16, 14)
            card_layout.setSpacing(9)

            label_row = QHBoxLayout()
            field_label = QLabel(label_text)
            field_label.setObjectName("floatingLabel")
            status = QLabel("Checking secure store…")
            status.setObjectName("credentialStatus")
            self.status_labels[name] = status
            label_row.addWidget(field_label)
            label_row.addStretch(1)
            label_row.addWidget(status)
            card_layout.addLayout(label_row)

            input_row = QHBoxLayout()
            field = QLineEdit()
            field.setEchoMode(QLineEdit.Password)
            field.setPlaceholderText(hint)
            field.setClearButtonEnabled(True)
            self.fields[name] = field
            eye = HoverButton("◉")
            eye.setObjectName("eyeButton")
            eye.setToolTip("Reveal or hide this credential")
            eye.setFixedWidth(42)
            eye.setCheckable(True)
            self.eye_buttons[name] = eye
            eye.toggled.connect(lambda revealed, key=name: self._toggle_reveal(key, revealed))
            input_row.addWidget(field, 1)
            input_row.addWidget(eye)
            card_layout.addLayout(input_row)

            actions = QHBoxLayout()
            actions.addStretch(1)
            save_button = HoverButton("Save securely")
            save_button.setObjectName("primaryButton")
            save_button.clicked.connect(lambda checked=False, key=name: self._save(key))
            remove_button = HoverButton("Remove")
            remove_button.setObjectName("secondaryButton")
            remove_button.clicked.connect(lambda checked=False, key=name: self.delete_requested.emit(key))
            actions.addWidget(remove_button)
            actions.addWidget(save_button)
            card_layout.addLayout(actions)
            root.addWidget(card)

        root.addStretch(1)
        safety = QLabel(
            "Keep Binance withdrawal permissions disabled. Live order execution remains subject to the existing safety locks."
        )
        safety.setObjectName("muted")
        safety.setWordWrap(True)
        root.addWidget(safety)

    def _toggle_reveal(self, name: str, revealed: bool) -> None:
        self.fields[name].setEchoMode(QLineEdit.Normal if revealed else QLineEdit.Password)
        eye = self.eye_buttons[name]
        eye.setText("◉" if revealed else "◎")
        eye.setToolTip("Hide this credential" if revealed else "Reveal this credential")

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
    """Responsive shell preserving the existing backend's signal contract."""

    analyze_requested = pyqtSignal(str)
    credential_save_requested = pyqtSignal(str, str)
    credential_delete_requested = pyqtSignal(str)

    NAV_ITEMS = (
        ("psx", "PSX", "▤"),
        ("global_stocks", "Global Stocks", "◫"),
        ("crypto", "Crypto", "₿"),
        ("forex", "Forex", "⇄"),
        ("settings", "Settings", "⚙"),
    )

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Omni Trader")
        self.resize(1520, 940)
        self.setMinimumSize(960, 650)
        self.setStyleSheet(APP_STYLESHEET)
        self.sidebar_collapsed = False
        self.active_section = "psx"
        self.nav_buttons: dict[str, QPushButton] = {}
        self.nav_icons = {key: icon for key, _label, icon in self.NAV_ITEMS}
        self.nav_labels = {key: label for key, label, _icon in self.NAV_ITEMS}

        shell = QWidget()
        shell.setObjectName("shell")
        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(14, 14, 14, 12)
        shell_layout.setSpacing(14)

        self.sidebar = self._build_sidebar()
        shell_layout.addWidget(self.sidebar)

        workspace = QWidget()
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(14)
        shell_layout.addWidget(workspace, 1)

        header = QHBoxLayout()
        heading_stack = QVBoxLayout()
        brand = QLabel("OMNI TRADER")
        brand.setObjectName("brand")
        self.page_title = QLabel("Pakistan Stock Exchange")
        self.page_title.setObjectName("muted")
        heading_stack.addWidget(brand)
        heading_stack.addWidget(self.page_title)
        header.addLayout(heading_stack)
        header.addStretch(1)
        self.connection_status = QLabel("STARTING FEEDS")
        self.connection_status.setObjectName("statusPill")
        header.addWidget(self.connection_status)
        workspace_layout.addLayout(header)

        self.summary_scroll = QScrollArea()
        self.summary_scroll.setObjectName("summaryScroll")
        self.summary_scroll.setWidgetResizable(True)
        self.summary_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.summary_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        summary_host = QWidget()
        summary_layout = QHBoxLayout(summary_host)
        summary_layout.setContentsMargins(2, 2, 2, 8)
        summary_layout.setSpacing(10)
        self.summary_cards = {
            "psx": MarketSummaryCard("PSX MARKET"),
            "crypto": MarketSummaryCard("BTC / USDT"),
            "global_stocks": MarketSummaryCard("GLOBAL STOCKS"),
        }
        for card in self.summary_cards.values():
            card.setMinimumWidth(185)
            card.setMinimumHeight(94)
            summary_layout.addWidget(card, 1)
        summary_layout.addStretch(1)
        self.summary_scroll.setWidget(summary_host)
        self.summary_scroll.setFixedHeight(112)
        workspace_layout.addWidget(self.summary_scroll)

        body = QHBoxLayout()
        body.setSpacing(14)
        self.center_stack = QStackedWidget()
        self.center_stack.setObjectName("centerStack")
        self.market_pages = {
            "psx": MarketPage("Pakistan Stock Exchange"),
            "global_stocks": MarketPage("Global Stocks"),
            "crypto": MarketPage("Crypto Markets"),
            "forex": MarketPage("Forex"),
        }
        for key, _label, _icon in self.NAV_ITEMS:
            if key == "settings":
                continue
            self.center_stack.addWidget(self.market_pages[key])
        self.settings_page = SettingsPage()
        self.center_stack.addWidget(self.settings_page)
        body.addWidget(self.center_stack, 1)

        self.ai_page = OmniAIPage()
        self.ai_page.analyze_requested.connect(self.analyze_requested.emit)
        body.addWidget(self.ai_page)
        workspace_layout.addLayout(body, 1)

        footer = QHBoxLayout()
        note = QLabel("Feeds may be delayed or sample. AI signals are analysis only; order routing stays opt-in.")
        note.setObjectName("muted")
        self.clock = QLabel("LOCAL SNAPSHOT: —")
        self.clock.setObjectName("muted")
        footer.addWidget(note)
        footer.addStretch(1)
        footer.addWidget(self.clock)
        workspace_layout.addLayout(footer)

        self.setCentralWidget(shell)
        self.select_section("psx")

    def _build_sidebar(self) -> QWidget:
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setMinimumWidth(68)
        self.sidebar.setMaximumWidth(220)
        layout = QVBoxLayout(self.sidebar)
        layout.setContentsMargins(10, 14, 10, 14)
        layout.setSpacing(7)

        brand_row = QHBoxLayout()
        self.sidebar_brand = QLabel("OT")
        self.sidebar_brand.setObjectName("sidebarBrand")
        brand_row.addWidget(self.sidebar_brand)
        brand_row.addStretch(1)
        self.collapse_button = HoverButton("‹")
        self.collapse_button.setObjectName("collapseButton")
        self.collapse_button.setFixedSize(34, 34)
        self.collapse_button.clicked.connect(self.toggle_sidebar)
        brand_row.addWidget(self.collapse_button)
        layout.addLayout(brand_row)
        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)
        layout.addSpacing(7)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        for key, label, icon in self.NAV_ITEMS:
            button = HoverButton(f"{icon}   {label}")
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setMinimumHeight(46)
            button.setToolTip(label)
            self.nav_group.addButton(button)
            self.nav_buttons[key] = button
            button.clicked.connect(lambda checked=False, section=key: self.select_section(section))
            layout.addWidget(button)

        layout.addStretch(1)
        self.ai_nav_button = HoverButton("✦   OMNI AI")
        self.ai_nav_button.setObjectName("aiNavButton")
        self.ai_nav_button.setMinimumHeight(48)
        self.ai_nav_button.clicked.connect(self._focus_ai)
        layout.addWidget(self.ai_nav_button)
        self.sidebar_status = QLabel("●  FEEDS CONNECTING")
        self.sidebar_status.setObjectName("sidebarStatus")
        self.sidebar_status.setWordWrap(True)
        layout.addWidget(self.sidebar_status)
        return self.sidebar

    def _focus_ai(self) -> None:
        self.ai_page.focus_upload()

    def toggle_sidebar(self) -> None:
        self.sidebar_collapsed = not self.sidebar_collapsed
        self.sidebar.setFixedWidth(72 if self.sidebar_collapsed else 208)
        self.collapse_button.setText("›" if self.sidebar_collapsed else "‹")
        self.sidebar_brand.setText("✦" if self.sidebar_collapsed else "OMNI")
        for key, button in self.nav_buttons.items():
            icon = self.nav_icons[key]
            label = self.nav_labels[key]
            button.setText(icon if self.sidebar_collapsed else f"{icon}   {label}")
            button.setToolTip(label)
        self.ai_nav_button.setText("✦" if self.sidebar_collapsed else "✦   OMNI AI")
        self.sidebar_status.setText("●" if self.sidebar_collapsed else "●  FEEDS CONNECTING")

    def select_section(self, section: str) -> None:
        if section not in {*self.market_pages, "settings"}:
            return
        self.active_section = section
        page = self.settings_page if section == "settings" else self.market_pages[section]
        self.center_stack.setCurrentWidget(page)
        button = self.nav_buttons.get(section)
        if button is not None:
            button.setChecked(True)
        self.page_title.setText(
            "Settings & secure connections" if section == "settings" else self.market_pages[section].market_title
        )

    def update_market(self, market: str, quotes: Sequence[dict[str, object]]) -> None:
        page = self.market_pages.get(market)
        if page is None:
            return
        page.update_quotes(quotes)
        if market in {"psx", "global_stocks"} and quotes:
            self.summary_cards[market].update_quote(quotes[0])

    def update_crypto(self, quote: dict[str, object]) -> None:
        page = self.market_pages["crypto"]
        existing = getattr(
            page,
            "_crypto_quotes",
            {str(row.get("symbol", "")): row for row in page._quotes},
        )
        existing[str(quote.get("symbol", ""))] = quote
        page._crypto_quotes = existing
        page.update_quotes(list(existing.values()))
        btc = existing.get("BTCUSDT")
        if btc:
            self.summary_cards["crypto"].update_quote(btc)
        if bool(quote.get("is_live", False)):
            self.connection_status.setText("CRYPTO STREAM LIVE")
            self.sidebar_status.setText("●  CRYPTO LIVE")

    def set_connection_status(self, text: str) -> None:
        status = text.upper()
        self.connection_status.setText(status)
        if "LIVE" in status:
            self.sidebar_status.setText("●  FEEDS LIVE")
        elif "ERROR" in status:
            self.sidebar_status.setText("●  FEED ISSUE")
        else:
            self.sidebar_status.setText("●  FEEDS CONNECTING")

    def set_ai_busy(self, busy: bool) -> None:
        self.ai_page.analyze_button.setEnabled(not busy and bool(self.ai_page.image_path))

    def update_ai_result(self, signal: dict[str, str]) -> None:
        self.ai_page.show_result(signal)

    def update_ai_error(self, message: str) -> None:
        self.ai_page.show_error(message)


APP_STYLESHEET = f"""
QMainWindow, QWidget {{ background: {BG_BLACK}; color: {WHITE}; font-family: 'Segoe UI'; font-size: 10pt; }}
QWidget#shell {{ background: {BG_BLACK}; }}
QFrame#sidebar {{ background: #0E131B; border: 1px solid #1A2430; border-radius: 15px; }}
QLabel#brand {{ color: {WHITE}; font-size: 21px; font-weight: 800; letter-spacing: 2px; }}
QLabel#sidebarBrand {{ color: {ELECTRIC_BLUE}; font-size: 17px; font-weight: 900; letter-spacing: 2px; }}
QLabel#sectionTitle {{ color: {WHITE}; font-size: 18px; font-weight: 700; letter-spacing: .4px; }}
QLabel#eyebrow {{ color: {ELECTRIC_BLUE}; font-size: 10px; font-weight: 800; letter-spacing: 1.3px; }}
QLabel#muted {{ color: {MUTED}; font-size: 9pt; }}
QLabel#statusPill {{ color: {NEON_GREEN}; background: #102018; border: 1px solid #245A32; border-radius: 12px; padding: 8px 12px; font-weight: 700; }}
QLabel#statusPill[live="true"] {{ color: {NEON_GREEN}; border-color: {NEON_GREEN}; }}
QLabel#sidebarStatus {{ color: {NEON_GREEN}; padding: 8px 4px; font-size: 9pt; font-weight: 700; }}
QLabel#divider {{ background: #26313E; border: none; }}
QFrame#panel, QFrame#settingsCard {{ background: {PANEL_BLACK}; border: 1px solid #202B38; border-radius: 14px; }}
QFrame#chartCard {{ background: {PANEL_BLACK}; border: 1px solid #202B38; border-radius: 15px; }}
QFrame#summaryCard {{ background: {PANEL_BLACK}; border: 1px solid #202B38; border-radius: 14px; }}
QLabel#summaryValue {{ color: {WHITE}; font-size: 20px; font-weight: 800; }}
QFrame#aiPanel {{ background: #0E151E; border: 1px solid {ELECTRIC_BLUE}; border-radius: 15px; }}
QLabel#aiTitle {{ color: {ELECTRIC_BLUE}; font-size: 19px; font-weight: 900; letter-spacing: 1px; }}
QLabel#aiBadge {{ color: {ELECTRIC_BLUE}; background: #0D2730; border: 1px solid #145B69; border-radius: 9px; padding: 4px 7px; font-size: 8pt; font-weight: 800; }}
QScrollArea#chatScroll {{ background: transparent; border: 1px solid #1E2A37; border-radius: 12px; }}
QWidget#chatScroll > QWidget > QWidget {{ background: transparent; }}
QFrame#chatBubbleAI {{ background: #111B26; border: 1px solid #213140; border-radius: 11px; }}
QFrame#chatBubbleUser {{ background: #10222A; border: 1px solid #145363; border-radius: 11px; }}
QLabel#chatAuthor {{ color: {ELECTRIC_BLUE}; font-size: 8pt; font-weight: 900; letter-spacing: .7px; }}
QLabel#chatText {{ color: {WHITE}; font-size: 9pt; }}
QLabel#imagePreview {{ color: {MUTED}; background: #0A1017; border: 1px solid #24303D; border-radius: 12px; }}
QLabel#floatingLabel {{ color: {ELECTRIC_BLUE}; font-size: 9pt; font-weight: 700; }}
QLabel#credentialStatus {{ color: {MUTED}; font-size: 8pt; font-weight: 700; }}
QLabel#credentialStatus[success="true"] {{ color: {NEON_GREEN}; }}
QStackedWidget#centerStack {{ background: transparent; border: none; }}
QTableWidget {{ color: {WHITE}; background: {PANEL_BLACK}; gridline-color: #202B38; border: 1px solid #202B38; border-radius: 11px; selection-background-color: #183340; alternate-background-color: #121923; }}
QHeaderView::section {{ color: {MUTED}; background: #151E29; border: none; border-bottom: 1px solid #26313E; padding: 9px; font-size: 8pt; font-weight: 800; }}
QTableWidget::item {{ padding: 8px; border-bottom: 1px solid #1A2430; }}
QLineEdit {{ color: {WHITE}; background: #090E14; border: 1px solid #263544; border-radius: 11px; padding: 11px 12px; selection-background-color: #155765; }}
QLineEdit:focus {{ border: 1px solid {ELECTRIC_BLUE}; }}
QPushButton {{ color: {WHITE}; background: #18212C; border: 1px solid #293746; border-radius: 11px; padding: 10px 13px; font-weight: 700; }}
QPushButton:hover {{ background: #24313E; border-color: #506477; }}
QPushButton:pressed {{ background: #101821; }}
QPushButton:disabled {{ color: #596473; background: #151A21; border-color: #242A33; }}
QPushButton#navButton {{ color: {MUTED}; background: transparent; border: 1px solid transparent; text-align: left; padding: 11px 12px; }}
QPushButton#navButton:hover {{ color: {WHITE}; background: #17212C; border-color: #263646; }}
QPushButton#navButton:checked {{ color: {NEON_GREEN}; background: #142319; border: 1px solid #286034; }}
QPushButton#aiNavButton {{ color: {ELECTRIC_BLUE}; background: #0E222A; border: 1px solid #15515D; text-align: left; padding: 12px; }}
QPushButton#aiNavButton:hover {{ color: {WHITE}; background: #12323C; border-color: {ELECTRIC_BLUE}; }}
QPushButton#collapseButton {{ color: {ELECTRIC_BLUE}; background: #121B24; border-color: #273542; padding: 0; font-size: 17px; }}
QPushButton#collapseButton:hover {{ background: #16303A; border-color: {ELECTRIC_BLUE}; }}
QPushButton#primaryButton {{ color: #061006; background: {NEON_GREEN}; border: 1px solid {NEON_GREEN}; }}
QPushButton#primaryButton:hover {{ color: #000; background: #62FF62; border-color: #62FF62; }}
QPushButton#secondaryButton {{ color: {ELECTRIC_BLUE}; background: #10212A; border: 1px solid #176071; }}
QPushButton#secondaryButton:hover {{ color: {WHITE}; background: #15313B; border-color: {ELECTRIC_BLUE}; }}
QPushButton#uploadButton {{ color: {ELECTRIC_BLUE}; background: #101B25; border: 1px dashed {ELECTRIC_BLUE}; border-radius: 12px; }}
QPushButton#uploadButton:hover {{ color: {WHITE}; background: #12303B; border-style: solid; }}
QPushButton#eyeButton {{ color: {ELECTRIC_BLUE}; background: #101D27; border: 1px solid #23414F; border-radius: 10px; font-size: 14px; padding: 5px; }}
QPushButton#eyeButton:hover, QPushButton#eyeButton:checked {{ color: {WHITE}; background: #123541; border-color: {ELECTRIC_BLUE}; }}
QScrollBar:horizontal {{ background: #0E141C; height: 8px; border-radius: 4px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: #334251; min-width: 30px; border-radius: 4px; }}
QScrollBar::handle:horizontal:hover {{ background: {ELECTRIC_BLUE}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar:vertical {{ background: #0E141C; width: 8px; border-radius: 4px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #334251; min-height: 28px; border-radius: 4px; }}
QScrollBar::handle:vertical:hover {{ background: {ELECTRIC_BLUE}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""
