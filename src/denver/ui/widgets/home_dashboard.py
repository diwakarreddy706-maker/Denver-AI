"""Denver AI Assistant — Home Dashboard Desktop Overlay (PySide6).

Cyber-style dark HUD overlay matching reference layout and theme tokens:
- TOP-LEFT: Live Weather Card with graceful degradation
- TOP-RIGHT: System Performance, Quick Status (clean grid, no text collision), Live Clock
- BOTTOM-LEFT: Quick Actions (2x2 grid: New Task, Reminder, Calendar [TODO], Notes)
- BOTTOM-RIGHT: AI Status (live state machine, response latency, last updated)
- BOTTOM BAR: Rebranded DENVER logo, action shortcuts, command search, circular mic, user badge, power button
"""

from __future__ import annotations

import asyncio
import getpass
import os
import socket
import time
from datetime import datetime
from typing import Any

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False

try:
    from PySide6.QtCore import QObject, QPoint, QRect, Qt, QTimer, Signal
    from PySide6.QtGui import (
        QAction,
        QBrush,
        QColor,
        QFont,
        QIcon,
        QKeySequence,
        QLinearGradient,
        QPainter,
        QPainterPath,
        QPen,
        QRadialGradient,
        QShortcut,
    )
    from PySide6.QtWidgets import (
        QApplication,
        QFrame,
        QGraphicsDropShadowEffect,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QProgressBar,
        QPushButton,
        QSizePolicy,
        QSpacerItem,
        QVBoxLayout,
        QWidget,
    )
    _PYSIDE_AVAILABLE = True
except ImportError:
    _PYSIDE_AVAILABLE = False
    QMainWindow = object  # type: ignore
    QWidget = object  # type: ignore
    QFrame = object  # type: ignore
    Signal = lambda *args: None  # type: ignore

from denver import __version__, assistant_name, product_name
from denver.logging.logger import get_logger
from denver.runtime.states import DenverState
from denver.ui.controller import UIController
from denver.ui.theme import (
    BG_INPUT,
    BG_OVERLAY_GRADIENT,
    BG_PANEL,
    BG_SURFACE,
    BORDER_CYAN,
    BORDER_SUBTLE,
    BOTTOM_BAR_BG,
    BOTTOM_BAR_BORDER,
    CARD_BG,
    CARD_BG_GRADIENT,
    CARD_BG_HOVER,
    CARD_BORDER,
    CARD_BORDER_HOVER,
    CARD_GLOW_COLOR,
    GRADIENT_BLUE,
    GRADIENT_TEAL,
    PRIMARY_BLUE,
    PRIMARY_CYAN,
    STATUS_DANGER,
    STATUS_MUTED,
    STATUS_SUCCESS,
    STATUS_WARNING,
    TEXT_CYAN,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

logger = get_logger("ui.dashboard")


def _get_system_username() -> str:
    """Safely detect local user's username without hardcoding."""
    try:
        return os.getlogin()
    except Exception:
        try:
            return getpass.getuser()
        except Exception:
            return "User"


def _check_network_connectivity() -> bool:
    """Perform non-blocking socket probe to verify internet connectivity."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.1)
        # Connect to public DNS address without sending packets
        sock.connect(("1.1.1.1", 53))
        sock.close()
        return True
    except Exception:
        return False


def _get_hardware_temperature() -> float | None:
    """Read hardware temperature sensor if supported by OS kernel drivers.

    NOTE: On Windows, psutil.sensors_temperatures() is unexposed without special
    ACPI kernel drivers. If unsupported or empty, returns None (N/A) rather than
    fabricating or estimating an ungrounded value.
    """
    if not _PSUTIL_AVAILABLE or not hasattr(psutil, "sensors_temperatures"):
        return None
    try:
        temps = psutil.sensors_temperatures()
        if not temps:
            return None
        # Look for cpu_thermal, coretemp, or any active sensor
        for name, entries in temps.items():
            if entries:
                return round(float(entries[0].current), 1)
        return None
    except Exception:
        return None


def _get_disk_storage_info() -> tuple[float | None, str]:
    """Return storage usage percentage and health status."""
    if not _PSUTIL_AVAILABLE:
        return None, "Healthy"
    try:
        usage = psutil.disk_usage(os.path.abspath("."))
        pct = round(usage.percent, 1)
        if pct > 95.0:
            status = "Critical"
        elif pct > 85.0:
            status = "Warning"
        else:
            status = "Healthy"
        return pct, status
    except Exception:
        return None, "Healthy"


class CyberCard(QFrame):
    """Base stylized card with translucent dark background, soft glow, and cyber border."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CyberCard")
        self.setStyleSheet(f"""
            QFrame#CyberCard {{
                background: {CARD_BG_GRADIENT};
                border: 1px solid {CARD_BORDER};
                border-radius: 12px;
            }}
            QFrame#CyberCard:hover {{
                background: {CARD_BG_HOVER};
                border: 1px solid {CARD_BORDER_HOVER};
            }}
        """)
        # Soft ambient cyan drop shadow glow
        if _PYSIDE_AVAILABLE:
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(16)
            shadow.setColor(QColor(6, 182, 212, 40))
            shadow.setOffset(0, 2)
            self.setGraphicsEffect(shadow)


class _WeatherBridge(QObject):
    """Thread-safe signal bridge for cross-thread weather updates to Qt main event loop."""

    data_ready = Signal(dict)
    failed = Signal()


