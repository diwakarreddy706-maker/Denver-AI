"""Security Confirmation Modal Dialog."""

from __future__ import annotations

import time
from typing import Any

try:
    from PySide6.QtCore import Qt, QTimer, Signal
    from PySide6.QtWidgets import (
        QDialog,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
    _PYSIDE_AVAILABLE = True
except ImportError:
    _PYSIDE_AVAILABLE = False
    QDialog = object  # type: ignore
    Signal = lambda *args: None  # type: ignore

from denver.ui.state import ConfirmationItem
from denver.ui.theme import (
    BG_PANEL,
    BG_SURFACE,
    BORDER_SUBTLE,
    STATUS_DANGER,
    STATUS_MUTED,
    STATUS_WARNING,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


class SecurityConfirmationDialog(QDialog):
    """Modal dialog prompting the user to confirm or cancel a high-risk automation action."""

    if _PYSIDE_AVAILABLE:
        confirmed = Signal(str)
        cancelled = Signal(str)

    def __init__(self, item: ConfirmationItem, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._item = item
        self.setWindowTitle("Security Confirmation — Denver")
        self.setFixedSize(420, 240)
        self.setModal(True)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {BG_SURFACE};
                border: 2px solid {STATUS_DANGER};
                border-radius: 8px;
            }}
        """)
        self._init_ui()

        # 1-second countdown tick timer
        if _PYSIDE_AVAILABLE:
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._on_tick)
            self._timer.start(1000)

    def _init_ui(self) -> None:
        if not _PYSIDE_AVAILABLE:
            return

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header with Security Warning Badge
        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        warn_icon = QLabel("⚠️")
        warn_icon.setStyleSheet("font-size: 18px;")
        header_row.addWidget(warn_icon)

        title_lbl = QLabel("PRIVILEGED ACTION CONFIRMATION")
        title_lbl.setStyleSheet(f"color: {STATUS_DANGER}; font-size: 13px; font-weight: 700; letter-spacing: 1.5px;")
        header_row.addWidget(title_lbl)
        header_row.addStretch()

        layout.addLayout(header_row)

        # Action description
        desc_lbl = QLabel(self._item.description)
        desc_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 600;")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        # Action details & token
        details_lbl = QLabel(f"Action: {self._item.action_name.upper()} | Token: {self._item.token}")
        details_lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; background-color: {BG_PANEL}; padding: 4px 8px; border-radius: 4px; border: 1px solid {BORDER_SUBTLE};"
        )
        layout.addWidget(details_lbl)

        # Timeout countdown label
        self.timeout_lbl = QLabel(f"Expires in {int(self._item.seconds_remaining)}s")
        self.timeout_lbl.setStyleSheet(f"color: {STATUS_WARNING}; font-size: 11px; font-weight: 600;")
        layout.addWidget(self.timeout_lbl)

        layout.addStretch()

        # Action Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.cancel_btn = QPushButton("CANCEL")
        self.cancel_btn.setProperty("class", "DialogButtonSecondary")
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addWidget(self.cancel_btn)

        self.confirm_btn = QPushButton("CONFIRM ACTION")
        self.confirm_btn.setProperty("class", "DialogButtonDanger")
        self.confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.confirm_btn.clicked.connect(self._on_confirm)
        btn_row.addWidget(self.confirm_btn)

        layout.addLayout(btn_row)

    def _on_tick(self) -> None:
        rem = self._item.seconds_remaining
        if rem <= 0:
            if hasattr(self, "_timer"):
                self._timer.stop()
            self._on_cancel()
        else:
            self.timeout_lbl.setText(f"Expires in {int(rem)}s")

    def _on_confirm(self) -> None:
        if _PYSIDE_AVAILABLE and hasattr(self, "confirmed"):
            self.confirmed.emit(self._item.token)
        self.accept()

    def _on_cancel(self) -> None:
        if _PYSIDE_AVAILABLE and hasattr(self, "cancelled"):
            self.cancelled.emit(self._item.token)
        self.reject()
