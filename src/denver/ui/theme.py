"""Denver Cyber-Command-Center Design System & Stylesheet for Denver Cockpit."""

from __future__ import annotations

# ============================================================================
# Color Palette Constants (Cyber Command Center Aesthetic)
# ============================================================================
BG_ROOT = "#070B14"
BG_SURFACE = "#0F172A"
BG_PANEL = "#111827"
BG_PANEL_ALT = "#1E293B"
BG_GLASS = "rgba(17, 24, 39, 0.90)"
BG_INPUT = "#0A0F1D"

BORDER_SUBTLE = "#1E293B"
BORDER_ACCENT = "#3B82F6"
BORDER_CYAN = "#06B6D4"
BORDER_PURPLE = "#8B6CF6"

PRIMARY_BLUE = "#3B82F6"
PRIMARY_CYAN = "#06B6D4"
PRIMARY_PURPLE = "#8B6CF6"

STATUS_SUCCESS = "#22C55E"
STATUS_WARNING = "#F59E0B"
STATUS_DANGER = "#EF4444"
STATUS_MUTED = "#64748B"

TEXT_PRIMARY = "#F8FAFC"
TEXT_SECONDARY = "#94A3B8"
TEXT_MUTED = "#64748B"
TEXT_CYAN = "#38BDF8"

# Dashboard & Cyber Card Tokens (Glassmorphic HUD Design System)
BG_APP = "#060A13"
BG_SIDEBAR = "#080E1B"
BG_OVERLAY_GRADIENT = "qradialgradient(cx: 0.5, cy: 0.45, radius: 0.85, fx: 0.5, fy: 0.45, stop: 0 #0c1833, stop: 0.5 #080e1e, stop: 1 #04070e)"
CARD_BG = "rgba(13, 20, 36, 0.78)"
CARD_BG_GLASS = "rgba(11, 18, 33, 0.72)"
CARD_BG_GRADIENT = "qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 rgba(18, 28, 52, 0.85), stop: 1 rgba(10, 16, 30, 0.90))"
CARD_BG_HOVER = "qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 rgba(22, 36, 66, 0.90), stop: 1 rgba(12, 20, 38, 0.94))"
CARD_BORDER = "rgba(56, 189, 248, 0.18)"
CARD_BORDER_HOVER = "rgba(6, 182, 212, 0.75)"
CARD_BORDER_PURPLE = "rgba(139, 92, 246, 0.50)"
CARD_GLOW_COLOR = "rgba(6, 182, 212, 0.30)"
GRADIENT_TEAL = "qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, stop: 0 #06b6d4, stop: 1 #0284c7)"
GRADIENT_BLUE = "qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, stop: 0 #3b82f6, stop: 1 #1d4ed8)"
GRADIENT_PURPLE_CYAN = "qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, stop: 0 #38BDF8, stop: 1 #A855F7)"
GRADIENT_BTN_TASK = "qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, stop: 0 #2563EB, stop: 1 #1D4ED8)"
GRADIENT_BTN_REMINDER = "qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, stop: 0 #0D9488, stop: 1 #0F766E)"
GRADIENT_BTN_CALENDAR = "qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, stop: 0 #7C3AED, stop: 1 #6D28D9)"
GRADIENT_BTN_NOTES = "qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, stop: 0 #1E40AF, stop: 1 #1E3A8A)"
GRADIENT_SEND_BTN = "qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, stop: 0 #38BDF8, stop: 1 #6366F1)"
BOTTOM_BAR_BG = "rgba(6, 10, 19, 0.96)"
BOTTOM_BAR_BORDER = "rgba(30, 41, 59, 0.7)"

