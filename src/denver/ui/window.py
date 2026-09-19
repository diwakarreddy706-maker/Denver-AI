"""Denver AI Assistant — Primary Home Dashboard Window."""

from __future__ import annotations

from typing import Any

try:
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QColor, QFont
    from PySide6.QtWidgets import (
        QFrame,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
    _PYSIDE_AVAILABLE = True
except ImportError:
    _PYSIDE_AVAILABLE = False
    QMainWindow = object  # type: ignore
    QWidget = object  # type: ignore

import psutil

from denver import __version__, assistant_name, product_name
from denver.logging.logger import get_logger
from denver.runtime.states import DenverState
from denver.ui.controller import UIController
from denver.ui.state import ActivityItem, CockpitState, ConfirmationItem
from denver.ui.theme import (
    BG_OVERLAY_GRADIENT,
    CARD_BG_GRADIENT,
    CARD_BORDER,
    PRIMARY_CYAN,
    STATUS_DANGER,
    STATUS_SUCCESS,
    TEXT_CYAN,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from denver.ui.widgets.confirmation_dialog import SecurityConfirmationDialog
from denver.ui.widgets.home_dashboard import (
    AIStatusCard,
    BottomBarWidget,
    LiveClockCard,
    QuickActionsCard,
    QuickStatusCard,
    SystemPerformanceCard,
    WeatherCard,
    _get_disk_storage_info,
)
from denver.ui.widgets.settings_dialog import SettingsDialog

logger = get_logger("ui.window")


class MainWindow(QMainWindow):
    """Main window for Denver AI Assistant — Clean HUD Home Dashboard."""

    def __init__(self, controller: UIController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle(f"{product_name} — Home Dashboard")
        self.resize(1200, 800)
        self.setMinimumSize(960, 640)

        self._init_ui()
        self._bind_signals()

    def _init_ui(self) -> None:
        if not _PYSIDE_AVAILABLE:
            return

        # Central widget with radial dark cyber background
        central = QWidget(self)
        central.setObjectName("DashboardCentral")
        central.setStyleSheet(f"""
            QWidget#DashboardCentral {{
                background: {BG_OVERLAY_GRADIENT};
                font-family: 'Segoe UI', -apple-system, sans-serif;
            }}
        """)
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Main HUD Body Area
        body_widget = QWidget()
        body_layout = QVBoxLayout(body_widget)
        body_layout.setContentsMargins(32, 28, 32, 18)
        body_layout.setSpacing(16)

        # TOP SECTION: Weather (top-left) vs. Stacked Cards (top-right)
        top_row = QHBoxLayout()
        top_row.setSpacing(24)

        # TOP-LEFT Weather Card
        self.weather_card = WeatherCard()
        top_row.addWidget(self.weather_card, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        top_row.addStretch(1)

        # TOP-RIGHT Stacked Cards (System Performance, Quick Status, Live Clock)
        top_right_col = QVBoxLayout()
        top_right_col.setSpacing(12)
        top_right_col.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)

        self.perf_card = SystemPerformanceCard()
        top_right_col.addWidget(self.perf_card)

        self.quick_status_card = QuickStatusCard()
        top_right_col.addWidget(self.quick_status_card)

        self.clock_card = LiveClockCard()
        top_right_col.addWidget(self.clock_card)

        top_row.addLayout(top_right_col)
        body_layout.addLayout(top_row)

        # CENTER SECTION: Open ambient space matching reference;
        # hosts a floating translucent response card when Denver responds to queries.
        self.center_area = QWidget()
        center_layout = QVBoxLayout(self.center_area)
        center_layout.setContentsMargins(40, 0, 40, 0)
        center_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.response_card = QFrame()
        self.response_card.setObjectName("ResponseCard")
        self.response_card.setMinimumWidth(500)
        self.response_card.setMaximumWidth(750)
        self.response_card.setStyleSheet(f"""
            QFrame#ResponseCard {{
                background: {CARD_BG_GRADIENT};
                border: 1px solid {CARD_BORDER};
                border-radius: 12px;
                padding: 12px;
            }}
        """)
        resp_layout = QVBoxLayout(self.response_card)
        resp_layout.setContentsMargins(14, 10, 14, 10)
        resp_layout.setSpacing(6)

        # Response Header with query and close button
        resp_header = QHBoxLayout()
        self.resp_query_lbl = QLabel("💬")
        self.resp_query_lbl.setStyleSheet(f"color: {TEXT_CYAN}; font-size: 11px; font-weight: 700;")
        resp_header.addWidget(self.resp_query_lbl, stretch=1)

        resp_close_btn = QPushButton("✕")
        resp_close_btn.setFixedSize(20, 20)
        resp_close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        resp_close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_MUTED};
                border: none;
                font-size: 11px;
            }}
            QPushButton:hover {{
                color: {STATUS_DANGER};
            }}
        """)
        resp_close_btn.clicked.connect(self.response_card.hide)
        resp_header.addWidget(resp_close_btn)
        resp_layout.addLayout(resp_header)

        self.resp_text_lbl = QLabel("")
        self.resp_text_lbl.setWordWrap(True)
        self.resp_text_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 500; line-height: 1.4;")
        resp_layout.addWidget(self.resp_text_lbl)

        # Hidden by default to preserve the clean, spacious ambient look of Image 2
        self.response_card.hide()
        center_layout.addWidget(self.response_card)

        body_layout.addWidget(self.center_area, stretch=1)

        # BOTTOM SECTION: Quick Actions (bottom-left) vs. AI Status (bottom-right)
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(24)

        # BOTTOM-LEFT Quick Actions
        self.actions_card = QuickActionsCard(controller=self.controller)
        bottom_row.addWidget(self.actions_card, alignment=Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft)

        bottom_row.addStretch(1)

        # BOTTOM-RIGHT AI Status Card
        self.ai_status_card = AIStatusCard(controller=self.controller)
        bottom_row.addWidget(self.ai_status_card, alignment=Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)

        body_layout.addLayout(bottom_row)
        root_layout.addWidget(body_widget, stretch=1)

        # BOTTOM BAR (Full-width docked)
        self.bottom_bar = BottomBarWidget(controller=self.controller)
        self.bottom_bar.close_requested.connect(self.close)
        self.bottom_bar.settings_requested.connect(self._open_settings)
        self.bottom_bar.command_submitted.connect(self._on_command_submitted)
        root_layout.addWidget(self.bottom_bar)

        # Periodic Telemetry Update Timer (every 2s)
        self.telemetry_timer = QTimer(self)
        self.telemetry_timer.timeout.connect(self._on_telemetry_tick)
        self.telemetry_timer.start(2000)

    def _bind_signals(self) -> None:
        if not self.controller or not hasattr(self.controller, "bridge") or not self.controller.bridge:
            return

        bridge = self.controller.bridge
        if hasattr(bridge, "telemetry_updated"):
            bridge.telemetry_updated.connect(self._on_telemetry_updated)
        if hasattr(bridge, "state_changed"):
            bridge.state_changed.connect(self._on_state_changed)
        if hasattr(bridge, "activity_added"):
            bridge.activity_added.connect(self._on_activity_added)
        if hasattr(bridge, "confirmation_requested"):
            bridge.confirmation_requested.connect(self._on_confirmation_requested)
        if hasattr(bridge, "voice_state_changed"):
            bridge.voice_state_changed.connect(self._on_voice_state_changed)

    def _on_telemetry_tick(self) -> None:
        """Periodic background poll for CPU, memory, storage, and quick status."""
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent
        storage, _ = _get_disk_storage_info()

        self.perf_card.update_telemetry(cpu_pct=cpu, mem_pct=mem, storage_pct=storage)
        self.quick_status_card.refresh_quick_status()

    def _on_telemetry_updated(self, state: Any) -> None:
        cpu = getattr(state, "cpu_percent", None)
        ram = getattr(state, "ram_percent", None)
        self.perf_card.update_telemetry(cpu_pct=cpu, mem_pct=ram)

    def _on_state_changed(self, new_state: DenverState, reason: str = "") -> None:
        self.ai_status_card.update_status(new_state)

    def _on_voice_state_changed(self, listening: bool) -> None:
        state = DenverState.LISTENING if listening else DenverState.STANDBY
        self.ai_status_card.update_status(state)

    def _on_activity_added(self, item: Any) -> None:
        latency_ms = getattr(item, "latency_ms", 0.0) or 0.0
        latency_s = latency_ms / 1000.0
        state = self.controller.state.current_state if self.controller else DenverState.STANDBY
        self.ai_status_card.update_status(state=state, latency_s=latency_s)

        # Present response smoothly in central response card if text is available
        resp_text = getattr(item, "response_text", "")
        cmd_text = getattr(item, "command_text", "")
        if resp_text:
            self.resp_query_lbl.setText(f"💬 \"{cmd_text}\"" if cmd_text else "💬 Result")
            self.resp_text_lbl.setText(resp_text)
            self.response_card.show()

    def _on_command_submitted(self, text: str) -> None:
        if self.controller:
            self.controller.submit_command(text)

    def _on_confirmation_requested(self, item: ConfirmationItem) -> None:
        dialog = SecurityConfirmationDialog(item, parent=self)
        if dialog.exec():
            token = getattr(item, "token", "")
            if token and self.controller:
                self.controller.submit_command(f"Denver, confirm {token}")
        else:
            token = getattr(item, "token", "")
            if token and self.controller:
                self.controller.submit_command(f"Denver, cancel {token}")

    def _open_settings(self) -> None:
        dialog = SettingsDialog(parent=self)
        dialog.exec()

    def keyPressEvent(self, event: Any) -> None:
        """Escape key closes window."""
        if _PYSIDE_AVAILABLE and event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
        else:
            super().keyPressEvent(event)
