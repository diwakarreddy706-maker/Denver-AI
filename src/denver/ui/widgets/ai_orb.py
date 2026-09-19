"""Denver AI Assistant — Central Futuristic Glowing AI Orb Widget."""

from __future__ import annotations

import math
from typing import Any

try:
    from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
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
    from PySide6.QtWidgets import QWidget
    _PYSIDE_AVAILABLE = True
except ImportError:
    _PYSIDE_AVAILABLE = False
    QWidget = object  # type: ignore

from denver.runtime.states import DenverState


class DenverAIOrbWidget(QWidget):
    """Central glowing circular AI orb matching the reference commercial design.

    Features concentric multi-ring neon halo, radial gradient core, Denver 'A'
    monogram, subtle futuristic wave effects, and dynamic breathing/listening states.
    """

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(220, 180)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._pulse_phase = 0.0
        self._state = DenverState.STANDBY

        if _PYSIDE_AVAILABLE:
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._on_tick)
            self._timer.start(40)  # ~25 FPS smooth pulse

    def set_state(self, state: DenverState) -> None:
        """Update orb state for reactive color/pulse behavior."""
        self._state = state
        self.update()

    def _on_tick(self) -> None:
        speed = 0.04
        if self._state == DenverState.LISTENING:
            speed = 0.09
        elif self._state == DenverState.PROCESSING:
            speed = 0.12
        elif self._state == DenverState.SPEAKING:
            speed = 0.07

        self._pulse_phase = (self._pulse_phase + speed) % (2.0 * math.pi)
        self.update()

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def paintEvent(self, event: Any) -> None:
        if not _PYSIDE_AVAILABLE:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0

        # Pulse delta (-1.0 to 1.0)
        pulse = math.sin(self._pulse_phase)

        # Draw subtle futuristic horizontal wave lines in background
        self._draw_background_waves(painter, cx, cy, pulse)

        # Outer Neon Halo Glow
        halo_radius = 64.0 + pulse * 4.0
        halo_grad = QRadialGradient(cx, cy, halo_radius + 20)
        halo_grad.setColorAt(0.0, QColor(56, 189, 248, 60))
        halo_grad.setColorAt(0.5, QColor(139, 92, 246, 35))
        halo_grad.setColorAt(0.85, QColor(37, 99, 235, 15))
        halo_grad.setColorAt(1.0, QColor(6, 10, 19, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(halo_grad))
        painter.drawEllipse(QPointF(cx, cy), halo_radius + 20, halo_radius + 20)

        # Concentric Outer Ring 1 (Cyan/Purple gradient)
        pen1 = QPen()
        pen1.setWidthF(2.5)
        pen_grad = QLinearGradient(cx - 50, cy - 50, cx + 50, cy + 50)
        if self._state == DenverState.LISTENING:
            pen_grad.setColorAt(0.0, QColor("#22C55E"))
            pen_grad.setColorAt(1.0, QColor("#06B6D4"))
        elif self._state == DenverState.PROCESSING:
            pen_grad.setColorAt(0.0, QColor("#F59E0B"))
            pen_grad.setColorAt(1.0, QColor("#EC4899"))
        else:
            pen_grad.setColorAt(0.0, QColor("#38BDF8"))
            pen_grad.setColorAt(1.0, QColor("#A855F7"))
        pen1.setBrush(QBrush(pen_grad))
        painter.setPen(pen1)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), 58.0, 58.0)

        # Concentric Inner Ring 2 (Thin subtle border)
        pen2 = QPen(QColor(56, 189, 248, 80))
        pen2.setWidthF(1.2)
        painter.setPen(pen2)
        painter.drawEllipse(QPointF(cx, cy), 52.0, 52.0)

        # Core Circular Glass Body
        core_grad = QRadialGradient(cx - 10, cy - 10, 50)
        core_grad.setColorAt(0.0, QColor(26, 46, 92))
        core_grad.setColorAt(0.65, QColor(13, 23, 46))
        core_grad.setColorAt(1.0, QColor(8, 14, 28))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(core_grad))
        painter.drawEllipse(QPointF(cx, cy), 48.0, 48.0)

        # Denver Futuristic 'A' Monogram in center
        self._draw_a_monogram(painter, cx, cy)

    def _draw_background_waves(self, painter: QPainter, cx: float, cy: float, pulse: float) -> None:
        """Draw subtle horizontal glowing wave curves extending left and right."""
        pen = QPen(QColor(56, 189, 248, 28))
        pen.setWidthF(1.2)
        painter.setPen(pen)

        path1 = QPainterPath()
        path1.moveTo(0, cy + 8)
        path1.cubicTo(
            cx * 0.5, cy + 18 + pulse * 6,
            cx * 0.75, cy - 12 - pulse * 4,
            cx - 55, cy
        )
        painter.drawPath(path1)

        path2 = QPainterPath()
        path2.moveTo(cx + 55, cy)
        path2.cubicTo(
            cx + (self.width() - cx) * 0.25, cy - 14 - pulse * 5,
            cx + (self.width() - cx) * 0.65, cy + 16 + pulse * 4,
            self.width(), cy - 6
        )
        painter.drawPath(path2)

        # Secondary subtle purple wave
        pen_purple = QPen(QColor(168, 85, 247, 20))
        pen_purple.setWidthF(1.0)
        painter.setPen(pen_purple)
        path3 = QPainterPath()
        path3.moveTo(10, cy - 10)
        path3.cubicTo(cx * 0.45, cy - 20, cx * 0.8, cy + 15, cx - 50, cy + 6)
        painter.drawPath(path3)

        path4 = QPainterPath()
        path4.moveTo(cx + 50, cy + 6)
        path4.cubicTo(cx + (self.width() - cx) * 0.35, cy + 18, cx + (self.width() - cx) * 0.7, cy - 16, self.width() - 10, cy + 4)
        painter.drawPath(path4)

    def _draw_a_monogram(self, painter: QPainter, cx: float, cy: float) -> None:
        """Draw modern stylized Denver 'A' monogram with vivid cyan-to-purple gradient."""
        font = QFont("Segoe UI", 26, QFont.Weight.Black)
        painter.setFont(font)

        text_grad = QLinearGradient(cx - 15, cy - 20, cx + 15, cy + 20)
        text_grad.setColorAt(0.0, QColor("#38BDF8"))
        text_grad.setColorAt(0.5, QColor("#818CF8"))
        text_grad.setColorAt(1.0, QColor("#C084FC"))

        painter.setPen(QPen(QBrush(text_grad), 1.0))
        rect = QRectF(cx - 24, cy - 22, 48, 44)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "A")
