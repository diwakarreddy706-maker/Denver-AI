"""Live System Telemetry Monitor Panel Widget with Auto-Repair Controls."""

from __future__ import annotations

from typing import Any

try:
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtWidgets import (
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QProgressBar,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
    _PYSIDE_AVAILABLE = True
except ImportError:
    _PYSIDE_AVAILABLE = False
    QWidget = object  # type: ignore
    Signal = lambda *args: None  # type: ignore

from denver.ui.state import CockpitState
from denver.ui.theme import (
    BG_PANEL,
    BORDER_SUBTLE,
    PRIMARY_BLUE,
    PRIMARY_CYAN,
    STATUS_DANGER,
    STATUS_SUCCESS,
    STATUS_WARNING,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


class TelemetryCard(QFrame):
    """Compact cyber metric card with primary numerical value and slim visual bar."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("TelemetryCard")
        self.setMinimumHeight(84)
        self.setStyleSheet(f"""
            QFrame#TelemetryCard {{
                background-color: {BG_PANEL};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: 8px;
            }}
            QFrame#TelemetryCard:hover {{
                border: 1px solid {PRIMARY_CYAN};
                background-color: rgba(17, 24, 39, 0.98);
            }}
        """)
        self._init_ui(title)

    def _init_ui(self, title: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        # Top row: Metric Title + Unit tag
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(4)
        title_lbl = QLabel(title.upper())
        title_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; font-weight: 700; letter-spacing: 1px;")
        top_row.addWidget(title_lbl)
        top_row.addStretch()
        layout.addLayout(top_row)

        # Middle row: Large prominent numerical value
        self.value_lbl = QLabel("N/A")
        self.value_lbl.setMinimumHeight(24)
        self.value_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 16px; font-weight: 800; letter-spacing: 0.5px; padding: 0px;")
        layout.addWidget(self.value_lbl)

        # Progress bar indicator
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: rgba(30, 41, 59, 0.6);
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {PRIMARY_CYAN};
                border-radius: 2px;
            }}
        """)
        layout.addWidget(self.progress_bar)

        # Bottom row: Context subtext
        self.subtext_lbl = QLabel("")
        self.subtext_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px; font-weight: 500;")
        layout.addWidget(self.subtext_lbl)

    def set_data(self, value_text: str, percent: int | None = None, subtext: str = "") -> None:
        self.value_lbl.setText(value_text)
        self.subtext_lbl.setText(subtext)
        if percent is not None:
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(min(100, max(0, percent)))
            color = STATUS_SUCCESS if percent < 75 else (STATUS_WARNING if percent < 90 else STATUS_DANGER)
            self.progress_bar.setStyleSheet(f"""
                QProgressBar {{
                    background-color: rgba(30, 41, 59, 0.6);
                    border: none;
                    border-radius: 2px;
                }}
                QProgressBar::chunk {{
                    background-color: {color};
                    border-radius: 2px;
                }}
            """)
        else:
            self.progress_bar.setVisible(False)


