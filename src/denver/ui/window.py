"""Denver AI Assistant — Commercial AI Operating System Dashboard.

Matches high-end SaaS desktop reference design with glowing AI orb, glassmorphic
sidebar navigation, quick actions, central multi-modal input bar, live weather,
and telemetry HUD stack.
"""

from __future__ import annotations

from datetime import datetime
import os
from typing import Any

try:
    from PySide6.QtCore import QPoint, Qt, QTimer, Signal
    from PySide6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter
    from PySide6.QtWidgets import (
        QFrame,
        QGraphicsDropShadowEffect,
        QHBoxLayout,
        QLabel,
        QLineEdit,
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
    BG_APP,
    BG_INPUT,
    BG_OVERLAY_GRADIENT,
    CARD_BG_GLASS,
    CARD_BG_GRADIENT,
    CARD_BORDER,
    CARD_BORDER_PURPLE,
    GRADIENT_BTN_TASK,
    GRADIENT_PURPLE_CYAN,
    GRADIENT_SEND_BTN,
    PRIMARY_BLUE,
    PRIMARY_CYAN,
    PRIMARY_PURPLE,
    STATUS_DANGER,
    STATUS_SUCCESS,
    STATUS_WARNING,
    TEXT_CYAN,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from denver.ui.widgets.ai_orb import DenverAIOrbWidget
from denver.ui.widgets.confirmation_dialog import SecurityConfirmationDialog
from denver.ui.widgets.home_dashboard import WeatherCard, _get_disk_storage_info
from denver.ui.widgets.hud_panels import DenverHUDPanelStack
from denver.ui.widgets.settings_dialog import SettingsDialog
from denver.ui.widgets.sidebar import DenverSidebarWidget

logger = get_logger("ui.window")


class TopNavBar(QWidget):
    """Custom sleek top title bar with logo, breadcrumb, settings, and window controls."""

    settings_requested = Signal()
    minimize_requested = Signal()
    maximize_requested = Signal()
    close_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(46)
        self.setObjectName("TopNavBar")
        self.setStyleSheet(f"""
            QWidget#TopNavBar {{
                background-color: rgba(10, 15, 29, 0.95);
                border-bottom: 1px solid rgba(56, 189, 248, 0.12);
            }}
        """)
        self._drag_pos: QPoint | None = None
        self._init_ui()

    def _init_ui(self) -> None:
        if not _PYSIDE_AVAILABLE:
            return

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 12, 0)
        layout.setSpacing(10)

        # 1. Left: Gradient Monogram Badge + Title
        logo_badge = QLabel("A")
        logo_badge.setFixedSize(26, 26)
        logo_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_badge.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #38BDF8, stop:1 #8B5CF6);
            color: #FFFFFF;
            font-size: 13px;
            font-weight: 900;
            border-radius: 7px;
        """)
        layout.addWidget(logo_badge)

        title_lbl = QLabel(product_name)
        title_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 700;")
        layout.addWidget(title_lbl)

        sep_lbl = QLabel("/")
        sep_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; font-weight: 400;")
        layout.addWidget(sep_lbl)

        dash_lbl = QLabel("Home Dashboard")
        dash_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; font-weight: 500;")
        layout.addWidget(dash_lbl)

        layout.addStretch(1)

        # 2. Right: Notification Bell, Settings, Window Controls
        self.bell_btn = QPushButton("🔔")
        self.bell_btn.setToolTip("Notifications")
        self.bell_btn.setFixedSize(30, 30)
        self.bell_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bell_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_SECONDARY};
                border: none;
                border-radius: 6px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: rgba(255, 255, 255, 0.08);
                color: {PRIMARY_CYAN};
            }}
        """)
        layout.addWidget(self.bell_btn)

        self.settings_btn = QPushButton("⚙️")
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.setFixedSize(30, 30)
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_SECONDARY};
                border: none;
                border-radius: 6px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: rgba(255, 255, 255, 0.08);
                color: {PRIMARY_CYAN};
            }}
        """)
        self.settings_btn.clicked.connect(self.settings_requested.emit)
        layout.addWidget(self.settings_btn)

        # Window Controls Divider
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedHeight(18)
        sep.setStyleSheet("color: rgba(255, 255, 255, 0.15);")
        layout.addWidget(sep)

        # Minimize
        min_btn = QPushButton("─")
        min_btn.setFixedSize(30, 30)
        min_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        min_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_SECONDARY};
                border: none;
                border-radius: 6px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: rgba(255, 255, 255, 0.08);
                color: {TEXT_PRIMARY};
            }}
        """)
        min_btn.clicked.connect(self.minimize_requested.emit)
        layout.addWidget(min_btn)

        # Maximize / Restore
        max_btn = QPushButton("□")
        max_btn.setFixedSize(30, 30)
        max_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        max_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_SECONDARY};
                border: none;
                border-radius: 6px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: rgba(255, 255, 255, 0.08);
                color: {TEXT_PRIMARY};
            }}
        """)
        max_btn.clicked.connect(self.maximize_requested.emit)
        layout.addWidget(max_btn)

        # Close
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(30, 30)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_SECONDARY};
                border: none;
                border-radius: 6px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: {STATUS_DANGER};
                color: #FFFFFF;
            }}
        """)
        close_btn.clicked.connect(self.close_requested.emit)
        layout.addWidget(close_btn)

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            w = self.window()
            if w:
                self._drag_pos = event.globalPosition().toPoint() - w.frameGeometry().topLeft()
                event.accept()

    def mouseMoveEvent(self, event: Any) -> None:
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos:
            w = self.window()
            if w:
                w.move(event.globalPosition().toPoint() - self._drag_pos)
                event.accept()


