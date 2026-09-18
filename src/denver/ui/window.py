"""Denver Cockpit Main Window."""

from __future__ import annotations

from typing import Any

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QPushButton,
        QSplitter,
        QVBoxLayout,
        QWidget,
    )
    _PYSIDE_AVAILABLE = True
except ImportError:
    _PYSIDE_AVAILABLE = False
    QMainWindow = object  # type: ignore
    QWidget = object  # type: ignore

from denver import __version__, assistant_name, product_name
from denver.runtime.states import DenverState
from denver.ui.controller import UIController
from denver.ui.state import ActivityItem, CockpitState, ConfirmationItem
from denver.ui.theme import (
    BG_ROOT,
    BG_SURFACE,
    BORDER_SUBTLE,
    COCKPIT_STYLESHEET,
    PRIMARY_CYAN,
    STATUS_DANGER,
    STATUS_SUCCESS,
    STATUS_WARNING,
    TEXT_CYAN,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from denver.ui.widgets.activity_panel import ActivityPanelWidget
from denver.ui.widgets.automation_status import AutomationStatusWidget
from denver.ui.widgets.command_input import CommandInputWidget
from denver.ui.widgets.confirmation_dialog import SecurityConfirmationDialog
from denver.ui.widgets.core_visualizer import DenverCoreVisualizer
from denver.ui.widgets.memory_status import MemoryStatusWidget
from denver.ui.widgets.provider_status import ProviderStatusWidget
from denver.ui.widgets.settings_dialog import SettingsDialog
from denver.ui.widgets.telemetry_panel import TelemetryPanelWidget
from denver.ui.widgets.voice_status import VoiceStatusWidget


class MainWindow(QMainWindow):
    """Main window for Denver Cockpit — Cyber Command Center."""

    def __init__(self, controller: UIController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle(f"{product_name} — Cockpit v{__version__}")
        self.setMinimumSize(960, 680)
        self.resize(1160, 800)
        self.setStyleSheet(COCKPIT_STYLESHEET)
        self._init_ui()
        self._bind_signals()

    def _init_ui(self) -> None:
        if not _PYSIDE_AVAILABLE:
            return

        root = QWidget()
        root.setObjectName("CockpitRoot")
        self.setCentralWidget(root)

        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # 1. Top Navigation & Identity Bar
        top_bar = QFrame()
        top_bar.setObjectName("TopBar")
        top_bar.setStyleSheet(
            f"background-color: {BG_SURFACE}; border: 1px solid {BORDER_SUBTLE}; border-radius: 8px; padding: 6px 14px;"
        )
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(6, 4, 6, 4)
        top_layout.setSpacing(10)

        # Logo & Product Name
        logo_lbl = QLabel("◆ DENVER")
        logo_lbl.setObjectName("TitleLabel")
        logo_lbl.setStyleSheet(f"color: {PRIMARY_CYAN}; font-size: 16px; font-weight: 800; letter-spacing: 2px;")
        top_layout.addWidget(logo_lbl)

        sub_lbl = QLabel("PERSONAL AI ASSISTANT")
        sub_lbl.setObjectName("SubtitleLabel")
        sub_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; font-weight: 700; letter-spacing: 1.5px;")
        top_layout.addWidget(sub_lbl)

        top_layout.addStretch()

        # Global State Badge Pill
        self.state_pill = QLabel("● READY (STANDBY)")
        self.state_pill.setProperty("class", "StatusPillReady")
        self.state_pill.setStyleSheet(
            f"background-color: rgba(34, 197, 94, 0.12); color: {STATUS_SUCCESS}; border: 1px solid rgba(34, 197, 94, 0.4); border-radius: 10px; padding: 3px 12px; font-size: 10px; font-weight: 700; letter-spacing: 0.8px;"
        )
        top_layout.addWidget(self.state_pill)

        # Settings Action Button
        self.settings_btn = QPushButton("⚙ SETTINGS")
        self.settings_btn.setProperty("class", "QuickChip")
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.setStyleSheet(
            f"background-color: {BG_ROOT}; color: {TEXT_SECONDARY}; border: 1px solid {BORDER_SUBTLE}; border-radius: 6px; padding: 5px 12px; font-size: 11px; font-weight: 600;"
        )
        self.settings_btn.clicked.connect(self._open_settings)
        top_layout.addWidget(self.settings_btn)

        main_layout.addWidget(top_bar)

        # 2. Main Content Splitter (Left: Core & Telemetry; Right: Activity Feed)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background: transparent; }")

        # Left Panel (Core Visualizer + Telemetry)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        # Denver Animated Core Frame
        core_frame = QFrame()
        core_frame.setStyleSheet(
            f"background-color: {BG_SURFACE}; border: 1px solid {BORDER_SUBTLE}; border-radius: 8px;"
        )
        core_layout = QVBoxLayout(core_frame)
        core_layout.setContentsMargins(8, 8, 8, 8)
        core_layout.setSpacing(6)

        self.core_visualizer = DenverCoreVisualizer()
        core_layout.addWidget(self.core_visualizer, stretch=1)
        left_layout.addWidget(core_frame, stretch=1)

        # Telemetry Monitor Panel
        self.telemetry_panel = TelemetryPanelWidget()
        left_layout.addWidget(self.telemetry_panel, stretch=0)

        splitter.addWidget(left_widget)

        # Right Panel (Activity Feed)
        self.activity_panel = ActivityPanelWidget()
        splitter.addWidget(self.activity_panel)

        # Splitter proportion (38% left, 62% right)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 6)
        main_layout.addWidget(splitter, stretch=1)

        # 3. Subsystem Diagnostic Status Grid
        diag_frame = QFrame()
        diag_layout = QGridLayout(diag_frame)
        diag_layout.setContentsMargins(0, 0, 0, 0)
        diag_layout.setSpacing(8)

        self.voice_status_widget = VoiceStatusWidget()
        diag_layout.addWidget(self.voice_status_widget, 0, 0)

        self.provider_status_widget = ProviderStatusWidget()
        diag_layout.addWidget(self.provider_status_widget, 0, 1)

        self.automation_status_widget = AutomationStatusWidget()
        diag_layout.addWidget(self.automation_status_widget, 0, 2)

        self.memory_status_widget = MemoryStatusWidget()
        diag_layout.addWidget(self.memory_status_widget, 0, 3)

        main_layout.addWidget(diag_frame)

        # 4. Command Input Bar
        self.command_input = CommandInputWidget()
        self.command_input.command_submitted.connect(self._on_command_submitted)
        if hasattr(self.command_input, "voice_clicked"):
            self.command_input.voice_clicked.connect(self.controller.trigger_voice_listening)
        if hasattr(self.core_visualizer, "clicked"):
            self.core_visualizer.clicked.connect(self.controller.trigger_voice_listening)
        main_layout.addWidget(self.command_input)

    def _bind_signals(self) -> None:
        if not _PYSIDE_AVAILABLE or not self.controller.bridge:
            return

        bridge = self.controller.bridge
        bridge.state_changed.connect(self._on_state_changed)
        bridge.activity_added.connect(self._on_activity_added)
        bridge.telemetry_updated.connect(self._on_telemetry_updated)
        bridge.voice_state_changed.connect(self._on_voice_state_changed)
        bridge.ai_providers_updated.connect(self._on_ai_providers_updated)
        bridge.automation_updated.connect(self._on_automation_updated)
        bridge.memory_updated.connect(self._on_memory_updated)
        bridge.confirmation_required.connect(self._on_confirmation_required)

        # Plugins & Auto-Repair signals
        if hasattr(bridge, "plugins_updated") and hasattr(self.activity_panel, "plugins_widget"):
            bridge.plugins_updated.connect(self.activity_panel.plugins_widget.update_plugins)
            self.activity_panel.plugins_widget.plugin_toggled.connect(self.controller.toggle_plugin)
            self.activity_panel.plugins_widget.reload_requested.connect(self.controller.reload_plugins)

        if hasattr(bridge, "repair_completed"):
            bridge.repair_completed.connect(self.telemetry_panel.set_repair_result)

        if hasattr(self.telemetry_panel, "repair_requested"):
            self.telemetry_panel.repair_requested.connect(self.controller.trigger_system_repair)

        # Bind controller to EventBus
        self.controller.bind_event_bus()

    def _on_command_submitted(self, text: str) -> None:
        self.controller.submit_command(text)

    def _on_state_changed(self, state: DenverState, reason: str) -> None:
        self.core_visualizer.set_state(state)
        state_str = state.value.upper()
        if state == DenverState.STANDBY:
            self.state_pill.setText(f"● READY ({state_str})")
            self.state_pill.setStyleSheet(
                f"background-color: rgba(34, 197, 94, 0.12); color: {STATUS_SUCCESS}; border: 1px solid rgba(34, 197, 94, 0.4); border-radius: 10px; padding: 3px 12px; font-size: 10px; font-weight: 700; letter-spacing: 0.8px;"
            )
        elif state == DenverState.ERROR:
            self.state_pill.setText(f"● ERROR ({reason[:20]})")
            self.state_pill.setStyleSheet(
                f"background-color: rgba(239, 68, 68, 0.12); color: {STATUS_DANGER}; border: 1px solid rgba(239, 68, 68, 0.4); border-radius: 10px; padding: 3px 12px; font-size: 10px; font-weight: 700; letter-spacing: 0.8px;"
            )
        elif state in {DenverState.PROCESSING, DenverState.EXECUTING}:
            self.state_pill.setText(f"● {state_str}")
            self.state_pill.setStyleSheet(
                f"background-color: rgba(6, 182, 212, 0.12); color: {PRIMARY_CYAN}; border: 1px solid rgba(6, 182, 212, 0.4); border-radius: 10px; padding: 3px 12px; font-size: 10px; font-weight: 700; letter-spacing: 0.8px;"
            )
        else:
            self.state_pill.setText(f"● {state_str}")
            self.state_pill.setStyleSheet(
                f"background-color: rgba(100, 116, 139, 0.12); color: {TEXT_MUTED}; border: 1px solid rgba(100, 116, 139, 0.4); border-radius: 10px; padding: 3px 12px; font-size: 10px; font-weight: 700; letter-spacing: 0.8px;"
            )

    def _on_activity_added(self, item: ActivityItem) -> None:
        self.activity_panel.add_item(item)

    def _on_telemetry_updated(self, state: CockpitState) -> None:
        self.telemetry_panel.update_telemetry(state)
        if hasattr(self.activity_panel, "tasks_widget") and hasattr(state, "tasks_status"):
            self.activity_panel.tasks_widget.update_status(getattr(state, "tasks_status", None))
        if hasattr(self.activity_panel, "routines_widget") and hasattr(state, "routines_status"):
            self.activity_panel.routines_widget.update_status(getattr(state, "routines_status", None))

    def _on_voice_state_changed(self, state_text: str, active: bool, available: bool) -> None:
        self.voice_status_widget.set_voice_state(state_text, active, available)

    def _on_ai_providers_updated(self, providers: dict[str, str]) -> None:
        self.provider_status_widget.update_providers(providers)

    def _on_automation_updated(self, auto_status: dict[str, str]) -> None:
        self.automation_status_widget.update_automation(auto_status)

    def _on_memory_updated(self, memory_data: dict[str, Any]) -> None:
        self.memory_status_widget.update_memory(memory_data)

    def _on_confirmation_required(self, item: ConfirmationItem) -> None:
        dlg = SecurityConfirmationDialog(item, self)
        dlg.confirmed.connect(self.controller.confirm_action)
        dlg.cancelled.connect(self.controller.cancel_action)
        dlg.show()

    def _open_settings(self) -> None:
        settings = getattr(self.controller.app, "settings", None)
        if not settings:
            from denver.config.settings import get_settings
            settings = get_settings()
        dlg = SettingsDialog(settings, self)
        dlg.exec()
