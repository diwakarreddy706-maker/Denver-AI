"""Denver Cockpit Settings & Preferences Dialog."""

from __future__ import annotations

from typing import Any

try:
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QDialog,
        QFrame,
        QGridLayout,
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
    QDialog = object  # type: ignore
    Signal = lambda *args: None  # type: ignore

from denver import __version__, assistant_name, product_name
from denver.config.settings import DenverSettings
from denver.ui.theme import (
    BG_PANEL,
    BG_SURFACE,
    BORDER_SUBTLE,
    PRIMARY_BLUE,
    PRIMARY_CYAN,
    STATUS_MUTED,
    STATUS_SUCCESS,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


class SettingsDialog(QDialog):
    """Configuration dialog exposing safe preference adjustments without revealing secrets."""

    if _PYSIDE_AVAILABLE:
        settings_saved = Signal(dict)

    def __init__(self, settings: DenverSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self.setWindowTitle(f"Settings — {product_name}")
        self.setFixedSize(480, 420)
        self.setModal(True)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {BG_SURFACE};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: 8px;
            }}
        """)
        self._init_ui()

    def _init_ui(self) -> None:
        if not _PYSIDE_AVAILABLE:
            return

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title_lbl = QLabel(f"{product_name.upper()} PREFERENCES")
        title_lbl.setStyleSheet(f"color: {PRIMARY_CYAN}; font-size: 13px; font-weight: 700; letter-spacing: 1.5px;")
        layout.addWidget(title_lbl)

        grid = QGridLayout()
        grid.setSpacing(10)

        # 1. Privacy Mode
        grid.addWidget(QLabel("Privacy Mode:"), 0, 0)
        self.chk_privacy = QCheckBox("Mask sensitive entities in logs & memory")
        self.chk_privacy.setChecked(self._settings.privacy_mode)
        grid.addWidget(self.chk_privacy, 0, 1)

        # 2. Audio & Voice Enabled
        grid.addWidget(QLabel("Voice Pipeline:"), 1, 0)
        self.chk_voice = QCheckBox("Enable microphone capture & VAD")
        self.chk_voice.setChecked(self._settings.voice_enabled)
        grid.addWidget(self.chk_voice, 1, 1)

        # 3. Preferred TTS Voice
        grid.addWidget(QLabel("TTS Voice:"), 2, 0)
        self.combo_voice = QComboBox()
        self.combo_voice.addItems([
            "en-GB-RyanNeural",
            "en-US-JennyNeural",
            "en-US-GuyNeural",
            "en-AU-NatNeural",
        ])
        self.combo_voice.setCurrentText(self._settings.tts_voice)
        grid.addWidget(self.combo_voice, 2, 1)

        # 4. AI Provider Mode
        grid.addWidget(QLabel("AI Provider Mode:"), 3, 0)
        self.combo_ai_mode = QComboBox()
        self.combo_ai_mode.addItems(["auto", "local", "cloud"])
        self.combo_ai_mode.setCurrentText(self._settings.ai_mode)
        grid.addWidget(self.combo_ai_mode, 3, 1)

        # 5. Desktop Automation Enabled
        grid.addWidget(QLabel("Automation:"), 4, 0)
        self.chk_auto = QCheckBox("Enable allowlisted desktop control")
        self.chk_auto.setChecked(self._settings.automation_enabled)
        grid.addWidget(self.chk_auto, 4, 1)

        # 6. Default Browser
        grid.addWidget(QLabel("Default Browser:"), 5, 0)
        self.txt_browser = QLineEdit(self._settings.default_browser)
        grid.addWidget(self.txt_browser, 5, 1)

        layout.addLayout(grid)

        # Denver Vault Credential Status Section
        vault_box = QFrame()
        vault_box.setStyleSheet(f"background-color: {BG_PANEL}; border: 1px solid {BORDER_SUBTLE}; border-radius: 6px; padding: 8px;")
        vault_layout = QVBoxLayout(vault_box)
        vault_layout.setContentsMargins(6, 6, 6, 6)
        vault_layout.setSpacing(4)

        vault_header = QLabel("DENVER VAULT CREDENTIALS")
        vault_header.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 9px; font-weight: 700; letter-spacing: 1px;")
        vault_layout.addWidget(vault_header)

        groq_stat = "Configured" if self._settings.groq_api_key else "Not Configured (Default)"
        groq_lbl = QLabel(f"• Groq API Key: {groq_stat}")
        groq_lbl.setStyleSheet(f"color: {STATUS_SUCCESS if self._settings.groq_api_key else STATUS_MUTED}; font-size: 10px;")
        vault_layout.addWidget(groq_lbl)

        gemini_stat = "Configured" if self._settings.gemini_api_key else "Not Configured (Default)"
        gemini_lbl = QLabel(f"• Gemini API Key: {gemini_stat}")
        gemini_lbl.setStyleSheet(f"color: {STATUS_SUCCESS if self._settings.gemini_api_key else STATUS_MUTED}; font-size: 10px;")
        vault_layout.addWidget(gemini_lbl)

        layout.addWidget(vault_box)

        layout.addStretch()

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        close_btn = QPushButton("CANCEL")
        close_btn.setProperty("class", "DialogButtonSecondary")
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)

        save_btn = QPushButton("SAVE SETTINGS")
        save_btn.setProperty("class", "DialogButtonPrimary")
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

    def _on_save(self) -> None:
        updates = {
            "privacy_mode": self.chk_privacy.isChecked(),
            "voice_enabled": self.chk_voice.isChecked(),
            "tts_voice": self.combo_voice.currentText(),
            "ai_mode": self.combo_ai_mode.currentText(),
            "automation_enabled": self.chk_auto.isChecked(),
            "default_browser": self.txt_browser.text().strip() or "default",
        }
        if _PYSIDE_AVAILABLE and hasattr(self, "settings_saved"):
            self.settings_saved.emit(updates)
        self.accept()
