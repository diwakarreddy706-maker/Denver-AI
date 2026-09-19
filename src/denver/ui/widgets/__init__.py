"""Denver Cockpit Widgets."""

from __future__ import annotations

from denver.ui.widgets.activity_panel import ActivityItemCard, ActivityPanelWidget
from denver.ui.widgets.automation_status import AutomationBadge, AutomationStatusWidget
from denver.ui.widgets.command_input import CommandInputWidget
from denver.ui.widgets.confirmation_dialog import SecurityConfirmationDialog
from denver.ui.widgets.core_visualizer import DenverCoreVisualizer
from denver.ui.widgets.home_dashboard import (
    AIStatusCard,
    BottomBarWidget,
    DenverDashboardOverlay,
    DenverHomeTabWidget,
    LiveClockCard,
    QuickActionsCard,
    QuickStatusCard,
    SpotifyMediaCard,
    SystemPerformanceCard,
    WeatherCard,
)
from denver.ui.widgets.ai_orb import DenverAIOrbWidget
from denver.ui.widgets.hud_panels import (
    DenverHUDPanelStack,
    HUDAIStatusCard,
    HUDClockCard,
    HUDQuickStatusCard,
    HUDSystemPerformanceCard,
)
from denver.ui.widgets.memory_status import MemoryStatusWidget
from denver.ui.widgets.plugins_widget import PluginCardWidget, PluginsWidget
from denver.ui.widgets.provider_status import ProviderRow, ProviderStatusWidget
from denver.ui.widgets.routines_widget import ScheduledRoutinesWidget
from denver.ui.widgets.settings_dialog import SettingsDialog
from denver.ui.widgets.sidebar import DenverSidebarWidget
from denver.ui.widgets.tasks_widget import TasksOrchestrationWidget
from denver.ui.widgets.telemetry_panel import TelemetryCard, TelemetryPanelWidget
from denver.ui.widgets.voice_status import VoiceStatusWidget

__all__ = [
    "AIStatusCard",
    "ActivityItemCard",
    "ActivityPanelWidget",
    "AutomationBadge",
    "AutomationStatusWidget",
    "BottomBarWidget",
    "CommandInputWidget",
    "DenverAIOrbWidget",
    "DenverCoreVisualizer",
    "DenverDashboardOverlay",
    "DenverHUDPanelStack",
    "DenverHomeTabWidget",
    "DenverSidebarWidget",
    "HUDAIStatusCard",
    "HUDClockCard",
    "HUDQuickStatusCard",
    "HUDSystemPerformanceCard",
    "LiveClockCard",
    "MemoryStatusWidget",
    "PluginCardWidget",
    "PluginsWidget",
    "ProviderRow",
    "ProviderStatusWidget",
    "QuickActionsCard",
    "QuickStatusCard",
    "ScheduledRoutinesWidget",
    "SecurityConfirmationDialog",
    "SettingsDialog",
    "SpotifyMediaCard",
    "SystemPerformanceCard",
    "TasksOrchestrationWidget",
    "TelemetryCard",
    "TelemetryPanelWidget",
    "VoiceStatusWidget",
    "WeatherCard",
]

