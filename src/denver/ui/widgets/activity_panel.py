"""Cyber Activity & Conversation History Panel Widget."""

from __future__ import annotations

from typing import Any

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QFrame,
        QHBoxLayout,
        QLabel,
        QScrollArea,
        QVBoxLayout,
        QWidget,
    )
    _PYSIDE_AVAILABLE = True
except ImportError:
    _PYSIDE_AVAILABLE = False
    QWidget = object  # type: ignore

from denver.ui.state import ActivityItem
from denver.ui.theme import (
    BG_INPUT,
    BG_PANEL,
    BG_PANEL_ALT,
    BG_SURFACE,
    BORDER_ACCENT,
    BORDER_CYAN,
    BORDER_SUBTLE,
    PRIMARY_BLUE,
    PRIMARY_CYAN,
    STATUS_DANGER,
    STATUS_SUCCESS,
    STATUS_WARNING,
    TEXT_CYAN,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


class ActivityItemCard(QFrame):
    """Visual card for a single activity/command execution entry with User/Denver distinction."""

    def __init__(self, item: ActivityItem, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            f"background-color: {BG_PANEL}; border: 1px solid {BORDER_SUBTLE}; border-radius: 8px; padding: 8px;"
        )
        self._init_ui(item)

    def _init_ui(self, item: ActivityItem) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 1. Header Row: Timestamp, Action Badge, Risk Badge, Status Badge
        header_row = QHBoxLayout()
        header_row.setSpacing(6)

        time_label = QLabel(item.formatted_time)
        time_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; font-weight: 600;")
        header_row.addWidget(time_label)

        action_label = QLabel(item.action_name.upper())
        action_label.setStyleSheet(
            f"color: {PRIMARY_CYAN}; font-size: 9px; font-weight: 700; background-color: rgba(6, 182, 212, 0.12); padding: 2px 6px; border-radius: 4px; border: 1px solid rgba(6, 182, 212, 0.3);"
        )
        header_row.addWidget(action_label)

        header_row.addStretch()

        # Risk Badge
        risk_color = STATUS_SUCCESS if item.risk_level in {"SAFE", "LOW"} else (STATUS_WARNING if item.risk_level == "MEDIUM" else STATUS_DANGER)
        risk_label = QLabel(item.risk_level)
        risk_label.setStyleSheet(
            f"color: {risk_color}; font-size: 9px; font-weight: 700; border: 1px solid {risk_color}; padding: 1px 5px; border-radius: 3px;"
        )
        header_row.addWidget(risk_label)

        # Status Badge
        status_text = "SUCCESS" if item.success else "FAILED"
        status_color = STATUS_SUCCESS if item.success else STATUS_DANGER
        status_badge = QLabel(status_text)
        status_badge.setStyleSheet(
            f"color: {status_color}; font-size: 9px; font-weight: 700; background-color: rgba({239 if not item.success else 34}, {68 if not item.success else 197}, {68 if not item.success else 94}, 0.15); padding: 1px 6px; border-radius: 3px;"
        )
        header_row.addWidget(status_badge)

        layout.addLayout(header_row)

        # 2. User Command Text (User prompt bubble)
        if item.command_text:
            user_frame = QFrame()
            user_frame.setStyleSheet(
                f"background-color: {BG_INPUT}; border: 1px solid {BORDER_SUBTLE}; border-radius: 6px; padding: 6px 10px;"
            )
            u_layout = QHBoxLayout(user_frame)
            u_layout.setContentsMargins(4, 2, 4, 2)
            u_layout.setSpacing(6)

            u_icon = QLabel("› USER:")
            u_icon.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; font-weight: 700;")
            u_layout.addWidget(u_icon)

            user_lbl = QLabel(item.command_text)
            user_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px; font-weight: 600;")
            user_lbl.setWordWrap(True)
            u_layout.addWidget(user_lbl, stretch=1)

            layout.addWidget(user_frame)

        # 3. Denver Response Text (Assistant response container)
        if item.response_text:
            resp_frame = QFrame()
            resp_frame.setStyleSheet(
                f"background-color: {BG_PANEL_ALT}; border-left: 2px solid {PRIMARY_CYAN}; border-radius: 4px; padding: 8px 10px;"
            )
            r_layout = QVBoxLayout(resp_frame)
            r_layout.setContentsMargins(4, 2, 4, 2)
            r_layout.setSpacing(4)

            r_header = QLabel("◈ DENVER")
            r_header.setStyleSheet(f"color: {TEXT_CYAN}; font-size: 10px; font-weight: 700; letter-spacing: 1px;")
            r_layout.addWidget(r_header)

            resp_lbl = QLabel(item.response_text)
            resp_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px; line-height: 1.4;")
            resp_lbl.setWordWrap(True)
            r_layout.addWidget(resp_lbl)

            layout.addWidget(resp_frame)

        # 4. Latency / Memory / Error footer
        item_data = getattr(item, "data", None)
        has_memory_stats = bool(item_data and isinstance(item_data, dict) and item_data.get("memories_used", 0) > 0)
        if item.error or item.latency_ms > 0 or has_memory_stats:
            footer_row = QHBoxLayout()
            footer_row.setSpacing(8)
            if item.latency_ms > 0:
                lat_lbl = QLabel(f"⚡ {item.latency_ms:.1f}ms")
                lat_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 9px; font-weight: 600;")
                footer_row.addWidget(lat_lbl)
            if has_memory_stats and item_data:
                mem_used = item_data.get("memories_used", 0)
                mem_lbl = QLabel(f"🧠 Memory: {mem_used}")
                mem_lbl.setStyleSheet(f"color: {PRIMARY_CYAN}; font-size: 9px; font-weight: 700; background-color: rgba(6, 182, 212, 0.1); padding: 1px 5px; border-radius: 3px;")
                footer_row.addWidget(mem_lbl)
            if item.error:
                err_lbl = QLabel(f"⚠ {item.error}")
                err_lbl.setStyleSheet(f"color: {STATUS_DANGER}; font-size: 9px; font-weight: 600;")
                footer_row.addWidget(err_lbl)
            footer_row.addStretch()
            layout.addLayout(footer_row)




class EmptyStateWidget(QWidget):
    """Clean empty state placeholder shown when no activity exists."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 40, 20, 40)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_lbl = QLabel("◈")
        icon_lbl.setStyleSheet(f"color: {PRIMARY_CYAN}; font-size: 28px; font-weight: 700;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_lbl)

        title_lbl = QLabel("SYSTEM READY")
        title_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 14px; font-weight: 800; letter-spacing: 1.5px;")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_lbl)

        desc_lbl = QLabel("Waiting for your command...")
        desc_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc_lbl)

        hint_lbl = QLabel('Try: "What is my CPU usage?" or "Denver, what time is it?"')
        hint_lbl.setStyleSheet(f"color: {TEXT_CYAN}; font-size: 11px; font-style: italic;")
        hint_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint_lbl)


class ActivityPanelWidget(QWidget):
    """Multi-Tab Command Center housing Live Chat Stream, Tasks Orchestration, and Proactive Routines."""

    def __init__(self, controller: Any | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._init_ui()

    def _init_ui(self) -> None:
        if not _PYSIDE_AVAILABLE:
            return

        from PySide6.QtWidgets import QTabWidget
        from denver.ui.widgets.home_dashboard import DenverHomeTabWidget
        from denver.ui.widgets.routines_widget import ScheduledRoutinesWidget
        from denver.ui.widgets.tasks_widget import TasksOrchestrationWidget

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(6)

        # Tabbed Command Center
        self.tabs = QTabWidget()
        self.tabs.setObjectName("ActivityTabs")

        # ─── TAB 0: Home Dashboard (Cyber HUD Overlay Content) ───────
        self.home_tab = DenverHomeTabWidget(controller=self.controller)
        self.tabs.addTab(self.home_tab, "🏠 HOME")

        # ─── TAB 1: Live Chat & Activity Stream ───────────────────────
        self.stream_tab = QWidget()
        stream_layout = QVBoxLayout(self.stream_tab)
        stream_layout.setContentsMargins(4, 6, 4, 4)
        stream_layout.setSpacing(6)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet(
            f"background-color: {BG_SURFACE}; border: 1px solid {BORDER_SUBTLE}; border-radius: 8px;"
        )

        self.container = QWidget()
        self.container.setStyleSheet("background: transparent;")
        self.list_layout = QVBoxLayout(self.container)
        self.list_layout.setContentsMargins(8, 8, 8, 8)
        self.list_layout.setSpacing(8)

        # Empty state placeholder
        self.empty_state = EmptyStateWidget(self.container)
        self.list_layout.addWidget(self.empty_state)
        self.list_layout.addStretch()

        self.scroll_area.setWidget(self.container)
        stream_layout.addWidget(self.scroll_area, stretch=1)

        self.tabs.addTab(self.stream_tab, "💬 LIVE CHAT & STREAM")

        # ─── TAB 2: Intelligent Task Orchestration (Phase 9) ─────────
        self.tasks_widget = TasksOrchestrationWidget()
        self.tabs.addTab(self.tasks_widget, "📋 TASK WORKFLOWS")

        # ─── TAB 3: Proactive Scheduled Routines (Phase 8) ───────────
        self.routines_widget = ScheduledRoutinesWidget()
        self.tabs.addTab(self.routines_widget, "⚡ SCHEDULED ROUTINES")

        # ─── TAB 4: Modular Plugins & Extensions ──────────────────────
        from denver.ui.widgets.plugins_widget import PluginsWidget
        self.plugins_widget = PluginsWidget()
        self.tabs.addTab(self.plugins_widget, "🧩 PLUGINS")

        # Default to HOME tab (index 0)
        self.tabs.setCurrentIndex(0)

        main_layout.addWidget(self.tabs, stretch=1)

    def add_item(self, item: ActivityItem) -> None:
        """Append an activity card and scroll smoothly to the bottom."""
        if not _PYSIDE_AVAILABLE:
            return

        # Hide empty state once first item arrives
        if not self.empty_state.isHidden():
            self.empty_state.hide()

        # Switch to chat tab when new activity arrives
        if hasattr(self, "tabs") and hasattr(self, "stream_tab"):
            self.tabs.setCurrentWidget(self.stream_tab)

        card = ActivityItemCard(item, self.container)
        count = self.list_layout.count()
        self.list_layout.insertWidget(max(0, count - 1), card)

        QScrollArea.ensureVisible(
            self.scroll_area,
            0,
            self.container.height(),
            50,
            50,
        )
