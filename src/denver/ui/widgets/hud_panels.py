"""Denver AI Assistant — Right Telemetry & HUD Status Panels."""

from __future__ import annotations

from datetime import datetime
import os
from typing import Any

try:
    from PySide6.QtCore import Qt, QTimer
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
from denver.ui.theme import (
    CARD_BG_GLASS,
    CARD_BORDER,
    CARD_BORDER_PURPLE,
    PRIMARY_CYAN,
    PRIMARY_PURPLE,
    STATUS_DANGER,
    STATUS_SUCCESS,
    TEXT_CYAN,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


class BaseGlassPanel(QFrame):
    """Base translucent glass card with glowing cyber border."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {CARD_BG_GLASS};
                border: 1px solid {CARD_BORDER};
                border-radius: 14px;
            }}
            QFrame:hover {{
                border: 1px solid {CARD_BORDER_PURPLE};
            }}
        """)


class HUDSystemPerformanceCard(BaseGlassPanel):
    """Card 1: System Performance with CPU, Memory, and Storage progress bars."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # Header Row
        header = QHBoxLayout()
        header.setSpacing(6)
        icon_lbl = QLabel("📊")
        icon_lbl.setStyleSheet(f"color: {PRIMARY_CYAN}; font-size: 13px;")
        title_lbl = QLabel("System Performance")
        title_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px; font-weight: 700;")
        chevron_lbl = QLabel("›")
        chevron_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 14px; font-weight: 700;")

        header.addWidget(icon_lbl)
        header.addWidget(title_lbl)
        header.addStretch()
        header.addWidget(chevron_lbl)
        layout.addLayout(header)

        # CPU Row
        self.cpu_bar, self.cpu_lbl = self._create_metric_row(
            layout, "CPU", "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #38BDF8, stop:1 #06B6D4)"
        )
        # Memory Row
        self.mem_bar, self.mem_lbl = self._create_metric_row(
            layout, "Memory", "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #818CF8, stop:1 #C084FC)"
        )
        # Storage Row
        self.storage_bar, self.storage_lbl = self._create_metric_row(
            layout, "Storage", "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #34D399, stop:1 #10B981)"
        )

    def _create_metric_row(self, layout: QVBoxLayout, name: str, fill_gradient: str) -> tuple[QProgressBar, QLabel]:
        row = QHBoxLayout()
        row.setSpacing(8)

        label = QLabel(name)
        label.setFixedWidth(52)
        label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; font-weight: 600;")
        row.addWidget(label)

        bar = QProgressBar()
        bar.setFixedHeight(8)
        bar.setTextVisible(False)
        bar.setRange(0, 100)
        bar.setValue(20)
        bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: rgba(15, 23, 42, 0.9);
                border-radius: 4px;
                border: none;
            }}
            QProgressBar::chunk {{
                background: {fill_gradient};
                border-radius: 4px;
            }}
        """)
        row.addWidget(bar, stretch=1)

        val_lbl = QLabel("0%")
        val_lbl.setFixedWidth(36)
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        val_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 11px; font-weight: 700;")
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
            self.cpu_bar.setValue(int(cpu))
            self.cpu_lbl.setText(f"{cpu:.0f}%")
        if mem is not None:
            self.mem_bar.setValue(int(mem))
            self.mem_lbl.setText(f"{mem:.0f}%")
        if storage is not None:
            self.storage_bar.setValue(int(storage))
            self.storage_lbl.setText(f"{storage:.0f}%")


