"""Denver AI Assistant — Cyber HUD Display Widget.

Implements the dedicated, futuristic Cyber HUD specified in docs/Denver HUD.md:
- DENVER Brand Header & SYSTEM ONLINE status indicator
- 4 Telemetry Metrics: CPU LOAD (42%), MEMORY (35%), LATENCY (18ms), ACTIVE MODEL (llama-3.1-groq)
- Centered Animated Concentric Arc Reactor Visualizer
- Dynamic LISTENING / STANDBY / PROCESSING / EXECUTING state banner
- Real-time scrolling ACTIVITY LOG terminal with timestamps
- Cyber command input prompt: "> Ask Denver anything…"
"""

from __future__ import annotations

from datetime import datetime
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
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
        QGraphicsDropShadowEffect,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QProgressBar,
        QPushButton,
        QScrollArea,
        QVBoxLayout,
        QWidget,
    )
    _PYSIDE_AVAILABLE = True
else:
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
        )
        from PySide6.QtWidgets import (
            QFrame,
            QGraphicsDropShadowEffect,
            QGridLayout,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QProgressBar,
            QPushButton,
            QScrollArea,
            QVBoxLayout,
            QWidget,
        )
        _PYSIDE_AVAILABLE = True
    except ImportError:
        _PYSIDE_AVAILABLE = False
        QWidget = object
        QFrame = object
        Signal = lambda *args: None

import psutil

