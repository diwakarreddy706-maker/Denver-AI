"""Persistent Memory & SQLite Database Status Widget (Phase 7)."""

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
    TEXT_CYAN,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


class MemoryStatusWidget(QFrame):
    """Subsystem status widget for Denver Persistent Memory, SQLite DB, & Semantic Embeddings."""

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

        header_lbl = QLabel("DENVER MEMORY & INTELLIGENCE")
        header_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px; font-weight: 700; letter-spacing: 1.2px;")
        layout.addWidget(header_lbl)

        # Row 1: DB Status + WAL + Privacy
        row1 = QHBoxLayout()
        row1.setSpacing(4)
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {STATUS_SUCCESS}; font-size: 9px;")
        row1.addWidget(dot)

        self.db_label = QLabel("SQLite Ready (WAL)")
        self.db_label.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 10px; font-weight: 600;")
        row1.addWidget(self.db_label)
        row1.addStretch()

        self.semantic_label = QLabel("SEMANTIC: READY")
        self.semantic_label.setStyleSheet(f"color: {TEXT_CYAN}; font-size: 9px; font-weight: 700;")
        row1.addWidget(self.semantic_label)

        self.privacy_label = QLabel("PRIVACY: OFF")
        self.privacy_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 9px; font-weight: 700;")
        row1.addWidget(self.privacy_label)
        layout.addLayout(row1)

        # Row 2: Counts (Memories, Notes, Tasks)
        row2 = QHBoxLayout()
        row2.setSpacing(8)

        self.mem_count_lbl = QLabel("0 Memories")
        self.mem_count_lbl.setStyleSheet(f"color: {TEXT_CYAN}; font-size: 10px; font-weight: 600;")
        row2.addWidget(self.mem_count_lbl)

        self.notes_count_lbl = QLabel("0 Notes")
        self.notes_count_lbl.setStyleSheet(f"color: {TEXT_CYAN}; font-size: 10px; font-weight: 600;")
        row2.addWidget(self.notes_count_lbl)

        self.tasks_count_lbl = QLabel("0 Tasks")
        self.tasks_count_lbl.setStyleSheet(f"color: {TEXT_CYAN}; font-size: 10px; font-weight: 600;")
        row2.addWidget(self.tasks_count_lbl)

        row2.addStretch()
        layout.addLayout(row2)

    def update_memory(self, memory_data: dict[str, Any]) -> None:
        if not _PYSIDE_AVAILABLE:
            return
        if "memories_count" in memory_data or "total_memories" in memory_data:
            count = memory_data.get("active_memories", memory_data.get("memories_count", memory_data.get("total_memories", 0)))
            self.mem_count_lbl.setText(f"{count} Memories")
        if "notes_count" in memory_data:
            self.notes_count_lbl.setText(f"{memory_data['notes_count']} Notes")
        if "tasks_count" in memory_data:
            self.tasks_count_lbl.setText(f"{memory_data['tasks_count']} Tasks")
        if "privacy_mode" in memory_data:
            p_text = "PRIVACY: ON" if memory_data["privacy_mode"] else "PRIVACY: OFF"
            self.privacy_label.setText(p_text)
            self.privacy_label.setStyleSheet(
                f"color: {'#38BDF8' if memory_data['privacy_mode'] else TEXT_MUTED}; font-size: 9px; font-weight: 700;"
            )
        if "semantic_enabled" in memory_data:
            provider_str = memory_data.get("embedding_provider", "lexical")
            if memory_data["semantic_enabled"]:
                self.semantic_label.setText(f"SEMANTIC: ON ({provider_str})")
                self.semantic_label.setStyleSheet(f"color: {TEXT_CYAN}; font-size: 9px; font-weight: 700;")
            else:
                self.semantic_label.setText("SEMANTIC: OFF")
                self.semantic_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 9px; font-weight: 700;")
