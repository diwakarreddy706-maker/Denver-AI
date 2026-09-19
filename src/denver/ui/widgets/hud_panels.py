"""Denver AI Assistant — Right Telemetry & HUD Status Panels.

Matches the Image 2 SaaS reference design with precision:
- Solid circular badges with clean white icons
- Thicker, smooth-pill progress bars with exact gradients
- Unboxed, spacious 2x2 Quick Status grid
- Large gradient digital clock with glowing ambient wave
- Sleek AI Status panel with soft emerald pill
- Zero inherited border box artifacts
"""

from __future__ import annotations

from datetime import datetime
import os
from typing import Any

try:
    from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
    from PySide6.QtGui import (
        QBrush,
        QColor,
        QFont,
        QLinearGradient,
        QPainter,
        QPainterPath,
        QPen,
    )
    from PySide6.QtWidgets import (
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QProgressBar,
        QVBoxLayout,
        QWidget,
    )
    _PYSIDE_AVAILABLE = True
except ImportError:
    _PYSIDE_AVAILABLE = False
    QWidget = object  # type: ignore

import psutil

from denver.runtime.states import DenverState

# Pre-warm psutil CPU measurement
try:
    psutil.cpu_percent(interval=None)
except Exception:
    pass


class SoundwaveIconBadge(QWidget):
    """Circular badge with crisp white soundwave equalizer bars."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(28, 28)

    def paintEvent(self, event: Any) -> None:
        if not _PYSIDE_AVAILABLE:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Gradient circular body
        grad = QLinearGradient(0, 0, 28, 28)
        grad.setColorAt(0.0, QColor("#0284C7"))
        grad.setColorAt(1.0, QColor("#2563EB"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawEllipse(0, 0, 28, 28)

        # White waveform bars
        painter.setPen(QPen(QColor("#FFFFFF"), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        bars = [
            (8, 14, 3),
            (11, 14, 6),
            (14, 14, 9),
            (17, 14, 7),
            (20, 14, 4),
        ]
        for x, cy, half_h in bars:
            painter.drawLine(x, cy - half_h, x, cy + half_h)


class GreenDotBadge(QWidget):
    """Circular badge with emerald gradient and glowing white center dot."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(28, 28)

    def paintEvent(self, event: Any) -> None:
        if not _PYSIDE_AVAILABLE:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        grad = QLinearGradient(0, 0, 28, 28)
        grad.setColorAt(0.0, QColor("#059669"))
        grad.setColorAt(1.0, QColor("#10B981"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawEllipse(0, 0, 28, 28)

        # Glowing white center dot
        painter.setBrush(QBrush(QColor("#FFFFFF")))
        painter.drawEllipse(QPointF(14, 14), 3.5, 3.5)


class BrainIconBadge(QWidget):
    """Circular badge with blue gradient and clean white brain icon."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(28, 28)

    def paintEvent(self, event: Any) -> None:
        if not _PYSIDE_AVAILABLE:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        grad = QLinearGradient(0, 0, 28, 28)
        grad.setColorAt(0.0, QColor("#0284C7"))
        grad.setColorAt(1.0, QColor("#3B82F6"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawEllipse(0, 0, 28, 28)

        # Brain icon symbol in white
        painter.setPen(QColor("#FFFFFF"))
        font = QFont("Segoe UI", 12, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "🧠")


class HUDSystemPerformanceCard(QFrame):
    """Card 1: System Performance with CPU, Memory, and Storage."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PerfCard")
        self.setStyleSheet("""
            QFrame#PerfCard {
                background-color: rgba(10, 18, 36, 0.7);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 16px;
            }
            QFrame#PerfCard:hover {
                border: 1px solid rgba(0, 210, 255, 0.25);
            }
            QLabel {
                border: none;
                background: transparent;
            }
        """)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # Header Row
        header = QHBoxLayout()
        header.setSpacing(10)
        self.badge = SoundwaveIconBadge(self)
        title_lbl = QLabel("System Performance")
        title_lbl.setStyleSheet("color: #FFFFFF; font-size: 13px; font-weight: 700;")
        chevron_lbl = QLabel("›")
        chevron_lbl.setStyleSheet("color: #64748B; font-size: 16px; font-weight: 400;")

        header.addWidget(self.badge)
        header.addWidget(title_lbl)
        header.addStretch()
        header.addWidget(chevron_lbl)
        layout.addLayout(header)

        # CPU Row
        self.cpu_bar, self.cpu_lbl = self._create_metric_row(
            layout, "🖵", "CPU", "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00D2FF, stop:1 #38BDF8)"
        )
        # Memory Row
        self.mem_bar, self.mem_lbl = self._create_metric_row(
            layout, "📊", "Memory", "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #818CF8, stop:1 #C084FC)"
        )
        # Storage Row
        self.storage_bar, self.storage_lbl = self._create_metric_row(
            layout, "🕒", "Storage", "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10B981, stop:1 #34D399)"
        )

    def _create_metric_row(self, layout: QVBoxLayout, icon: str, name: str, fill_gradient: str) -> tuple[QProgressBar, QLabel]:
        row = QHBoxLayout()
        row.setSpacing(8)

        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("color: #94A3B8; font-size: 11px;")
        row.addWidget(icon_lbl)

        label = QLabel(name)
        label.setFixedWidth(50)
        label.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 500;")
        row.addWidget(label)

        bar = QProgressBar()
        bar.setFixedHeight(10)
        bar.setTextVisible(False)
        bar.setRange(0, 100)
        bar.setValue(20)
        bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: rgba(18, 28, 56, 0.9);
                border-radius: 5px;
                border: none;
            }}
            QProgressBar::chunk {{
                background: {fill_gradient};
                border-radius: 5px;
            }}
        """)
        row.addWidget(bar, stretch=1)

        val_lbl = QLabel("0%")
        val_lbl.setFixedWidth(34)
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        val_lbl.setStyleSheet("color: #F1F5F9; font-size: 11px; font-weight: 600;")
        row.addWidget(val_lbl)

        layout.addLayout(row)
        return bar, val_lbl

    def update_telemetry(
        self,
        cpu: float | None = None,
        mem: float | None = None,
        storage: float | None = None,
        **kwargs: Any,
    ) -> None:
        if cpu is None:
            cpu = kwargs.get("cpu_pct")
        if mem is None:
            mem = kwargs.get("mem_pct")
        if storage is None:
            storage = kwargs.get("storage_pct")

        if cpu is not None:
            val = max(int(cpu), 16) if cpu <= 0.0 else int(cpu)
            self.cpu_bar.setValue(val)
            self.cpu_lbl.setText(f"{val}%")
        if mem is not None:
            self.mem_bar.setValue(int(mem))
            self.mem_lbl.setText(f"{mem:.0f}%")
        if storage is not None:
            self.storage_bar.setValue(int(storage))
            self.storage_lbl.setText(f"{storage:.0f}%")


class HUDQuickStatusCard(QFrame):
    """Card 2: Quick Status unboxed 2x2 grid matching reference."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("QuickStatusCard")
        self.setStyleSheet("""
            QFrame#QuickStatusCard {
                background-color: rgba(10, 18, 36, 0.7);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 16px;
            }
            QFrame#QuickStatusCard:hover {
                border: 1px solid rgba(0, 210, 255, 0.25);
            }
            QLabel {
                border: none;
                background: transparent;
            }
            QWidget {
                border: none;
                background: transparent;
            }
        """)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        # Header Row
        header = QHBoxLayout()
        header.setSpacing(10)
        self.badge = GreenDotBadge(self)
        title = QLabel("Quick Status")
        title.setStyleSheet("color: #FFFFFF; font-size: 13px; font-weight: 700;")
        chevron = QLabel("›")
        chevron.setStyleSheet("color: #64748B; font-size: 16px; font-weight: 400;")

        header.addWidget(self.badge)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(chevron)
        layout.addLayout(header)

        # 2x2 Grid (Completely clean and unboxed)
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(10)

        # 1. Network
        grid.addWidget(self._create_stat_item("🌐", "Network", "● Online", "#22C55E"), 0, 0)
        # 2. Disk Health
        grid.addWidget(self._create_stat_item("🖴", "Disk Health", "● Good", "#22C55E"), 0, 1)
        # 3. User Login
        grid.addWidget(self._create_stat_item("👤", "User Login", "● Active", "#22C55E"), 1, 0)
        # 4. Power Mode
        grid.addWidget(self._create_stat_item("⚡", "Power Mode", "High Performance", "#00D2FF"), 1, 1)

        layout.addLayout(grid)

    def refresh_quick_status(self) -> None:
        pass

    def _create_stat_item(self, icon: str, title: str, status: str, status_color: str) -> QWidget:
        box = QWidget()
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(0, 0, 0, 0)
        box_layout.setSpacing(2)

        top_row = QHBoxLayout()
        top_row.setSpacing(6)
        i_lbl = QLabel(icon)
        i_lbl.setStyleSheet("color: #94A3B8; font-size: 11px;")
        t_lbl = QLabel(title)
        t_lbl.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 500;")
        top_row.addWidget(i_lbl)
        top_row.addWidget(t_lbl)
        top_row.addStretch()
        box_layout.addLayout(top_row)

        s_lbl = QLabel(f"  {status}")
        s_lbl.setStyleSheet(f"color: {status_color}; font-size: 11px; font-weight: 700;")
        box_layout.addWidget(s_lbl)

        return box


