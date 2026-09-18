"""Tasks & Workflow Orchestration Status Widget (Phase 9)."""

from __future__ import annotations

from typing import Any

try:
    from PySide6.QtWidgets import (  # type: ignore
        QFrame,
        QHBoxLayout,
        QLabel,
        QProgressBar,
        QVBoxLayout,
        QWidget,
    )
    _PYSIDE_AVAILABLE = True
except ImportError:
    _PYSIDE_AVAILABLE = False
    QWidget = object  # type: ignore
    QFrame = object  # type: ignore
    QLabel = object  # type: ignore
    QHBoxLayout = object  # type: ignore
    QVBoxLayout = object  # type: ignore
    QProgressBar = object  # type: ignore

from denver.ui.theme import (
    BG_PANEL,
    BORDER_SUBTLE,
    PRIMARY_CYAN,
    STATUS_DANGER,
    STATUS_SUCCESS,
    STATUS_WARNING,
    TEXT_CYAN,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


class TasksOrchestrationWidget(QFrame):
    """Cockpit widget displaying multi-step task workflows, DAG progress, and orchestration health."""

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

        header_lbl = QLabel("INTELLIGENT TASK & WORKFLOW ORCHESTRATION")
        header_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px; font-weight: 700; letter-spacing: 1.2px;")
        layout.addWidget(header_lbl)

        # Status row
        row1 = QHBoxLayout()
        row1.setSpacing(4)
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet(f"color: {STATUS_SUCCESS}; font-size: 9px;")
        row1.addWidget(self.status_dot)

        self.status_label = QLabel("Orchestration: Ready")
        self.status_label.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 10px; font-weight: 600;")
        row1.addWidget(self.status_label)
        row1.addStretch()

        self.active_tasks_label = QLabel("ACTIVE: 0")
        self.active_tasks_label.setStyleSheet(f"color: {TEXT_CYAN}; font-size: 9px; font-weight: 700;")
        row1.addWidget(self.active_tasks_label)
        layout.addLayout(row1)

        # Progress / Step Details
        row2 = QHBoxLayout()
        row2.setSpacing(6)
        self.current_step_label = QLabel("Step: Idle")
        self.current_step_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 9px;")
        row2.addWidget(self.current_step_label)
        row2.addStretch()

        self.safety_badge = QLabel("SAFETY: STRICT DAG")
        self.safety_badge.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 8px; font-weight: 700;")
        row2.addWidget(self.safety_badge)
        layout.addLayout(row2)

    def update_status(self, task_data: dict[str, Any] | None) -> None:
        """Update widget with real-time task orchestration metrics."""
        if not _PYSIDE_AVAILABLE or not task_data:
            return

        enabled = task_data.get("enabled", True)
        paused = task_data.get("is_global_paused", False)
        active_count = task_data.get("active_count", 0)
        current_step = task_data.get("current_step", "Idle")

        if not enabled:
            self.status_dot.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 9px;")
            self.status_label.setText("Orchestration: Disabled")
        elif paused:
            self.status_dot.setStyleSheet(f"color: {STATUS_WARNING}; font-size: 9px;")
            self.status_label.setText("Orchestration: Paused")
        else:
            self.status_dot.setStyleSheet(f"color: {STATUS_SUCCESS}; font-size: 9px;")
            self.status_label.setText("Orchestration: Ready")

        self.active_tasks_label.setText(f"ACTIVE: {active_count}")
        self.current_step_label.setText(f"Step: {current_step}")
