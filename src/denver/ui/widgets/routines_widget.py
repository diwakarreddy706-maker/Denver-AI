"""Scheduled Routines & Proactive Intelligence Status Widget (Phase 8)."""

from __future__ import annotations

from typing import Any

try:
    from PySide6.QtWidgets import (
        QFrame,
        QHBoxLayout,
        QLabel,
        QVBoxLayout,
        QWidget,
    )
    _PYSIDE_AVAILABLE = True
except ImportError:
    _PYSIDE_AVAILABLE = False
    QWidget = object  # type: ignore

from denver.ui.theme import (
    BG_PANEL,
    BORDER_SUBTLE,
    PRIMARY_CYAN,
    STATUS_SUCCESS,
    STATUS_WARNING,
    TEXT_CYAN,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


class ScheduledRoutinesWidget(QFrame):
    """Cockpit widget displaying active scheduled routines, triggers, and scheduler status."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            f"background-color: {BG_PANEL}; border: 1px solid {BORDER_SUBTLE}; border-radius: 8px; padding: 6px;"
        )
        self._init_ui()

    def _init_ui(self) -> None:
        if not _PYSIDE_AVAILABLE:
            return

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        header_lbl = QLabel("PROACTIVE ROUTINES & SCHEDULER")
        header_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px; font-weight: 700; letter-spacing: 1.2px;")
        layout.addWidget(header_lbl)

        # Status row
        row1 = QHBoxLayout()
        row1.setSpacing(4)
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet(f"color: {STATUS_SUCCESS}; font-size: 9px;")
        row1.addWidget(self.status_dot)

        self.status_label = QLabel("Scheduler: Active")
        self.status_label.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 10px; font-weight: 600;")
        row1.addWidget(self.status_label)
        row1.addStretch()

        self.routines_count_label = QLabel("ROUTINES: 0 ACTIVE")
        self.routines_count_label.setStyleSheet(f"color: {TEXT_CYAN}; font-size: 9px; font-weight: 700;")
        row1.addWidget(self.routines_count_label)
        layout.addLayout(row1)

        # Next run details
        row2 = QHBoxLayout()
        row2.setSpacing(6)
        self.next_run_label = QLabel("Next Run: None scheduled")
        self.next_run_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 9px;")
        row2.addWidget(self.next_run_label)
        row2.addStretch()

        self.safety_badge = QLabel("SAFETY: BOUNDED")
        self.safety_badge.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 8px; font-weight: 700;")
        row2.addWidget(self.safety_badge)
        layout.addLayout(row2)

    def update_status(self, scheduler_data: dict[str, Any] | None) -> None:
        """Update widget with real-time scheduler health metrics."""
        if not _PYSIDE_AVAILABLE or not scheduler_data:
            return

        enabled = scheduler_data.get("enabled", True)
        paused = scheduler_data.get("paused", False)
        running = scheduler_data.get("running", True)
        active_count = scheduler_data.get("active_routines", 0)
        total_count = scheduler_data.get("total_routines", 0)
        next_run = scheduler_data.get("next_run_at")

        if not enabled:
            self.status_dot.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 9px;")
            self.status_label.setText("Scheduler: Disabled")
        elif paused:
            self.status_dot.setStyleSheet(f"color: {STATUS_WARNING}; font-size: 9px;")
            self.status_label.setText("Scheduler: Paused")
        elif running:
            self.status_dot.setStyleSheet(f"color: {STATUS_SUCCESS}; font-size: 9px;")
            self.status_label.setText("Scheduler: Active")
        else:
            self.status_dot.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 9px;")
            self.status_label.setText("Scheduler: Stopped")

        self.routines_count_label.setText(f"ROUTINES: {active_count}/{total_count}")

        if next_run:
            self.next_run_label.setText(f"Next Run: {next_run}")
        else:
            self.next_run_label.setText("Next Run: None scheduled")
