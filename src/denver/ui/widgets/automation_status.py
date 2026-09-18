"""Desktop Automation Subsystem Status Widget."""

from __future__ import annotations

from typing import Any

try:
    from PySide6.QtWidgets import (
        QFrame,
        QGridLayout,
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
    STATUS_DANGER,
    STATUS_MUTED,
    STATUS_SUCCESS,
    STATUS_WARNING,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


class AutomationBadge(QFrame):
    """Compact status pill for an automation module."""

    def __init__(self, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        self._init_ui(name)

    def _init_ui(self, name: str) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)

        self.dot = QLabel("●")
        self.dot.setStyleSheet(f"color: {STATUS_SUCCESS}; font-size: 8px;")
        layout.addWidget(self.dot)

        self.label = QLabel(name)
        self.label.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 10px; font-weight: 600;")
        layout.addWidget(self.label)
        layout.addStretch()

    def set_status(self, status: str) -> None:
        s = status.upper()
        if s == "READY":
            self.dot.setStyleSheet(f"color: {STATUS_SUCCESS}; font-size: 8px;")
        elif s in {"UNAVAILABLE", "DEGRADED"}:
            self.dot.setStyleSheet(f"color: {STATUS_WARNING}; font-size: 8px;")
        elif s == "ERROR":
            self.dot.setStyleSheet(f"color: {STATUS_DANGER}; font-size: 8px;")
        else:
            self.dot.setStyleSheet(f"color: {STATUS_MUTED}; font-size: 8px;")


class AutomationStatusWidget(QFrame):
    """Subsystem status widget for Phase 5 Desktop Automation & Windows Control."""

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

        header_lbl = QLabel("DESKTOP AUTOMATION (WIN32)")
        header_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px; font-weight: 700; letter-spacing: 1.2px;")
        layout.addWidget(header_lbl)

        grid = QGridLayout()
        grid.setSpacing(4)

        self.apps_badge = AutomationBadge("Applications")
        grid.addWidget(self.apps_badge, 0, 0)

        self.win_badge = AutomationBadge("Windows")
        grid.addWidget(self.win_badge, 0, 1)

        self.vol_badge = AutomationBadge("Volume")
        grid.addWidget(self.vol_badge, 1, 0)

        self.browser_badge = AutomationBadge("Browser")
        grid.addWidget(self.browser_badge, 1, 1)

        self.shot_badge = AutomationBadge("Screenshot")
        grid.addWidget(self.shot_badge, 2, 0)

        self.sys_badge = AutomationBadge("System")
        grid.addWidget(self.sys_badge, 2, 1)

        layout.addLayout(grid)

    def update_automation(self, auto_status: dict[str, str]) -> None:
        if not _PYSIDE_AVAILABLE:
            return
        if "applications" in auto_status:
            self.apps_badge.set_status(auto_status["applications"])
        if "windows" in auto_status:
            self.win_badge.set_status(auto_status["windows"])
        if "volume" in auto_status:
            self.vol_badge.set_status(auto_status["volume"])
        if "browser" in auto_status:
            self.browser_badge.set_status(auto_status["browser"])
        if "screenshot" in auto_status:
            self.shot_badge.set_status(auto_status["screenshot"])
        if "system" in auto_status:
            self.sys_badge.set_status(auto_status["system"])