# ============================================================================
# Cyber-Command-Center QSS Stylesheet
# ============================================================================
COCKPIT_STYLESHEET = f"""
/* Root Window Styling */
QMainWindow, QWidget#CockpitRoot {{
    background-color: {BG_ROOT};
    color: {TEXT_PRIMARY};
    font-family: 'Segoe UI', 'SF Pro Display', -apple-system, sans-serif;
}}

/* Top Navigation & Status Bar */
QWidget#TopBar {{
    background-color: {BG_SURFACE};
    border-bottom: 1px solid {BORDER_SUBTLE};
    border-radius: 8px;
    padding: 6px 14px;
}}

QLabel#TitleLabel {{
    color: {TEXT_PRIMARY};
    font-size: 16px;
    font-weight: 800;
    letter-spacing: 2px;
}}

QLabel#SubtitleLabel {{
    color: {TEXT_CYAN};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
}}

/* Cyber Cards & Panels */
QFrame.CyberPanel {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 8px;
    padding: 10px;
}}

QFrame.CyberPanel:hover {{
    border: 1px solid {BORDER_ACCENT};
}}

QLabel.PanelHeader {{
    color: {TEXT_SECONDARY};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    margin-bottom: 4px;
}}

/* Metric Cards & Labels */
QLabel.MetricValue {{
    color: {TEXT_PRIMARY};
    font-size: 17px;
    font-weight: 800;
    letter-spacing: 0.5px;
}}

QLabel.MetricSubtext {{
    color: {TEXT_MUTED};
    font-size: 10px;
    font-weight: 500;
}}

/* Status Indicator Pills */
QLabel.StatusPillReady {{
    background-color: rgba(34, 197, 94, 0.12);
    color: {STATUS_SUCCESS};
    border: 1px solid rgba(34, 197, 94, 0.4);
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.8px;
}}

QLabel.StatusPillWarning {{
    background-color: rgba(245, 158, 11, 0.12);
    color: {STATUS_WARNING};
    border: 1px solid rgba(245, 158, 11, 0.4);
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.8px;
}}

QLabel.StatusPillDanger {{
    background-color: rgba(239, 68, 68, 0.12);
    color: {STATUS_DANGER};
    border: 1px solid rgba(239, 68, 68, 0.4);
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.8px;
}}

QLabel.StatusPillMuted {{
    background-color: rgba(100, 116, 139, 0.12);
    color: {STATUS_MUTED};
    border: 1px solid rgba(100, 116, 139, 0.4);
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.8px;
}}

/* Command Input Bar */
QLineEdit#CommandInput {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 13px;
    selection-background-color: {PRIMARY_BLUE};
}}

QLineEdit#CommandInput:focus {{
    border: 1px solid {PRIMARY_CYAN};
    background-color: #0c1424;
}}

QPushButton#SendButton {{
    background-color: {PRIMARY_BLUE};
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    padding: 10px 20px;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1px;
}}

QPushButton#SendButton:hover {{
    background-color: #2563eb;
}}

QPushButton#SendButton:pressed {{
    background-color: #1d4ed8;
}}

/* Quick Action Chips */
QPushButton.QuickChip {{
    background-color: {BG_SURFACE};
    color: {TEXT_SECONDARY};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 12px;
    padding: 4px 12px;
    font-size: 11px;
    font-weight: 600;
}}

QPushButton.QuickChip:hover {{
    background-color: {BG_PANEL_ALT};
    color: {TEXT_PRIMARY};
    border: 1px solid {PRIMARY_CYAN};
}}

/* Activity Feed & Scroll Area */
QScrollArea {{
    background: transparent;
    border: none;
}}

QScrollBar:vertical {{
    background: {BG_ROOT};
    width: 6px;
    border-radius: 3px;
}}

QScrollBar::handle:vertical {{
    background: {BORDER_SUBTLE};
    min-height: 24px;
    border-radius: 3px;
}}

QScrollBar::handle:vertical:hover {{
    background: {PRIMARY_BLUE};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

/* Tabbed Command Hub */
QTabWidget::pane {{
    border: 1px solid {BORDER_SUBTLE};
    background-color: {BG_SURFACE};
    border-radius: 8px;
    top: -1px;
}}

QTabBar::tab {{
    background-color: {BG_INPUT};
    color: {TEXT_SECONDARY};
    border: 1px solid {BORDER_SUBTLE};
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 8px 16px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.8px;
    margin-right: 4px;
}}

QTabBar::tab:selected {{
    background-color: {BG_SURFACE};
    color: {TEXT_CYAN};
    border-top: 2px solid {PRIMARY_CYAN};
    border-left: 1px solid {BORDER_SUBTLE};
    border-right: 1px solid {BORDER_SUBTLE};
}}

QTabBar::tab:hover:!selected {{
    background-color: {BG_PANEL_ALT};
    color: {TEXT_PRIMARY};
}}

/* Dialog Windows */
QDialog {{
    background-color: {BG_SURFACE};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 8px;
}}

QPushButton.DialogButtonPrimary {{
    background-color: {PRIMARY_BLUE};
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 12px;
    font-weight: 600;
}}

QPushButton.DialogButtonDanger {{
    background-color: {STATUS_DANGER};
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 12px;
    font-weight: 600;
}}

QPushButton.DialogButtonSecondary {{
    background-color: {BG_PANEL_ALT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 12px;
}}
"""