class HUDQuickStatusCard(BaseGlassPanel):
    """Card 2: Quick Status 2x2 grid (Network, Disk Health, User Login, Power Mode)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # Header Row
        header = QHBoxLayout()
        header.setSpacing(6)
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {STATUS_SUCCESS}; font-size: 12px;")
        title = QLabel("Quick Status")
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px; font-weight: 700;")
        chevron = QLabel("›")
        chevron.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 14px; font-weight: 700;")
        header.addWidget(dot)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(chevron)
        layout.addLayout(header)

        # 2x2 Grid
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)

        # 1. Network
        grid.addWidget(self._create_stat_widget("🌐 Network", "● Online", STATUS_SUCCESS), 0, 0)
        # 2. Disk Health
        grid.addWidget(self._create_stat_widget("🖴 Disk Health", "● Good", STATUS_SUCCESS), 0, 1)
        # 3. User Login
        grid.addWidget(self._create_stat_widget("👤 User Login", "● Active", STATUS_SUCCESS), 1, 0)
        # 4. Power Mode
        grid.addWidget(self._create_stat_widget("⚡ Power Mode", "High Performance", PRIMARY_CYAN), 1, 1)

        layout.addLayout(grid)

    def refresh_quick_status(self) -> None:
        """Poll or refresh network / disk quick status indicators."""
        pass


    def _create_stat_widget(self, title: str, status: str, status_color: str) -> QWidget:
        box = QWidget()
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(0, 0, 0, 0)
        box_layout.setSpacing(2)

        t_lbl = QLabel(title)
        t_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; font-weight: 600;")
        s_lbl = QLabel(status)
        s_lbl.setStyleSheet(f"color: {status_color}; font-size: 10px; font-weight: 700;")

        box_layout.addWidget(t_lbl)
        box_layout.addWidget(s_lbl)
        return box


class HUDClockCard(BaseGlassPanel):
    """Card 3: Large glowing digital clock and date with calendar icon."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._init_ui()

        if _PYSIDE_AVAILABLE:
            self.timer = QTimer(self)
            self.timer.timeout.connect(self._update_time)
            self.timer.start(1000)
        self._update_time()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(2)

        top_row = QHBoxLayout()
        self.time_lbl = QLabel("08:19 PM")
        self.time_lbl.setStyleSheet(f"""
            color: {TEXT_CYAN};
            font-size: 20px;
            font-weight: 800;
            letter-spacing: 1px;
        """)
        cal_icon = QLabel("📅")
        cal_icon.setStyleSheet(f"color: {PRIMARY_PURPLE}; font-size: 16px;")

        top_row.addWidget(self.time_lbl)
        top_row.addStretch()
        top_row.addWidget(cal_icon)
        layout.addLayout(top_row)

        self.date_lbl = QLabel("Saturday, September 13, 2025")
        self.date_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; font-weight: 600;")
        layout.addWidget(self.date_lbl)

    def _update_time(self) -> None:
        now = datetime.now()
        self.time_lbl.setText(now.strftime("%I:%M %p"))
        self.date_lbl.setText(now.strftime("%A, %B %d, %Y"))


class HUDAIStatusCard(BaseGlassPanel):
    """Card 4: AI Status panel showing state, response latency, and last updated."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        # Header Row
        header = QHBoxLayout()
        header.setSpacing(6)
        brain_icon = QLabel("🧠")
        brain_icon.setStyleSheet(f"color: {PRIMARY_CYAN}; font-size: 13px;")
        title = QLabel("AI Status")
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px; font-weight: 700;")
        header.addWidget(brain_icon)
        header.addWidget(title)
        header.addStretch()

        self.state_pill = QLabel("● Ready")
        self.state_pill.setStyleSheet(f"""
            color: {STATUS_SUCCESS};
            font-size: 10px;
            font-weight: 700;
            background: rgba(34, 197, 94, 0.12);
            padding: 2px 8px;
            border-radius: 8px;
            border: 1px solid rgba(34, 197, 94, 0.35);
        """)
        header.addWidget(self.state_pill)
        layout.addLayout(header)

        # Metrics Row
        row1 = QHBoxLayout()
        r1_t = QLabel("Response Time")
        r1_t.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; font-weight: 500;")
        self.latency_lbl = QLabel("0.2s")
        self.latency_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 10px; font-weight: 700;")
        row1.addWidget(r1_t)
        row1.addStretch()
        row1.addWidget(self.latency_lbl)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        r2_t = QLabel("Last Updated")
        r2_t.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; font-weight: 500;")
        self.updated_lbl = QLabel(datetime.now().strftime("%I:%M %p"))
        self.updated_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 10px; font-weight: 700;")
        row2.addWidget(r2_t)
        row2.addStretch()
        row2.addWidget(self.updated_lbl)
        layout.addLayout(row2)

    def update_status(self, state: DenverState | None = None, latency_s: float | None = None) -> None:
        if state is not None:
            if state == DenverState.LISTENING:
                self.state_pill.setText("● Listening")
                self.state_pill.setStyleSheet("color: #38BDF8; background: rgba(56, 189, 248, 0.15); padding: 2px 8px; border-radius: 8px; border: 1px solid rgba(56, 189, 248, 0.4);")
            elif state == DenverState.PROCESSING:
                self.state_pill.setText("● Processing")
                self.state_pill.setStyleSheet("color: #F59E0B; background: rgba(245, 158, 11, 0.15); padding: 2px 8px; border-radius: 8px; border: 1px solid rgba(245, 158, 11, 0.4);")
            elif state == DenverState.SPEAKING:
                self.state_pill.setText("● Speaking")
                self.state_pill.setStyleSheet("color: #A855F7; background: rgba(168, 85, 247, 0.15); padding: 2px 8px; border-radius: 8px; border: 1px solid rgba(168, 85, 247, 0.4);")
            else:
                self.state_pill.setText("● Ready")
                self.state_pill.setStyleSheet(f"color: {STATUS_SUCCESS}; background: rgba(34, 197, 94, 0.12); padding: 2px 8px; border-radius: 8px; border: 1px solid rgba(34, 197, 94, 0.35);")

        if latency_s is not None:
            self.latency_lbl.setText(f"{latency_s:.1f}s")
        self.updated_lbl.setText(datetime.now().strftime("%I:%M %p"))


class DenverHUDPanelStack(QWidget):
    """Unified right telemetry HUD stack hosting all 4 glass panels."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(270)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 16, 16, 16)
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

        # Periodic background poll (2s) for CPU, Memory, Storage
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
