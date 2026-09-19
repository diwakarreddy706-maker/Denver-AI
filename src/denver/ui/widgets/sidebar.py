"""Denver AI Assistant — Left Navigation & Quick Actions Sidebar."""

from __future__ import annotations

from typing import Any

try:
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtWidgets import (
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
    _PYSIDE_AVAILABLE = True
except ImportError:
    _PYSIDE_AVAILABLE = False
    QWidget = object  # type: ignore

from denver.logging.logger import get_logger
from denver.ui.controller import UIController
from denver.ui.theme import (
    BORDER_SUBTLE,
    GRADIENT_BTN_CALENDAR,
    GRADIENT_BTN_NOTES,
    GRADIENT_BTN_REMINDER,
    GRADIENT_BTN_TASK,
    PRIMARY_CYAN,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

logger = get_logger("ui.sidebar")


class DenverSidebarWidget(QWidget):
    """Left navigation sidebar matching reference SaaS dashboard design."""

    nav_selected = Signal(str)
    action_triggered = Signal(str)

    def __init__(self, controller: UIController | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setFixedWidth(184)
        self.setObjectName("DenverSidebar")
        self.setStyleSheet("""
            QWidget#DenverSidebar {
                background-color: rgba(8, 14, 28, 0.65);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 16px;
            }
        """)
        self._init_ui()

    def _init_ui(self) -> None:
        if not _PYSIDE_AVAILABLE:
            return

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 16, 10, 16)
        layout.setSpacing(6)

        # 1. Main Navigation Items
        self.nav_btns: dict[str, QPushButton] = {}
        nav_items = [
            ("Home", "⌂", True),
            ("Assistant", "💬", False),
            ("Files", "📁", False),
            ("Tools", "⊞", False),
            ("Settings", "⚙", False),
        ]

        for name, icon, is_active in nav_items:
            btn = self._create_nav_button(name, icon, is_active)
            self.nav_btns[name] = btn
            layout.addWidget(btn)

        layout.addStretch(1)

        # 2. Quick Actions Section
        qa_header = QHBoxLayout()
        qa_header.setSpacing(6)
        qa_icon = QLabel("⚡")
        qa_icon.setStyleSheet(f"color: {PRIMARY_CYAN}; font-size: 13px;")
        qa_title = QLabel("Quick Actions")
        qa_title.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px; font-weight: 700; letter-spacing: 0.3px;")
        qa_header.addWidget(qa_icon)
        qa_header.addWidget(qa_title)
        qa_header.addStretch()
        layout.addLayout(qa_header)

        # 2x2 Gradient Buttons Grid
        grid = QGridLayout()
        grid.setSpacing(8)

        self.btn_task = self._create_action_card("New Task", "📝", "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1E40AF, stop:1 #2563EB)")
        self.btn_task.clicked.connect(self._on_new_task)
        grid.addWidget(self.btn_task, 0, 0)

        self.btn_reminder = self._create_action_card("Reminder", "📅", "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0D9488, stop:1 #06B6D4)")
        self.btn_reminder.clicked.connect(self._on_new_reminder)
        grid.addWidget(self.btn_reminder, 0, 1)

        self.btn_calendar = self._create_action_card("Calendar", "📅", "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #6D28D9, stop:1 #8B5CF6)")
        self.btn_calendar.clicked.connect(self._on_calendar)
        grid.addWidget(self.btn_calendar, 1, 0)

        self.btn_notes = self._create_action_card("Notes", "📄", "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1E3A8A, stop:1 #3B82F6)")
        self.btn_notes.clicked.connect(self._on_notes)
        grid.addWidget(self.btn_notes, 1, 1)

        layout.addLayout(grid)

    def _create_nav_button(self, name: str, icon: str, is_active: bool) -> QPushButton:
        btn = QPushButton(f"  {icon}   {name}")
        btn.setFixedHeight(38)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)

        if is_active:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(0, 180, 255, 0.28), stop:1 rgba(139, 92, 246, 0.12));
                    color: #FFFFFF;
                    border: none;
                    border-left: 3px solid #00E5FF;
                    border-radius: 8px;
                    font-size: 12px;
                    font-weight: 700;
                    text-align: left;
                    padding-left: 10px;
                }}
            """)
        else:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {TEXT_SECONDARY};
                    border: none;
                    border-left: 3px solid transparent;
                    border-radius: 8px;
                    font-size: 12px;
                    font-weight: 600;
                    text-align: left;
                    padding-left: 10px;
                }}
                QPushButton:hover {{
                    background: rgba(30, 41, 59, 0.45);
                    color: {TEXT_PRIMARY};
                }}
            """)

        btn.clicked.connect(lambda _, n=name: self._on_nav_clicked(n))
        return btn

    def _on_nav_clicked(self, name: str) -> None:
        for n, b in self.nav_btns.items():
            is_active = (n == name)
            if is_active:
                b.setStyleSheet(f"""
                    QPushButton {{
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(0, 180, 255, 0.28), stop:1 rgba(139, 92, 246, 0.12));
                        color: #FFFFFF;
                        border: none;
                        border-left: 3px solid #00E5FF;
                        border-radius: 8px;
                        font-size: 12px;
                        font-weight: 700;
                        text-align: left;
                        padding-left: 10px;
                    }}
                """)
            else:
                b.setStyleSheet(f"""
                    QPushButton {{
                        background: transparent;
                        color: {TEXT_SECONDARY};
                        border: none;
                        border-left: 3px solid transparent;
                        border-radius: 8px;
                        font-size: 12px;
                        font-weight: 600;
                        text-align: left;
                        padding-left: 10px;
                    }}
                    QPushButton:hover {{
                        background: rgba(30, 41, 59, 0.45);
                        color: {TEXT_PRIMARY};
                    }}
                """)
        self.nav_selected.emit(name)

    def _create_action_card(self, title: str, icon: str, gradient: str) -> QPushButton:
        btn = QPushButton(f"{icon}\n{title}")
        btn.setFixedSize(78, 62)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {gradient};
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 12px;
                font-size: 10px;
                font-weight: 700;
                line-height: 1.3;
                padding: 4px;
            }}
            QPushButton:hover {{
                border: 1px solid rgba(255, 255, 255, 0.45);
            }}
            QPushButton:pressed {{
                background: rgba(14, 165, 233, 0.85);
            }}
        """)
        return btn

    def _on_new_task(self) -> None:
        logger.info("Sidebar action: New Task")
        self.action_triggered.emit("new_task")
        if self.controller:
            self.controller.submit_command("create task New Task")

    def _on_new_reminder(self) -> None:
        logger.info("Sidebar action: Reminder")
        self.action_triggered.emit("reminder")
        if self.controller:
            self.controller.submit_command("create reminder in 10 minutes Check progress")

    def _on_calendar(self) -> None:
        logger.info("Sidebar action: Calendar")
        self.action_triggered.emit("calendar")
        if self.controller:
            self.controller.submit_command("show calendar")

    def _on_notes(self) -> None:
        logger.info("Sidebar action: Notes")
        self.action_triggered.emit("notes")
        if self.controller:
            self.controller.submit_command("create note Quick Note: Added from dashboard")