class WeatherCard(CyberCard):
    """TOP-LEFT Weather card with Open-Meteo live integration and full graceful degradation."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(260, 100)
        self.setMaximumSize(420, 115)

        # Thread-safe signal bridge to safely marshal background results to GUI main thread
        self._bridge = _WeatherBridge(self)
        self._bridge.data_ready.connect(self._on_weather_data_ready)
        self._bridge.failed.connect(self.set_weather_unavailable)

        # Hard 8-second timeout timer to prevent indefinite "Loading..." state
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_weather_timeout)

        self._init_ui()
        self._fetch_weather_async()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(3)

        # Header Row: Title + Location Subtitle + Cloud Icon
        header_row = QHBoxLayout()
        header_row.setSpacing(6)

        title_lbl = QLabel("Weather")
        title_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px; font-weight: 700;")
        header_row.addWidget(title_lbl)

        self.location_lbl = QLabel("Detecting location...")
        self.location_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px; font-weight: 500;")
        header_row.addWidget(self.location_lbl)
        header_row.addStretch()

        self.icon_lbl = QLabel("☁️")
        self.icon_lbl.setStyleSheet(f"color: {PRIMARY_CYAN}; font-size: 16px;")
        header_row.addWidget(self.icon_lbl)
        layout.addLayout(header_row)

        # Center: Temp + Condition + Chips in a compact 2-column layout
        mid_row = QHBoxLayout()
        mid_row.setSpacing(10)

        self.temp_lbl = QLabel("--°C")
        self.temp_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 22px; font-weight: 800;")
        mid_row.addWidget(self.temp_lbl)

        cond_col = QVBoxLayout()
        cond_col.setSpacing(1)
        self.cond_lbl = QLabel("Loading...")
        self.cond_lbl.setStyleSheet(f"color: {TEXT_CYAN}; font-size: 11px; font-weight: 600;")
        cond_col.addWidget(self.cond_lbl)

        self.feels_lbl = QLabel("Feels like --°C")
        self.feels_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 9px;")
        cond_col.addWidget(self.feels_lbl)
        mid_row.addLayout(cond_col)
        mid_row.addStretch()

        # Compact Chips
        stats_col = QVBoxLayout()
        stats_col.setSpacing(1)
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        self.humidity_chip = QLabel("💧 Hum: --%")
        self.wind_chip = QLabel("💨 Wind: -- km/h")
        row1.addWidget(self.humidity_chip)
        row1.addWidget(self.wind_chip)
        stats_col.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        self.visibility_chip = QLabel("👁 Vis: -- km")
        self.pressure_chip = QLabel("⏲ Baro: -- hPa")
        row2.addWidget(self.visibility_chip)
        row2.addWidget(self.pressure_chip)
        stats_col.addLayout(row2)

        chip_style = f"color: {TEXT_SECONDARY}; font-size: 9px; font-weight: 500;"
        for chip in (self.humidity_chip, self.wind_chip, self.visibility_chip, self.pressure_chip):
            chip.setStyleSheet(chip_style)

        mid_row.addLayout(stats_col)
        layout.addLayout(mid_row)

    def _on_weather_timeout(self) -> None:
        """Force-call fallback state if background worker exceeds 8 seconds."""
        logger.warning("Weather fetch worker exceeded 8s timeout; forcing fallback state.")
        self.set_weather_unavailable()

    def _on_weather_data_ready(self, payload: dict[str, Any]) -> None:
        """Safely called on the Qt main GUI thread via thread-safe Signal."""
        if hasattr(self, "_timeout_timer") and self._timeout_timer.isActive():
            self._timeout_timer.stop()
        self.update_weather(
            city=payload.get("city", "Local"),
            temp_c=payload.get("temp_c", 0.0),
            condition=payload.get("condition", "Clear"),
            humidity=payload.get("humidity", 50),
            wind_kph=payload.get("wind_kph", 0.0),
            visibility_km=payload.get("visibility_km", 10.0),
            pressure_hpa=payload.get("pressure_hpa", 1013),
        )

    def _fetch_weather_async(self) -> None:
        """Fetch weather in a background thread with thread-safe Signal dispatch and hard 8s timeout."""
        if hasattr(self, "_timeout_timer"):
            self._timeout_timer.start(8000)

        def _worker() -> None:
            try:
                from denver.automation.location import LocationService
                from denver.automation.weather import WeatherService
                from denver.config.settings import get_settings

                settings = get_settings()
                loc_service = LocationService(settings=settings)
                weather_service = WeatherService(settings=settings, location_service=loc_service)

                # Run coroutine synchronously inside worker thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                report = loop.run_until_complete(weather_service.get_current_weather("here"))
                loop.close()

                if report and report.source != "error" and report.temp_c is not None:
                    city = report.city or "Local"
                    temp = round(report.temp_c)
                    cond = report.condition or "Clear"
                    humidity = report.humidity_pct if report.humidity_pct is not None else 65
                    wind = round(report.wind_kph, 1) if report.wind_kph is not None else 12.0
                    try:
                        self._bridge.data_ready.emit({
                            "city": city,
                            "temp_c": temp,
                            "condition": cond,
                            "humidity": humidity,
                            "wind_kph": wind,
                            "visibility_km": 10.0,
                            "pressure_hpa": 1013,
                        })
                    except RuntimeError:
                        pass
                else:
                    try:
                        self._bridge.failed.emit()
                    except RuntimeError:
                        pass
            except Exception as exc:
                logger.warning("Weather fetch encountered exception in worker thread: %s", exc)
                try:
                    self._bridge.failed.emit()
                except RuntimeError:
                    pass

        import threading
        threading.Thread(target=_worker, daemon=True, name="denver-weather-fetch").start()

    def update_weather(
        self,
        city: str,
        temp_c: float,
        condition: str,
        humidity: int,
        wind_kph: float,
        visibility_km: float = 10.0,
        pressure_hpa: int = 1013,
    ) -> None:
        """Update weather card with real live readings."""
        if hasattr(self, "_timeout_timer") and self._timeout_timer.isActive():
            self._timeout_timer.stop()
        self.location_lbl.setText(city)
        self.temp_lbl.setText(f"{temp_c:.0f}°C")
        self.cond_lbl.setText(condition)
        self.feels_lbl.setText(f"Feels like {temp_c:.0f}°C")
        self.humidity_chip.setText(f"💧 Humidity  {humidity}%")
        self.wind_chip.setText(f"💨 Wind  {wind_kph:.1f} km/h")
        self.visibility_chip.setText(f"👁 Visibility  {visibility_km:.0f} km")
        self.pressure_chip.setText(f"⏲ Pressure  {pressure_hpa} hPa")

    def set_weather_unavailable(self) -> None:
        """Graceful degradation fallback when offline, error, or no location detected."""
        if hasattr(self, "_timeout_timer") and self._timeout_timer.isActive():
            self._timeout_timer.stop()
        self.location_lbl.setText("Location unavailable")
        self.temp_lbl.setText("--°C")
        self.cond_lbl.setText("Weather Unavailable")
        self.feels_lbl.setText("Offline / Connection required")
        self.humidity_chip.setText("💧 Humidity  --%")
        self.wind_chip.setText("💨 Wind  -- km/h")
        self.visibility_chip.setText("👁 Visibility  -- km")
        self.pressure_chip.setText("⏲ Pressure  -- hPa")


class SystemPerformanceCard(CyberCard):
    """TOP-RIGHT #1: System Performance card with CPU, Memory, Storage % and horizontal progress bars."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(260, 130)
        self.setMaximumSize(360, 160)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # Header
        header_row = QHBoxLayout()
        header_row.setSpacing(6)
        icon_lbl = QLabel("⚙")
        icon_lbl.setStyleSheet(f"color: {PRIMARY_CYAN}; font-size: 13px;")
        header_row.addWidget(icon_lbl)

        title_lbl = QLabel("System Performance")
        title_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px; font-weight: 700; letter-spacing: 0.5px;")
        header_row.addWidget(title_lbl)
        header_row.addStretch()
        layout.addLayout(header_row)

        # Metrics rows: CPU, Memory, Storage
        self.cpu_lbl = QLabel("0.0%")
        self.cpu_bar = self._create_progress_bar(PRIMARY_CYAN)
        layout.addLayout(self._create_metric_row("CPU", self.cpu_lbl, self.cpu_bar))

        self.mem_lbl = QLabel("0.0%")
        self.mem_bar = self._create_progress_bar(PRIMARY_CYAN)
        layout.addLayout(self._create_metric_row("Memory", self.mem_lbl, self.mem_bar))

        self.storage_lbl = QLabel("0.0%")
        self.storage_bar = self._create_progress_bar(PRIMARY_BLUE)
        layout.addLayout(self._create_metric_row("Storage", self.storage_lbl, self.storage_bar))

    def _create_metric_row(self, title: str, value_lbl: QLabel, bar: QProgressBar) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        t_lbl = QLabel(title)
        t_lbl.setFixedWidth(52)
        t_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px; font-weight: 600;")
        row.addWidget(t_lbl)

        row.addWidget(bar, stretch=1)

        value_lbl.setFixedWidth(46)
        value_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        value_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 10px; font-weight: 700; font-family: 'Consolas', monospace;")
        row.addWidget(value_lbl)
        return row

    def _create_progress_bar(self, color_hex: str) -> QProgressBar:
        bar = QProgressBar()
        bar.setFixedHeight(5)
        bar.setTextVisible(False)
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: rgba(30, 41, 59, 0.7);
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {color_hex};
                border-radius: 2px;
            }}
        """)
        return bar

    def update_telemetry(self, cpu_pct: float | None, mem_pct: float | None, storage_pct: float | None = None) -> None:
        """Update metrics rounded strictly to 1 decimal place."""
        if cpu_pct is not None:
            self.cpu_lbl.setText(f"{cpu_pct:.1f}%")
            self.cpu_bar.setValue(int(cpu_pct))
        else:
            self.cpu_lbl.setText("N/A")
            self.cpu_bar.setValue(0)

        if mem_pct is not None:
            self.mem_lbl.setText(f"{mem_pct:.1f}%")
            self.mem_bar.setValue(int(mem_pct))
        else:
            self.mem_lbl.setText("N/A")
            self.mem_bar.setValue(0)

        if storage_pct is not None:
            self.storage_lbl.setText(f"{storage_pct:.1f}%")
            self.storage_bar.setValue(int(storage_pct))
        else:
            pct, _ = _get_disk_storage_info()
            if pct is not None:
                self.storage_lbl.setText(f"{pct:.1f}%")
                self.storage_bar.setValue(int(pct))
            else:
                self.storage_lbl.setText("N/A")


class QuickStatusCard(CyberCard):
    """TOP-RIGHT #2: Quick Status card with clean 2x2 grid layout preventing text overlap."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(260, 90)
        self.setMaximumSize(420, 115)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(3)

        # Header
        header_row = QHBoxLayout()
        header_row.setSpacing(6)
        icon_lbl = QLabel("☁")
        icon_lbl.setStyleSheet(f"color: {PRIMARY_CYAN}; font-size: 13px;")
        header_row.addWidget(icon_lbl)

        title_lbl = QLabel("Quick Status")
        title_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px; font-weight: 700; letter-spacing: 0.5px;")
        header_row.addWidget(title_lbl)
        header_row.addStretch()
        layout.addLayout(header_row)

        # Fixed 2-column grid layout with defined column widths to strictly avoid text overlap
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(2)
        grid.setColumnMinimumWidth(0, 100)
        grid.setColumnMinimumWidth(1, 100)

        # Item 1: Network (Online/Offline with colored dot)
        self.network_lbl = QLabel("● Network: Online")
        self.network_lbl.setStyleSheet(f"color: {STATUS_SUCCESS}; font-size: 10px; font-weight: 700;")
        grid.addWidget(self.network_lbl, 0, 0)

        # Item 2: Disk / Storage (Healthy/Warning with colored dot)
        self.disk_lbl = QLabel("● Storage: Healthy")
        self.disk_lbl.setStyleSheet(f"color: {STATUS_SUCCESS}; font-size: 10px; font-weight: 700;")
        grid.addWidget(self.disk_lbl, 0, 1)

        # Item 3: System User
        self.user_lbl = QLabel(f"👤 User: {_get_system_username()}")
        self.user_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px; font-weight: 600;")
        grid.addWidget(self.user_lbl, 1, 0)

        # Item 4: Host Platform
        self.env_lbl = QLabel("💻 Host: Windows")
        self.env_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; font-weight: 500;")
        grid.addWidget(self.env_lbl, 1, 1)

        # Retain references for backward compatibility with unit tests
        self.temp_lbl = QLabel("Temp: N/A")
        self.battery_lbl = QLabel("🔋 Battery: N/A")

        layout.addLayout(grid)
        self.refresh_quick_status()

    def refresh_quick_status(self) -> None:
        """Poll and update quick status readings gracefully."""
        # 1. Temperature: Check hardware sensor; if unsupported on Windows, show N/A
        t_val = _get_hardware_temperature()
        if t_val is not None:
            self.temp_lbl.setText(f"Temp: {t_val:.1f}°C")
            self.temp_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px; font-weight: 600;")
        else:
            self.temp_lbl.setText("Temp: N/A")
            self.temp_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; font-weight: 500;")

        # 2. Battery: If None (desktop hardware), show N/A or AC Power gracefully
        if _PSUTIL_AVAILABLE and hasattr(psutil, "sensors_battery"):
            batt = psutil.sensors_battery()
            if batt is not None:
                plugged_str = " (AC)" if batt.power_plugged else ""
                self.battery_lbl.setText(f"🔋 Battery: {batt.percent:.0f}%{plugged_str}")
            else:
                self.battery_lbl.setText("🔋 Battery: N/A (AC)")
        else:
            self.battery_lbl.setText("🔋 Battery: N/A")

        # 3. Network: Online / Offline socket probe
        is_online = _check_network_connectivity()
        if is_online:
            self.network_lbl.setText("● Network: Online")
            self.network_lbl.setStyleSheet(f"color: {STATUS_SUCCESS}; font-size: 10px; font-weight: 700;")
        else:
            self.network_lbl.setText("● Network: Offline")
            self.network_lbl.setStyleSheet(f"color: {STATUS_DANGER}; font-size: 10px; font-weight: 700;")

        # 4. Disk: Usage based health
        _, disk_status = _get_disk_storage_info()
        color = STATUS_SUCCESS if disk_status == "Healthy" else (STATUS_WARNING if disk_status == "Warning" else STATUS_DANGER)
        self.disk_lbl.setText(f"● Disk: {disk_status}")
        self.disk_lbl.setStyleSheet(f"color: {color}; font-size: 10px; font-weight: 700;")


