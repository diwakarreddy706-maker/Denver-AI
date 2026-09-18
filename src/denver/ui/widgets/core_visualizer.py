"""Central Animated Denver Core HUD Widget."""

from __future__ import annotations

import math
from typing import Any

try:
    from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
    from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QRadialGradient
    from PySide6.QtWidgets import QWidget
    _PYSIDE_AVAILABLE = True
except ImportError:
    _PYSIDE_AVAILABLE = False
    QWidget = object  # type: ignore
    Signal = lambda *args: None  # type: ignore

from denver.runtime.states import DenverState
from denver.ui.theme import (
    BG_ROOT,
    BORDER_CYAN,
    BORDER_PURPLE,
    PRIMARY_BLUE,
    PRIMARY_CYAN,
    PRIMARY_PURPLE,
    STATUS_DANGER,
    STATUS_MUTED,
    STATUS_SUCCESS,
    STATUS_WARNING,
    TEXT_CYAN,
    TEXT_MUTED,
    TEXT_PRIMARY,
)


class DenverCoreVisualizer(QWidget):
    """Custom-painted, animated circular HUD visualizer reflecting Denver's actual state."""

    if _PYSIDE_AVAILABLE:
        clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(260, 260)
        if _PYSIDE_AVAILABLE:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setToolTip("Click HUD to activate Voice Listening (Push-to-Talk)")

        self._state: DenverState = DenverState.BOOTING
        self._rotation_angle: float = 0.0
        self._pulse_phase: float = 0.0
        self._pulse_speed: float = 0.04
        self._rotation_speed: float = 0.8

        # Animation timer (30 FPS - 33ms interval)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(33)

    def mousePressEvent(self, event: Any) -> None:
        if _PYSIDE_AVAILABLE and hasattr(self, "clicked"):
            self.clicked.emit()
        super().mousePressEvent(event)

    def set_state(self, state: DenverState) -> None:
        """Update active Denver state and configure dynamic animation parameters."""
        self._state = state
        if state == DenverState.LISTENING:
            self._pulse_speed = 0.12
            self._rotation_speed = 2.4
        elif state in {DenverState.PROCESSING, DenverState.EXECUTING}:
            self._pulse_speed = 0.10
            self._rotation_speed = 3.6
        elif state == DenverState.SPEAKING:
            self._pulse_speed = 0.14
            self._rotation_speed = 1.8
        elif state == DenverState.ERROR:
            self._pulse_speed = 0.03
            self._rotation_speed = 0.4
        elif state in {DenverState.SHUTTING_DOWN, DenverState.STOPPED}:
            self._pulse_speed = 0.01
            self._rotation_speed = 0.2
        else:  # STANDBY / BOOTING
            self._pulse_speed = 0.04
            self._rotation_speed = 0.8
        self.update()

    def _on_tick(self) -> None:
        self._rotation_angle = (self._rotation_angle + self._rotation_speed) % 360.0
        self._pulse_phase = (self._pulse_phase + self._pulse_speed) % (2.0 * math.pi)
        self.update()

    def paintEvent(self, event: Any) -> None:
        """Render concentric cyber rings, rotating arc segments, and glowing core."""
        if not _PYSIDE_AVAILABLE:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()
        center = QPointF(width / 2.0, height / 2.0)
        radius = min(width, height) / 2.0 - 16.0

        if radius <= 15:
            return

        # Determine color mapping from state
        primary_color, accent_color, state_label = self._get_state_visuals()

        # 1. Background radial ambient glow
        pulse = 0.88 + 0.12 * math.sin(self._pulse_phase)
        glow_radius = radius * 1.15 * pulse
        gradient = QRadialGradient(center, glow_radius)
        glow_c = QColor(primary_color)
        glow_c.setAlphaF(0.14)
        gradient.setColorAt(0.0, glow_c)
        glow_fade = QColor(primary_color)
        glow_fade.setAlphaF(0.0)
        gradient.setColorAt(1.0, glow_fade)
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center, glow_radius, glow_radius)

        # 2. Outer Technical Orbit Ring with Compass Tick Marks
        outer_pen = QPen(QColor(BORDER_CYAN if self._state != DenverState.ERROR else STATUS_DANGER))
        outer_pen.setWidth(1)
        outer_pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(outer_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(center, radius, radius)

        # Draw 24 perimeter ticks with 4 cardinal node indicators
        painter.save()
        painter.translate(center)
        painter.rotate(self._rotation_angle * 0.4)
        tick_pen = QPen(QColor(TEXT_MUTED))
        tick_pen.setWidth(1)
        painter.setPen(tick_pen)
        for i in range(24):
            tick_len = 6 if (i % 6 == 0) else 3
            if i % 6 == 0:
                cardinal_pen = QPen(QColor(primary_color))
                cardinal_pen.setWidth(2)
                painter.setPen(cardinal_pen)
                painter.drawLine(0, int(-radius), 0, int(-radius + tick_len))
                painter.setPen(tick_pen)
            else:
                painter.drawLine(0, int(-radius), 0, int(-radius + tick_len))
            painter.rotate(15)
        painter.restore()

        # 3. Rotating Outer Cyber Arc Segments (Forward)
        arc_radius = radius * 0.84
        rect_arc = QRectF(center.x() - arc_radius, center.y() - arc_radius, arc_radius * 2, arc_radius * 2)

        arc_pen = QPen(QColor(accent_color))
        arc_pen.setWidth(3)
        arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc_pen)
        start_angle_1 = int(self._rotation_angle * 16)
        painter.drawArc(rect_arc, start_angle_1, int(75 * 16))
        painter.drawArc(rect_arc, start_angle_1 + int(180 * 16), int(75 * 16))

        # 4. Counter-Rotating Inner Tech Dots & Arcs (Reverse)
        inner_arc_radius = radius * 0.68
        rect_inner_arc = QRectF(center.x() - inner_arc_radius, center.y() - inner_arc_radius, inner_arc_radius * 2, inner_arc_radius * 2)
        inner_arc_pen = QPen(QColor(primary_color))
        inner_arc_pen.setWidth(2)
        inner_arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(inner_arc_pen)
        start_angle_2 = int(-self._rotation_angle * 1.5 * 16)
        painter.drawArc(rect_inner_arc, start_angle_2, int(85 * 16))
        painter.drawArc(rect_inner_arc, start_angle_2 + int(180 * 16), int(85 * 16))

        # 5. Dynamic Waveform Harmonics Ring (Active when listening/speaking/executing)
        if self._state in {DenverState.LISTENING, DenverState.SPEAKING, DenverState.PROCESSING, DenverState.EXECUTING}:
            wave_radius = radius * 0.58
            wave_pen = QPen(QColor(accent_color))
            wave_pen.setWidth(1)
            painter.setPen(wave_pen)
            num_samples = 36
            for i in range(num_samples):
                angle = i * (360.0 / num_samples)
                rad = math.radians(angle + self._rotation_angle)
                wave_amp = 4.0 * math.sin(self._pulse_phase * 3.0 + i * 0.4)
                r_pt = wave_radius + wave_amp
                px = center.x() + r_pt * math.cos(rad)
                py = center.y() + r_pt * math.sin(rad)
                painter.drawPoint(QPointF(px, py))

        # 6. Central Solid Pulsing Core Sphere
        core_radius = radius * 0.46 * pulse
        core_gradient = QRadialGradient(center, core_radius)
        c_inner = QColor(primary_color)
        c_inner.setAlphaF(0.28)
        c_outer = QColor(BG_ROOT)
        c_outer.setAlphaF(0.92)
        core_gradient.setColorAt(0.0, c_inner)
        core_gradient.setColorAt(0.75, c_outer)
        core_gradient.setColorAt(1.0, QColor(primary_color))

        painter.setBrush(QBrush(core_gradient))
        painter.setPen(QPen(QColor(primary_color), 1.5))
        painter.drawEllipse(center, core_radius, core_radius)

        # 7. Central Typography HUD Label (No line collisions)
        painter.setPen(QPen(QColor(TEXT_PRIMARY)))
        font_name = QFont("Segoe UI Variable Display", 12, QFont.Weight.Bold)
        if not font_name.exactMatch():
            font_name = QFont("Segoe UI", 12, QFont.Weight.Bold)
        font_name.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.0)
        painter.setFont(font_name)
        text_rect = QRectF(center.x() - 70, center.y() - 18, 140, 20)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, "DENVER")

        # 8. State Pill Badge inside Core
        badge_font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        badge_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)
        painter.setFont(badge_font)

        badge_w = 84
        badge_h = 16
        badge_rect = QRectF(center.x() - (badge_w / 2), center.y() + 6, badge_w, badge_h)
        badge_bg = QColor(primary_color)
        badge_bg.setAlphaF(0.18)
        painter.setBrush(QBrush(badge_bg))
        painter.setPen(QPen(QColor(primary_color), 1))
        painter.drawRoundedRect(badge_rect, 8, 8)

        painter.setPen(QPen(QColor(primary_color)))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, state_label)

    def _get_state_visuals(self) -> tuple[str, str, str]:
        """Map Denver state to primary color, accent color, and display label."""
        if self._state == DenverState.LISTENING:
            return PRIMARY_CYAN, "#38BDF8", "LISTENING"
        if self._state == DenverState.PROCESSING:
            return PRIMARY_PURPLE, PRIMARY_CYAN, "PROCESSING"
        if self._state == DenverState.EXECUTING:
            return PRIMARY_BLUE, PRIMARY_CYAN, "EXECUTING"
        if self._state == DenverState.SPEAKING:
            return STATUS_SUCCESS, PRIMARY_CYAN, "SPEAKING"
        if self._state == DenverState.ERROR:
            return STATUS_DANGER, STATUS_WARNING, "ERROR"
        if self._state == DenverState.STANDBY:
            return PRIMARY_CYAN, PRIMARY_BLUE, "READY"
        if self._state in {DenverState.SHUTTING_DOWN, DenverState.STOPPED}:
            return STATUS_MUTED, "#475569", "OFFLINE"
        return PRIMARY_BLUE, PRIMARY_CYAN, "BOOTING"
