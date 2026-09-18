"""Voice Pipeline & Audio Subsystem Status Widget."""

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
    STATUS_DANGER,
    STATUS_MUTED,
    STATUS_SUCCESS,
    STATUS_WARNING,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


class VoiceStatusWidget(QFrame):
    """Subsystem status widget for Phase 4 VoicePipeline, VAD, WakeWord, STT, and TTS."""

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

        header_lbl = QLabel("VOICE & AUDIO PIPELINE")
        header_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px; font-weight: 700; letter-spacing: 1.2px;")
        layout.addWidget(header_lbl)

        # Row 1: Mic state + Pipeline state
        row1 = QHBoxLayout()
        row1.setSpacing(4)
        self.mic_dot = QLabel("●")
        self.mic_dot.setStyleSheet(f"color: {STATUS_SUCCESS}; font-size: 9px;")
        row1.addWidget(self.mic_dot)

        self.mic_lbl = QLabel("Microphone: Ready")
        self.mic_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 10px; font-weight: 600;")
        row1.addWidget(self.mic_lbl)
        row1.addStretch()

        self.pipeline_state_lbl = QLabel("STANDBY")
        self.pipeline_state_lbl.setStyleSheet(f"color: {PRIMARY_CYAN}; font-size: 9px; font-weight: 700;")
        row1.addWidget(self.pipeline_state_lbl)
        layout.addLayout(row1)

        # Row 2: Components (VAD, STT, TTS)
        row2 = QHBoxLayout()
        row2.setSpacing(6)

        self.vad_badge = QLabel("VAD: Energy")
        self.vad_badge.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 9px; background-color: rgba(30, 41, 59, 0.8); padding: 1px 4px; border-radius: 2px;"
        )
        row2.addWidget(self.vad_badge)

        self.stt_badge = QLabel("STT: Whisper")
        self.stt_badge.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 9px; background-color: rgba(30, 41, 59, 0.8); padding: 1px 4px; border-radius: 2px;"
        )
        row2.addWidget(self.stt_badge)

        self.tts_badge = QLabel("TTS: Edge")
        self.tts_badge.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 9px; background-color: rgba(30, 41, 59, 0.8); padding: 1px 4px; border-radius: 2px;"
        )
        row2.addWidget(self.tts_badge)

        row2.addStretch()
        layout.addLayout(row2)

    def set_voice_state(self, state_text: str, mic_active: bool = False, mic_available: bool = True) -> None:
        if not _PYSIDE_AVAILABLE:
            return
        self.pipeline_state_lbl.setText(state_text.upper())
        if not mic_available:
            self.mic_dot.setStyleSheet(f"color: {STATUS_DANGER}; font-size: 9px;")
            self.mic_lbl.setText("Microphone: Unavailable")
        elif mic_active:
            self.mic_dot.setStyleSheet(f"color: {PRIMARY_CYAN}; font-size: 9px;")
            self.mic_lbl.setText("Microphone: Listening")
        else:
            self.mic_dot.setStyleSheet(f"color: {STATUS_SUCCESS}; font-size: 9px;")
            self.mic_lbl.setText("Microphone: Ready")
