"""Denver System Tray Icon.

Provides background status, overlay test triggers, cockpit launcher,
microphone muting toggle, and clean application termination.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from denver import __version__, assistant_name, product_name
from denver.logging.logger import get_logger
from denver.ui.theme import PRIMARY_CYAN
from denver.ui.widgets.wake_overlay import notify_wake_overlay

logger = get_logger("ui.tray")


def create_tray_pixmap(is_muted: bool = False) -> QPixmap:
    """Generate a clean 32x32 Denver tray icon (cyan normal, amber/red when muted)."""
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    ring_color = QColor("#f87171" if is_muted else PRIMARY_CYAN)
    bg_color = QColor(15, 23, 42)

    # Outer ring
    painter.setPen(ring_color)
    painter.setBrush(bg_color)
    painter.drawEllipse(2, 2, 28, 28)

    # Inner core
    painter.setBrush(ring_color)
    painter.drawEllipse(10, 10, 12, 12)
    painter.end()
    return pixmap


class DenverTrayIcon(QSystemTrayIcon):
    """System tray controller for background and headless Denver operation."""

    def __init__(
        self,
        denver_app: object | None = None,
        on_open_cockpit: Callable[[], None] | None = None,
        on_quit: Callable[[], None] | None = None,
        parent: QObject | None = None,
    ) -> None:
        icon = QIcon(create_tray_pixmap(False))
        super().__init__(icon, parent)
        self.denver_app = denver_app
        self.on_open_cockpit = on_open_cockpit
        self.on_quit = on_quit

        self._is_muted = False
        self._action_mute: QAction | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        self.setIcon(QIcon(create_tray_pixmap(self._is_muted)))
        self.setToolTip(f"{product_name} v{__version__}")

        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: #0F172A;
                color: #F8FAFC;
                border: 1px solid #1E293B;
                padding: 4px;
                font-family: 'Segoe UI', sans-serif;
            }
            QMenu::item {
                padding: 6px 20px 6px 12px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #1E293B;
                color: #22D3EE;
            }
            QMenu::separator {
                height: 1px;
                background-color: #334155;
                margin: 4px 8px;
            }
        """)

        # Title / branding
        title_action = QAction(f"◈ {assistant_name}", menu)
        title_action.setEnabled(False)
        menu.addAction(title_action)
        menu.addSeparator()

        # HUD Overlay Trigger
        test_overlay_action = QAction("Show Overlay (Test)", menu)
        test_overlay_action.triggered.connect(self._trigger_overlay_test)
        menu.addAction(test_overlay_action)

        # Cockpit Window Launcher
        cockpit_action = QAction("Open Cockpit", menu)
        cockpit_action.triggered.connect(self._trigger_open_cockpit)
        menu.addAction(cockpit_action)

        menu.addSeparator()

        # Microphone Mute Toggle
        self._action_mute = QAction("Mute Microphone", menu)
        self._action_mute.triggered.connect(self.toggle_microphone_mute)
        menu.addAction(self._action_mute)

        menu.addSeparator()

        # Clean Exit
        quit_action = QAction("Quit Denver", menu)
        quit_action.triggered.connect(self.request_quit)
        menu.addAction(quit_action)

        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)

    def _trigger_overlay_test(self) -> None:
        """Trigger HUD overlay to show LISTENING state."""
        logger.info("Tray: Manual HUD overlay trigger requested.")
        notify_wake_overlay("LISTENING")

    def _trigger_open_cockpit(self) -> None:
        """Launch or foreground the main Cockpit window."""
        if self.on_open_cockpit:
            self.on_open_cockpit()
        else:
            logger.info("Tray: Open Cockpit requested without custom callback.")

    def toggle_microphone_mute(self) -> bool:
        """Toggle audio capture muting, updating UI and tray icon."""
        pipeline = getattr(self.denver_app, "voice_pipeline", None) if self.denver_app else None
        if pipeline and hasattr(pipeline, "toggle_mute"):
            self._is_muted = pipeline.toggle_mute()
        else:
            self._is_muted = not self._is_muted

        self.update_mute_state(self._is_muted)
        return self._is_muted

    def update_mute_state(self, is_muted: bool) -> None:
        """Update action label and icon to reflect muted state."""
        self._is_muted = is_muted
        if self._action_mute:
            self._action_mute.setText("Unmute Microphone" if is_muted else "Mute Microphone")
        self.setIcon(QIcon(create_tray_pixmap(is_muted)))
        status_txt = "MUTED" if is_muted else "ONLINE"
        self.setToolTip(f"{product_name} v{__version__} ({status_txt})")
        logger.info("Microphone mute state updated: %s", "MUTED" if is_muted else "ACTIVE")

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in {QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick}:
            if self.on_open_cockpit:
                self.on_open_cockpit()
            else:
                notify_wake_overlay("LISTENING")

    def request_quit(self) -> None:
        """Perform clean shutdown across background threads and Qt loop."""
        logger.info("Tray: Clean quit requested.")
        self.hide()
        if self.on_quit:
            try:
                self.on_quit()
            except Exception as exc:
                logger.warning("Error in on_quit callback: %s", exc)

        qapp = QApplication.instance()
        if qapp:
            qapp.quit()