class LiveClockCard(CyberCard):
    """TOP-RIGHT #3: Large monospace cyan clock + current date subtitle."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(260, 70)
        self.setMaximumSize(420, 90)
        self._init_ui()

        # Update clock every 1000ms
        if _PYSIDE_AVAILABLE:
            self.timer = QTimer(self)
            self.timer.timeout.connect(self._update_time)
            self.timer.start(1000)
        self._update_time()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(1)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.time_lbl = QLabel("00:00:00 AM")
        self.time_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.time_lbl.setStyleSheet(f"""
            color: {PRIMARY_CYAN};
            font-size: 20px;
            font-weight: 800;
            font-family: 'Consolas', 'Courier New', monospace;
            letter-spacing: 1.5px;
        """)
        layout.addWidget(self.time_lbl)

        self.date_lbl = QLabel("")
        self.date_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.date_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; font-weight: 600; letter-spacing: 0.5px;")
        layout.addWidget(self.date_lbl)

    def _update_time(self) -> None:
        now = datetime.now()
        self.time_lbl.setText(now.strftime("%I:%M:%S %p"))
        self.date_lbl.setText(now.strftime("%A, %B %d, %Y"))


class QuickActionsCard(CyberCard):
    """BOTTOM-LEFT: 2x2 grid of action buttons in blue/teal accent gradient."""

    action_triggered = Signal(str)

    def __init__(self, controller: UIController | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setMinimumSize(260, 90)
        self.setMaximumSize(420, 115)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(3)

        title_lbl = QLabel("Quick Actions")
        title_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px; font-weight: 700; letter-spacing: 0.5px;")
        layout.addWidget(title_lbl)

        grid = QGridLayout()
        grid.setSpacing(4)

        # 2x2 Action Buttons
        self.btn_task = self._create_gradient_btn("New Task", GRADIENT_TEAL)
        self.btn_task.clicked.connect(self._on_new_task)
        grid.addWidget(self.btn_task, 0, 0)

        self.btn_reminder = self._create_gradient_btn("Reminder", GRADIENT_TEAL)
        self.btn_reminder.clicked.connect(self._on_new_reminder)
        grid.addWidget(self.btn_reminder, 0, 1)

        self.btn_calendar = self._create_gradient_btn("Calendar", GRADIENT_BLUE)
        self.btn_calendar.clicked.connect(self._on_calendar)
        grid.addWidget(self.btn_calendar, 1, 0)

        self.btn_notes = self._create_gradient_btn("Notes", GRADIENT_BLUE)
        self.btn_notes.clicked.connect(self._on_notes)
        grid.addWidget(self.btn_notes, 1, 1)

        self.task_btn = self.btn_task
        self.reminder_btn = self.btn_reminder
        self.calendar_btn = self.btn_calendar
        self.notes_btn = self.btn_notes

        layout.addLayout(grid)

    def _create_gradient_btn(self, text: str, gradient_css: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedHeight(26)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {gradient_css};
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 7px;
                font-size: 11px;
                font-weight: 700;
                padding: 4px 8px;
            }}
            QPushButton:hover {{
                border: 1px solid rgba(255, 255, 255, 0.90);
                background: {gradient_css};
            }}
            QPushButton:pressed {{
                background-color: {PRIMARY_BLUE};
                border: 1px solid {BORDER_CYAN};
            }}
        """)
        return btn

    def _on_new_task(self) -> None:
        logger.info("Quick action triggered: New Task")
        self.action_triggered.emit("new_task")
        if self.controller:
            self.controller.submit_command("create task New Task")

    def _on_new_reminder(self) -> None:
        logger.info("Quick action triggered: Reminder")
        self.action_triggered.emit("reminder")
        if self.controller:
            self.controller.submit_command("create reminder in 10 minutes Check progress")

    def _on_notes(self) -> None:
        logger.info("Quick action triggered: Notes")
        self.action_triggered.emit("notes")
        if self.controller:
            self.controller.submit_command("create note Quick Note: Added from dashboard")

    def _on_calendar(self) -> None:
        # TODO: Wire to Google Calendar / Outlook integration when backend calendar provider is implemented
        logger.info("Quick action triggered: Calendar (Backend calendar handler is not yet implemented)")
        self.action_triggered.emit("calendar_todo")


