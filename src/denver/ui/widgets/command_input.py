"""Cyber Command Input Bar Widget."""

from __future__ import annotations

from typing import Any

try:
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtWidgets import (
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
    _PYSIDE_AVAILABLE = True
except ImportError:
    _PYSIDE_AVAILABLE = False
    QWidget = object  # type: ignore
    Signal = lambda *args: None  # type: ignore

from denver.ui.theme import (
    BG_INPUT,
    BORDER_CYAN,
    BORDER_SUBTLE,
    PRIMARY_BLUE,
    PRIMARY_CYAN,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


class CommandInputWidget(QWidget):
    """Natural language command input bar with cyber aesthetic and quick-action chips."""

    if _PYSIDE_AVAILABLE:
        command_submitted = Signal(str)
        voice_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        if not _PYSIDE_AVAILABLE:
            return

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Primary Input Row
        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self.mic_btn = QPushButton("🎙️")
        self.mic_btn.setObjectName("MicButton")
        self.mic_btn.setToolTip("Click to speak (Voice Push-To-Talk)")
        self.mic_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mic_btn.setStyleSheet(
            f"QPushButton#MicButton {{ background: rgba(6, 182, 212, 0.15); color: {PRIMARY_CYAN}; border: 1px solid rgba(6, 182, 212, 0.4); border-radius: 6px; padding: 6px 12px; font-size: 14px; font-weight: bold; }}"
            f"QPushButton#MicButton:hover {{ background: rgba(6, 182, 212, 0.3); border: 1px solid {PRIMARY_CYAN}; }}"
        )
        self.mic_btn.clicked.connect(self._on_mic_clicked)
        input_row.addWidget(self.mic_btn)

        self.input_field = QLineEdit()
        self.input_field.setObjectName("CommandInput")
        self.input_field.setPlaceholderText("◈ Ask Denver anything, speak, or type a command... (e.g. 'what time is it', 'open whatsapp')")
        self.input_field.returnPressed.connect(self._on_submit)
        input_row.addWidget(self.input_field, stretch=1)

        self.send_btn = QPushButton("➤ SEND")
        self.send_btn.setObjectName("SendButton")
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.clicked.connect(self._on_submit)
        input_row.addWidget(self.send_btn)

        layout.addLayout(input_row)

        # Quick Suggestion Chips Row
        chips_row = QHBoxLayout()
        chips_row.setSpacing(6)

        label_quick = QLabel("QUICK:")
        label_quick.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 9px; font-weight: 700; letter-spacing: 1px;")
        chips_row.addWidget(label_quick)

        chips = [
            ("🕒 TIME", "Denver, what time is it?"),
            ("⚡ CPU", "Denver, what is my CPU usage?"),
            ("🖥️ SYSTEM", "Denver, get system summary"),
            ("🧮 CALCULATOR", "Denver, open calculator"),
        ]

        for display_name, full_cmd in chips:
            btn = QPushButton(display_name)
            btn.setProperty("class", "QuickChip")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, cmd=full_cmd: self._on_chip_clicked(cmd))
            chips_row.addWidget(btn)

        chips_row.addStretch()
        layout.addLayout(chips_row)

    def _on_chip_clicked(self, command_text: str) -> None:
        self.input_field.setText(command_text)
        self._on_submit()

    def _on_submit(self) -> None:
        text = self.input_field.text().strip()
        if not text:
            return
        self.input_field.clear()
        if _PYSIDE_AVAILABLE and hasattr(self, "command_submitted"):
            self.command_submitted.emit(text)

    def _on_mic_clicked(self) -> None:
        if _PYSIDE_AVAILABLE and hasattr(self, "voice_clicked"):
            self.voice_clicked.emit()

    def set_enabled_state(self, enabled: bool) -> None:
        if _PYSIDE_AVAILABLE:
            self.input_field.setEnabled(enabled)
            self.send_btn.setEnabled(enabled)
            if hasattr(self, "mic_btn"):
                self.mic_btn.setEnabled(enabled)