class TelemetryPanelWidget(QWidget):
    """Compact grid of live telemetry cards with 1-click Auto-Repair and database health controls."""

    if _PYSIDE_AVAILABLE:
        repair_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        if not _PYSIDE_AVAILABLE:
            return

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Header with Auto Repair trigger
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(6)

        header_lbl = QLabel("SYSTEM TELEMETRY & HEALTH")
        header_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px; font-weight: 700; letter-spacing: 1.2px;")
        header_row.addWidget(header_lbl)

        header_row.addStretch()

        self.repair_btn = QPushButton("🛠 AUTO REPAIR")
        self.repair_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.repair_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(6, 182, 212, 0.12);
                color: {PRIMARY_CYAN};
                border: 1px solid rgba(6, 182, 212, 0.4);
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 9px;
                font-weight: 700;
            }}
            QPushButton:hover {{
                background-color: rgba(6, 182, 212, 0.25);
                border: 1px solid {PRIMARY_CYAN};
            }}
        """)
        self.repair_btn.clicked.connect(self._on_repair_clicked)
        header_row.addWidget(self.repair_btn)

        layout.addLayout(header_row)

        grid = QGridLayout()
        grid.setSpacing(6)

        self.cpu_card = TelemetryCard("CPU LOAD")
        grid.addWidget(self.cpu_card, 0, 0)

        self.ram_card = TelemetryCard("RAM USAGE")
        grid.addWidget(self.ram_card, 0, 1)

        self.battery_card = TelemetryCard("BATTERY")
        grid.addWidget(self.battery_card, 1, 0)

        self.uptime_card = TelemetryCard("UPTIME")
        grid.addWidget(self.uptime_card, 1, 1)

        layout.addLayout(grid)

        # SQLite Health / Maintenance Sub-bar
        self.health_bar = QFrame()
        self.health_bar.setStyleSheet(f"background-color: {BG_PANEL}; border: 1px solid {BORDER_SUBTLE}; border-radius: 6px; padding: 4px 8px;")
        h_layout = QHBoxLayout(self.health_bar)
        h_layout.setContentsMargins(4, 2, 4, 2)
        h_layout.setSpacing(6)

        self.db_status_lbl = QLabel("● SQLite: HEALTHY (WAL)")
        self.db_status_lbl.setStyleSheet(f"color: {STATUS_SUCCESS}; font-size: 10px; font-weight: 600;")
        h_layout.addWidget(self.db_status_lbl)

        h_layout.addStretch()

        self.repair_status_lbl = QLabel("Self-healing ready")
        self.repair_status_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 9px; font-weight: 500;")
        h_layout.addWidget(self.repair_status_lbl)

        layout.addWidget(self.health_bar)

    def _on_repair_clicked(self) -> None:
        self.repair_status_lbl.setText("Running repair...")
        self.repair_status_lbl.setStyleSheet(f"color: {PRIMARY_CYAN}; font-size: 9px; font-weight: 700;")
        if hasattr(self, "repair_requested"):
            self.repair_requested.emit()

    def set_repair_result(self, fixed_count: int, detected_count: int) -> None:
        """Update the repair status label with results."""
        if not _PYSIDE_AVAILABLE:
            return
        if fixed_count > 0:
            self.repair_status_lbl.setText(f"Repaired {fixed_count} issue(s)")
            self.repair_status_lbl.setStyleSheet(f"color: {STATUS_SUCCESS}; font-size: 9px; font-weight: 700;")
        elif detected_count == 0:
            self.repair_status_lbl.setText("All systems optimal")
            self.repair_status_lbl.setStyleSheet(f"color: {STATUS_SUCCESS}; font-size: 9px; font-weight: 600;")
        else:
            self.repair_status_lbl.setText(f"{detected_count} issue(s) detected")
            self.repair_status_lbl.setStyleSheet(f"color: {STATUS_WARNING}; font-size: 9px; font-weight: 600;")

    def update_telemetry(self, state: CockpitState) -> None:
        """Refresh cards from live CockpitState values."""
        if not _PYSIDE_AVAILABLE:
            return

        # CPU
        if state.cpu_percent is not None:
            self.cpu_card.set_data(f"{state.cpu_percent:.1f}%", int(state.cpu_percent), "Processor Load")
        else:
            self.cpu_card.set_data("N/A", None, "Telemetry Unavailable")

        # RAM
        if state.ram_percent is not None:
            sub = f"{state.ram_used_gb:.1f} / {state.ram_total_gb:.1f} GB" if state.ram_used_gb and state.ram_total_gb else "Memory Load"
            self.ram_card.set_data(f"{state.ram_percent:.1f}%", int(state.ram_percent), sub)
        else:
            self.ram_card.set_data("N/A", None, "Memory Unavailable")

        # Battery
        if state.battery_percent is not None:
            status_desc = "Plugged In" if state.battery_charging else "On Battery"
            self.battery_card.set_data(f"{state.battery_percent}%", state.battery_percent, status_desc)
        else:
            self.battery_card.set_data("AC Power", None, "Desktop / Direct AC")

        # Uptime
        self.uptime_card.set_data(state.uptime_formatted, None, f"{state.uptime_seconds:.0f}s active")