class DenverBottomStatusBar(QWidget):
    """Bottom docked status bar with active state indicator and audio visualizer wave."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(38)
        self.setObjectName("DenverBottomStatusBar")
        self.setStyleSheet(f"""
            QWidget#DenverBottomStatusBar {{
                background-color: rgba(10, 15, 29, 0.95);
                border-top: 1px solid rgba(56, 189, 248, 0.12);
            }}
        """)
        self._init_ui()

    def _init_ui(self) -> None:
        if not _PYSIDE_AVAILABLE:
            return

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 0, 18, 0)
        layout.setSpacing(12)

        # Left: Assistant Brand and Status
        avatar = QLabel("D")
        avatar.setFixedSize(20, 20)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #06B6D4, stop:1 #3B82F6);
            color: #FFFFFF;
            font-size: 11px;
            font-weight: 800;
            border-radius: 10px;
        """)
        layout.addWidget(avatar)

        brand_lbl = QLabel(product_name)
        brand_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 11px; font-weight: 700;")
        layout.addWidget(brand_lbl)

        help_lbl = QLabel("● Always here to help")
        help_lbl.setStyleSheet(f"color: {PRIMARY_CYAN}; font-size: 11px; font-weight: 500;")
        layout.addWidget(help_lbl)

        layout.addStretch(1)

        # Right: Wave Bars + State
        self.wave_lbl = QLabel("ılılı.")
        self.wave_lbl.setStyleSheet(f"color: {PRIMARY_CYAN}; font-size: 13px; font-weight: 700; letter-spacing: 2px;")
        layout.addWidget(self.wave_lbl)

        self.state_lbl = QLabel("Standby")
        self.state_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; font-weight: 600;")
        layout.addWidget(self.state_lbl)

        ver_lbl = QLabel(f"v{__version__}")
        ver_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px;")
        layout.addWidget(ver_lbl)

    def set_state(self, state: DenverState) -> None:
        if state == DenverState.LISTENING:
            self.state_lbl.setText("Listening...")
            self.state_lbl.setStyleSheet(f"color: {PRIMARY_CYAN}; font-size: 11px; font-weight: 600;")
            self.wave_lbl.setStyleSheet("color: #38BDF8; font-size: 14px; font-weight: 800; letter-spacing: 3px;")
        elif state == DenverState.PROCESSING:
            self.state_lbl.setText("Processing...")
            self.state_lbl.setStyleSheet(f"color: {STATUS_WARNING}; font-size: 11px; font-weight: 600;")
        elif state == DenverState.SPEAKING:
            self.state_lbl.setText("Speaking...")
            self.state_lbl.setStyleSheet("color: #C084FC; font-size: 11px; font-weight: 600;")
        else:
            self.state_lbl.setText("Standby")
            self.state_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; font-weight: 600;")
            self.wave_lbl.setStyleSheet(f"color: {PRIMARY_CYAN}; font-size: 13px; font-weight: 700; letter-spacing: 2px;")


