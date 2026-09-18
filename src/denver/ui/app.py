"""Denver Cockpit Application & System Tray Lifecycle Orchestrator."""

from __future__ import annotations

import asyncio
import sys
import threading
import time
from typing import Any

try:
    from PySide6.QtCore import QObject, Qt, QTimer
    from PySide6.QtGui import QAction, QColor, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
    from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon
    _PYSIDE_AVAILABLE = True
except ImportError:
    _PYSIDE_AVAILABLE = False
    QApplication = object  # type: ignore

from denver import __version__, assistant_name, product_name
from denver.app.application import DenverApplication
from denver.logging.logger import get_logger
from denver.ui.controller import QtEventBridge, UIController
from denver.ui.theme import BG_ROOT, COCKPIT_STYLESHEET, PRIMARY_CYAN
from denver.ui.window import MainWindow

logger = get_logger("ui.app")


def _create_tray_pixmap() -> QPixmap:
    """Generate a clean 32x32 cyber cyan Denver tray icon."""
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Outer cyan ring
    painter.setPen(QColor(PRIMARY_CYAN))
    painter.setBrush(QColor(15, 23, 42))
    painter.drawEllipse(2, 2, 28, 28)

    # Inner cyan core
    painter.setBrush(QColor(PRIMARY_CYAN))
    painter.drawEllipse(10, 10, 12, 12)
    painter.end()
    return pixmap


class DenverCockpitApp:
    """Coordinates QApplication lifecycle, main window, system tray, and async backend thread."""

    def __init__(self, denver_app: DenverApplication | None = None) -> None:
        self.denver_app = denver_app or DenverApplication()
        self.qapp: QApplication | None = None
        self.window: MainWindow | None = None
        self.controller: UIController | None = None
        self.tray_icon: QSystemTrayIcon | None = None
        self._async_loop: asyncio.AbstractEventLoop | None = None
        self._backend_thread: threading.Thread | None = None
        self._is_shutting_down = False

    def initialize_qt(self) -> None:
        """Initialize Qt Application, bridge, controller, and main window."""
        if not _PYSIDE_AVAILABLE:
            logger.warning("PySide6 is not available; graphical interface cannot be initialized.")
            return

        if not QApplication.instance():
            self.qapp = QApplication(sys.argv)
        else:
            self.qapp = QApplication.instance()

        self.qapp.setApplicationName(product_name)
        self.qapp.setApplicationVersion(__version__)
        self.qapp.setStyleSheet(COCKPIT_STYLESHEET)

        # Start backend asyncio event loop in dedicated background thread
        self._start_backend_thread()

        # Initialize UI Controller & Bridge
        bridge = QtEventBridge()
        self.controller = UIController(
            app_instance=self.denver_app,
            bridge=bridge,
            event_loop=self._async_loop,
        )

        # Create Main Window
        self.window = MainWindow(controller=self.controller)

        # Setup System Tray
        self._setup_system_tray()

        # Setup Global Hotkey shortcut (Ctrl+Shift+D)
        self._setup_shortcuts()

        # Handle Qt app quit
        self.qapp.aboutToQuit.connect(self._on_app_about_to_quit)

    def _start_backend_thread(self) -> None:
        """Run Denver backend async lifecycle in a background thread."""
        ready_event = threading.Event()

        def _worker() -> None:
            self._async_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._async_loop)
            ready_event.set()

            # Start Denver application inside this loop
            self._async_loop.run_until_complete(self.denver_app.start())
            try:
                self._async_loop.run_forever()
            finally:
                # Cleanup loop
                self._async_loop.close()

        self._backend_thread = threading.Thread(target=_worker, name="DenverBackendAsync", daemon=True)
        self._backend_thread.start()
        ready_event.wait(timeout=5.0)

    def _setup_system_tray(self) -> None:
        if not _PYSIDE_AVAILABLE or not QSystemTrayIcon.isSystemTrayAvailable():
            logger.debug("System tray is not available on this platform.")
            return

        tray_icon_img = QIcon(_create_tray_pixmap())
        self.tray_icon = QSystemTrayIcon(tray_icon_img, self.qapp)
        self.tray_icon.setToolTip(f"{product_name} v{__version__}")

        # Tray Context Menu
        menu = QMenu()
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: #0F172A;
                color: #F8FAFC;
                border: 1px solid #1E293B;
                padding: 4px;
            }}
            QMenu::item:selected {{
                background-color: #3B82F6;
            }}
        """)

        title_action = QAction(f"◈ {assistant_name} Cockpit", menu)
        title_action.setEnabled(False)
        menu.addAction(title_action)
        menu.addSeparator()

        show_action = QAction("Open Cockpit", menu)
        show_action.triggered.connect(self.show_window)
        menu.addAction(show_action)

        hide_action = QAction("Hide to Tray", menu)
        hide_action.triggered.connect(self.hide_window)
        menu.addAction(hide_action)

        menu.addSeparator()

        status_action = QAction("System Status", menu)
        status_action.triggered.connect(self._show_tray_status)
        menu.addAction(status_action)

        settings_action = QAction("Settings", menu)
        settings_action.triggered.connect(lambda: self.window._open_settings() if self.window else None)
        menu.addAction(settings_action)

        menu.addSeparator()

        exit_action = QAction("Exit Denver", menu)
        exit_action.triggered.connect(self.shutdown)
        menu.addAction(exit_action)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in {QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick}:
            if self.window:
                if self.window.isVisible() and not self.window.isMinimized():
                    self.window.hide()
                else:
                    self.show_window()

    def _show_tray_status(self) -> None:
        if self.tray_icon:
            st = self.denver_app.state_machine.current_state.value.upper()
            self.tray_icon.showMessage(
                product_name,
                f"Status: {st}\nUptime: {self.denver_app.health_service.uptime_seconds:.0f}s",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )

    def _setup_shortcuts(self) -> None:
        if self.window and _PYSIDE_AVAILABLE:
            shortcut = QShortcut(QKeySequence("Ctrl+Shift+D"), self.window)
            shortcut.activated.connect(self.toggle_window)

    def show_window(self) -> None:
        if self.window:
            self.window.showNormal()
            self.window.raise_()
            self.window.activateWindow()

    def hide_window(self) -> None:
        if self.window:
            self.window.hide()

    def toggle_window(self) -> None:
        if self.window:
            if self.window.isVisible() and not self.window.isMinimized():
                self.window.hide()
            else:
                self.show_window()

    def _on_app_about_to_quit(self) -> None:
        self.shutdown()

    def shutdown(self) -> None:
        """Perform graceful shutdown of backend and Qt GUI."""
        if self._is_shutting_down:
            return
        self._is_shutting_down = True
        logger.info("Gracefully shutting down Denver Cockpit...")

        # Hide tray and window
        if self.tray_icon:
            self.tray_icon.hide()
        if self.window:
            self.window.hide()

        # Stop Denver backend asynchronously
        if self._async_loop and self._async_loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                self.denver_app.stop(reason="gui_exit"),
                self._async_loop,
            )
            try:
                future.result(timeout=5.0)
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("Error stopping backend during GUI shutdown: %s", exc)

            # Stop loop
            self._async_loop.call_soon_threadsafe(self._async_loop.stop)

        if self.qapp:
            self.qapp.quit()

    def run(self) -> int:
        """Run the Qt event loop."""
        self.initialize_qt()
        self.show_window()
        if self.qapp:
            return self.qapp.exec()
        return 0
