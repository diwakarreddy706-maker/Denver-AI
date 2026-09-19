"""Denver AI Assistant — Modern Weather Glass Card matching reference SaaS design."""

from __future__ import annotations

import threading
from typing import Any

try:
    from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, Signal
    from PySide6.QtGui import (
        QBrush,
        QColor,
        QFont,
        QLinearGradient,
        QPainter,
        QPainterPath,
        QPen,
        QRadialGradient,
    )
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
    QFrame = object  # type: ignore
    QWidget = object  # type: ignore

from denver.logging.logger import get_logger
from denver.ui.theme import (
    CARD_BG_GLASS,
    CARD_BORDER,
    PRIMARY_CYAN,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

logger = get_logger("ui.weather_glass")


class _WeatherSignalBridge(QObject):
    data_ready = Signal(dict)
    failed = Signal()


class ModernWeatherGlassCard(QFrame):
    """Modern glassmorphic weather card with illustration, temperature, and live location."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(250, 96)
        self.setObjectName("WeatherGlassCard")
        self.setStyleSheet(f"""
            QFrame#WeatherGlassCard {{
                background-color: rgba(10, 18, 38, 0.7);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 16px;
            }}
            QFrame#WeatherGlassCard:hover {{
                border: 1px solid rgba(56, 189, 248, 0.28);
            }}
        """)

        self._bridge = _WeatherSignalBridge()
        self._bridge.data_ready.connect(self._on_weather_data_ready)
        self._bridge.failed.connect(self._set_unavailable)

        self._init_ui()
        self._fetch_weather_async()

    def _init_ui(self) -> None:
        if not _PYSIDE_AVAILABLE:
            return

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # Left Column: Weather Icon + City Location Pin
        left_col = QVBoxLayout()
        left_col.setSpacing(6)
        left_col.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        self.icon_lbl = QLabel("⛅")
        self.icon_lbl.setStyleSheet("font-size: 26px;")
        left_col.addWidget(self.icon_lbl)

        self.loc_lbl = QLabel("📍 Bengaluru, India")
        self.loc_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; font-weight: 500;")
        left_col.addWidget(self.loc_lbl)

        layout.addLayout(left_col)
        layout.addStretch(1)

        # Right Column: Big Temperature + Condition
        right_col = QVBoxLayout()
        right_col.setSpacing(2)
        right_col.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.temp_lbl = QLabel("22°C")
        self.temp_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.temp_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 24px; font-weight: 800;")
        right_col.addWidget(self.temp_lbl)

        self.cond_lbl = QLabel("Overcast")
        self.cond_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.cond_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; font-weight: 500;")
        right_col.addWidget(self.cond_lbl)

        layout.addLayout(right_col)

    def paintEvent(self, event: Any) -> None:
        super().paintEvent(event)
        if not _PYSIDE_AVAILABLE:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())

        # Subtle dark mountain/wave curve in background matching reference
        wave_path = QPainterPath()
        wave_path.moveTo(w * 0.4, h)
        wave_path.cubicTo(w * 0.55, h - 26, w * 0.75, h - 38, w, h - 14)
        wave_path.lineTo(w, h)
        wave_path.closeSubpath()

        grad = QLinearGradient(w * 0.5, h - 40, w, h)
        grad.setColorAt(0.0, QColor(30, 58, 138, 45))
        grad.setColorAt(1.0, QColor(14, 116, 144, 25))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawPath(wave_path)

    def update_weather(self, city: str, temp_c: float, condition: str, **kwargs: Any) -> None:
        """Update display with real weather information."""
        if city:
            self.loc_lbl.setText(f"📍 {city}")
        self.temp_lbl.setText(f"{int(round(temp_c))}°C")
        self.cond_lbl.setText(condition.capitalize() if condition else "Clear")

        cond_lower = condition.lower() if condition else ""
        if "rain" in cond_lower or "drizzle" in cond_lower:
            self.icon_lbl.setText("🌧️")
        elif "cloud" in cond_lower or "overcast" in cond_lower:
            self.icon_lbl.setText("⛅")
        elif "snow" in cond_lower:
            self.icon_lbl.setText("❄️")
        elif "thunder" in cond_lower or "storm" in cond_lower:
            self.icon_lbl.setText("⛈️")
        else:
            self.icon_lbl.setText("☀️")

    def _set_unavailable(self) -> None:
        self.loc_lbl.setText("📍 Local Weather")
        self.temp_lbl.setText("22°C")
        self.cond_lbl.setText("Overcast")
        self.icon_lbl.setText("⛅")

    def _on_weather_data_ready(self, payload: dict[str, Any]) -> None:
        self.update_weather(
            city=payload.get("city", "Bengaluru, India"),
            temp_c=payload.get("temp_c", 22.0),
            condition=payload.get("condition", "Overcast"),
        )

    def _fetch_weather_async(self) -> None:
        def _worker() -> None:
            try:
                import asyncio
                from denver.automation.location import LocationService
                from denver.automation.weather import WeatherService
                from denver.config.settings import get_settings

                settings = get_settings()
                loc_service = LocationService(settings=settings)
                weather_service = WeatherService(settings=settings, location_service=loc_service)

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                report = loop.run_until_complete(weather_service.get_current_weather("here"))
                loop.close()

                if report and report.source != "error" and report.temp_c is not None:
                    city = report.city or "Bengaluru"
                    country = "India"
                    display_loc = f"{city}, {country}" if country not in city else city
                    self._bridge.data_ready.emit({
                        "city": display_loc,
                        "temp_c": report.temp_c,
                        "condition": report.condition or "Overcast",
                    })
                else:
                    self._bridge.failed.emit()
            except Exception as ex:
                logger.debug(f"Weather background fetch error: {ex}")
                self._bridge.failed.emit()


        t = threading.Thread(target=_worker, daemon=True, name="ModernWeatherWorker")
        t.start()