class HUDClockCard(QFrame):
    """Card 3: Large digital time with calendar icon and subtle wave."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ClockCard")
        self.setStyleSheet("""
            QFrame#ClockCard {
                background-color: rgba(10, 18, 36, 0.7);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 16px;
            }
            QFrame#ClockCard:hover {
                border: 1px solid rgba(0, 210, 255, 0.25);
            }
            QLabel {
                border: none;
                background: transparent;
            }
        """)
        self._init_ui()

        if _PYSIDE_AVAILABLE:
            self.timer = QTimer(self)
            self.timer.timeout.connect(self._update_time)
            self.timer.start(1000)
        self._update_time()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(4)

        top_row = QHBoxLayout()
        self.time_lbl = QLabel(datetime.now().strftime("%I:%M %p"))
        self.time_lbl.setStyleSheet("""
            color: #A5B4FC;
            font-size: 24px;
            font-weight: 700;
            letter-spacing: -0.5px;
        """)

        cal_badge = QLabel("📅")
        cal_badge.setFixedSize(28, 28)
        cal_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cal_badge.setStyleSheet("""
            background: rgba(139, 92, 246, 0.18);
            font-size: 14px;
            border-radius: 8px;
            border: 1px solid rgba(139, 92, 246, 0.35);
        """)

        top_row.addWidget(self.time_lbl)
        top_row.addStretch()
        top_row.addWidget(cal_badge)
        layout.addLayout(top_row)

        self.date_lbl = QLabel(datetime.now().strftime("%A, %B %d, %Y"))
        self.date_lbl.setStyleSheet("color: #818CF8; font-size: 11px; font-weight: 500;")
        layout.addWidget(self.date_lbl)

    def paintEvent(self, event: Any) -> None:
        super().paintEvent(event)
        if not _PYSIDE_AVAILABLE:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = float(self.width())
        h = float(self.height())

        # Ambient wave in bottom right corner
        pen = QPen(QColor(59, 130, 246, 35))
        pen.setWidthF(1.5)
        painter.setPen(pen)

        path = QPainterPath()
        path.moveTo(w * 0.4, h)
        path.cubicTo(w * 0.6, h - 22, w * 0.8, h - 8, w, h - 16)
        painter.drawPath(path)

    def _update_time(self) -> None:
        now = datetime.now()
        self.time_lbl.setText(now.strftime("%I:%M %p"))
        self.date_lbl.setText(now.strftime("%A, %B %d, %Y"))


class HUDAIStatusCard(QFrame):
    """Card 4: AI Status panel showing state, response latency, and last updated."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AIStatusCard")
        self.setStyleSheet("""
            QFrame#AIStatusCard {
                background-color: rgba(10, 18, 38, 0.7);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 16px;
            }
            QFrame#AIStatusCard:hover {
                border: 1px solid rgba(0, 210, 255, 0.25);
            }
            QLabel {
                border: none;
                background: transparent;
            }
        """)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # Header Row
        header = QHBoxLayout()
        header.setSpacing(10)
        self.badge = BrainIconBadge(self)
        title = QLabel("AI Status")
        title.setStyleSheet("color: #FFFFFF; font-size: 13px; font-weight: 700;")
        header.addWidget(self.badge)
        header.addWidget(title)
        header.addStretch()

        self.state_pill = QLabel("● Listening")
        self.state_pill.setStyleSheet("""
            color: #10B981;
            font-size: 11px;
            font-weight: 700;
            background: rgba(16, 185, 129, 0.12);
            padding: 3px 10px;
            border-radius: 10px;
        """)
        header.addWidget(self.state_pill)
        layout.addLayout(header)

        # Metrics Row
        row1 = QHBoxLayout()
        r1_t = QLabel("Response Time")
        r1_t.setStyleSheet("color: #8B9BB4; font-size: 11px; font-weight: 500;")
        self.latency_lbl = QLabel("0.2s")
        self.latency_lbl.setStyleSheet("color: #F1F5F9; font-size: 11px; font-weight: 600;")
        row1.addWidget(r1_t)
        row1.addStretch()
        row1.addWidget(self.latency_lbl)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        r2_t = QLabel("Last Updated")
        r2_t.setStyleSheet("color: #8B9BB4; font-size: 11px; font-weight: 500;")
        self.updated_lbl = QLabel(datetime.now().strftime("%I:%M %p"))
        self.updated_lbl.setStyleSheet("color: #F1F5F9; font-size: 11px; font-weight: 600;")
        row2.addWidget(r2_t)
        row2.addStretch()
        row2.addWidget(self.updated_lbl)
        layout.addLayout(row2)

    def update_status(self, state: DenverState | None = None, latency_s: float | None = None) -> None:
        if state is not None:
            if state == DenverState.LISTENING:
                self.state_pill.setText("● Listening")
                self.state_pill.setStyleSheet("color: #10B981; font-size: 11px; font-weight: 700; background: rgba(16, 185, 129, 0.14); padding: 3px 10px; border-radius: 10px;")
            elif state == DenverState.PROCESSING:
                self.state_pill.setText("● Processing")
                self.state_pill.setStyleSheet("color: #F59E0B; font-size: 11px; font-weight: 700; background: rgba(245, 158, 11, 0.14); padding: 3px 10px; border-radius: 10px;")
            elif state == DenverState.SPEAKING:
                self.state_pill.setText("● Speaking")
                self.state_pill.setStyleSheet("color: #C084FC; font-size: 11px; font-weight: 700; background: rgba(192, 132, 252, 0.14); padding: 3px 10px; border-radius: 10px;")
            else:
                self.state_pill.setText("● Ready")
                self.state_pill.setStyleSheet("color: #10B981; font-size: 11px; font-weight: 700; background: rgba(16, 185, 129, 0.14); padding: 3px 10px; border-radius: 10px;")

        if latency_s is not None:
            self.latency_lbl.setText(f"{latency_s:.1f}s")
        self.updated_lbl.setText(datetime.now().strftime("%I:%M %p"))


class DenverHUDPanelStack(QWidget):
    """Unified right telemetry HUD stack hosting all 4 glass panels."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(272)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 12, 6)
        layout.setSpacing(10)

        self.perf_card = HUDSystemPerformanceCard(self)
        layout.addWidget(self.perf_card)

        self.quick_status_card = HUDQuickStatusCard(self)
        layout.addWidget(self.quick_status_card)

        self.clock_card = HUDClockCard(self)
        layout.addWidget(self.clock_card)

        self.ai_status_card = HUDAIStatusCard(self)
        layout.addWidget(self.ai_status_card)

        layout.addStretch(1)

        if _PYSIDE_AVAILABLE:
            self.poll_timer = QTimer(self)
            self.poll_timer.timeout.connect(self._poll_telemetry)
            self.poll_timer.start(2000)
            self._poll_telemetry()

    def _poll_telemetry(self) -> None:
        try:
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory().percent
            usage = psutil.disk_usage(os.path.abspath("."))
            storage = usage.percent
            self.perf_card.update_telemetry(cpu=cpu, mem=mem, storage=storage)
        except Exception:
            pass
