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
        self.setFixedHeight(180)
        self.setMinimumWidth(380)
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
        halo_radius = 68.0 + pulse * 4.0
        halo_grad = QRadialGradient(cx, cy, halo_radius + 32)
        halo_grad.setColorAt(0.0, QColor(0, 210, 255, 95))
        halo_grad.setColorAt(0.4, QColor(59, 130, 246, 60))
        halo_grad.setColorAt(0.7, QColor(139, 92, 246, 35))
        halo_grad.setColorAt(1.0, QColor(6, 11, 23, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(halo_grad))
        painter.drawEllipse(QPointF(cx, cy), halo_radius + 32, halo_radius + 32)

        # Concentric Outer Ring 1 (Cyan/Purple glowing neon gradient)
        pen1 = QPen()
        pen1.setWidthF(3.0)
        pen_grad = QLinearGradient(cx - 60, cy - 60, cx + 60, cy + 60)
        if self._state == DenverState.LISTENING:
            pen_grad.setColorAt(0.0, QColor("#00E5FF"))
            pen_grad.setColorAt(1.0, QColor("#3B82F6"))
        elif self._state == DenverState.PROCESSING:
            pen_grad.setColorAt(0.0, QColor("#F59E0B"))
            pen_grad.setColorAt(1.0, QColor("#EC4899"))
        elif self._state == DenverState.SPEAKING:
            pen_grad.setColorAt(0.0, QColor("#A855F7"))
            pen_grad.setColorAt(1.0, QColor("#6366F1"))
        else:
            pen_grad.setColorAt(0.0, QColor("#00D2FF"))
            pen_grad.setColorAt(0.6, QColor("#3B82F6"))
            pen_grad.setColorAt(1.0, QColor("#A855F7"))
        pen1.setBrush(QBrush(pen_grad))
        painter.setPen(pen1)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), 62.0, 62.0)

        # Concentric Inner Ring 2 (Thin subtle glowing purple/cyan border)
        pen2 = QPen(QColor(139, 92, 246, 120))
        pen2.setWidthF(1.5)
        painter.setPen(pen2)
        painter.drawEllipse(QPointF(cx, cy), 54.0, 54.0)

        # Core Circular Glass Body
        core_grad = QRadialGradient(cx - 12, cy - 14, 52)
        core_grad.setColorAt(0.0, QColor(24, 48, 96))
        core_grad.setColorAt(0.65, QColor(10, 20, 42))
        core_grad.setColorAt(1.0, QColor(5, 10, 22))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(core_grad))
        painter.drawEllipse(QPointF(cx, cy), 50.0, 50.0)

        # Denver Futuristic 'A' Monogram in center
        self._draw_a_monogram(painter, cx, cy)

    def _draw_background_waves(self, painter: QPainter, cx: float, cy: float, pulse: float) -> None:
        """Draw subtle horizontal glowing wave curves extending left and right."""
        w = self.width()

        # Cyan primary wave
        pen_cyan = QPen(QColor(0, 210, 255, 45))
        pen_cyan.setWidthF(1.5)
        painter.setPen(pen_cyan)

        path1 = QPainterPath()
        path1.moveTo(0, cy + 6)
        path1.cubicTo(
            cx * 0.45, cy + 24 + pulse * 7,
            cx * 0.75, cy - 20 - pulse * 5,
            cx - 62, cy
        )
        painter.drawPath(path1)

        path2 = QPainterPath()
        path2.moveTo(cx + 62, cy)
        path2.cubicTo(
            cx + (w - cx) * 0.25, cy - 22 - pulse * 6,
            cx + (w - cx) * 0.65, cy + 22 + pulse * 5,
            w, cy - 8
        )
        painter.drawPath(path2)

        # Purple secondary ambient wave
        pen_purple = QPen(QColor(168, 85, 247, 30))
        pen_purple.setWidthF(1.2)
        painter.setPen(pen_purple)

        path3 = QPainterPath()
        path3.moveTo(0, cy - 14)
        path3.cubicTo(cx * 0.4, cy - 28, cx * 0.78, cy + 20, cx - 58, cy + 8)
        painter.drawPath(path3)

        path4 = QPainterPath()
        path4.moveTo(cx + 58, cy + 8)
        path4.cubicTo(cx + (w - cx) * 0.35, cy + 26, cx + (w - cx) * 0.72, cy - 24, w, cy + 6)
        painter.drawPath(path4)

    def _draw_a_monogram(self, painter: QPainter, cx: float, cy: float) -> None:
        """Draw sleek modern geometric 'A' monogram matching Image 2 reference."""
        # Gradient for the monogram
        grad = QLinearGradient(cx, cy - 22, cx, cy + 22)
        grad.setColorAt(0.0, QColor("#00E5FF"))
        grad.setColorAt(0.5, QColor("#818CF8"))
        grad.setColorAt(1.0, QColor("#C084FC"))

        # Draw stylized geometric triangular A with cross cutout
        path = QPainterPath()
        # Outer triangle with rounded apex
        path.moveTo(cx - 20, cy + 20)
        path.lineTo(cx - 4, cy - 18)
        path.quadTo(cx, cy - 22, cx + 4, cy - 18)
        path.lineTo(cx + 20, cy + 20)
        path.lineTo(cx + 10, cy + 20)
        path.lineTo(cx + 6, cy + 8)
        path.lineTo(cx - 6, cy + 8)
        path.lineTo(cx - 10, cy + 20)
        path.closeSubpath()

        # Inner triangular cutout
        path.moveTo(cx, cy - 8)
        path.lineTo(cx + 4, cy + 2)
        path.lineTo(cx - 4, cy + 2)
        path.closeSubpath()

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawPath(path)