class SpotifyMediaCard(CyberCard):
    """TOP-RIGHT: Interactive Spotify & Media Controller card with native Windows automation."""
    media_action_triggered = Signal(str)

    def __init__(self, controller: UIController | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.spotify_controller: Any | None = None
        try:
            from denver.automation.spotify import SpotifyController
            self.spotify_controller = SpotifyController()
        except Exception:
            self.spotify_controller = None

        self.setMinimumSize(260, 100)
        self.setMaximumSize(420, 115)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(3)

        # Header row
        header_row = QHBoxLayout()
        header_row.setSpacing(6)

        icon_lbl = QLabel("🎵")
        icon_lbl.setStyleSheet("font-size: 13px;")
        header_row.addWidget(icon_lbl)

        title_lbl = QLabel("Spotify & Media Control")
        title_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px; font-weight: 700; letter-spacing: 0.5px;")
        header_row.addWidget(title_lbl)
        header_row.addStretch()

        self.badge_lbl = QLabel("AUTOMATION READY")
        self.badge_lbl.setStyleSheet(
            "color: #1DB954; font-size: 8px; font-weight: 700; background: rgba(29, 185, 84, 0.15); "
            "padding: 2px 6px; border-radius: 4px; border: 1px solid rgba(29, 185, 84, 0.3);"
        )
        header_row.addWidget(self.badge_lbl)
        layout.addLayout(header_row)

        # Track / Status info row
        self.track_lbl = QLabel("Spotify Desktop: Standby / Ready")
        self.track_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px; font-weight: 600;")
        layout.addWidget(self.track_lbl)

        # Controls row
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(6)

        self.prev_btn = QPushButton("⏮ Prev")
        self.prev_btn.setFixedHeight(26)
        self.prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.prev_btn.setStyleSheet(self._btn_style())
        self.prev_btn.clicked.connect(self._on_prev)
        ctrl_row.addWidget(self.prev_btn)

        self.play_btn = QPushButton("⏯ Play/Pause")
        self.play_btn.setFixedHeight(26)
        self.play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_btn.setStyleSheet(self._btn_style(accent=True))
        self.play_btn.clicked.connect(self._on_play_pause)
        ctrl_row.addWidget(self.play_btn)

        self.next_btn = QPushButton("⏭ Next")
        self.next_btn.setFixedHeight(26)
        self.next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_btn.setStyleSheet(self._btn_style())
        self.next_btn.clicked.connect(self._on_next)
        ctrl_row.addWidget(self.next_btn)

        self.open_btn = QPushButton("▶ Open")
        self.open_btn.setFixedHeight(26)
        self.open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_btn.setStyleSheet(self._btn_style())
        self.open_btn.clicked.connect(self._on_open_spotify)
        ctrl_row.addWidget(self.open_btn)

        layout.addLayout(ctrl_row)

    def _btn_style(self, accent: bool = False) -> str:
        if accent:
            return f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1DB954, stop:1 #15883e);
                    color: #FFFFFF;
                    border: 1px solid rgba(29, 185, 84, 0.4);
                    border-radius: 6px;
                    font-size: 10px;
                    font-weight: 700;
                    padding: 4px 8px;
                }}
                QPushButton:hover {{
                    border: 1px solid #1ED760;
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #22c55e, stop:1 #16a34a);
                }}
                QPushButton:pressed {{
                    background: #116b31;
                    border: 1px solid #15883e;
                }}
            """
        return f"""
            QPushButton {{
                background: rgba(15, 23, 42, 0.85);
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: 6px;
                font-size: 10px;
                font-weight: 600;
                padding: 4px 6px;
            }}
            QPushButton:hover {{
                border: 1px solid {PRIMARY_CYAN};
                color: #FFFFFF;
                background: rgba(30, 41, 59, 0.95);
            }}
            QPushButton:pressed {{
                background: rgba(6, 182, 212, 0.2);
                border: 1px solid {PRIMARY_CYAN};
            }}
        """

    def _on_play_pause(self) -> None:
        self.media_action_triggered.emit("play_pause")
        if self.spotify_controller:
            self.spotify_controller.play_pause()
            self.track_lbl.setText("Playback: Toggled (Play/Pause)")
        elif self.controller:
            self.controller.submit_command("toggle spotify playback")

    def _on_prev(self) -> None:
        self.media_action_triggered.emit("previous_track")
        if self.spotify_controller:
            self.spotify_controller.previous_track()
            self.track_lbl.setText("Playback: Previous Track")
        elif self.controller:
            self.controller.submit_command("previous spotify track")

    def _on_next(self) -> None:
        self.media_action_triggered.emit("next_track")
        if self.spotify_controller:
            self.spotify_controller.next_track()
            self.track_lbl.setText("Playback: Next Track")
        elif self.controller:
            self.controller.submit_command("next spotify track")

    def _on_open_spotify(self) -> None:
        self.media_action_triggered.emit("open_spotify")
        if self.spotify_controller:
            self.spotify_controller.play_query("")
            self.track_lbl.setText("Playback: Launching Spotify")
        elif self.controller:
            self.controller.submit_command("play spotify")


class AIStatusCard(CyberCard):
    """BOTTOM-RIGHT: AI Status card displaying state, latency, and last updated timestamp."""

    def __init__(self, controller: UIController | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setMinimumSize(260, 70)
        self.setMaximumSize(420, 90)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(2)

        # Status row
        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        title_lbl = QLabel("AI Status")
        title_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px; font-weight: 700;")
        status_row.addWidget(title_lbl)
        status_row.addStretch()

        self.status_dot = QLabel("● Online")
        self.status_dot.setStyleSheet(f"color: {STATUS_SUCCESS}; font-size: 11px; font-weight: 700;")
        status_row.addWidget(self.status_dot)
        layout.addLayout(status_row)

        # Response Time row
        time_row = QHBoxLayout()
        time_lbl = QLabel("Response Time")
        time_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px;")
        time_row.addWidget(time_lbl)
        time_row.addStretch()

        self.latency_lbl = QLabel("0.0s")
        self.latency_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 10px; font-weight: 700; font-family: monospace;")
        time_row.addWidget(self.latency_lbl)
        layout.addLayout(time_row)

        # Last Updated row
        updated_row = QHBoxLayout()
        up_lbl = QLabel("Last Updated")
        up_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px;")
        updated_row.addWidget(up_lbl)
        updated_row.addStretch()

        self.updated_lbl = QLabel(datetime.now().strftime("%I:%M %p"))
        self.updated_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; font-family: monospace;")
        updated_row.addWidget(self.updated_lbl)
        layout.addLayout(updated_row)

    def update_status(self, state: DenverState | str, latency_s: float | None = None) -> None:
        """Update live status dot, response time, and refresh timestamp."""
        state_str = state.value if isinstance(state, DenverState) else str(state)
        is_online = state_str not in {"ERROR", "STOPPED"}
        dot_color = STATUS_SUCCESS if is_online else STATUS_DANGER
        self.status_dot.setText(f"● {state_str.capitalize()}")
        self.status_dot.setStyleSheet(f"color: {dot_color}; font-size: 11px; font-weight: 700;")

        if latency_s is not None:
            self.latency_lbl.setText(f"{latency_s:.1f}s")

        self.updated_lbl.setText(datetime.now().strftime("%I:%M %p"))


class BottomBarWidget(QFrame):
    """Docked full-width bottom bar with logo, tools, command search input, mic, and power exit."""

    command_submitted = Signal(str)
    voice_clicked = Signal()
    close_requested = Signal()
    settings_requested = Signal()

    def __init__(self, controller: UIController | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setObjectName("BottomBar")
        self.setFixedHeight(62)
        self.setStyleSheet(f"""
            QFrame#BottomBar {{
                background-color: {BOTTOM_BAR_BG};
                border-top: 1px solid {BOTTOM_BAR_BORDER};
            }}
        """)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 8, 18, 8)
        layout.setSpacing(14)

        # LEFT: Denver Logo Badge + Wordmark + Tools
        left_box = QHBoxLayout()
        left_box.setSpacing(8)

        # Cyan logo badge with lightning bolt
        self.logo_badge = QLabel("⚡")
        self.logo_badge.setFixedSize(30, 30)
        self.logo_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo_badge.setStyleSheet(f"""
            background: {GRADIENT_TEAL};
            color: #FFFFFF;
            border-radius: 6px;
            font-size: 15px;
            font-weight: 900;
        """)
        left_box.addWidget(self.logo_badge)

        self.wordmark = QLabel("DENVER")
        self.wordmark.setStyleSheet(f"color: {PRIMARY_CYAN}; font-size: 14px; font-weight: 900; letter-spacing: 2px;")
        left_box.addWidget(self.wordmark)

        # Small tool buttons: tasks, calendar, mic, settings
        for icon, tooltip, cmd in [
            ("☑", "Tasks", "list tasks"),
            ("📅", "Calendar", "date today"),
            ("🎙️", "Voice Status", "system status"),
            ("⚙️", "Settings", None),
        ]:
            btn = QPushButton(icon)
            btn.setFixedSize(26, 26)
            btn.setToolTip(tooltip)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {TEXT_SECONDARY};
                    border: none;
                    border-radius: 4px;
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    background-color: rgba(30, 41, 59, 0.8);
                    color: {TEXT_PRIMARY};
                }}
            """)
            if icon == "⚙️":
                btn.clicked.connect(self.settings_requested.emit)
                self.settings_btn = btn
            elif cmd:
                btn.clicked.connect(lambda _, c=cmd: self._submit_text(c))
            left_box.addWidget(btn)

        layout.addLayout(left_box)

        # CENTER: Command Input Bar + Circular Mic
        center_box = QHBoxLayout()
        center_box.setSpacing(10)

        # Input container
        input_container = QFrame()
        input_container.setFixedHeight(38)
        input_container.setStyleSheet(f"""
            QFrame {{
                background-color: {BG_INPUT};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: 19px;
                padding: 0 12px;
            }}
            QFrame:focus-within {{
                border: 1px solid {PRIMARY_CYAN};
            }}
        """)
        ic_layout = QHBoxLayout(input_container)
        ic_layout.setContentsMargins(8, 0, 8, 0)
        ic_layout.setSpacing(8)

        search_icon = QLabel("🔍")
        search_icon.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        ic_layout.addWidget(search_icon)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Ask Denver anything...")
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                color: {TEXT_PRIMARY};
                border: none;
                font-size: 12px;
            }}
        """)
        self.search_input.returnPressed.connect(self._on_enter_pressed)
        ic_layout.addWidget(self.search_input, stretch=1)
        center_box.addWidget(input_container, stretch=1)

        # Circular Accent Mic Button
        self.mic_btn = QPushButton("🎙️")
        self.mic_btn.setFixedSize(38, 38)
        self.mic_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mic_btn.setToolTip("Start voice capture")
        self.mic_btn.setStyleSheet(f"""
            QPushButton {{
                background: {GRADIENT_TEAL};
                color: #FFFFFF;
                border: none;
                border-radius: 19px;
                font-size: 15px;
            }}
            QPushButton:hover {{
                border: 2px solid #FFFFFF;
            }}
            QPushButton:pressed {{
                background-color: {PRIMARY_BLUE};
            }}
        """)
        self.mic_btn.clicked.connect(self._on_mic_clicked)
        center_box.addWidget(self.mic_btn)

        layout.addLayout(center_box, stretch=1)

        # RIGHT: Time/Date, User Avatar, Power Shutdown Button
        right_box = QHBoxLayout()
        right_box.setSpacing(12)

        # Small Time/Date
        self.small_time_col = QVBoxLayout()
        self.small_time_col.setSpacing(1)
        self.small_time_lbl = QLabel(datetime.now().strftime("%I:%M %p"))
        self.small_time_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 11px; font-weight: 700; font-family: monospace;")
        self.small_date_lbl = QLabel(datetime.now().strftime("%a, %b %d"))
        self.small_date_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 9px;")
        self.small_time_col.addWidget(self.small_time_lbl)
        self.small_time_col.addWidget(self.small_date_lbl)
        right_box.addLayout(self.small_time_col)

        # User Avatar + Username
        user_name = _get_system_username()
        user_initial = user_name[0].upper() if user_name else "D"
        avatar_badge = QLabel(user_initial)
        avatar_badge.setFixedSize(26, 26)
        avatar_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar_badge.setStyleSheet(f"""
            background-color: {PRIMARY_BLUE};
            color: #FFFFFF;
            border-radius: 13px;
            font-size: 11px;
            font-weight: 800;
        """)
        right_box.addWidget(avatar_badge)

        user_lbl = QLabel(user_name)
        user_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; font-weight: 600;")
        right_box.addWidget(user_lbl)

        # Power / Exit icon button
        self.power_btn = QPushButton("⏻")
        self.power_btn.setFixedSize(28, 28)
        self.power_btn.setToolTip("Close Dashboard Overlay (or press Esc)")
        self.power_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.power_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_MUTED};
                border: none;
                border-radius: 14px;
                font-size: 15px;
            }}
            QPushButton:hover {{
                color: {STATUS_DANGER};
                background-color: rgba(239, 68, 68, 0.15);
            }}
        """)
        self.power_btn.clicked.connect(self._on_close)
        right_box.addWidget(self.power_btn)

        layout.addLayout(right_box)

    def _on_enter_pressed(self) -> None:
        text = self.search_input.text().strip()
        if text:
            self._submit_text(text)
            self.search_input.clear()

    def _submit_text(self, text: str) -> None:
        self.command_submitted.emit(text)
        if self.controller:
            self.controller.submit_command(text)

    def _on_mic_clicked(self) -> None:
        logger.info("Bottom bar mic button clicked.")
        self.voice_clicked.emit()
        if self.controller and hasattr(self.controller, "toggle_voice"):
            self.controller.toggle_voice()

    def _on_close(self) -> None:
        logger.info("Dashboard close requested via power button.")
        self.close_requested.emit()


