"""Denver Cockpit Widgets."""

from __future__ import annotations

from denver.ui.widgets.activity_panel import ActivityItemCard, ActivityPanelWidget
from denver.ui.widgets.automation_status import AutomationBadge, AutomationStatusWidget
from denver.ui.widgets.command_input import CommandInputWidget
from denver.ui.widgets.confirmation_dialog import SecurityConfirmationDialog
from denver.ui.widgets.core_visualizer import DenverCoreVisualizer
from denver.ui.widgets.memory_status import MemoryStatusWidget
from denver.ui.widgets.plugins_widget import PluginCardWidget, PluginsWidget
from denver.ui.widgets.provider_status import ProviderRow, ProviderStatusWidget
from denver.ui.widgets.routines_widget import ScheduledRoutinesWidget
from denver.ui.widgets.settings_dialog import SettingsDialog
from denver.ui.widgets.tasks_widget import TasksOrchestrationWidget
from denver.ui.widgets.telemetry_panel import TelemetryCard, TelemetryPanelWidget
from denver.ui.widgets.voice_status import VoiceStatusWidget

__all__ = [
    "ActivityItemCard",
    "ActivityPanelWidget",
    "AutomationBadge",
    "AutomationStatusWidget",
    "CommandInputWidget",
    "DenverCoreVisualizer",
    "MemoryStatusWidget",
    "PluginCardWidget",
    "PluginsWidget",
    "ProviderRow",
    "ProviderStatusWidget",
    "ScheduledRoutinesWidget",
    "SecurityConfirmationDialog",
    "SettingsDialog",
    "TasksOrchestrationWidget",
    "TelemetryCard",
    "TelemetryPanelWidget",
    "VoiceStatusWidget",
]
