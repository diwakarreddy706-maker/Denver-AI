"""AI Provider Status Panel Widget."""

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
    STATUS_DANGER,
    STATUS_MUTED,
    STATUS_SUCCESS,
    STATUS_WARNING,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


class ProviderRow(QFrame):
    """Single AI provider status row with indicator dot."""

    def __init__(self, name: str, is_local: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        self._init_ui(name, is_local)

    def _init_ui(self, name: str, is_local: bool) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(6)

        self.dot_lbl = QLabel("●")
        self.dot_lbl.setStyleSheet(f"color: {STATUS_MUTED}; font-size: 9px;")
        layout.addWidget(self.dot_lbl)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 11px; font-weight: 600;")
        layout.addWidget(name_lbl)

        tag = "LOCAL" if is_local else "CLOUD"
        tag_lbl = QLabel(tag)
        tag_lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 8px; font-weight: 700; background-color: rgba(30, 41, 59, 0.8); padding: 1px 4px; border-radius: 2px;"
        )
        layout.addWidget(tag_lbl)

        layout.addStretch()

        self.status_lbl = QLabel("NOT CONFIGURED")
        self.status_lbl.setStyleSheet(f"color: {STATUS_MUTED}; font-size: 9px; font-weight: 600;")
        layout.addWidget(self.status_lbl)

    def set_status(self, status: str) -> None:
        stat_clean = status.upper().replace("_", " ")
        self.status_lbl.setText(stat_clean)
        if stat_clean == "READY":
            self.dot_lbl.setStyleSheet(f"color: {STATUS_SUCCESS}; font-size: 9px;")
            self.status_lbl.setStyleSheet(f"color: {STATUS_SUCCESS}; font-size: 9px; font-weight: 700;")
        elif stat_clean in {"UNAVAILABLE", "OFFLINE", "DEGRADED"}:
            self.dot_lbl.setStyleSheet(f"color: {STATUS_WARNING}; font-size: 9px;")
            self.status_lbl.setStyleSheet(f"color: {STATUS_WARNING}; font-size: 9px; font-weight: 600;")
        elif stat_clean == "ERROR":
            self.dot_lbl.setStyleSheet(f"color: {STATUS_DANGER}; font-size: 9px;")
            self.status_lbl.setStyleSheet(f"color: {STATUS_DANGER}; font-size: 9px; font-weight: 700;")
        else:  # NOT CONFIGURED
            self.dot_lbl.setStyleSheet(f"color: {STATUS_MUTED}; font-size: 9px;")
            self.status_lbl.setStyleSheet(f"color: {STATUS_MUTED}; font-size: 9px; font-weight: 600;")


class ProviderStatusWidget(QFrame):
    """Subsystem status widget for Denver AI Multi-Model Provider Router."""

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
        layout.setSpacing(3)

        header_lbl = QLabel("AI PROVIDERS (MULTI-MODEL)")
        header_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px; font-weight: 700; letter-spacing: 1.2px;")
        layout.addWidget(header_lbl)

        self.ollama_row = ProviderRow("Ollama", is_local=True)
        layout.addWidget(self.ollama_row)

        self.lmstudio_row = ProviderRow("LM Studio", is_local=True)
        layout.addWidget(self.lmstudio_row)

        self.groq_row = ProviderRow("Groq", is_local=False)
        layout.addWidget(self.groq_row)

        self.gemini_row = ProviderRow("Gemini", is_local=False)
        layout.addWidget(self.gemini_row)

    def update_providers(self, providers: dict[str, str]) -> None:
        if not _PYSIDE_AVAILABLE:
            return
        if "ollama" in providers:
            self.ollama_row.set_status(providers["ollama"])
        if "lmstudio" in providers:
            self.lmstudio_row.set_status(providers["lmstudio"])
        if "groq" in providers:
            self.groq_row.set_status(providers["groq"])
        if "gemini" in providers:
            self.gemini_row.set_status(providers["gemini"])