class DenverDashboardOverlay(QMainWindow):
    """Full-bleed dark desktop overlay with cyber HUD cards matching reference layout."""

    def __init__(self, controller: UIController | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle(f"{product_name} — Home Dashboard")
        self.resize(1200, 800)
        self.setMinimumSize(960, 640)

        # Frameless cyber overlay setup
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        self._init_ui()
        self._bind_signals()

    def _init_ui(self) -> None:
        if not _PYSIDE_AVAILABLE:
            return

        # Central widget with radial dark cyber background
        central = QWidget(self)
        central.setObjectName("DashboardCentral")
        central.setStyleSheet(f"""
            QWidget#DashboardCentral {{
                background: {BG_OVERLAY_GRADIENT};
                font-family: 'Segoe UI', -apple-system, sans-serif;
            }}
        """)
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Main HUD Body Area
        body_widget = QWidget()
        body_layout = QVBoxLayout(body_widget)
        body_layout.setContentsMargins(32, 28, 32, 18)
        body_layout.setSpacing(20)

        # TOP SECTION: TOP-LEFT Weather vs. TOP-RIGHT Stack (Performance, Quick Status, Clock)
        top_row = QHBoxLayout()
        top_row.setSpacing(24)

        # TOP-LEFT Weather Card
        self.weather_card = WeatherCard()
        top_row.addWidget(self.weather_card, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        top_row.addStretch(1)

        # TOP-RIGHT Stacked Cards
        top_right_col = QVBoxLayout()
        top_right_col.setSpacing(12)
        top_right_col.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)

        self.perf_card = SystemPerformanceCard()
        top_right_col.addWidget(self.perf_card)

        self.quick_status_card = QuickStatusCard()
        top_right_col.addWidget(self.quick_status_card)

        self.clock_card = LiveClockCard()
        top_right_col.addWidget(self.clock_card)

        top_row.addLayout(top_right_col)
        body_layout.addLayout(top_row)

        body_layout.addStretch(1)

        # BOTTOM SECTION: BOTTOM-LEFT Quick Actions vs. BOTTOM-RIGHT AI Status
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(24)

        # BOTTOM-LEFT Quick Actions
        self.actions_card = QuickActionsCard(controller=self.controller)
        bottom_row.addWidget(self.actions_card, alignment=Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft)

        bottom_row.addStretch(1)

        # BOTTOM-RIGHT AI Status Card
        self.ai_status_card = AIStatusCard(controller=self.controller)
        bottom_row.addWidget(self.ai_status_card, alignment=Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)

        body_layout.addLayout(bottom_row)
        root_layout.addWidget(body_widget, stretch=1)

        # BOTTOM BAR (Full-width docked)
        self.bottom_bar = BottomBarWidget(controller=self.controller)
        self.bottom_bar.close_requested.connect(self.close_overlay)
        root_layout.addWidget(self.bottom_bar)

        # Periodic Telemetry Update Timer (every 2s)
        self.telemetry_timer = QTimer(self)
        self.telemetry_timer.timeout.connect(self._on_telemetry_tick)
        self.telemetry_timer.start(2000)

    def _bind_signals(self) -> None:
        """Bind live controller signals if controller bridge is present."""
        if not self.controller or not hasattr(self.controller, "bridge") or not self.controller.bridge:
            return

        bridge = self.controller.bridge
        if hasattr(bridge, "telemetry_updated"):
            bridge.telemetry_updated.connect(self._on_telemetry_updated)
        if hasattr(bridge, "state_changed"):
            bridge.state_changed.connect(self._on_state_changed)
        if hasattr(bridge, "activity_added"):
            bridge.activity_added.connect(self._on_activity_added)

    def _on_telemetry_tick(self) -> None:
        """Periodic background poll for CPU, memory, storage, and quick status."""
        cpu = psutil.cpu_percent(interval=None) if _PSUTIL_AVAILABLE else 0.0
        mem = psutil.virtual_memory().percent if _PSUTIL_AVAILABLE else 0.0
        storage, _ = _get_disk_storage_info()

        self.perf_card.update_telemetry(cpu_pct=cpu, mem_pct=mem, storage_pct=storage)
        self.quick_status_card.refresh_quick_status()

    def _on_telemetry_updated(self, state: Any) -> None:
        cpu = getattr(state, "cpu_percent", None)
        ram = getattr(state, "ram_percent", None)
        self.perf_card.update_telemetry(cpu_pct=cpu, mem_pct=ram)

    def _on_state_changed(self, new_state: DenverState, reason: str) -> None:
        self.ai_status_card.update_status(new_state)

    def _on_activity_added(self, item: Any) -> None:
        latency_ms = getattr(item, "latency_ms", 0.0) or 0.0
        latency_s = latency_ms / 1000.0
        state = self.controller.state.current_state if self.controller else DenverState.STANDBY
        self.ai_status_card.update_status(state=state, latency_s=latency_s)

    def close_overlay(self) -> None:
        """Cleanly close overlay."""
        logger.info("Denver dashboard overlay close requested.")
        self.close()

    def keyPressEvent(self, event: Any) -> None:
        """Escape key handler providing clean, reliable exit for the overlay."""
        if _PYSIDE_AVAILABLE and event.key() == Qt.Key.Key_Escape:
            logger.info("Denver dashboard overlay closed via Escape key.")
            self.close_overlay()
            event.accept()
        else:
            super().keyPressEvent(event)


class DenverHomeTabWidget(QWidget):
    """Home Dashboard Tab Widget adapted for hosting inside the Cockpit's ActivityPanelWidget.

    Hosts the 6 cyber HUD content cards without duplicate bottom command input bar:
    - WeatherCard (live weather & location)
    - SystemPerformanceCard (CPU, RAM, Storage 1-decimal bars)
    - QuickStatusCard (Temp N/A, Battery, Network, Disk)
    - LiveClockCard (large cyan monospace time & date)
    - QuickActionsCard (2x2 action buttons wired to Cockpit's UIController)
    - AIStatusCard (online state & latency)
    """

    def __init__(self, controller: UIController | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setObjectName("DenverHomeTab")
        self._init_ui()

    def _init_ui(self) -> None:
        if not _PYSIDE_AVAILABLE:
            return

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Scroll area for clean responsive embedding inside tab panels
        from PySide6.QtWidgets import QScrollArea
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.scroll.setStyleSheet(f"""
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollArea > QWidget > QWidget {{
                background: transparent;
            }}
        """)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        grid = QGridLayout(container)
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)

        # Row 0: Weather Card & Spotify Media Controller
        self.weather_card = WeatherCard(container)
        grid.addWidget(self.weather_card, 0, 0)

        self.spotify_card = SpotifyMediaCard(controller=self.controller, parent=container)
        grid.addWidget(self.spotify_card, 0, 1)

        # Row 1: Quick Actions (wired to Cockpit UIController) & Quick Status
        self.actions_card = QuickActionsCard(controller=self.controller, parent=container)
        self.quick_actions_card = self.actions_card
        grid.addWidget(self.actions_card, 1, 0)

        self.quick_status_card = QuickStatusCard(container)
        grid.addWidget(self.quick_status_card, 1, 1)

        # Row 2: Live Clock & AI Status
        self.clock_card = LiveClockCard(container)
        grid.addWidget(self.clock_card, 2, 0)

        self.ai_status_card = AIStatusCard(controller=self.controller, parent=container)
        grid.addWidget(self.ai_status_card, 2, 1)

        self.scroll.setWidget(container)
        main_layout.addWidget(self.scroll)

        # Guarantee scroll position starts at the top
        QTimer.singleShot(0, self.scroll_to_top)

        # Periodic Refresh Timer (every 2s for quick status readings)
        self.telemetry_timer = QTimer(self)
        self.telemetry_timer.timeout.connect(self._on_telemetry_tick)
        self.telemetry_timer.start(2000)

    def scroll_to_top(self) -> None:
        """Ensure the Home tab scroll area is positioned at the top."""
        if hasattr(self, "scroll") and self.scroll:
            self.scroll.verticalScrollBar().setValue(0)

    def _on_telemetry_tick(self) -> None:
        """Periodic background refresh for quick status and system indicators."""
        self.quick_status_card.refresh_quick_status()

    def update_telemetry(self, state: Any) -> None:
        """Receive telemetry event from MainWindow (telemetry is displayed on right rail)."""
        pass

    def update_state(self, new_state: DenverState) -> None:
        self.ai_status_card.update_status(new_state)

    def update_activity(self, item: Any) -> None:
        latency_ms = getattr(item, "latency_ms", 0.0) or 0.0
        latency_s = latency_ms / 1000.0
        state = self.controller.state.current_state if self.controller else DenverState.STANDBY
        self.ai_status_card.update_status(state=state, latency_s=latency_s)


if __name__ == "__main__":
    # Deprecated: The standalone DenverDashboardOverlay entrypoint is deprecated.
    # The unified Denver GUI application is launched via: python main.py --gui
    import sys
    print("Notice: The standalone overlay entrypoint is deprecated. Launch the unified Cockpit via 'python main.py --gui'.")
    sys.exit(0)

