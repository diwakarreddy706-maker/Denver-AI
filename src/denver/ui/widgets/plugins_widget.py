"""Cyber Plugins Management & Sandboxed Extension Center Widget."""

from __future__ import annotations

from typing import Any

try:
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtWidgets import (
        QFrame,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QScrollArea,
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
    BG_PANEL,
    BG_PANEL_ALT,
    BG_SURFACE,
    BORDER_CYAN,
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


class PluginCardWidget(QFrame):
    """Visual card representing a discovered modular plugin with status and toggle controls."""

    if _PYSIDE_AVAILABLE:
        toggle_requested = Signal(str, bool)

    def __init__(self, data: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.plugin_id = data.get("id", "")
        self.is_enabled = bool(data.get("enabled", True))
        self.setStyleSheet(
            f"background-color: {BG_PANEL}; border: 1px solid {BORDER_SUBTLE}; border-radius: 8px; padding: 6px;"
        )
        self._init_ui(data)

    def _init_ui(self, data: dict[str, Any]) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # 1. Header: Name, Version, ID, Risk Badge, and Toggle Switch Button
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        name_lbl = QLabel(f"🧩 {data.get('name', self.plugin_id)}")
        name_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 700;")
        top_row.addWidget(name_lbl)

        ver_lbl = QLabel(f"v{data.get('version', '1.0.0')}")
        ver_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; font-weight: 600;")
        top_row.addWidget(ver_lbl)

        top_row.addStretch()

        # Risk Level Badge
        risk_level = data.get("max_risk", "LOW").upper()
        risk_color = (
            STATUS_SUCCESS
            if risk_level in {"LOW", "SAFE"}
            else (
                STATUS_WARNING
                if risk_level == "MEDIUM"
                else (STATUS_DANGER if risk_level in {"HIGH", "CRITICAL"} else TEXT_MUTED)
            )
        )
        risk_badge = QLabel(f"RISK: {risk_level}")
        risk_badge.setStyleSheet(
            f"color: {risk_color}; font-size: 9px; font-weight: 700; border: 1px solid {risk_color}; padding: 1px 5px; border-radius: 3px; background-color: rgba(0,0,0,0.3);"
        )
        top_row.addWidget(risk_badge)

        # Toggle Button
        self.toggle_btn = QPushButton("ENABLED" if self.is_enabled else "DISABLED")
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_button_style()
        self.toggle_btn.clicked.connect(self._on_toggle_clicked)
        top_row.addWidget(self.toggle_btn)

        layout.addLayout(top_row)

        # 2. Description & Author
        desc_text = data.get("description", "No description provided.")
        desc_lbl = QLabel(desc_text)
        desc_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; line-height: 1.3;")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        # 3. Permissions row
        perms = data.get("permissions", [])
        if perms:
            perm_row = QHBoxLayout()
            perm_row.setSpacing(4)
            perm_title = QLabel("Permissions:")
            perm_title.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 9px; font-weight: 600;")
            perm_row.addWidget(perm_title)
            for p in perms[:4]:
                p_tag = QLabel(p.lower())
                p_tag.setStyleSheet(
                    f"color: {TEXT_CYAN}; font-size: 8px; font-weight: 700; background-color: rgba(6, 182, 212, 0.1); border: 1px solid rgba(6, 182, 212, 0.3); padding: 1px 4px; border-radius: 3px;"
                )
                perm_row.addWidget(p_tag)
            if len(perms) > 4:
                more_tag = QLabel(f"+{len(perms) - 4} more")
                more_tag.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 8px;")
                perm_row.addWidget(more_tag)
            perm_row.addStretch()
            layout.addLayout(perm_row)

    def _update_button_style(self) -> None:
        if self.is_enabled:
            self.toggle_btn.setText("● ENABLED")
            self.toggle_btn.setStyleSheet(
                f"background-color: rgba(34, 197, 94, 0.15); color: {STATUS_SUCCESS}; border: 1px solid rgba(34, 197, 94, 0.4); border-radius: 4px; padding: 3px 10px; font-size: 10px; font-weight: 700;"
            )
        else:
            self.toggle_btn.setText("○ DISABLED")
            self.toggle_btn.setStyleSheet(
                f"background-color: rgba(100, 116, 139, 0.15); color: {TEXT_MUTED}; border: 1px solid rgba(100, 116, 139, 0.4); border-radius: 4px; padding: 3px 10px; font-size: 10px; font-weight: 700;"
            )

    def _on_toggle_clicked(self) -> None:
        new_state = not self.is_enabled
        self.is_enabled = new_state
        self._update_button_style()
        if hasattr(self, "toggle_requested"):
            self.toggle_requested.emit(self.plugin_id, new_state)


class PluginsWidget(QWidget):
    """Main Widget for managing Denver Modular Plugins & Extensions."""

    if _PYSIDE_AVAILABLE:
        plugin_toggled = Signal(str, bool)
        reload_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        if not _PYSIDE_AVAILABLE:
            return

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 6, 4, 4)
        main_layout.setSpacing(6)

        # Header Bar
        header_row = QHBoxLayout()
        header_row.setContentsMargins(4, 2, 4, 2)
        header_row.setSpacing(8)

        title_lbl = QLabel("MODULAR PLUGINS & EXTENSIONS")
        title_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 11px; font-weight: 800; letter-spacing: 1px;")
        header_row.addWidget(title_lbl)

        self.count_badge = QLabel("0 Installed")
        self.count_badge.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; font-weight: 600;")
        header_row.addWidget(self.count_badge)

        header_row.addStretch()

        self.reload_btn = QPushButton("🔄 RELOAD")
        self.reload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reload_btn.setStyleSheet(
            f"background-color: {BG_PANEL}; color: {PRIMARY_CYAN}; border: 1px solid rgba(6, 182, 212, 0.4); border-radius: 4px; padding: 3px 8px; font-size: 10px; font-weight: 700;"
        )
        self.reload_btn.clicked.connect(self._on_reload_clicked)
        header_row.addWidget(self.reload_btn)

        main_layout.addLayout(header_row)

        # Scroll Area for plugin cards
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

        self.scroll_area.setWidget(self.container)
        main_layout.addWidget(self.scroll_area, stretch=1)

    def update_plugins(self, plugins_list: list[dict[str, Any]]) -> None:
        """Render discovered plugins list."""
        if not _PYSIDE_AVAILABLE:
            return

        # Clear existing items
        while self.list_layout.count() > 0:
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.count_badge.setText(f"{len(plugins_list)} Installed")

        if not plugins_list:
            empty_lbl = QLabel("No plugins discovered in plugins/ directory.\nAdd plugins with manifest.json to extend Denver.")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; padding: 20px;")
            self.list_layout.addWidget(empty_lbl)
            self.list_layout.addStretch()
            return

        for p_data in plugins_list:
            card = PluginCardWidget(p_data, self.container)
            card.toggle_requested.connect(self._on_card_toggled)
            self.list_layout.addWidget(card)

        self.list_layout.addStretch()

    def _on_card_toggled(self, plugin_id: str, enabled: bool) -> None:
        if hasattr(self, "plugin_toggled"):
            self.plugin_toggled.emit(plugin_id, enabled)

    def _on_reload_clicked(self) -> None:
        if hasattr(self, "reload_requested"):
            self.reload_requested.emit()