from denver.logging.logger import get_logger
from denver.runtime.states import DenverState
from denver.ui.controller import UIController
from denver.ui.theme import (
    BG_INPUT,
    BORDER_CYAN,
    BORDER_SUBTLE,
    CARD_BG_GRADIENT,
    CARD_BORDER,
    GRADIENT_TEAL,
    PRIMARY_BLUE,
    PRIMARY_CYAN,
    STATUS_DANGER,
    STATUS_SUCCESS,
    STATUS_WARNING,
    TEXT_CYAN,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from denver.ui.widgets.core_visualizer import DenverCoreVisualizer

logger = get_logger("ui.cyber_hud")


class CyberTelemetryStatCard(QFrame):
    """Clean cyber stat card for CPU, Memory, Latency, and Active Model."""

    def __init__(self, title: str, initial_value: str, accent_color: str = PRIMARY_CYAN, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._accent = accent_color
        self.setStyleSheet(f"""
            QFrame {{
                background: rgba(8, 14, 28, 0.75);
                border: 1px solid rgba(0, 229, 255, 0.15);
                border-radius: 12px;
                padding: 4px;
            }}
            QFrame:hover {{
                border: 1px solid {PRIMARY_CYAN};
                background: rgba(12, 22, 44, 0.85);
            }}
        """)
        self._init_ui(title, initial_value)

    def _init_ui(self, title: str, initial_value: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(2)

        self.title_lbl = QLabel(title.upper())
        self.title_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; font-weight: 700; letter-spacing: 1px;")
        layout.addWidget(self.title_lbl)

        self.val_lbl = QLabel(initial_value)
        self.val_lbl.setStyleSheet(f"color: {self._accent}; font-size: 22px; font-weight: 800; font-family: 'Consolas', 'Courier New', monospace;")
        layout.addWidget(self.val_lbl)

    def set_value(self, val_text: str) -> None:
        self.val_lbl.setText(val_text)


class DenverCyberHUDWidget(QWidget):
    """Primary Cyber HUD Cockpit Mode Widget adhering to docs/Denver HUD.md."""

    command_submitted = Signal(str)
    voice_toggled = Signal()

    def __init__(self, controller: UIController | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setObjectName("DenverCyberHUD")
        self.setStyleSheet("""
            QWidget#DenverCyberHUD {
                background: qradialgradient(cx:0.5, cy:0.25, radius:0.8, fx:0.5, fy:0.25, stop:0 rgba(0, 210, 255, 0.08), stop:1 rgba(3, 7, 18, 0.95));
                font-family: 'Segoe UI', -apple-system, sans-serif;
            }
        """)
        self._init_ui()
        self._seed_default_activity()
        self._bind_controller()

    def _init_ui(self) -> None:
        if not _PYSIDE_AVAILABLE:
            return

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(12)

        # ─── 1. TOP HEADER: BRAND & SYSTEM ONLINE STATUS ───────────────────────
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        # Futuristic DENVER Wordmark
        self.brand_lbl = QLabel("DENVER")
        self.brand_lbl.setStyleSheet(f"""
            color: #FFFFFF;
            font-size: 26px;
            font-weight: 900;
            letter-spacing: 4px;
            font-family: 'Consolas', 'Segoe UI Variable Display', sans-serif;
        """)
        header_row.addWidget(self.brand_lbl)
        header_row.addStretch()

        # SYSTEM ONLINE badge
        self.status_badge = QLabel("● SYSTEM ONLINE")
        self.status_badge.setStyleSheet(f"""
            color: {STATUS_SUCCESS};
            font-size: 11px;
            font-weight: 800;
            letter-spacing: 1px;
            background: rgba(16, 185, 129, 0.14);
            border: 1px solid rgba(16, 185, 129, 0.4);
            border-radius: 12px;
            padding: 4px 14px;
        """)
        header_row.addWidget(self.status_badge)
        layout.addLayout(header_row)

        # ─── 2. TELEMETRY CARDS (CPU LOAD, MEMORY, LATENCY, ACTIVE MODEL) ───────
        stat_grid = QHBoxLayout()
        stat_grid.setSpacing(12)

        self.cpu_card = CyberTelemetryStatCard("CPU LOAD", "42%", accent_color="#00E5FF", parent=self)
        stat_grid.addWidget(self.cpu_card)

        self.mem_card = CyberTelemetryStatCard("MEMORY", "35%", accent_color="#A5B4FC", parent=self)
        stat_grid.addWidget(self.mem_card)

        self.latency_card = CyberTelemetryStatCard("LATENCY", "18ms", accent_color="#10B981", parent=self)
        stat_grid.addWidget(self.latency_card)

        # Resolve active model name
        initial_model = "llama-3.1-groq"
        if self.controller and hasattr(self.controller, "app") and self.controller.app:
            router = getattr(self.controller.app, "provider_router", None)
            if router and getattr(router, "active_provider_name", None):
                initial_model = f"{router.active_provider_name}"

        self.model_card = CyberTelemetryStatCard("ACTIVE MODEL", initial_model, accent_color="#38BDF8", parent=self)
        stat_grid.addWidget(self.model_card)

        layout.addLayout(stat_grid)

        # ─── 3. CENTER ARC REACTOR & DYNAMIC STATE BANNER ──────────────────────
        center_box = QVBoxLayout()
        center_box.setSpacing(8)
        center_box.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.reactor = DenverCoreVisualizer(self)
        self.reactor.setFixedSize(180, 180)
        self.reactor.clicked.connect(self._toggle_voice)
        center_box.addWidget(self.reactor, alignment=Qt.AlignmentFlag.AlignCenter)

        # Dynamic State Banner (LISTENING / STANDBY / PROCESSING / SPEAKING)
        self.state_banner = QLabel("L I S T E N I N G")
        self.state_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_banner.setStyleSheet(f"""
            color: #00E5FF;
            font-size: 13px;
            font-weight: 800;
            letter-spacing: 3px;
            background: rgba(0, 229, 255, 0.12);
            border: 1px solid rgba(0, 229, 255, 0.35);
            border-radius: 14px;
            padding: 4px 20px;
        """)
        center_box.addWidget(self.state_banner, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addLayout(center_box)

        # ─── 4. ACTIVITY LOG (TERMINAL STREAM) ──────────────────────────────────
        log_header = QHBoxLayout()
        log_icon = QLabel("▤")
        log_icon.setStyleSheet(f"color: {PRIMARY_CYAN}; font-size: 13px;")
        log_title = QLabel("ACTIVITY LOG")
        log_title.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 11px; font-weight: 700; letter-spacing: 1px;")
        log_header.addWidget(log_icon)
        log_header.addWidget(log_title)
        log_header.addStretch()
        layout.addLayout(log_header)

        # Scrollable Activity Log Frame
        self.log_frame = QFrame(self)
        self.log_frame.setFixedHeight(120)
        self.log_frame.setStyleSheet("""
            QFrame {
                background: rgba(6, 11, 23, 0.88);
                border: 1px solid rgba(0, 229, 255, 0.18);
                border-radius: 10px;
            }
        """)
        log_frame_layout = QVBoxLayout(self.log_frame)
        log_frame_layout.setContentsMargins(12, 8, 12, 8)
        log_frame_layout.setSpacing(4)

        self.scroll_area = QScrollArea(self.log_frame)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("background: transparent; border: none;")
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.log_container = QWidget()
        self.log_container.setStyleSheet("background: transparent;")
        self.log_layout = QVBoxLayout(self.log_container)
        self.log_layout.setContentsMargins(0, 0, 0, 0)
        self.log_layout.setSpacing(3)
        self.log_layout.addStretch(1)

        self.scroll_area.setWidget(self.log_container)
        log_frame_layout.addWidget(self.scroll_area)
        layout.addWidget(self.log_frame)

        # ─── 5. CYBER COMMAND PROMPT: "> Ask Denver anything…" ──────────────────
        prompt_frame = QFrame(self)
        prompt_frame.setFixedHeight(46)
        prompt_frame.setStyleSheet(f"""
            QFrame {{
                background: rgba(10, 18, 38, 0.9);
                border: 1px solid rgba(0, 210, 255, 0.35);
                border-radius: 23px;
                padding: 0 12px;
            }}
            QFrame:focus-within {{
                border: 1px solid #00E5FF;
            }}
        """)
        prompt_layout = QHBoxLayout(prompt_frame)
        prompt_layout.setContentsMargins(12, 0, 8, 0)
        prompt_layout.setSpacing(8)

        # Prompt symbol '>'
        chevron = QLabel(">")
        chevron.setStyleSheet("color: #00E5FF; font-size: 16px; font-weight: 900; font-family: monospace;")
        prompt_layout.addWidget(chevron)

        # Line Edit
        self.prompt_edit = QLineEdit()
        self.prompt_edit.setPlaceholderText("Ask Denver anything…")
        self.prompt_edit.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                border: none;
                color: #FFFFFF;
                font-size: 13px;
                font-weight: 500;
            }}
        """)
        self.prompt_edit.returnPressed.connect(self._on_submit)
        prompt_layout.addWidget(self.prompt_edit, stretch=1)

        # Mic Button
        self.mic_btn = QPushButton("🎙")
        self.mic_btn.setFixedSize(30, 30)
        self.mic_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mic_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_SECONDARY};
                border: none;
                border-radius: 15px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                color: #00E5FF;
                background: rgba(0, 229, 255, 0.12);
            }}
        """)
        self.mic_btn.clicked.connect(self._toggle_voice)
        prompt_layout.addWidget(self.mic_btn)

        # Send Button
        self.send_btn = QPushButton("▶")
        self.send_btn.setFixedSize(30, 30)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.setStyleSheet("""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #00D2FF, stop:1 #8B5CF6);
                border: none;
                border-radius: 15px;
                color: #FFFFFF;
                font-size: 11px;
                font-weight: 800;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #00B4D8, stop:1 #7C3AED);
            }}
        """)
        self.send_btn.clicked.connect(self._on_submit)
        prompt_layout.addWidget(self.send_btn)

        layout.addWidget(prompt_frame)

        # Periodic Hardware Poller (CPU & RAM)
        self.telemetry_timer = QTimer(self)
        self.telemetry_timer.timeout.connect(self._poll_hardware)
        self.telemetry_timer.start(2000)
        self._poll_hardware()

    def _seed_default_activity(self) -> None:
        """Seed initial activity log entries matching docs/Denver HUD.md format."""
        now = datetime.now()
        t_base = now.strftime("%H:%M:")
        entries = [
            f"{t_base}14  *system online*",
            f"{t_base}21  *voice input captured*",
            f"{t_base}23  *intent resolved*",
            f"{t_base}24  *executing task*",
        ]
        for entry in entries:
            self._append_log_line(entry)

    def _append_log_line(self, line: str) -> None:
        """Append a clean terminal log entry with timestamp and italicized description."""
        lbl = QLabel(line)
        lbl.setStyleSheet(f"""
            color: #E2E8F0;
            font-size: 11px;
            font-family: 'Consolas', 'Courier New', monospace;
            padding: 1px 0;
        """)
        # Insert before the stretch at the bottom
        insert_idx = max(0, self.log_layout.count() - 1)
        self.log_layout.insertWidget(insert_idx, lbl)

        # Auto-scroll to bottom
        QTimer.singleShot(10, self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> None:
        if hasattr(self, "scroll_area") and self.scroll_area:
            v_bar = self.scroll_area.verticalScrollBar()
            v_bar.setValue(v_bar.maximum())

    def add_activity_event(self, text: str, timestamp: str | None = None) -> None:
        """Dynamically add an event formatted as: HH:MM:SS *event text*."""
        t_str = timestamp or datetime.now().strftime("%H:%M:%S")
        clean_text = text.replace("*", "").strip()
        formatted = f"{t_str}  *{clean_text}*"
        self._append_log_line(formatted)

    def set_state(self, state: DenverState) -> None:
        """Update reactor and glowing state banner."""
        self.reactor.set_state(state)
        state_name = state.value if isinstance(state, DenverState) else str(state)

        # Format state label with spaces for high-tech aesthetic
        spaced = " ".join(list(state_name))

        if state == DenverState.LISTENING:
            self.state_banner.setText(spaced)
            self.state_banner.setStyleSheet("color: #00E5FF; font-size: 13px; font-weight: 800; letter-spacing: 3px; background: rgba(0, 229, 255, 0.14); border: 1px solid #00E5FF; border-radius: 14px; padding: 4px 20px;")
            self.add_activity_event("voice input captured")
        elif state == DenverState.PROCESSING:
            self.state_banner.setText(spaced)
            self.state_banner.setStyleSheet("color: #F59E0B; font-size: 13px; font-weight: 800; letter-spacing: 3px; background: rgba(245, 158, 11, 0.14); border: 1px solid #F59E0B; border-radius: 14px; padding: 4px 20px;")
            self.add_activity_event("intent resolved")
        elif state == DenverState.EXECUTING:
            self.state_banner.setText(spaced)
            self.state_banner.setStyleSheet("color: #10B981; font-size: 13px; font-weight: 800; letter-spacing: 3px; background: rgba(16, 185, 129, 0.14); border: 1px solid #10B981; border-radius: 14px; padding: 4px 20px;")
            self.add_activity_event("executing task")
        elif state == DenverState.SPEAKING:
            self.state_banner.setText(spaced)
            self.state_banner.setStyleSheet("color: #C084FC; font-size: 13px; font-weight: 800; letter-spacing: 3px; background: rgba(192, 132, 252, 0.14); border: 1px solid #C084FC; border-radius: 14px; padding: 4px 20px;")
        elif state == DenverState.ERROR:
            self.state_banner.setText(spaced)
            self.state_banner.setStyleSheet("color: #EF4444; font-size: 13px; font-weight: 800; letter-spacing: 3px; background: rgba(239, 68, 68, 0.14); border: 1px solid #EF4444; border-radius: 14px; padding: 4px 20px;")
        else:
            self.state_banner.setText("S T A N D B Y")
            self.state_banner.setStyleSheet("color: #38BDF8; font-size: 13px; font-weight: 800; letter-spacing: 3px; background: rgba(56, 189, 248, 0.10); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 14px; padding: 4px 20px;")

    def _poll_hardware(self) -> None:
        """Poll live CPU and RAM percentages."""
        try:
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory().percent
            self.cpu_card.set_value(f"{round(cpu)}%")
            self.mem_card.set_value(f"{round(mem)}%")
        except Exception:
            pass

    def update_telemetry(self, cpu_pct: float | None = None, mem_pct: float | None = None, latency_ms: float | None = None, model: str | None = None) -> None:
        if cpu_pct is not None:
            self.cpu_card.set_value(f"{round(cpu_pct)}%")
        if mem_pct is not None:
            self.mem_card.set_value(f"{round(mem_pct)}%")
        if latency_ms is not None:
            self.latency_card.set_value(f"{round(latency_ms)}ms")
        if model is not None:
            self.model_card.set_value(model)

    def _on_submit(self) -> None:
        text = self.prompt_edit.text().strip()
        if not text:
            return
        self.prompt_edit.clear()
        self.command_submitted.emit(text)
        self.add_activity_event(f"command submitted: {text}")
        if self.controller:
            self.controller.submit_command(text)

    def _toggle_voice(self) -> None:
        self.voice_toggled.emit()
        if self.controller and hasattr(self.controller, "toggle_voice_listening"):
            self.controller.toggle_voice_listening()
        elif self.controller:
            self.controller.submit_command("Denver, listen")

    def _bind_controller(self) -> None:
        if not self.controller or not hasattr(self.controller, "bridge") or not self.controller.bridge:
            return
        bridge = self.controller.bridge
        if hasattr(bridge, "state_changed"):
            bridge.state_changed.connect(lambda state, reason: self.set_state(state))
        if hasattr(bridge, "activity_added"):
            bridge.activity_added.connect(self._on_activity_added)

    def _on_activity_added(self, item: Any) -> None:
        action = getattr(item, "action_name", "") or "action"
        success = getattr(item, "success", True)
        status_suffix = "completed" if success else "failed"
        self.add_activity_event(f"{action} {status_suffix}")

        latency_ms = getattr(item, "latency_ms", None)
        if latency_ms:
            self.latency_card.set_value(f"{round(latency_ms)}ms")