class MainWindow(QMainWindow):
    """Main window for Denver AI Assistant — Commercial SaaS OS Desktop."""

    def __init__(self, controller: UIController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle(f"{product_name} — Home Dashboard")
        self.resize(1200, 800)
        self.setMinimumSize(1000, 680)

        # Sleek frameless styling with custom draggable titlebar
        if _PYSIDE_AVAILABLE:
            self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)

        self._init_ui()
        self._bind_signals()

    def _init_ui(self) -> None:
        if not _PYSIDE_AVAILABLE:
            return

        # Root Central Widget with dark futuristic radial background
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

        # 1. TOP NAV BAR
        self.top_bar = TopNavBar(self)
        self.top_bar.settings_requested.connect(self._open_settings)
        self.top_bar.minimize_requested.connect(self.showMinimized)
        self.top_bar.maximize_requested.connect(self._toggle_maximize)
        self.top_bar.close_requested.connect(self.close)
        root_layout.addWidget(self.top_bar)

        # 2. MAIN 3-COLUMN BODY
        body_widget = QWidget()
        body_layout = QHBoxLayout(body_widget)
        body_layout.setContentsMargins(12, 10, 12, 10)
        body_layout.setSpacing(14)

        # COLUMN A: Left Sidebar Navigation & Quick Actions
        self.sidebar = DenverSidebarWidget(controller=self.controller, parent=self)
        self.sidebar.action_triggered.connect(self._on_sidebar_action)
        body_layout.addWidget(self.sidebar)

        # COLUMN B: Center Stage (Greeting + Weather, Glowing AI Orb, Action Pills, Input Bar)
        center_container = QWidget()
        center_layout = QVBoxLayout(center_container)
        center_layout.setContentsMargins(10, 8, 10, 8)
        center_layout.setSpacing(12)

        # B1. Top Row: Greeting + Weather Card
        top_stage_row = QHBoxLayout()
        top_stage_row.setSpacing(16)

        # Dynamic Greeting Block
        greeting_box = QVBoxLayout()
        greeting_box.setSpacing(2)

        hour = datetime.now().hour
        if 5 <= hour < 12:
            greet_text = "Good Morning,"
        elif 12 <= hour < 18:
            greet_text = "Good Afternoon,"
        else:
            greet_text = "Good Evening,"

        self.greet_lbl = QLabel(greet_text)
        self.greet_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 23px; font-weight: 800; letter-spacing: -0.4px;")
        greeting_box.addWidget(self.greet_lbl)

        self.greet_sub = QLabel("Your AI Assistant is ready!")
        self.greet_sub.setStyleSheet(f"color: {PRIMARY_CYAN}; font-size: 19px; font-weight: 700; letter-spacing: -0.2px;")
        greeting_box.addWidget(self.greet_sub)

        self.greet_desc = QLabel("Ask anything, get things done, stay productive.")
        self.greet_desc.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; font-weight: 500;")
        greeting_box.addWidget(self.greet_desc)

        top_stage_row.addLayout(greeting_box, stretch=1)

        # Weather Card
        self.weather_card = WeatherCard()
        top_stage_row.addWidget(self.weather_card, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)

        center_layout.addLayout(top_stage_row)

        # B2. Central AI Glowing Orb
        orb_container = QHBoxLayout()
        orb_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ai_orb = DenverAIOrbWidget(self)
        self.ai_orb.clicked.connect(self._on_orb_clicked)
        orb_container.addWidget(self.ai_orb)
        center_layout.addLayout(orb_container)

        # B3. 4 Action Suggestion Pills
        pills_layout = QHBoxLayout()
        pills_layout.setSpacing(10)
        pills_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        pills_data = [
            ("💬", "Answer Questions", "Denver, what can you help me with?"),
            ("📄", "Write && Edit", "Denver, help me write a summary of today's tasks"),
            ("📈", "Analyze Data", "Denver, analyze system performance and memory"),
            ("📁", "Help with Files", "Denver, check recent project files"),
        ]

        for icon, label, prompt in pills_data:
            pill_btn = self._create_action_pill(icon, label, prompt)
            pills_layout.addWidget(pill_btn)

        center_layout.addLayout(pills_layout)

        # B4. Central Response Floating Card (Hidden by default, displays assistant answer)
        self.response_card = QFrame()
        self.response_card.setObjectName("ResponseCard")
        self.response_card.setStyleSheet(f"""
            QFrame#ResponseCard {{
                background: {CARD_BG_GLASS};
                border: 1px solid {CARD_BORDER_PURPLE};
                border-radius: 14px;
                padding: 10px;
            }}
        """)
        resp_layout = QVBoxLayout(self.response_card)
        resp_layout.setContentsMargins(14, 8, 14, 8)
        resp_layout.setSpacing(4)

        resp_header = QHBoxLayout()
        self.resp_query_lbl = QLabel("💬 Result")
        self.resp_query_lbl.setStyleSheet(f"color: {TEXT_CYAN}; font-size: 11px; font-weight: 700;")
        resp_header.addWidget(self.resp_query_lbl, stretch=1)

        resp_close = QPushButton("✕")
        resp_close.setFixedSize(18, 18)
        resp_close.setCursor(Qt.CursorShape.PointingHandCursor)
        resp_close.setStyleSheet(f"""
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
        resp_close.clicked.connect(self.response_card.hide)
        resp_header.addWidget(resp_close)
        resp_layout.addLayout(resp_header)

        self.resp_text_lbl = QLabel("")
        self.resp_text_lbl.setWordWrap(True)
        self.resp_text_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px; font-weight: 500; line-height: 1.4;")
        resp_layout.addWidget(self.resp_text_lbl)

        self.response_card.hide()
        center_layout.addWidget(self.response_card)

        center_layout.addStretch(1)

        # B5. Large Rounded AI Input Bar
        self.input_container = QFrame()
        self.input_container.setObjectName("InputContainer")
        self.input_container.setStyleSheet(f"""
            QFrame#InputContainer {{
                background-color: rgba(15, 23, 42, 0.85);
                border: 1px solid rgba(56, 189, 248, 0.35);
                border-radius: 26px;
                padding: 4px 10px;
            }}
            QFrame#InputContainer:focus-within {{
                border: 1px solid {PRIMARY_CYAN};
            }}
        """)
        input_row = QHBoxLayout(self.input_container)
        input_row.setContentsMargins(10, 4, 6, 4)
        input_row.setSpacing(10)

        # Sparkle icon
        sparkle = QLabel("✨")
        sparkle.setStyleSheet(f"color: {PRIMARY_CYAN}; font-size: 14px;")
        input_row.addWidget(sparkle)

        # Line Edit
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("Ask Denver anything...")
        self.input_edit.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                border: none;
                color: {TEXT_PRIMARY};
                font-size: 13px;
                font-weight: 500;
            }}
        """)
        self.input_edit.returnPressed.connect(self._submit_input)
        input_row.addWidget(self.input_edit, stretch=1)

        # Attachment button
        attach_btn = QPushButton("📎")
        attach_btn.setToolTip("Attach file or context")
        attach_btn.setFixedSize(28, 28)
        attach_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        attach_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_SECONDARY};
                border: none;
                border-radius: 14px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                color: {PRIMARY_CYAN};
                background: rgba(255, 255, 255, 0.08);
            }}
        """)
        input_row.addWidget(attach_btn)

        # Mic button
        self.mic_btn = QPushButton("🎙️")
        self.mic_btn.setToolTip("Voice Input")
        self.mic_btn.setFixedSize(28, 28)
        self.mic_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mic_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_SECONDARY};
                border: none;
                border-radius: 14px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                color: {PRIMARY_CYAN};
                background: rgba(255, 255, 255, 0.08);
            }}
        """)
        self.mic_btn.clicked.connect(self._toggle_voice_listen)
        input_row.addWidget(self.mic_btn)

        # Circular Send Button
        self.send_btn = QPushButton("➔")
        self.send_btn.setToolTip("Send command")
        self.send_btn.setFixedSize(36, 36)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.setStyleSheet("""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #38BDF8, stop:1 #8B5CF6);
                border: none;
                border-radius: 18px;
                color: #FFFFFF;
                font-size: 15px;
                font-weight: 800;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #06B6D4, stop:1 #7C3AED);
            }}
        """)
        self.send_btn.clicked.connect(self._submit_input)
        input_row.addWidget(self.send_btn)

        center_layout.addWidget(self.input_container)
        body_layout.addWidget(center_container, stretch=1)

        # COLUMN C: Right Telemetry HUD Panels (Performance, Quick Status, Clock, AI Status)
        self.hud_stack = DenverHUDPanelStack(self)
        body_layout.addWidget(self.hud_stack)

        # Backwards compatibility handles
        self.perf_card = self.hud_stack.perf_card
        self.quick_status_card = self.hud_stack.quick_status_card
        self.clock_card = self.hud_stack.clock_card
        self.ai_status_card = self.hud_stack.ai_status_card

        root_layout.addWidget(body_widget, stretch=1)

        # 3. BOTTOM STATUS BAR
        self.bottom_bar = DenverBottomStatusBar(self)
        root_layout.addWidget(self.bottom_bar)

    def _create_action_pill(self, icon: str, title: str, prompt: str) -> QPushButton:
        """Create a rounded translucent suggestion action pill."""
        btn = QPushButton(f"{icon}  {title}")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(15, 23, 42, 0.75);
                border: 1px solid rgba(56, 189, 248, 0.25);
                border-radius: 18px;
                padding: 7px 16px;
                color: {TEXT_PRIMARY};
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: rgba(56, 189, 248, 0.15);
                border: 1px solid {PRIMARY_CYAN};
                color: #FFFFFF;
            }}
            QPushButton:pressed {{
                background-color: rgba(56, 189, 248, 0.25);
            }}
        """)
        btn.clicked.connect(lambda: self._on_action_pill_clicked(prompt))
        return btn

    def _on_action_pill_clicked(self, prompt: str) -> None:
        self.input_edit.setText(prompt)
        self._submit_input()

    def _submit_input(self) -> None:
        text = self.input_edit.text().strip()
        if not text:
            return
        self.input_edit.clear()
        if self.controller:
            self.controller.submit_command(text)

    def _toggle_voice_listen(self) -> None:
        if self.controller and hasattr(self.controller, "toggle_voice_listening"):
            self.controller.toggle_voice_listening()
        elif self.controller:
            self.controller.submit_command("Denver, listen")

    def _on_orb_clicked(self) -> None:
        """Clicking the central orb toggles listening or submits greeting."""
        if self.controller:
            self.controller.submit_command("Denver, hello")

    def _on_sidebar_action(self, action_name: str) -> None:
        if self.controller:
            self.controller.submit_command(f"Denver, {action_name}")

    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

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

    def _on_telemetry_updated(self, state: Any) -> None:
        cpu = getattr(state, "cpu_percent", None)
        ram = getattr(state, "ram_percent", None)
        self.perf_card.update_telemetry(cpu=cpu, mem=ram)

    def _on_state_changed(self, new_state: DenverState, reason: str = "") -> None:
        self.ai_status_card.update_status(new_state)
        self.ai_orb.set_state(new_state)
        self.bottom_bar.set_state(new_state)

    def _on_voice_state_changed(self, listening: bool) -> None:
        state = DenverState.LISTENING if listening else DenverState.STANDBY
        self.ai_status_card.update_status(state)
        self.ai_orb.set_state(state)
        self.bottom_bar.set_state(state)

    def _on_activity_added(self, item: Any) -> None:
        latency_ms = getattr(item, "latency_ms", 0.0) or 0.0
        latency_s = latency_ms / 1000.0
        state = self.controller.state.current_state if self.controller else DenverState.STANDBY
        self.ai_status_card.update_status(state=state, latency_s=latency_s)

        resp_text = getattr(item, "response_text", "")
        cmd_text = getattr(item, "command_text", "")
        if resp_text:
            self.resp_query_lbl.setText(f"💬 \"{cmd_text}\"" if cmd_text else "💬 Result")
            self.resp_text_lbl.setText(resp_text)
            self.response_card.show()

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
