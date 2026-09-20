"""Unified Command Engine Service for Denver AI Assistant."""

from __future__ import annotations

import datetime
import re
import time
from typing import Any

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False

from denver.automation.executor import AutomationExecutor
from denver.automation.models import AutomationRequest
from denver.commands.executor import ActionExecutor
from denver.commands.models import (
    ActionRequest,
    ActionResult,
    CommandCategory,
    CommandContext,
    CommandIntent,
    CommandRequest,
    CommandResponse,
    CommandRiskLevel,
)
from denver.commands.normalizer import CommandNormalizer
from denver.commands.registry import ActionDefinition, ActionRegistry
from denver.commands.router import IntentRouter
from denver.commands.safety import SafetyValidator
from denver.config.settings import DenverSettings, get_settings
from denver.context.budget import ContextBudgetConfig
from denver.context.engine import ContextEngine
from denver.context.models import ContextBundle
from denver.logging.logger import get_logger
from denver.memory.memory_service import MemoryService
from denver.memory.models import MemoryCategory, PrivacyLevel
from denver.providers.models import ProviderRequest, ToolDefinition, ToolParameter
from denver.providers.router import ProviderRouter

from denver.runtime.event_bus import DenverEventBus, get_event_bus
from denver.runtime.events import (
    AirGappedModeChanged,
    CommandExecutionCompleted,
    CommandExecutionStarted,
    CommandFailed,
    CommandNormalized,
    CommandReceived,
    CommandRouted,
    ProviderModeChanged,
    SpotifyPlaybackChanged,
)
from denver.runtime.state_machine import DenverStateMachine
from denver.runtime.states import DenverState
from denver.utils.logging_helpers import mask_phone

logger = get_logger("command_engine")


class CommandEngineService:
    """Core command processing engine orchestrating normalization, routing, safety, and action execution."""

    def __init__(
        self,
        memory_service: MemoryService,
        state_machine: DenverStateMachine | None = None,
        event_bus: DenverEventBus | None = None,
        settings: DenverSettings | None = None,
        provider_router: ProviderRouter | None = None,
        automation_executor: AutomationExecutor | None = None,
        scheduler: Any | None = None,
        routine_registry: Any | None = None,
        task_registry: Any | None = None,
        workflow_engine: Any | None = None,
    ) -> None:
        self.memory = memory_service
        self.state_machine = state_machine
        self.event_bus = event_bus or get_event_bus()
        self.settings = settings or get_settings()
        self.provider_router = provider_router
        self.scheduler = scheduler
        self.routine_registry = routine_registry
        self.task_registry = task_registry
        self.workflow_engine = workflow_engine
        self._is_sleeping = False

        self.normalizer = CommandNormalizer(assistant_name=self.settings.assistant_name)
        self.router = IntentRouter()
        self.registry = ActionRegistry()
        self.safety = SafetyValidator(allow_destructive_actions=self.settings.allow_destructive_actions)
        self.executor = ActionExecutor(self.registry)
        self.automation = automation_executor or AutomationExecutor(
            event_bus=self.event_bus,
            allow_high_risk_actions=self.settings.allow_high_risk_actions,
        )
        self.context_engine = ContextEngine(
            memory_service=self.memory,
            event_bus=self.event_bus,
            budget_config=ContextBudgetConfig(
                max_turns=self.settings.context_max_turns,
                max_chars=self.settings.context_max_chars,
                max_memories=self.settings.memory_top_k,
                allow_private_cloud=self.settings.allow_private_cloud_context,
                allow_sensitive_cloud=self.settings.allow_sensitive_cloud_context,
            ),
        )
        from denver.automation.vision import VisionEngine
        self.vision_engine = VisionEngine(
            screenshot_controller=getattr(self.automation, "screenshot", None),
            output_dir=getattr(self.settings, "screenshot_dir", "data/screenshots"),
        )
        from denver.audio.meeting import MeetingIntelligenceEngine
        self.meeting_engine = MeetingIntelligenceEngine(
            user_name=getattr(self.settings, "user_name", "Diwakar") or "Diwakar",
            output_dir=getattr(self.settings, "meetings_dir", "data/meetings"),
        )
        from denver.proactive.engine import ProactiveIntelligenceEngine
        self.proactive_engine = ProactiveIntelligenceEngine(
            event_bus=self.event_bus,
            enabled=getattr(self.settings, "proactive_mode_enabled", True),
        )
        from denver.automation.web_agent import WebAgent
        self.web_agent = WebAgent(
            output_dir=getattr(self.settings, "web_screenshots_dir", "data/screenshots/web"),
        )
        from denver.automation.location import LocationService
        self.location_service = LocationService(
            settings=self.settings,
            memory_service=self.memory,
        )
        from denver.automation.weather import WeatherService
        self.weather_service = WeatherService(
            settings=self.settings,
            web_agent=self.web_agent,
            location_service=self.location_service,
        )
        from denver.automation.navigation import NavigationService
        self.navigation_service = NavigationService(
            settings=self.settings,
            weather_service=self.weather_service,
            location_service=self.location_service,
        )
        from denver.plugins.loader import PluginRegistry
        self.plugin_registry = PluginRegistry()
        try:
            self.plugin_registry.discover_and_load_all()
        except Exception as exc:
            logger.debug("Plugin initial scan note: %s", exc)
        from denver.automation.spotify import SpotifyController
        self.spotify_controller = SpotifyController()


        self._register_default_actions()


    def _register_default_actions(self) -> None:
        """Register all built-in deterministic action handlers."""
        # 1. Utilities
        self.registry.register(
            ActionDefinition(
                name="assistant_call",
                description="Responds promptly when user addresses Denver.",
                category=CommandCategory.UTILITY,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_assistant_call,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="get_time",
                description="Queries the current system time.",
                category=CommandCategory.UTILITY,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_get_time,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="get_date",
                description="Queries the current calendar date.",
                category=CommandCategory.UTILITY,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_get_date,
            )
        )

        # 2. System Telemetry & Control
        self.registry.register(
            ActionDefinition(
                name="get_system_status",
                description="Retrieves overall system status and readiness.",
                category=CommandCategory.SYSTEM,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_get_system_status,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="get_cpu",
                description="Measures current CPU load percentage.",
                category=CommandCategory.SYSTEM,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_get_cpu,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="get_ram",
                description="Measures current RAM memory utilization.",
                category=CommandCategory.SYSTEM,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_get_ram,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="get_battery",
                description="Queries system battery status.",
                category=CommandCategory.SYSTEM,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_get_battery,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="get_battery_status",
                description="Queries system battery status.",
                category=CommandCategory.SYSTEM,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_get_battery,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="get_system_summary",
                description="Retrieves comprehensive hardware, OS, and system status telemetry.",
                category=CommandCategory.SYSTEM,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_get_system_summary,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="lock_workstation",
                description="Locks the active Windows workstation immediately.",
                category=CommandCategory.SYSTEM,
                risk_level=CommandRiskLevel.HIGH,
                requires_confirmation=False,
                handler=self._handle_lock_workstation,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="enter_sleep_mode",
                description="Puts Denver into dormant sleep mode while keeping background monitoring active.",
                category=CommandCategory.SYSTEM,
                risk_level=CommandRiskLevel.SAFE,
                requires_confirmation=False,
                handler=self._handle_enter_sleep_mode,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="wake_up",
                description="Wakes Denver up from sleep mode into active ready standby.",
                category=CommandCategory.SYSTEM,
                risk_level=CommandRiskLevel.SAFE,
                requires_confirmation=False,
                handler=self._handle_wake_up,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="system_repair",
                description="Diagnoses system health bottlenecks and applies safe automated repairs.",
                category=CommandCategory.SYSTEM,
                risk_level=CommandRiskLevel.LOW,
                requires_confirmation=False,
                handler=self._handle_system_repair,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="set_voice_brevity",
                description="Switches voice response brevity mode between concise and detailed.",
                category=CommandCategory.SYSTEM,
                risk_level=CommandRiskLevel.SAFE,
                requires_confirmation=False,
                handler=self._handle_set_voice_brevity,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="list_plugins",
                description="Lists all installed Denver plugins and active extension states.",
                category=CommandCategory.SYSTEM,
                risk_level=CommandRiskLevel.SAFE,
                requires_confirmation=False,
                handler=self._handle_list_plugins,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="enable_plugin",
                description="Enables an installed Denver plugin.",
                category=CommandCategory.SYSTEM,
                risk_level=CommandRiskLevel.LOW,
                requires_confirmation=False,
                handler=self._handle_enable_plugin,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="disable_plugin",
                description="Disables an installed Denver plugin.",
                category=CommandCategory.SYSTEM,
                risk_level=CommandRiskLevel.LOW,
                requires_confirmation=False,
                handler=self._handle_disable_plugin,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="reload_plugins",
                description="Rescans and reloads all plugins from the plugins directory.",
                category=CommandCategory.SYSTEM,
                risk_level=CommandRiskLevel.LOW,
                requires_confirmation=False,
                handler=self._handle_reload_plugins,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="export_memory",
                description="Exports a sanitized, privacy-safe JSON snapshot of all saved memories.",
                category=CommandCategory.MEMORY,
                risk_level=CommandRiskLevel.SAFE,
                requires_confirmation=False,
                handler=self._handle_export_memory,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="clear_all_notes",
                description="Clears all user notes from persistent storage.",
                category=CommandCategory.MEMORY,
                risk_level=CommandRiskLevel.HIGH,
                requires_confirmation=True,
                handler=self._handle_clear_all_notes,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="list_memories",
                description="Lists all saved notes, memories, and preferences.",
                category=CommandCategory.MEMORY,
                risk_level=CommandRiskLevel.SAFE,
                requires_confirmation=False,
                handler=self._handle_list_memories,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="read_clipboard",
                description="Reads the current text content from the Windows clipboard.",
                category=CommandCategory.UTILITY,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_read_clipboard,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="summarize_clipboard",
                description="Summarizes copied clipboard text using AI intelligence.",
                category=CommandCategory.UTILITY,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_summarize_clipboard,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="type_text",
                description="Types text directly into the active focused desktop window.",
                category=CommandCategory.SYSTEM,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_type_text,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="press_key",
                description="Presses a keyboard key in the active window.",
                category=CommandCategory.SYSTEM,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_press_key,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="scroll_window",
                description="Scrolls the active window up or down.",
                category=CommandCategory.SYSTEM,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_scroll_window,
            )
        )

        # 3. Application Lifecycle
        self.registry.register(
            ActionDefinition(
                name="open_application",
                description="Opens or launches an allowlisted desktop application.",
                category=CommandCategory.APPLICATION,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_open_application,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="close_application",
                description="Closes or terminates a running allowlisted application.",
                category=CommandCategory.APPLICATION,
                risk_level=CommandRiskLevel.MEDIUM,
                handler=self._handle_close_application,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="send_whatsapp_message",
                description="Drafts or sends a WhatsApp message to a specified contact.",
                category=CommandCategory.APPLICATION,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_send_whatsapp_message,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="spotify_play_pause",
                description="Toggles Spotify or system media playback (Play / Pause).",
                category=CommandCategory.APPLICATION,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_spotify_play_pause,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="spotify_next_track",
                description="Skips to the next song or track on Spotify.",
                category=CommandCategory.APPLICATION,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_spotify_next_track,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="spotify_previous_track",
                description="Returns to the previous song or track on Spotify.",
                category=CommandCategory.APPLICATION,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_spotify_previous_track,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="spotify_play_query",
                description="Searches and plays a specific song, artist, album, or playlist on Spotify.",
                category=CommandCategory.APPLICATION,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_spotify_play_query,
            )
        )

        # 4. Window Management
        self.registry.register(
            ActionDefinition(
                name="minimize_window",
                description="Minimizes a targeted window by title.",
                category=CommandCategory.APPLICATION,
                risk_level=CommandRiskLevel.MEDIUM,
                handler=self._handle_minimize_window,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="maximize_window",
                description="Maximizes a targeted window by title.",
                category=CommandCategory.APPLICATION,
                risk_level=CommandRiskLevel.MEDIUM,
                handler=self._handle_maximize_window,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="restore_window",
                description="Restores a minimized or maximized window.",
                category=CommandCategory.APPLICATION,
                risk_level=CommandRiskLevel.MEDIUM,
                handler=self._handle_restore_window,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="focus_window",
                description="Brings a targeted window to foreground focus.",
                category=CommandCategory.APPLICATION,
                risk_level=CommandRiskLevel.MEDIUM,
                handler=self._handle_focus_window,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="show_desktop",
                description="Minimizes all windows to display the desktop.",
                category=CommandCategory.APPLICATION,
                risk_level=CommandRiskLevel.MEDIUM,
                handler=self._handle_show_desktop,
            )
        )

        # 5. Volume Control
        self.registry.register(
            ActionDefinition(
                name="get_volume",
                description="Queries the current master audio volume.",
                category=CommandCategory.SYSTEM,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_get_volume,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="set_volume",
                description="Sets the master volume to a specific percentage.",
                category=CommandCategory.SYSTEM,
                risk_level=CommandRiskLevel.MEDIUM,
                handler=self._handle_set_volume,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="increase_volume",
                description="Increases the master volume by a step.",
                category=CommandCategory.SYSTEM,
                risk_level=CommandRiskLevel.MEDIUM,
                handler=self._handle_increase_volume,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="decrease_volume",
                description="Decreases the master volume by a step.",
                category=CommandCategory.SYSTEM,
                risk_level=CommandRiskLevel.MEDIUM,
                handler=self._handle_decrease_volume,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="mute_volume",
                description="Mutes system audio output.",
                category=CommandCategory.SYSTEM,
                risk_level=CommandRiskLevel.MEDIUM,
                handler=self._handle_mute_volume,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="unmute_volume",
                description="Unmutes system audio output.",
                category=CommandCategory.SYSTEM,
                risk_level=CommandRiskLevel.MEDIUM,
                handler=self._handle_unmute_volume,
            )
        )

        # 6. Browser & Web Navigation
        self.registry.register(
            ActionDefinition(
                name="open_browser",
                description="Opens an allowlisted website or validated HTTP/HTTPS URL in the default browser.",
                category=CommandCategory.APPLICATION,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_open_browser,
            )
        )

        # 7. Screenshot
        self.registry.register(
            ActionDefinition(
                name="take_screenshot",
                description="Captures the desktop screen and saves it into the safe Denver screenshots directory.",
                category=CommandCategory.SYSTEM,
                risk_level=CommandRiskLevel.MEDIUM,
                handler=self._handle_take_screenshot,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="analyze_screen",
                description="Captures active screen and performs multimodal visual reasoning and error diagnosis.",
                category=CommandCategory.SYSTEM,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_analyze_screen,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="start_meeting_notes",
                description="Starts system audio loopback recording and live meeting intelligence session.",
                category=CommandCategory.SYSTEM,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_start_meeting_notes,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="stop_meeting_notes",
                description="Stops live meeting recording and generates finalized markdown meeting notes.",
                category=CommandCategory.SYSTEM,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_stop_meeting_notes,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="get_meeting_summary",
                description="Retrieves active or latest meeting notes and action items summary.",
                category=CommandCategory.SYSTEM,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_get_meeting_summary,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="get_proactive_suggestions",
                description="Evaluates context and retrieves active proactive suggestions.",
                category=CommandCategory.UTILITY,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_get_proactive_suggestions,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="set_proactive_mode",
                description="Enables or disables autonomous proactive suggestions mode.",
                category=CommandCategory.UTILITY,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_set_proactive_mode,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="dismiss_proactive_suggestions",
                description="Dismisses active proactive recommendations.",
                category=CommandCategory.UTILITY,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_dismiss_proactive_suggestions,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="web_search_query",
                description="Executes deep web research and returns structured search results.",
                category=CommandCategory.UTILITY,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_web_search_query,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="extract_web_page",
                description="Fetches target webpage and extracts readable article text and DOM structure.",
                category=CommandCategory.UTILITY,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_extract_web_page,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="capture_web_screenshot",
                description="Renders target website and captures visual browser screenshot.",
                category=CommandCategory.SYSTEM,
                risk_level=CommandRiskLevel.MEDIUM,
                handler=self._handle_capture_web_screenshot,
            )
        )

        # 8. Confirmation & Interactive Control
        self.registry.register(
            ActionDefinition(
                name="confirm_action",
                description="Confirms and executes a pending privileged automation action.",
                category=CommandCategory.UTILITY,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_confirm_action,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="cancel_action",
                description="Cancels and clears pending confirmation requests.",
                category=CommandCategory.UTILITY,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_cancel_action,
            )
        )

        # 9. Notes
        self.registry.register(
            ActionDefinition(
                name="create_note",
                description="Stores a new user note or reminder.",
                category=CommandCategory.NOTE,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_create_note,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="list_notes",
                description="Lists stored user notes.",
                category=CommandCategory.NOTE,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_list_notes,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="search_notes",
                description="Searches user notes by keyword.",
                category=CommandCategory.NOTE,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_search_notes,
            )
        )

        # 10. Tasks
        self.registry.register(
            ActionDefinition(
                name="create_task",
                description="Creates a new scheduled task.",
                category=CommandCategory.TASK,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_create_task,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="list_tasks",
                description="Lists pending scheduled tasks.",
                category=CommandCategory.TASK,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_list_tasks,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="complete_task",
                description="Marks a task as completed.",
                category=CommandCategory.TASK,
                risk_level=CommandRiskLevel.MEDIUM,
                handler=self._handle_complete_task,
            )
        )

        # 11. Memory & Preferences
        self.registry.register(
            ActionDefinition(
                name="remember",
                description="Persists a generic memory item.",
                category=CommandCategory.MEMORY,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_remember,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="recall_memory",
                description="Queries stored memories by keyword.",
                category=CommandCategory.MEMORY,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_recall_memory,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="forget_memory",
                description="Deletes or clears a memory item.",
                category=CommandCategory.MEMORY,
                risk_level=CommandRiskLevel.MEDIUM,
                handler=self._handle_forget_memory,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="set_preference",
                description="Sets or updates a user preference.",
                category=CommandCategory.MEMORY,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_set_preference,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="get_preference",
                description="Retrieves a user preference value.",
                category=CommandCategory.MEMORY,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_get_preference,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="list_preferences",
                description="Lists all saved user preferences.",
                category=CommandCategory.MEMORY,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_list_preferences,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="clear_context",
                description="Clears the active short-term conversation context buffer.",
                category=CommandCategory.MEMORY,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_clear_context,
            )
        )

        # 12. Scheduled Routines & Proactive Controls
        self.registry.register(
            ActionDefinition(
                name="list_routines",
                description="Lists all user-defined scheduled routines.",
                category=CommandCategory.ROUTINE,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_list_routines,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="pause_scheduler",
                description="Globally pauses all scheduled routine executions.",
                category=CommandCategory.ROUTINE,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_pause_scheduler,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="resume_scheduler",
                description="Resumes global scheduled routine executions.",
                category=CommandCategory.ROUTINE,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_resume_scheduler,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="enable_scheduler",
                description="Enables the background routine scheduler service.",
                category=CommandCategory.ROUTINE,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_enable_scheduler,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="disable_scheduler",
                description="Disables the background routine scheduler service.",
                category=CommandCategory.ROUTINE,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_disable_scheduler,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="pause_routine",
                description="Pauses an individual scheduled routine by ID or name.",
                category=CommandCategory.ROUTINE,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_pause_routine,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="resume_routine",
                description="Resumes an individual scheduled routine by ID or name.",
                category=CommandCategory.ROUTINE,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_resume_routine,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="delete_routine",
                description="Deletes a scheduled routine and its history.",
                category=CommandCategory.ROUTINE,
                risk_level=CommandRiskLevel.MEDIUM,
                handler=self._handle_delete_routine,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="run_routine_now",
                description="Immediately executes a scheduled routine on demand.",
                category=CommandCategory.ROUTINE,
                risk_level=CommandRiskLevel.MEDIUM,
                handler=self._handle_run_routine_now,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="create_reminder",
                description="Creates a new scheduled time-based reminder routine.",
                category=CommandCategory.ROUTINE,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_create_reminder,
            )
        )

        # 14. Phase 9 Task & Workflow Orchestration
        self.registry.register(
            ActionDefinition(
                name="plan_task",
                description="Plans and creates a new multi-step task workflow DAG.",
                category=CommandCategory.TASK,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_plan_task,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="show_task_status",
                description="Shows status, plan, and progress of an orchestrated task.",
                category=CommandCategory.TASK,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_show_task_status,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="show_task_history",
                description="Displays execution history and step records for a task.",
                category=CommandCategory.TASK,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_show_task_history,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="run_task",
                description="Executes a planned task workflow.",
                category=CommandCategory.TASK,
                risk_level=CommandRiskLevel.MEDIUM,
                handler=self._handle_run_task,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="pause_task",
                description="Pauses an active task execution.",
                category=CommandCategory.TASK,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_pause_task,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="resume_task",
                description="Resumes a paused task execution.",
                category=CommandCategory.TASK,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_resume_task,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="cancel_task",
                description="Cancels an active or pending task workflow.",
                category=CommandCategory.TASK,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_cancel_task,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="delete_task",
                description="Deletes an orchestrated task and its history.",
                category=CommandCategory.TASK,
                risk_level=CommandRiskLevel.MEDIUM,
                handler=self._handle_delete_task,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="pause_all_tasks",
                description="Globally pauses all task workflow executions.",
                category=CommandCategory.TASK,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_pause_all_tasks,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="resume_all_tasks",
                description="Globally resumes all task workflow executions.",
                category=CommandCategory.TASK,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_resume_all_tasks,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="enable_tasks",
                description="Enables task workflow orchestration subsystem.",
                category=CommandCategory.TASK,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_enable_tasks,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="disable_tasks",
                description="Disables task workflow orchestration subsystem.",
                category=CommandCategory.TASK,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_disable_tasks,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="approve_task_step",
                description="Approves a pending confirmation token for a task step.",
                category=CommandCategory.TASK,
                risk_level=CommandRiskLevel.MEDIUM,
                handler=self._handle_approve_task_step,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="reject_task_step",
                description="Rejects a pending confirmation token for a task step.",
                category=CommandCategory.TASK,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_reject_task_step,
            )
        )

        # 16. Live Weather Actions
        self.registry.register(
            ActionDefinition(
                name="get_weather",
                description="Queries current weather conditions for a specified city.",
                category=CommandCategory.UTILITY,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_get_weather,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="get_weather_forecast",
                description="Queries multi-day or 24h weather forecast for a specified city.",
                category=CommandCategory.UTILITY,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_get_weather_forecast,
            )
        )

        # 17. Fastest-Route Navigation & Directions Actions
        self.registry.register(
            ActionDefinition(
                name="get_directions",
                description="Calculates fastest route, distance, and duration between origin and destination.",
                category=CommandCategory.APPLICATION,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_get_directions,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="navigate_to",
                description="Calculates navigation route to a destination from the user's saved home.",
                category=CommandCategory.APPLICATION,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_navigate_to,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="switch_directions_mode",
                description="Re-runs the last requested route with an updated travel mode.",
                category=CommandCategory.APPLICATION,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_switch_directions_mode,
            )
        )

        # 18. Saved Locations Actions
        self.registry.register(
            ActionDefinition(
                name="save_location",
                description="Saves and geocodes a named address (e.g. home, office) into memory.",
                category=CommandCategory.MEMORY,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_save_location,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="get_saved_location",
                description="Retrieves a saved user location or lists all saved locations.",
                category=CommandCategory.MEMORY,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_get_saved_location,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="delete_saved_location",
                description="Deletes a saved user location by its label.",
                category=CommandCategory.MEMORY,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_delete_saved_location,
            )
        )

        # 19. Live Current Location Actions
        self.registry.register(
            ActionDefinition(
                name="get_current_location",
                description="Detects and reports the device's real-time physical/network location.",
                category=CommandCategory.UTILITY,
                risk_level=CommandRiskLevel.SAFE,
                handler=self._handle_get_current_location,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="save_current_location",
                description="Detects current location and prompts for confirmation before saving to memory.",
                category=CommandCategory.MEMORY,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_save_current_location,
            )
        )

        # 21. Air-Gapped Mode & LLM Provider Actions
        self.registry.register(
            ActionDefinition(
                name="set_air_gap_mode",
                description="Toggles air-gapped / local-only mode to prevent cloud leakage.",
                category=CommandCategory.SYSTEM,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_set_air_gap_mode,
            )
        )
        self.registry.register(
            ActionDefinition(
                name="switch_llm_provider",
                description="Switches active LLM inference provider (groq, gemini, ollama, lmstudio).",
                category=CommandCategory.SYSTEM,
                risk_level=CommandRiskLevel.LOW,
                handler=self._handle_switch_llm_provider,
            )
        )



    # -------------------------------------------------------------------------
    # Handlers Implementation
    # -------------------------------------------------------------------------
    async def _handle_list_routines(self, params: dict[str, Any]) -> ActionResult:
        if not self.routine_registry:
            return ActionResult(
                success=True,
                message="Scheduled routines subsystem is not configured.",
                action_name="list_routines",
                data={"routines": []},
            )
        routines = await self.routine_registry.list_routines(enabled_only=False)
        if not routines:
            return ActionResult(
                success=True,
                message="You have no scheduled routines configured.",
                action_name="list_routines",
                data={"routines": [], "count": 0},
            )
        summary = [
            f"- {r.name} ({r.routine_id}): {r.status.value}, next run: {r.next_run_at.isoformat() if r.next_run_at else 'None'}"
            for r in routines
        ]
        return ActionResult(
            success=True,
            message=f"You have {len(routines)} routine(s):\n" + "\n".join(summary),
            action_name="list_routines",
            data={"count": len(routines), "routines": [r.to_dict() for r in routines]},
        )

    async def _handle_pause_scheduler(self, params: dict[str, Any]) -> ActionResult:
        if not self.scheduler:
            return ActionResult(success=False, message="Scheduler is not configured.", action_name="pause_scheduler")
        await self.scheduler.pause()
        return ActionResult(success=True, message="Scheduler paused. All scheduled routines are paused.", action_name="pause_scheduler")

    async def _handle_resume_scheduler(self, params: dict[str, Any]) -> ActionResult:
        if not self.scheduler:
            return ActionResult(success=False, message="Scheduler is not configured.", action_name="resume_scheduler")
        await self.scheduler.resume()
        return ActionResult(success=True, message="Scheduler resumed. Active routines will run as scheduled.", action_name="resume_scheduler")

    async def _handle_enable_scheduler(self, params: dict[str, Any]) -> ActionResult:
        if not self.scheduler:
            return ActionResult(success=False, message="Scheduler is not configured.", action_name="enable_scheduler")
        self.scheduler.enable()
        if not self.scheduler.is_running:
            await self.scheduler.start()
        return ActionResult(success=True, message="Scheduler service enabled and started.", action_name="enable_scheduler")

    async def _handle_disable_scheduler(self, params: dict[str, Any]) -> ActionResult:
        if not self.scheduler:
            return ActionResult(success=False, message="Scheduler is not configured.", action_name="disable_scheduler")
        self.scheduler.disable()
        await self.scheduler.stop()
        return ActionResult(success=True, message="Scheduler service disabled.", action_name="disable_scheduler")

    async def _find_routine_by_id_or_name(self, target: str) -> Any | None:
        target = target.strip()
        routine = None
        if self.routine_registry:
            routine = await self.routine_registry.get_routine(target)
            if not routine:
                routine = await self.routine_registry.get_by_name(target)

        if not routine:
            # Check compound routines loader
            try:
                from denver.scheduler.compound_routines import get_compound_routine_loader
                c_loader = get_compound_routine_loader()
                c_def = c_loader.find_by_name_or_trigger(target)
                if c_def:
                    routine = c_def.to_routine()
                    if self.routine_registry:
                        try:
                            saved = await self.routine_registry.create_routine(
                                name=routine.name,
                                trigger=routine.trigger,
                                actions=routine.actions,
                                description=routine.description,
                                enabled=routine.enabled,
                            )
                            routine = saved
                        except Exception:
                            pass
            except Exception:
                pass
        return routine

    async def _handle_pause_routine(self, params: dict[str, Any]) -> ActionResult:
        target = params.get("routine_id", "")
        routine = await self._find_routine_by_id_or_name(target)
        if not routine:
            return ActionResult(success=False, message=f"Routine '{target}' not found.", action_name="pause_routine")
        await self.routine_registry.pause_routine(routine.routine_id)
        if self.scheduler:
            self.scheduler.notify_schedule_change()
        return ActionResult(success=True, message=f"Routine '{routine.name}' has been paused.", action_name="pause_routine", data={"routine_id": routine.routine_id})

    async def _handle_resume_routine(self, params: dict[str, Any]) -> ActionResult:
        target = params.get("routine_id", "")
        routine = await self._find_routine_by_id_or_name(target)
        if not routine:
            return ActionResult(success=False, message=f"Routine '{target}' not found.", action_name="resume_routine")
        await self.routine_registry.resume_routine(routine.routine_id)
        if self.scheduler:
            self.scheduler.notify_schedule_change()
        return ActionResult(success=True, message=f"Routine '{routine.name}' has been resumed.", action_name="resume_routine", data={"routine_id": routine.routine_id})

    async def _handle_delete_routine(self, params: dict[str, Any]) -> ActionResult:
        target = params.get("routine_id", "")
        routine = await self._find_routine_by_id_or_name(target)
        if not routine:
            return ActionResult(success=False, message=f"Routine '{target}' not found.", action_name="delete_routine")
        await self.routine_registry.delete_routine(routine.routine_id)
        if self.scheduler:
            self.scheduler.notify_schedule_change()
        return ActionResult(success=True, message=f"Routine '{routine.name}' deleted.", action_name="delete_routine", data={"routine_id": routine.routine_id})

    async def _handle_run_routine_now(self, params: dict[str, Any]) -> ActionResult:
        target = params.get("routine_id", "")
        routine = await self._find_routine_by_id_or_name(target)
        if not routine:
            return ActionResult(success=False, message=f"Routine '{target}' not found.", action_name="run_routine_now")

        if self.scheduler:
            execution = await self.scheduler.run_routine_now(routine.routine_id)
            return ActionResult(
                success=execution.status.value in {"SUCCESS", "RUNNING", "COMPLETED"},
                message=f"Routine '{routine.name}' executed with status: {execution.status.value}.",
                action_name="run_routine_now",
                data=execution.to_dict(),
            )

        # Fallback direct execution if scheduler loop is not active
        executed_actions = []
        action_errors = []
        for action in routine.actions:
            try:
                res = await self.executor.execute(
                    ActionRequest(action_name=action.action_name, params=action.params)
                )
                executed_actions.append({"action": action.action_name, "success": res.success, "message": res.message})
                if not res.success and res.error:
                    action_errors.append(f"{action.action_name}: {res.message}")
            except Exception as exc:
                action_errors.append(f"{action.action_name}: {exc}")

        success = len(action_errors) == 0
        summary_msg = f"Routine '{routine.name}' completed {len(executed_actions)} action(s)."
        if action_errors:
            summary_msg += f" Encountered {len(action_errors)} error(s): {', '.join(action_errors)}"

        return ActionResult(
            success=success,
            message=summary_msg,
            action_name="run_routine_now",
            data={"routine_id": routine.routine_id, "actions": executed_actions, "errors": action_errors},
        )


    async def _handle_create_reminder(self, params: dict[str, Any]) -> ActionResult:
        if not self.routine_registry:
            return ActionResult(success=False, message="Routine registry is not configured.", action_name="create_reminder")
        raw_time = params.get("time", "").strip()
        msg = params.get("message", "").strip() or "Reminder"

        import re
        hh_mm = ""
        m_24 = re.search(r"\b([01]?[0-9]|2[0-3]):([0-5][0-9])\b", raw_time)
        if m_24:
            hh_mm = f"{int(m_24.group(1)):02d}:{m_24.group(2)}"
        else:
            m_12 = re.search(r"\b(\d{1,2})(?::([0-5][0-9]))?\s*(am|pm)\b", raw_time, re.IGNORECASE)
            if m_12:
                hr = int(m_12.group(1))
                mn = m_12.group(2) or "00"
                meridiem = m_12.group(3).lower()
                if meridiem == "pm" and hr < 12:
                    hr += 12
                elif meridiem == "am" and hr == 12:
                    hr = 0
                hh_mm = f"{hr:02d}:{mn}"
            else:
                hh_mm = "09:00"

        time_str = hh_mm
        from denver.scheduler.models import RoutineAction, RoutineTrigger, TriggerType
        trigger = RoutineTrigger(
            trigger_type=TriggerType.DAILY,
            time_of_day=time_str,
            timezone="UTC",
        )
        action = RoutineAction(
            action_name="create_note",
            params={"title": f"Reminder: {msg[:20]}", "content": msg},
            description=f"Reminder: {msg}",
        )
        routine = await self.routine_registry.create_routine(
            name=f"Reminder: {msg[:30]}",
            trigger=trigger,
            actions=[action],
            description=f"Automated reminder for '{msg}' at {time_str}",
        )
        if self.scheduler:
            self.scheduler.notify_schedule_change()
        return ActionResult(
            success=True,
            message=f"Reminder scheduled for {time_str}: '{msg}'.",
            action_name="create_reminder",
            data={"routine_id": routine.routine_id, "next_run_at": routine.next_run_at.isoformat() if routine.next_run_at else None},
        )
    async def _handle_assistant_call(self, params: dict[str, Any]) -> ActionResult:
        user_name = getattr(self.settings, "user_name", "Diwakar") or "Diwakar"
        return ActionResult(
            success=True,
            message=f"Yes, {user_name}? I'm listening.",
            action_name="assistant_call",
            data={"status": "listening"},
        )

    async def _handle_get_time(self, params: dict[str, Any]) -> ActionResult:
        now = datetime.datetime.now()
        time_str = now.strftime("%I:%M %p")
        return ActionResult(
            success=True,
            message=f"The current time is {time_str}.",
            action_name="get_time",
            data={"time": time_str, "hour": now.hour, "minute": now.minute},
        )

    async def _handle_get_date(self, params: dict[str, Any]) -> ActionResult:
        now = datetime.datetime.now()
        date_str = now.strftime("%A, %B %d, %Y")
        return ActionResult(
            success=True,
            message=f"Today's date is {date_str}.",
            action_name="get_date",
            data={"date": date_str, "year": now.year, "month": now.month, "day": now.day},
        )

    async def _handle_get_system_status(self, params: dict[str, Any]) -> ActionResult:
        state = self.state_machine.current_state.value if self.state_machine else "STANDBY"
        return ActionResult(
            success=True,
            message=f"Denver is operational and in {state} state.",
            action_name="get_system_status",
            data={"assistant": self.settings.assistant_name, "state": state},
        )

    async def _handle_get_cpu(self, params: dict[str, Any]) -> ActionResult:
        cpu_pct = psutil.cpu_percent(interval=None) if _PSUTIL_AVAILABLE else 0.0
        return ActionResult(
            success=True,
            message=f"CPU usage is currently at {cpu_pct} percent.",
            action_name="get_cpu",
            data={"cpu_percent": cpu_pct},
        )

    async def _handle_get_ram(self, params: dict[str, Any]) -> ActionResult:
        if _PSUTIL_AVAILABLE:
            vm = psutil.virtual_memory()
            ram_pct = vm.percent
            used_gb = round(vm.used / (1024**3), 2)
            total_gb = round(vm.total / (1024**3), 2)
        else:
            ram_pct, used_gb, total_gb = 0.0, 0.0, 0.0

        return ActionResult(
            success=True,
            message=f"Memory utilization is at {ram_pct} percent ({used_gb} GB used of {total_gb} GB).",
            action_name="get_ram",
            data={"ram_percent": ram_pct, "used_gb": used_gb, "total_gb": total_gb},
        )

    async def _handle_get_battery(self, params: dict[str, Any]) -> ActionResult:
        if _PSUTIL_AVAILABLE and hasattr(psutil, "sensors_battery"):
            batt = psutil.sensors_battery()
            if batt:
                plugged = "plugged in" if batt.power_plugged else "on battery"
                return ActionResult(
                    success=True,
                    message=f"Battery is at {batt.percent} percent ({plugged}).",
                    action_name="get_battery",
                    data={"percent": batt.percent, "power_plugged": batt.power_plugged},
                )
        return ActionResult(
            success=True,
            message="Battery status is unavailable or system is desktop-powered.",
            action_name="get_battery",
            data={"percent": None, "power_plugged": True},
        )

    async def _handle_get_system_summary(self, params: dict[str, Any]) -> ActionResult:
        res = await self.automation.execute(AutomationRequest(action_name="get_system_summary", params=params))
        return ActionResult(
            success=res.success,
            message=res.message,
            action_name="get_system_summary",
            data=res.data,
            error=res.error,
        )

    async def _handle_lock_workstation(self, params: dict[str, Any]) -> ActionResult:
        res = await self.automation.execute(AutomationRequest(action_name="lock_workstation", params=params))
        return ActionResult(
            success=res.success,
            message=res.message or "Workstation locked successfully.",
            action_name="lock_workstation",
            data=res.data,
            error=res.error,
        )

    async def _handle_enter_sleep_mode(self, params: dict[str, Any]) -> ActionResult:
        self._is_sleeping = True
        return ActionResult(
            success=True,
            message="Going to sleep mode. I will stay running silently in the background and monitor your laptop. Say 'Denver, wake up' when you need me.",
            action_name="enter_sleep_mode",
            data={"is_sleeping": True},
        )

    async def _handle_wake_up(self, params: dict[str, Any]) -> ActionResult:
        self._is_sleeping = False
        return ActionResult(
            success=True,
            message="I'm awake and ready! How can I help you?",
            action_name="wake_up",
            data={"is_sleeping": False},
        )

    async def _handle_read_clipboard(self, params: dict[str, Any]) -> ActionResult:
        res = await self.automation.execute(AutomationRequest(action_name="read_clipboard", params=params))
        return ActionResult(
            success=res.success,
            message=res.message,
            action_name="read_clipboard",
            data=res.data,
            error=res.error,
        )

    async def _handle_summarize_clipboard(self, params: dict[str, Any]) -> ActionResult:
        res = await self.automation.execute(AutomationRequest(action_name="read_clipboard", params=params))
        raw_text = res.data.get("text", "") if res.success else ""
        if not raw_text or not raw_text.strip():
            return ActionResult(
                success=True,
                message="Your clipboard is empty, so there is nothing to summarize.",
                action_name="summarize_clipboard",
                data={"summary": "", "text_length": 0},
            )

        # 1. Try cloud AI summarization if provider_router is available
        summary_text: str | None = None
        if self.provider_router:
            try:
                ai_prompt = (
                    f"Summarize the following clipboard text in 1 or 2 clear, informative sentences:\n\n{raw_text[:3000]}"
                )
                ai_resp = await self.provider_router.complete(ai_prompt)
                if ai_resp and ai_resp.content:
                    summary_text = ai_resp.content.strip()
            except Exception as exc:
                logger.debug("AI summarization failed, falling back to extractive summary: %s", exc)

        # 2. Local extractive summary fallback
        if not summary_text:
            from denver.automation.clipboard import summarize_text_locally
            summary_text = summarize_text_locally(raw_text, sentence_limit=2)

        return ActionResult(
            success=True,
            message=f"Clipboard summary: {summary_text}",
            action_name="summarize_clipboard",
            data={"summary": summary_text, "text_length": len(raw_text)},
        )

    async def _handle_type_text(self, params: dict[str, Any]) -> ActionResult:
        res = await self.automation.execute(AutomationRequest(action_name="type_text", params=params))
        return ActionResult(
            success=res.success,
            message=res.message,
            action_name="type_text",
            data=res.data,
            error=res.error,
        )

    async def _handle_press_key(self, params: dict[str, Any]) -> ActionResult:
        res = await self.automation.execute(AutomationRequest(action_name="press_key", params=params))
        return ActionResult(
            success=res.success,
            message=res.message,
            action_name="press_key",
            data=res.data,
            error=res.error,
        )

    async def _handle_scroll_window(self, params: dict[str, Any]) -> ActionResult:
        res = await self.automation.execute(AutomationRequest(action_name="scroll_window", params=params))
        return ActionResult(
            success=res.success,
            message=res.message,
            action_name="scroll_window",
            data=res.data,
            error=res.error,
        )

    async def _handle_open_application(self, params: dict[str, Any]) -> ActionResult:
        app_name = params.get("application", "unknown")
        req = AutomationRequest(action_name="open_application", target=app_name, params=params)
        res = await self.automation.execute(req)
        return ActionResult(
            success=res.success,
            message=res.message,
            action_name="open_application",
            data=res.data,
            error=res.error,
        )

    async def _handle_close_application(self, params: dict[str, Any]) -> ActionResult:
        app_name = params.get("application", "unknown")
        req = AutomationRequest(action_name="close_application", target=app_name, params=params)
        res = await self.automation.execute(req)
        return ActionResult(
            success=res.success,
            message=res.message,
            action_name="close_application",
            data=res.data,
            error=res.error,
        )

    async def _handle_set_air_gap_mode(self, params: dict[str, Any]) -> ActionResult:
        enabled = bool(params.get("enabled", True))
        if self.provider_router:
            self.provider_router.set_air_gapped_mode(enabled)
        await self.event_bus.publish(AirGappedModeChanged(enabled=enabled))
        status_desc = "ENABLED (Offline Local-Only Mode)" if enabled else "DISABLED (Cloud Fallback Available)"
        return ActionResult(
            success=True,
            message=f"Air-Gapped privacy mode is now {status_desc}.",
            action_name="set_air_gap_mode",
            data={"air_gapped": enabled},
        )

    async def _handle_switch_llm_provider(self, params: dict[str, Any]) -> ActionResult:
        prov = params.get("provider", "groq").strip().lower()
        if self.provider_router:
            self.provider_router.set_active_provider(prov)
        is_air_gapped = bool(self.provider_router.air_gapped_mode if self.provider_router else False)
        await self.event_bus.publish(
            ProviderModeChanged(
                active_provider=prov,
                air_gapped=is_air_gapped,
            )
        )
        return ActionResult(
            success=True,
            message=f"Switched active AI provider to '{prov}'.",
            action_name="switch_llm_provider",
            data={"active_provider": prov, "air_gapped": is_air_gapped},
        )

    async def _handle_send_whatsapp_message(self, params: dict[str, Any]) -> ActionResult:
        msg = params.get("message", "")
        contact = (params.get("contact", "") or params.get("recipient", "")).strip()
        phone = params.get("phone", "").strip()
        resolved_name = contact

        # 1. Resolve phone number and canonical name from ContactBook (data/contacts.json)
        if not phone and contact:
            try:
                from denver.memory.contacts import get_contact_book
                cb = get_contact_book()
                match_res = cb.find_contact_matches(contact)

                if match_res.is_ambiguous and len(match_res.candidates) > 1:
                    candidate_descriptions = []
                    for c, _ in match_res.candidates:
                        desc = c.name
                        if c.relationship and c.relationship != "direct_phone":
                            desc += f" ({c.relationship})"
                        elif c.phone:
                            desc += f" ({mask_phone(c.phone)})"
                        candidate_descriptions.append(desc)

                    if len(candidate_descriptions) == 2:
                        candidates_str = f"{candidate_descriptions[0]} and {candidate_descriptions[1]}"
                    else:
                        candidates_str = ", ".join(candidate_descriptions[:-1]) + f", and {candidate_descriptions[-1]}"

                    clarification = f"I found multiple contacts matching '{contact}': {candidates_str}. Who do you mean?"
                    logger.info("Ambiguous contact match for '%s' (%d candidates). Requested clarification.", contact, len(match_res.candidates))
                    return ActionResult(
                        success=False,
                        message=clarification,
                        action_name="send_whatsapp_message",
                        data={
                            "ambiguous": True,
                            "query": contact,
                            "candidates": [c.to_dict() for c, _ in match_res.candidates],
                        },
                        error="AmbiguousContactMatch",
                    )

                if match_res.best_match:
                    matched = match_res.best_match
                    resolved_name = matched.name
                    if matched.clean_phone() and len(matched.clean_phone()) >= 7:
                        phone = matched.clean_phone()
                        logger.info("Resolved contact '%s' -> '%s' (phone: '%s') via ContactBook.", contact, resolved_name, mask_phone(phone))
            except Exception as cb_err:
                logger.debug("ContactBook lookup failed: %s", cb_err)

        # 2. Check persistent memory for stored contact info if still unresolved
        if not phone and contact and hasattr(self, "memory") and self.memory:
            clean_c = re.sub(r"[^a-zA-Z0-9_]", "", contact.lower().replace(" ", "_"))
            for key in (f"contact_{clean_c}", f"{clean_c}_phone", f"{clean_c}_number", clean_c):
                try:
                    pref = await self.memory.get_preference(key)
                    if pref and pref.value:
                        val = str(pref.value).strip().replace(" ", "").replace("-", "").replace("+", "")
                        if val.isdigit() and len(val) >= 7:
                            phone = val
                            logger.info("Resolved contact '%s' to phone '%s' from memory.", contact, mask_phone(phone))
                            break
                except Exception:
                    pass

        req = AutomationRequest(
            action_name="send_whatsapp_message",
            target=resolved_name or contact or "WhatsApp",
            params={"message": msg, "contact": resolved_name or contact, "phone": phone},
        )
        res = await self.automation.execute(req)

        # 3. Publish WhatsApp telemetry event to DenverEventBus
        if hasattr(self, "event_bus") and self.event_bus:
            try:
                from denver.runtime.events import WhatsAppMessageDispatched
                await self.event_bus.publish(
                    WhatsAppMessageDispatched(
                        contact=resolved_name or contact,
                        phone=phone,
                        message=msg,
                        success=res.success,
                    )
                )
            except Exception as ev_err:
                logger.debug("WhatsApp event bus publication skipped: %s", ev_err)

        return ActionResult(
            success=res.success,
            message=res.message,
            action_name="send_whatsapp_message",
            data=res.data,
            error=res.error,
        )

    async def _handle_spotify_play_pause(self, params: dict[str, Any]) -> ActionResult:
        res = self.spotify_controller.play_pause()
        if hasattr(self, "event_bus") and self.event_bus:
            try:
                from denver.runtime.events import SpotifyPlaybackChanged
                await self.event_bus.publish(SpotifyPlaybackChanged(action="play_pause", success=res.success))
            except Exception:
                pass
        return ActionResult(
            success=res.success,
            message=res.message,
            action_name="spotify_play_pause",
            data=res.data,
            error=res.error,
        )

    async def _handle_spotify_next_track(self, params: dict[str, Any]) -> ActionResult:
        res = self.spotify_controller.next_track()
        if hasattr(self, "event_bus") and self.event_bus:
            try:
                from denver.runtime.events import SpotifyPlaybackChanged
                await self.event_bus.publish(SpotifyPlaybackChanged(action="next_track", success=res.success))
            except Exception:
                pass
        return ActionResult(
            success=res.success,
            message=res.message,
            action_name="spotify_next_track",
            data=res.data,
            error=res.error,
        )

    async def _handle_spotify_previous_track(self, params: dict[str, Any]) -> ActionResult:
        res = self.spotify_controller.previous_track()
        if hasattr(self, "event_bus") and self.event_bus:
            try:
                from denver.runtime.events import SpotifyPlaybackChanged
                await self.event_bus.publish(SpotifyPlaybackChanged(action="previous_track", success=res.success))
            except Exception:
                pass
        return ActionResult(
            success=res.success,
            message=res.message,
            action_name="spotify_previous_track",
            data=res.data,
            error=res.error,
        )

    async def _handle_spotify_play_query(self, params: dict[str, Any]) -> ActionResult:
        query = params.get("query", "").strip()
        res = self.spotify_controller.play_query(query)
        if hasattr(self, "event_bus") and self.event_bus:
            try:
                from denver.runtime.events import SpotifyPlaybackChanged
                await self.event_bus.publish(SpotifyPlaybackChanged(action="play_query", query=query, success=res.success))
            except Exception:
                pass
        return ActionResult(
            success=res.success,
            message=res.message,
            action_name="spotify_play_query",
            data=res.data,
            error=res.error,
        )


    async def _handle_minimize_window(self, params: dict[str, Any]) -> ActionResult:
        win_name = params.get("window", "")
        req = AutomationRequest(action_name="minimize_window", target=win_name, params=params)
        res = await self.automation.execute(req)
        return ActionResult(
            success=res.success,
            message=res.message,
            action_name="minimize_window",
            data=res.data,
            error=res.error,
        )

    async def _handle_maximize_window(self, params: dict[str, Any]) -> ActionResult:
        win_name = params.get("window", "")
        req = AutomationRequest(action_name="maximize_window", target=win_name, params=params)
        res = await self.automation.execute(req)
        return ActionResult(
            success=res.success,
            message=res.message,
            action_name="maximize_window",
            data=res.data,
            error=res.error,
        )

    async def _handle_restore_window(self, params: dict[str, Any]) -> ActionResult:
        win_name = params.get("window", "")
        req = AutomationRequest(action_name="restore_window", target=win_name, params=params)
        res = await self.automation.execute(req)
        return ActionResult(
            success=res.success,
            message=res.message,
            action_name="restore_window",
            data=res.data,
            error=res.error,
        )

    async def _handle_focus_window(self, params: dict[str, Any]) -> ActionResult:
        win_name = params.get("window", "")
        req = AutomationRequest(action_name="focus_window", target=win_name, params=params)
        res = await self.automation.execute(req)
        return ActionResult(
            success=res.success,
            message=res.message,
            action_name="focus_window",
            data=res.data,
            error=res.error,
        )

    async def _handle_show_desktop(self, params: dict[str, Any]) -> ActionResult:
        req = AutomationRequest(action_name="show_desktop", params=params)
        res = await self.automation.execute(req)
        return ActionResult(
            success=res.success,
            message=res.message,
            action_name="show_desktop",
            data=res.data,
            error=res.error,
        )

    async def _handle_get_volume(self, params: dict[str, Any]) -> ActionResult:
        req = AutomationRequest(action_name="get_volume", params=params)
        res = await self.automation.execute(req)
        return ActionResult(
            success=res.success,
            message=res.message,
            action_name="get_volume",
            data=res.data,
            error=res.error,
        )

    async def _handle_set_volume(self, params: dict[str, Any]) -> ActionResult:
        req = AutomationRequest(action_name="set_volume", params=params)
        res = await self.automation.execute(req)
        return ActionResult(
            success=res.success,
            message=res.message,
            action_name="set_volume",
            data=res.data,
            error=res.error,
        )

    async def _handle_increase_volume(self, params: dict[str, Any]) -> ActionResult:
        req = AutomationRequest(action_name="increase_volume", params=params)
        res = await self.automation.execute(req)
        return ActionResult(
            success=res.success,
            message=res.message,
            action_name="increase_volume",
            data=res.data,
            error=res.error,
        )

    async def _handle_decrease_volume(self, params: dict[str, Any]) -> ActionResult:
        req = AutomationRequest(action_name="decrease_volume", params=params)
        res = await self.automation.execute(req)
        return ActionResult(
            success=res.success,
            message=res.message,
            action_name="decrease_volume",
            data=res.data,
            error=res.error,
        )

    async def _handle_mute_volume(self, params: dict[str, Any]) -> ActionResult:
        req = AutomationRequest(action_name="mute_volume", params=params)
        res = await self.automation.execute(req)
        return ActionResult(
            success=res.success,
            message=res.message,
            action_name="mute_volume",
            data=res.data,
            error=res.error,
        )

    async def _handle_unmute_volume(self, params: dict[str, Any]) -> ActionResult:
        req = AutomationRequest(action_name="unmute_volume", params=params)
        res = await self.automation.execute(req)
        return ActionResult(
            success=res.success,
            message=res.message,
            action_name="unmute_volume",
            data=res.data,
            error=res.error,
        )

    async def _handle_open_browser(self, params: dict[str, Any]) -> ActionResult:
        target = params.get("url") or params.get("target") or ""
        req = AutomationRequest(action_name="open_browser", target=target, params=params)
        res = await self.automation.execute(req)
        return ActionResult(
            success=res.success,
            message=res.message,
            action_name="open_browser",
            data=res.data,
            error=res.error,
        )

    async def _handle_take_screenshot(self, params: dict[str, Any]) -> ActionResult:
        req = AutomationRequest(action_name="take_screenshot", params=params)
        res = await self.automation.execute(req)
        return ActionResult(
            success=res.success,
            message=res.message,
            action_name="take_screenshot",
            data=res.data,
            error=res.error,
        )

    async def _handle_analyze_screen(self, params: dict[str, Any]) -> ActionResult:
        prompt = params.get("prompt", "Analyze what is on the screen and describe the active application and any errors.")
        if not prompt or not prompt.strip():
            prompt = "Analyze what is on the screen and describe the active application and any errors."

        focus_mode = params.get("focus_mode", "general")
        vision_res = await self.vision_engine.analyze_screen(
            prompt=prompt,
            provider_router=self.provider_router,
            focus_mode=focus_mode,
        )

        if vision_res.success:
            return ActionResult(
                success=True,
                message=vision_res.text,
                action_name="analyze_screen",
                data=vision_res.to_dict(),
            )
        else:
            return ActionResult(
                success=False,
                message=f"Screen vision analysis failed: {vision_res.error or vision_res.text}",
                action_name="analyze_screen",
                data=vision_res.to_dict(),
                error="VisionAnalysisError",
            )

    async def _handle_start_meeting_notes(self, params: dict[str, Any]) -> ActionResult:
        title = params.get("title", "Live Meeting")
        if not title or not title.strip():
            title = "Live Meeting"
        session = await self.meeting_engine.start_meeting(title=title)
        return ActionResult(
            success=True,
            message=f"Started meeting intelligence session '{session.title}'. System audio loopback recording is active and listening for action items and mentions.",
            action_name="start_meeting_notes",
            data={"meeting_id": session.meeting_id, "title": session.title, "start_time": session.start_time},
        )

    async def _handle_stop_meeting_notes(self, params: dict[str, Any]) -> ActionResult:
        session = await self.meeting_engine.stop_meeting()
        if not session:
            return ActionResult(
                success=False,
                message="No active meeting session was found to stop.",
                action_name="stop_meeting_notes",
                data={},
            )
        
        action_count = len(session.action_items)
        mention_count = len(session.mentions)
        msg = f"Meeting '{session.title}' ended ({session.formatted_duration}). Captured {len(session.segments)} segments, {action_count} action items, and {mention_count} mentions. Notes saved."
        return ActionResult(
            success=True,
            message=msg,
            action_name="stop_meeting_notes",
            data=self.meeting_engine.get_summary_dict(),
        )

    async def _handle_get_meeting_summary(self, params: dict[str, Any]) -> ActionResult:
        summary = self.meeting_engine.get_summary_dict()
        if summary.get("status") == "NO_ACTIVE_SESSION":
            return ActionResult(
                success=False,
                message="No meeting session is currently active or recorded.",
                action_name="get_meeting_summary",
                data=summary,
            )
        return ActionResult(
            success=True,
            message=f"Meeting '{summary.get('title')}' Summary:\n{summary.get('markdown_notes')}",
            action_name="get_meeting_summary",
            data=summary,
        )

    async def _handle_system_repair(self, params: dict[str, Any]) -> ActionResult:
        from denver.health.repair import SystemRepairManager

        dry_run = params.get("dry_run", False)
        manager = SystemRepairManager(settings=self.settings)
        report = manager.run_repair(dry_run=dry_run)
        spoken_msg = report.format_spoken_summary()

        return ActionResult(
            success=True,
            message=spoken_msg,
            action_name="system_repair",
            data=report.to_dict(),
        )

    async def _handle_set_voice_brevity(self, params: dict[str, Any]) -> ActionResult:
        mode = str(params.get("mode", "concise")).strip().lower()
        if mode not in ("concise", "detailed", "normal"):
            mode = "concise"

        self.settings.voice_brevity = mode
        msg = (
            "Voice responses switched to concise mode. I will keep verbal answers brief and to the point."
            if mode == "concise"
            else "Voice responses switched to detailed mode. I will provide comprehensive verbal explanations."
        )

        return ActionResult(
            success=True,
            message=msg,
            action_name="set_voice_brevity",
            data={"voice_brevity": mode},
        )

    async def _handle_list_plugins(self, params: dict[str, Any]) -> ActionResult:
        plugins = self.plugin_registry.list_plugins()
        if not plugins:
            return ActionResult(
                success=True,
                message="No external plugins currently installed in the plugins directory.",
                action_name="list_plugins",
                data={"plugins": []},
            )

        lines = [f"{p['name']} ({p['id']}) v{p['version']}: {'ENABLED' if p['enabled'] else 'DISABLED'}" for p in plugins]
        spoken = f"Found {len(plugins)} installed plugins: " + ", ".join(lines)
        return ActionResult(
            success=True,
            message=spoken,
            action_name="list_plugins",
            data={"plugins": plugins},
        )

    async def _handle_enable_plugin(self, params: dict[str, Any]) -> ActionResult:
        p_id = str(params.get("plugin_id", "")).strip().lower()
        if not p_id:
            return ActionResult(success=False, message="Please specify a valid plugin ID to enable.", action_name="enable_plugin")

        success = self.plugin_registry.enable_plugin(p_id)
        msg = f"Plugin '{p_id}' has been enabled successfully." if success else f"Plugin '{p_id}' not found or failed to enable."
        return ActionResult(
            success=success,
            message=msg,
            action_name="enable_plugin",
            data={"plugin_id": p_id, "enabled": success},
        )

    async def _handle_disable_plugin(self, params: dict[str, Any]) -> ActionResult:
        p_id = str(params.get("plugin_id", "")).strip().lower()
        if not p_id:
            return ActionResult(success=False, message="Please specify a valid plugin ID to disable.", action_name="disable_plugin")

        success = self.plugin_registry.disable_plugin(p_id)
        return ActionResult(
            success=True,
            message=f"Plugin '{p_id}' has been disabled.",
            action_name="disable_plugin",
            data={"plugin_id": p_id, "enabled": False},
        )

    async def _handle_reload_plugins(self, params: dict[str, Any]) -> ActionResult:
        count = self.plugin_registry.reload_all()
        return ActionResult(
            success=True,
            message=f"Plugin reload complete. {count} active plugins loaded.",
            action_name="reload_plugins",
            data={"loaded_count": count},
        )

    async def _handle_export_memory(self, params: dict[str, Any]) -> ActionResult:
        target_path = str(params.get("path") or "data/memory_export.json")
        try:
            snapshot = await self.memory.export_safe_memory(export_path=target_path)
            counts = snapshot.get("counts", {})
            total_items = sum(counts.values()) if isinstance(counts, dict) else 0
            return ActionResult(
                success=True,
                message=f"Memory export complete. {total_items} items saved to {target_path}.",
                action_name="export_memory",
                data={"path": target_path, "counts": counts},
            )
        except Exception as exc:
            return ActionResult(
                success=False,
                message=f"Failed to export memory: {exc}",
                action_name="export_memory",
            )

    async def _handle_clear_all_notes(self, params: dict[str, Any]) -> ActionResult:
        try:
            cleared_count = await self.memory.clear_all_notes()
            return ActionResult(
                success=True,
                message=f"All saved notes cleared ({cleared_count} notes removed).",
                action_name="clear_all_notes",
                data={"cleared_count": cleared_count},
            )
        except Exception as exc:
            return ActionResult(
                success=False,
                message=f"Failed to clear notes: {exc}",
                action_name="clear_all_notes",
            )

    async def _handle_list_memories(self, params: dict[str, Any]) -> ActionResult:
        try:
            notes = await self.memory.list_notes()
            prefs = await self.memory.list_preferences()
            locations = await self.memory.list_saved_locations()
            spoken = f"You have {len(notes)} notes, {len(prefs)} preferences, and {len(locations)} saved locations."
            return ActionResult(
                success=True,
                message=spoken,
                action_name="list_memories",
                data={
                    "notes_count": len(notes),
                    "preferences_count": len(prefs),
                    "locations_count": len(locations),
                },
            )
        except Exception as exc:
            return ActionResult(
                success=False,
                message=f"Failed to list memories: {exc}",
                action_name="list_memories",
            )

    async def _handle_get_proactive_suggestions(self, params: dict[str, Any]) -> ActionResult:
        from denver.proactive.models import ProactiveContext

        # Collect live telemetry signals
        battery_pct = None
        plugged = None
        mem_pct = None
        cpu_pct = None
        try:
            sys_summary = self.automation.system.get_system_summary()
            battery_pct = sys_summary.get("battery_percent")
            plugged = sys_summary.get("power_plugged")
            mem_pct = sys_summary.get("memory_percent")
            cpu_pct = sys_summary.get("cpu_percent")
        except Exception:
            pass

        active_title = None
        active_proc = None
        try:
            fg = self.automation.windows.get_foreground_window()
            if fg:
                active_title = fg.title
                active_proc = fg.process_name
        except Exception:
            pass

        pending_tasks = []
        try:
            tasks = await self.memory.list_tasks(include_completed=False)
            pending_tasks = [getattr(t, "task_text", str(t)) for t in tasks]
        except Exception:
            pass

        ctx = ProactiveContext(
            battery_percent=battery_pct,
            battery_power_plugged=plugged,
            cpu_percent=cpu_pct,
            memory_percent=mem_pct,
            active_window_title=active_title,
            active_window_process=active_proc,
            pending_tasks_count=len(pending_tasks),
            pending_tasks_summary=pending_tasks,
        )

        # Evaluate and gather active suggestions
        self.proactive_engine.evaluate(ctx)
        suggestions = self.proactive_engine.get_active_suggestions()

        if not suggestions:
            return ActionResult(
                success=True,
                message="No urgent proactive suggestions at the moment. Everything is running smoothly!",
                action_name="get_proactive_suggestions",
                data={"suggestions": []},
            )

        lines = ["Here are your proactive suggestions:"]
        for idx, s in enumerate(suggestions, 1):
            lines.append(f"{idx}. [{s.category.value.upper()}] {s.title}: {s.message}")

        return ActionResult(
            success=True,
            message="\n".join(lines),
            action_name="get_proactive_suggestions",
            data={"suggestions": [s.to_dict() for s in suggestions]},
        )

    async def _handle_set_proactive_mode(self, params: dict[str, Any]) -> ActionResult:
        enabled = params.get("enabled", True)
        self.proactive_engine.set_enabled(enabled)
        status_str = "enabled" if enabled else "disabled"
        return ActionResult(
            success=True,
            message=f"Proactive intelligence mode has been {status_str}.",
            action_name="set_proactive_mode",
            data={"enabled": enabled},
        )

    async def _handle_dismiss_proactive_suggestions(self, params: dict[str, Any]) -> ActionResult:
        count = self.proactive_engine.dismiss_suggestion()
        return ActionResult(
            success=True,
            message=f"Dismissed {count} proactive suggestion(s).",
            action_name="dismiss_proactive_suggestions",
            data={"dismissed_count": count},
        )

    async def _handle_web_search_query(self, params: dict[str, Any]) -> ActionResult:
        query = params.get("query", "").strip()
        if not query:
            return ActionResult(
                success=False,
                message="Web search query cannot be empty.",
                action_name="web_search_query",
                data={},
            )

        res = await self.web_agent.search_web(query)
        if not res.success:
            return ActionResult(
                success=False,
                message=f"Web search failed: {res.error}",
                action_name="web_search_query",
                data=res.data,
                error="WebSearchError",
            )

        results = res.data.get("results", [])
        lines = [f"Found {len(results)} web search results for '{query}':"]
        for idx, r in enumerate(results[:5], 1):
            title = r.get("title", "Result")
            url = r.get("url", "")
            snippet = r.get("snippet", "")
            lines.append(f"{idx}. **{title}**\n   {snippet}\n   URL: {url}")

        return ActionResult(
            success=True,
            message="\n\n".join(lines),
            action_name="web_search_query",
            data=res.data,
        )

    async def _handle_extract_web_page(self, params: dict[str, Any]) -> ActionResult:
        url = params.get("url", "").strip()
        if not url:
            return ActionResult(
                success=False,
                message="Target webpage URL cannot be empty.",
                action_name="extract_web_page",
                data={},
            )

        res = await self.web_agent.extract_page_content(url)
        if not res.success:
            return ActionResult(
                success=False,
                message=f"Failed to extract webpage content: {res.error}",
                action_name="extract_web_page",
                data={"url": url},
                error="WebExtractionError",
            )

        preview = res.content[:1500] if len(res.content) > 1500 else res.content
        msg = f"📄 Extracted content from **{res.title}** ({res.url}):\n\n{preview}"
        if len(res.content) > 1500:
            msg += "\n\n*(Content truncated for preview)*"

        return ActionResult(
            success=True,
            message=msg,
            action_name="extract_web_page",
            data=res.to_dict(),
        )

    async def _handle_capture_web_screenshot(self, params: dict[str, Any]) -> ActionResult:
        url = params.get("url", "").strip()
        if not url:
            return ActionResult(
                success=False,
                message="Website URL cannot be empty.",
                action_name="capture_web_screenshot",
                data={},
            )

        res = await self.web_agent.capture_web_screenshot(url)
        if not res.success:
            return ActionResult(
                success=False,
                message=f"Failed to capture website screenshot: {res.error}",
                action_name="capture_web_screenshot",
                data={"url": url},
                error="WebScreenshotError",
            )

        return ActionResult(
            success=True,
            message=f"Successfully captured webpage screenshot of {res.url} to '{res.screenshot_path}'.",
            action_name="capture_web_screenshot",
            data=res.to_dict(),
        )

    async def _handle_confirm_action(self, params: dict[str, Any]) -> ActionResult:
        token = params.get("token")
        pending = None
        if token:
            pending = self.automation.confirmation.get_pending(token)
        else:
            pending = self.automation.confirmation.get_latest_pending()

        if not pending:
            return ActionResult(
                success=False,
                message="There are no pending actions requiring confirmation.",
                action_name="confirm_action",
            )

        if pending.action_name == "save_current_location":
            self.automation.confirmation.validate_and_consume(pending.token)
            p = pending.action_params
            label = p.get("label", "home")
            raw_address = p.get("raw_address", "")
            lat = p.get("latitude")
            lon = p.get("longitude")
            saved = await self.memory.save_location(label, raw_address, lat, lon)
            return ActionResult(
                success=True,
                message=f"Confirmed. I've saved {label.capitalize()} as {raw_address}.",
                action_name="save_current_location",
                data=saved.to_dict() if saved else {},
            )

        req = AutomationRequest(
            action_name=pending.action_name,
            target=pending.action_params.get("application") or pending.action_params.get("target") or "",
            params=pending.action_params,
            confirmation_token=pending.token,
        )
        res = await self.automation.execute(req)
        return ActionResult(
            success=res.success,
            message=res.message,
            action_name=pending.action_name,
            data=res.data,
            error=res.error,
        )

    async def _handle_cancel_action(self, params: dict[str, Any]) -> ActionResult:
        token = params.get("token")
        if token:
            self.automation.confirmation.validate_and_consume(token)
        else:
            self.automation.confirmation.clear()
        return ActionResult(
            success=True,
            message="Pending action has been cancelled.",
            action_name="cancel_action",
        )
    async def _handle_create_note(self, params: dict[str, Any]) -> ActionResult:
        title = params.get("title", "")
        content = params.get("content", "")
        note = await self.memory.create_note(title=title, content=content)
        return ActionResult(
            success=True,
            message=f"Created note: '{title or content}'.",
            action_name="create_note",
            data={"note": note.to_dict() if note else {}},
        )

    async def _handle_list_notes(self, params: dict[str, Any]) -> ActionResult:
        notes = await self.memory.list_notes()
        return ActionResult(
            success=True,
            message=f"Found {len(notes)} note(s).",
            action_name="list_notes",
            data={"notes": [n.to_dict() for n in notes]},
        )

    async def _handle_search_notes(self, params: dict[str, Any]) -> ActionResult:
        query = params.get("query", "")
        notes = await self.memory.search_notes(query)
        return ActionResult(
            success=True,
            message=f"Found {len(notes)} note(s) matching '{query}'.",
            action_name="search_notes",
            data={"query": query, "notes": [n.to_dict() for n in notes]},
        )

    async def _handle_create_task(self, params: dict[str, Any]) -> ActionResult:
        task_text = params.get("task_text", "")
        task = await self.memory.create_task(task_text=task_text)
        return ActionResult(
            success=True,
            message=f"Created task: '{task_text}'.",
            action_name="create_task",
            data={"task": task.to_dict() if task else {}},
        )

    async def _handle_list_tasks(self, params: dict[str, Any]) -> ActionResult:
        tasks = await self.memory.list_tasks(include_completed=False)
        return ActionResult(
            success=True,
            message=f"You have {len(tasks)} active task(s).",
            action_name="list_tasks",
            data={"tasks": [t.to_dict() for t in tasks]},
        )

    async def _handle_complete_task(self, params: dict[str, Any]) -> ActionResult:
        task_id = params.get("task_id", 1)
        completed = await self.memory.complete_task(task_id)
        if completed:
            return ActionResult(
                success=True,
                message=f"Task {task_id} marked as completed.",
                action_name="complete_task",
                data={"task_id": task_id},
            )
        return ActionResult(
            success=False,
            message=f"Task {task_id} not found.",
            action_name="complete_task",
            error="TaskNotFound",
        )

    async def _handle_remember(self, params: dict[str, Any]) -> ActionResult:
        category = params.get("category", "fact")
        key = params.get("key")
        content = params.get("content", "")

        # Detect categories and preference signals in text
        content_lower = content.lower()
        if any(w in content_lower for w in ("prefer", "favorite", "preference", "default")):
            category = "preference"
            pref_m = re.search(r"my (?:favorite|preferred)\s+([a-zA-Z0-9_\-]+)\s+is\s+(.+)", content, re.IGNORECASE)
            if pref_m:
                attr = pref_m.group(1).strip().lower()
                val = pref_m.group(2).strip().rstrip(".")
                await self.memory.set_preference(key=attr, value=val, category="general")
                await self.memory.set_preference(key=f"favorite_{attr}", value=val, category="general")
        elif any(w in content_lower for w in ("project", "repo", "repository", "codebase", "develop", "working on")):
            category = "project"
        elif any(w in content_lower for w in ("routine", "workflow", "mode", "session", "deep work", "focus")):
            category = "workflow"
        elif any(w in content_lower for w in ("birthday", "friend", "family", "mom", "dad", "appa", "amma")):
            category = "personal"

        item = await self.memory.remember(
            content=content,
            category=MemoryCategory.from_value(category),
            key=key,
            importance=0.8,
            confidence=1.0,
        )
        return ActionResult(
            success=True,
            message=f"I'll remember that: '{content}'.",
            action_name="remember",
            data={"memory": item.to_dict() if item else {}, "category": category},
        )

    async def _handle_recall_memory(self, params: dict[str, Any]) -> ActionResult:
        query = params.get("query", "")
        results = await self.memory.recall(query=query, top_k=5)
        if not results:
            # Fallback to checking preferences
            clean_q = query.strip().lower()
            prefs = await self.memory.list_preferences()
            matched_prefs = [
                p for p in prefs
                if clean_q in p.key.lower() or p.key.lower() in clean_q or clean_q in str(p.value).lower()
            ]
            if matched_prefs:
                top_p = matched_prefs[0]
                return ActionResult(
                    success=True,
                    message=f"I remember your {top_p.key}: {top_p.value}",
                    action_name="recall_memory",
                    data={"query": query, "preference": top_p.to_dict(), "memories": []},
                )

            return ActionResult(
                success=True,
                message=f"I couldn't find any memories matching '{query}'.",
                action_name="recall_memory",
                data={"query": query, "memories": []},
            )

        items_data = [r.to_dict() for r in results]
        top_mem = results[0].memory.content
        if len(results) == 1:
            msg = f"I remember: {top_mem}"
        else:
            lines = [f"I found {len(results)} relevant memories:"]
            for r in results:
                lines.append(f"- {r.memory.content}")
            msg = "\n".join(lines)

        return ActionResult(
            success=True,
            message=msg,
            action_name="recall_memory",
            data={"query": query, "memories": items_data, "top_match": top_mem},
        )

    async def _handle_forget_memory(self, params: dict[str, Any]) -> ActionResult:
        query = params.get("query", "")
        deleted_count = await self.memory.forget(query=query)
        if deleted_count > 0:
            msg = f"Cleared {deleted_count} memory item(s) related to '{query}'."
        else:
            msg = f"No memory found matching '{query}'."
        return ActionResult(
            success=deleted_count > 0,
            message=msg,
            action_name="forget_memory",
            data={"query": query, "deleted_count": deleted_count},
        )

    async def _handle_set_preference(self, params: dict[str, Any]) -> ActionResult:
        key = params.get("key", "")
        val = params.get("value", "")
        category = params.get("category", "general")
        pref = await self.memory.set_preference(key=key, value=val, category=category)
        if key.startswith("favorite_"):
            base_key = key[len("favorite_"):]
            if base_key:
                await self.memory.set_preference(key=base_key, value=val, category=category)
        else:
            await self.memory.set_preference(key=f"favorite_{key}", value=val, category=category)
        return ActionResult(
            success=True,
            message=f"Preference '{key}' has been updated to '{val}'.",
            action_name="set_preference",
            data={"preference": pref.to_dict() if pref else {}},
        )

    async def _handle_get_preference(self, params: dict[str, Any]) -> ActionResult:
        key = params.get("key", "")
        pref = await self.memory.get_preference(key=key)
        if not pref:
            alt_key = key[len("favorite_"):] if key.startswith("favorite_") else f"favorite_{key}"
            pref = await self.memory.get_preference(key=alt_key)

        if pref:
            return ActionResult(
                success=True,
                message=f"Your {key} is set to '{pref.value}'.",
                action_name="get_preference",
                data={"key": key, "value": pref.value},
            )

        # Fallback to recall query
        results = await self.memory.recall(query=key, top_k=1)
        if results:
            val = results[0].memory.content
            return ActionResult(
                success=True,
                message=f"Your {key} is {val}.",
                action_name="get_preference",
                data={"key": key, "value": val},
            )

        return ActionResult(
            success=False,
            message=f"I don't have a preference stored for '{key}'.",
            action_name="get_preference",
            error="PreferenceNotFound",
        )

    async def _handle_list_preferences(self, params: dict[str, Any]) -> ActionResult:
        prefs = await self.memory.list_preferences()
        pref_dict = {p.key: p.value for p in prefs}
        if not pref_dict:
            return ActionResult(
                success=True,
                message="No saved preferences found.",
                action_name="list_preferences",
                data={"preferences": {}},
            )
        lines = ["Saved preferences:"]
        for k, v in pref_dict.items():
            lines.append(f"- {k}: {v}")
        return ActionResult(
            success=True,
            message="\n".join(lines),
            action_name="list_preferences",
            data={"preferences": pref_dict},
        )

    async def _handle_clear_context(self, params: dict[str, Any]) -> ActionResult:
        self.memory.clear_short_term_buffer()
        return ActionResult(
            success=True,
            message="Conversation context has been cleared.",
            action_name="clear_context",
            data={"cleared": True},
        )


    def _get_tool_definitions(self) -> list[ToolDefinition]:
        """Convert registered actions into provider-independent ToolDefinitions."""
        tools: list[ToolDefinition] = []
        for action in self.registry.list_actions():
            params: list[ToolParameter] = []
            if action.name in {"open_application", "close_application"}:
                params.append(
                    ToolParameter(
                        name="application",
                        type="string",
                        description="Name of the application (e.g. notepad, chrome, calc)",
                        required=True,
                    )
                )
            elif action.name in {"create_note"}:
                params.append(ToolParameter(name="title", type="string", description="Note title", required=False))
                params.append(ToolParameter(name="content", type="string", description="Note content", required=True))
            elif action.name in {"search_notes"}:
                params.append(ToolParameter(name="query", type="string", description="Search query string", required=True))
            elif action.name in {"create_task"}:
                params.append(ToolParameter(name="task_text", type="string", description="Task description", required=True))
            elif action.name in {"complete_task"}:
                params.append(ToolParameter(name="task_id", type="integer", description="ID of task to complete", required=True))
            elif action.name in {"remember"}:
                params.append(ToolParameter(name="content", type="string", description="Information to remember", required=True))
                params.append(ToolParameter(name="category", type="string", description="Category for memory", required=False))
            elif action.name in {"recall_memory", "forget_memory"}:
                params.append(ToolParameter(name="query", type="string", description="Search query for memory", required=True))
            elif action.name in {"set_preference"}:
                params.append(ToolParameter(name="key", type="string", description="Preference key", required=True))
                params.append(ToolParameter(name="value", type="string", description="Preference value", required=True))
            elif action.name in {"minimize_window", "maximize_window", "restore_window", "focus_window"}:
                params.append(ToolParameter(name="window", type="string", description="Window title or keyword", required=True))
            elif action.name in {"open_browser"}:
                params.append(ToolParameter(name="url", type="string", description="URL or website name to open", required=True))
            elif action.name in {"set_volume"}:
                params.append(ToolParameter(name="value", type="integer", description="Volume percentage (0-100)", required=True))
            elif action.name in {"increase_volume", "decrease_volume"}:
                params.append(ToolParameter(name="step", type="integer", description="Volume change step percentage", required=False))
            elif action.name in {"take_screenshot"}:
                params.append(ToolParameter(name="filename", type="string", description="Optional screenshot filename", required=False))
            elif action.name in {"confirm_action"}:
                params.append(ToolParameter(name="token", type="string", description="Optional confirmation token", required=False))

            tools.append(
                ToolDefinition(
                    name=action.name,
                    description=action.description,
                    parameters=params,
                )
            )
        return tools

    async def _process_ai_fallback(
        self,
        req: CommandRequest,
        normalized: str,
        start_time: float,
    ) -> CommandResponse:
        """Handle unknown/complex commands via ProviderRouter fallback with safety validation."""
        if not self.settings.ai_enabled or self.provider_router is None:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            if self.state_machine and self.state_machine.can_transition_to(DenverState.STANDBY):
                await self.state_machine.transition_to(DenverState.STANDBY, reason="Unknown command completed (AI disabled)")

            await self.event_bus.publish(
                CommandFailed(action_name="unknown", reason="UnsupportedIntent", error="Intent not recognized")
            )
            await self.memory.log_audit(
                raw_command=req.raw_text,
                routed_action="unknown",
                provider_used="rules",
                status="blocked",
                latency_ms=elapsed_ms,
            )

            response = CommandResponse(
                success=False,
                message="I don't know how to do that yet.",
                action_name=None,
                data={"raw_text": req.raw_text, "normalized": normalized},
                risk_level=CommandRiskLevel.SAFE,
                confidence=0.0,
                latency_ms=elapsed_ms,
            )
            self.memory.add_conversation_turn(role="denver", content=response.message)
            return response

        # Fetch structured memory context & prepare tool definitions via ContextEngine
        ordered_providers = self.provider_router.get_ordered_providers()
        first_is_cloud = (ordered_providers[0].provider_type.value == "cloud") if ordered_providers else False
        recent_screen = self.vision_engine.get_recent_screen_context() if hasattr(self, "vision_engine") else None
        context_bundle = await self.context_engine.build_context(
            query=req.raw_text,
            is_cloud=first_is_cloud,
            active_screen_context=recent_screen,
        )
        tools = self._get_tool_definitions()

        provider_req = ProviderRequest(
            messages=[{"role": "user", "content": req.raw_text}],
            tools=tools,
            context_summary=context_bundle.context_string,
            temperature=0.7,
        )

        ai_res = await self.provider_router.generate(provider_req)

        if not ai_res.success:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            if self.state_machine and self.state_machine.can_transition_to(DenverState.STANDBY):
                await self.state_machine.transition_to(DenverState.STANDBY, reason="AI fallback unavailable")

            fallback_msg = (
                "No AI provider is currently available."
                if (ai_res.error and ("No AI provider" in ai_res.error or "All available AI providers failed" in ai_res.error))
                else (ai_res.error or "No AI provider is currently available.")
            )
            resp = CommandResponse(
                success=False,
                message=fallback_msg,
                action_name=None,
                data={
                    "error": ai_res.error,
                    "raw_text": req.raw_text,
                    "memories_used": context_bundle.memories_used_count,
                    "context_chars": context_bundle.total_characters,
                },
                risk_level=CommandRiskLevel.SAFE,
                confidence=0.0,
                latency_ms=elapsed_ms,
                error=ai_res.error,
            )
            self.memory.add_conversation_turn(role="denver", content=resp.message)
            return resp

        # Check if model returned tool proposals
        if ai_res.tool_calls:
            tc = ai_res.tool_calls[0]
            action_def = self.registry.get(tc.action_name)

            if not action_def:
                elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
                if self.state_machine and self.state_machine.can_transition_to(DenverState.STANDBY):
                    await self.state_machine.transition_to(DenverState.STANDBY, reason="AI tool not registered")

                err_msg = f"Proposed action '{tc.action_name}' is not recognized or registered."
                await self.event_bus.publish(
                    CommandFailed(action_name=tc.action_name, reason="ActionNotFound", error=err_msg)
                )
                await self.memory.log_audit(
                    raw_command=req.raw_text,
                    routed_action=tc.action_name,
                    provider_used=ai_res.provider_name,
                    status="blocked",
                    latency_ms=elapsed_ms,
                )
                resp = CommandResponse(
                    success=False,
                    message=err_msg,
                    action_name=tc.action_name,
                    risk_level=CommandRiskLevel.BLOCKED,
                    data={"ai_tool_call": tc.to_dict(), "provider": ai_res.provider_name},
                    error="ActionNotFound",
                    latency_ms=elapsed_ms,
                )
                self.memory.add_conversation_turn(role="denver", content=resp.message)
                return resp

            action_request = ActionRequest(
                action_name=tc.action_name,
                params=tc.parameters,
                risk_level=action_def.risk_level,
                requires_confirmation=action_def.requires_confirmation,
            )

            is_safe, safety_err = self.safety.validate(action_request)
            if not is_safe:
                elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
                logger.warning("AI proposed action '%s' blocked by safety: %s", tc.action_name, safety_err)
                if self.state_machine and self.state_machine.can_transition_to(DenverState.STANDBY):
                    await self.state_machine.transition_to(DenverState.STANDBY, reason="AI tool safety blocked")

                await self.event_bus.publish(
                    CommandFailed(action_name=tc.action_name, reason="SafetyBlocked", error=safety_err or "")
                )
                await self.memory.log_audit(
                    raw_command=req.raw_text,
                    routed_action=tc.action_name,
                    provider_used=ai_res.provider_name,
                    status="blocked",
                    latency_ms=elapsed_ms,
                )
                resp = CommandResponse(
                    success=False,
                    message=f"Action '{tc.action_name}' was blocked: {safety_err}",
                    action_name=tc.action_name,
                    data={"safety_violation": safety_err, "ai_tool_call": tc.to_dict(), "provider": ai_res.provider_name},
                    risk_level=CommandRiskLevel.BLOCKED,
                    confidence=1.0,
                    latency_ms=elapsed_ms,
                    error=safety_err,
                )
                self.memory.add_conversation_turn(role="denver", content=resp.message)
                return resp

            # Execute safe registered action
            if self.state_machine and self.state_machine.can_transition_to(DenverState.EXECUTING):
                await self.state_machine.transition_to(
                    DenverState.EXECUTING,
                    reason=f"Executing AI proposed action: '{tc.action_name}'",
                )

            await self.event_bus.publish(
                CommandExecutionStarted(
                    action_name=action_request.action_name,
                    risk_level=action_request.risk_level.value,
                )
            )

            result = await self.executor.execute(action_request)
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

            if self.state_machine and self.state_machine.can_transition_to(DenverState.STANDBY):
                await self.state_machine.transition_to(DenverState.STANDBY, reason="AI action completed")

            status_str = "success" if result.success else "failed"
            await self.memory.log_audit(
                raw_command=req.raw_text,
                routed_action=tc.action_name,
                provider_used=ai_res.provider_name,
                status=status_str,
                latency_ms=elapsed_ms,
            )

            resp = CommandResponse(
                success=result.success,
                message=result.message,
                action_name=tc.action_name,
                data={
                    "ai_proposed": True,
                    "provider": ai_res.provider_name,
                    "model": ai_res.model_name,
                    "memories_used": context_bundle.memories_used_count,
                    "context_chars": context_bundle.total_characters,
                    "retrieval_reasons": context_bundle.retrieval_reasons,
                    **result.data,
                },
                risk_level=action_def.risk_level,
                confidence=1.0,
                latency_ms=elapsed_ms,
                error=result.error,
            )
            self.memory.add_conversation_turn(role="denver", content=resp.message)
            return resp

        # Plain text AI conversational response
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        if self.state_machine and self.state_machine.can_transition_to(DenverState.STANDBY):
            await self.state_machine.transition_to(DenverState.STANDBY, reason="AI response completed")

        await self.memory.log_audit(
            raw_command=req.raw_text,
            routed_action="ai_chat",
            provider_used=ai_res.provider_name,
            status="success",
            latency_ms=elapsed_ms,
        )

        resp = CommandResponse(
            success=True,
            message=ai_res.text,
            action_name=None,
            data={
                "provider": ai_res.provider_name,
                "model": ai_res.model_name,
                "usage": ai_res.usage,
                "memories_used": context_bundle.memories_used_count,
                "context_chars": context_bundle.total_characters,
                "retrieval_reasons": context_bundle.retrieval_reasons,
            },
            risk_level=CommandRiskLevel.SAFE,
            confidence=1.0,
            latency_ms=elapsed_ms,
        )
        self.memory.add_conversation_turn(role="denver", content=resp.message)
        return resp

    # -------------------------------------------------------------------------
    # Phase 9 Task & Workflow Handlers
    # -------------------------------------------------------------------------
    async def _handle_plan_task(self, params: dict[str, Any]) -> ActionResult:
        if not self.task_registry:
            return ActionResult(
                success=False,
                message="Task orchestration subsystem is not configured.",
                action_name="plan_task",
                error="task_registry_unavailable",
            )
        plan_text = params.get("plan_text", "").strip()
        if not plan_text:
            return ActionResult(
                success=False,
                message="Please specify a task or workflow description to plan.",
                action_name="plan_task",
                error="missing_plan_text",
            )

        try:
            task = self.task_registry.create_task(title=plan_text[:60], description=plan_text)
            # Check if plan_text contains JSON or if AI planner should be used or default step
            if "{" in plan_text and "}" in plan_text:
                plan = self.task_registry.plan_task(task.task_id, plan_text)
            else:
                # Use single-step action or AI provider proposal
                actions = [{"step_id": "step_1", "action_name": "get_system_status", "description": plan_text}]
                plan = self.task_registry.plan_task(task.task_id, actions)

            return ActionResult(
                success=True,
                message=f"Created task plan '{plan.plan_id}' for task '{task.task_id}' with {len(plan.steps)} steps.",
                action_name="plan_task",
                data={"task": task.to_dict(), "plan": plan.to_dict()},
            )
        except Exception as exc:
            logger.error("Failed to plan task: %s", exc)
            return ActionResult(
                success=False,
                message=f"Failed to create task plan: {exc}",
                action_name="plan_task",
                error=str(exc),
            )

    async def _handle_show_task_status(self, params: dict[str, Any]) -> ActionResult:
        if not self.task_registry:
            return ActionResult(
                success=False,
                message="Task orchestration subsystem is not configured.",
                action_name="show_task_status",
                error="task_registry_unavailable",
            )
        task_id = params.get("task_id", "").strip()
        task = self.task_registry.get_task(task_id)
        if not task:
            return ActionResult(
                success=False,
                message=f"Task '{task_id}' not found.",
                action_name="show_task_status",
                error="not_found",
            )
        plan = self.task_registry.get_plan(task.current_plan_id) if task.current_plan_id else None
        return ActionResult(
            success=True,
            message=f"Task '{task.title}' [{task.task_id}] status: {task.status.value}",
            action_name="show_task_status",
            data={
                "task": task.to_dict(),
                "plan": plan.to_dict() if plan else None,
            },
        )

    async def _handle_show_task_history(self, params: dict[str, Any]) -> ActionResult:
        if not self.task_registry:
            return ActionResult(
                success=False,
                message="Task orchestration subsystem is not configured.",
                action_name="show_task_history",
                error="task_registry_unavailable",
            )
        task_id = params.get("task_id", "").strip()
        history = self.task_registry.get_task_history(task_id)
        return ActionResult(
            success=True,
            message=f"Found {len(history)} execution records for task '{task_id}'.",
            action_name="show_task_history",
            data={"executions": [h.to_dict() for h in history]},
        )

    async def _handle_run_task(self, params: dict[str, Any]) -> ActionResult:
        if not self.task_registry:
            return ActionResult(
                success=False,
                message="Task orchestration subsystem is not configured.",
                action_name="run_task",
                error="task_registry_unavailable",
            )
        task_id = params.get("task_id", "").strip()
        try:
            result = await self.task_registry.run_task(task_id)
            return ActionResult(
                success=(result.status.value == "completed"),
                message=f"Task '{task_id}' executed with status: {result.status.value}",
                action_name="run_task",
                data={
                    "task_id": result.task_id,
                    "execution_id": result.execution_id,
                    "status": result.status.value,
                    "steps_completed": result.steps_completed,
                    "steps_failed": result.steps_failed,
                    "duration_ms": result.duration_ms,
                },
                error=result.error_message if result.error_message else None,
            )
        except Exception as exc:
            logger.error("Error executing task %s: %s", task_id, exc)
            return ActionResult(
                success=False,
                message=f"Task execution error: {exc}",
                action_name="run_task",
                error=str(exc),
            )

    async def _handle_pause_task(self, params: dict[str, Any]) -> ActionResult:
        if not self.task_registry:
            return ActionResult(
                success=False,
                message="Task orchestration subsystem is not configured.",
                action_name="pause_task",
                error="task_registry_unavailable",
            )
        task_id = params.get("task_id", "").strip()
        success = self.task_registry.pause_task(task_id)
        return ActionResult(
            success=success,
            message=f"Task '{task_id}' has been paused." if success else f"Could not pause task '{task_id}'.",
            action_name="pause_task",
        )

    async def _handle_resume_task(self, params: dict[str, Any]) -> ActionResult:
        if not self.task_registry:
            return ActionResult(
                success=False,
                message="Task orchestration subsystem is not configured.",
                action_name="resume_task",
                error="task_registry_unavailable",
            )
        task_id = params.get("task_id", "").strip()
        success = self.task_registry.resume_task(task_id)
        return ActionResult(
            success=success,
            message=f"Task '{task_id}' has been resumed." if success else f"Could not resume task '{task_id}'.",
            action_name="resume_task",
        )

    async def _handle_cancel_task(self, params: dict[str, Any]) -> ActionResult:
        if not self.task_registry:
            return ActionResult(
                success=False,
                message="Task orchestration subsystem is not configured.",
                action_name="cancel_task",
                error="task_registry_unavailable",
            )
        task_id = params.get("task_id", "").strip()
        success = self.task_registry.cancel_task(task_id)
        return ActionResult(
            success=success,
            message=f"Task '{task_id}' has been cancelled." if success else f"Could not cancel task '{task_id}'.",
            action_name="cancel_task",
        )

    async def _handle_delete_task(self, params: dict[str, Any]) -> ActionResult:
        if not self.task_registry:
            return ActionResult(
                success=False,
                message="Task orchestration subsystem is not configured.",
                action_name="delete_task",
                error="task_registry_unavailable",
            )
        task_id = params.get("task_id", "").strip()
        success = self.task_registry.delete_task(task_id)
        return ActionResult(
            success=success,
            message=f"Task '{task_id}' has been deleted." if success else f"Could not delete task '{task_id}'.",
            action_name="delete_task",
        )

    async def _handle_pause_all_tasks(self, params: dict[str, Any]) -> ActionResult:
        if not self.task_registry:
            return ActionResult(
                success=False,
                message="Task orchestration subsystem is not configured.",
                action_name="pause_all_tasks",
                error="task_registry_unavailable",
            )
        self.task_registry.pause_all_tasks()
        return ActionResult(
            success=True,
            message="All active task workflows have been paused.",
            action_name="pause_all_tasks",
        )

    async def _handle_resume_all_tasks(self, params: dict[str, Any]) -> ActionResult:
        if not self.task_registry:
            return ActionResult(
                success=False,
                message="Task orchestration subsystem is not configured.",
                action_name="resume_all_tasks",
                error="task_registry_unavailable",
            )
        self.task_registry.resume_all_tasks()
        return ActionResult(
            success=True,
            message="All task workflows have been resumed.",
            action_name="resume_all_tasks",
        )

    async def _handle_enable_tasks(self, params: dict[str, Any]) -> ActionResult:
        if not self.task_registry:
            return ActionResult(
                success=False,
                message="Task orchestration subsystem is not configured.",
                action_name="enable_tasks",
                error="task_registry_unavailable",
            )
        self.task_registry.enable()
        return ActionResult(
            success=True,
            message="Task and workflow orchestration has been enabled.",
            action_name="enable_tasks",
        )

    async def _handle_disable_tasks(self, params: dict[str, Any]) -> ActionResult:
        if not self.task_registry:
            return ActionResult(
                success=False,
                message="Task orchestration subsystem is not configured.",
                action_name="disable_tasks",
                error="task_registry_unavailable",
            )
        self.task_registry.disable()
        return ActionResult(
            success=True,
            message="Task and workflow orchestration has been disabled.",
            action_name="disable_tasks",
        )

    async def _handle_approve_task_step(self, params: dict[str, Any]) -> ActionResult:
        if not self.task_registry:
            return ActionResult(
                success=False,
                message="Task orchestration subsystem is not configured.",
                action_name="approve_task_step",
                error="task_registry_unavailable",
            )
        approval_id = params.get("approval_id", "").strip()
        success = self.task_registry.approve_step(approval_id)
        return ActionResult(
            success=success,
            message=f"Step confirmation '{approval_id}' was approved." if success else f"Failed to approve '{approval_id}'.",
            action_name="approve_task_step",
        )

    async def _handle_reject_task_step(self, params: dict[str, Any]) -> ActionResult:
        if not self.task_registry:
            return ActionResult(
                success=False,
                message="Task orchestration subsystem is not configured.",
                action_name="reject_task_step",
                error="task_registry_unavailable",
            )
        approval_id = params.get("approval_id", "").strip()
        reason = params.get("reason", "User rejected confirmation")
        success = self.task_registry.reject_step(approval_id, reason=reason)
        return ActionResult(
            success=success,
            message=f"Step confirmation '{approval_id}' was rejected." if success else f"Failed to reject '{approval_id}'.",
            action_name="reject_task_step",
        )

    # -------------------------------------------------------------------------
    # Weather, Navigation & Saved Location Handlers (Phase 10)
    # -------------------------------------------------------------------------
    async def _resolve_city(self, requested_city: str | None) -> str:
        """Resolve city name from argument, live location, saved home location, or user preference."""
        clean = (requested_city or "").strip()
        if clean and clean.lower() not in {"here", "current", "current location", "my location", "current city", "today", "now", "right now"}:
            return clean

        # If 'here' or empty, prioritize real-time location detection
        if self.location_service:
            loc = await self.location_service.detect_current_location()
            if loc.success and (loc.city or loc.formatted_address):
                return loc.city or loc.formatted_address

        # Check saved location 'home'
        home_loc = await self.memory.get_saved_location("home")
        if home_loc and home_loc.raw_address:
            return home_loc.raw_address
        # Check user preferences for home_city or location
        pref_city = await self.memory.get_preference("home_city") or await self.memory.get_preference("city") or await self.memory.get_preference("location")
        if pref_city and pref_city.value:
            return pref_city.value
        return ""

    async def _handle_get_weather(self, params: dict[str, Any]) -> ActionResult:
        city = await self._resolve_city(params.get("city"))
        if not city:
            return ActionResult(
                success=True,
                message="Which city's weather would you like to check? You can say: 'weather in Paris' or save your home city by saying: 'remember this address as home: London'.",
                action_name="get_weather",
                data={"status": "missing_city"},
            )
        report = await self.weather_service.get_current_weather(city)
        return ActionResult(
            success=report.source != "error",
            message=report.to_spoken_summary(),
            action_name="get_weather",
            data=report.to_dict(),
        )

    async def _handle_get_weather_forecast(self, params: dict[str, Any]) -> ActionResult:
        city = await self._resolve_city(params.get("city"))
        if not city:
            return ActionResult(
                success=True,
                message="Which city's forecast would you like to check? You can say: 'weather forecast for Tokyo'.",
                action_name="get_weather_forecast",
                data={"status": "missing_city"},
            )
        days = params.get("days", 1)
        report = await self.weather_service.get_forecast(city, days=days)
        return ActionResult(
            success=report.source != "error",
            message=report.to_spoken_summary(),
            action_name="get_weather_forecast",
            data=report.to_dict(),
        )

    async def _handle_get_directions(self, params: dict[str, Any]) -> ActionResult:
        orig = params.get("origin", "").strip()
        dest = params.get("destination", "").strip()
        mode = params.get("mode", "driving").strip()

        # Resolve origin if 'here' or 'current location'
        if orig.lower() in ("here", "current location", "my location", "where i am"):
            if self.location_service:
                loc = await self.location_service.detect_current_location()
                if loc.success and (loc.formatted_address or loc.city):
                    orig = loc.formatted_address or loc.city

        # Resolve origin if 'home'
        elif orig.lower() in ("home", "my home", "my house"):
            home_loc = await self.memory.get_saved_location("home")
            if home_loc:
                orig = home_loc.raw_address
            else:
                return ActionResult(
                    success=True,
                    message="I don't have a home address saved yet to calculate directions from. You can save one by saying: 'remember this address as home: 123 Main Street'.",
                    action_name="get_directions",
                    data={"status": "missing_home"},
                )

        # Resolve destination if named label
        saved_dest = await self.memory.get_saved_location(dest.lower())
        if saved_dest:
            dest = saved_dest.raw_address

        res = await self.navigation_service.calculate_route(orig, dest, mode)
        return ActionResult(
            success=res.source != "error",
            message=res.spoken_summary,
            action_name="get_directions",
            data=res.to_dict(),
        )

    async def _handle_navigate_to(self, params: dict[str, Any]) -> ActionResult:
        dest = params.get("destination", "").strip()
        mode = params.get("mode", "driving").strip()

        # Resolve saved home location for origin
        home_loc = await self.memory.get_saved_location("home")
        if not home_loc:
            return ActionResult(
                success=True,
                message="I don't have a home address saved yet to navigate from. You can set one by saying: 'remember this address as home: [your address]'.",
                action_name="navigate_to",
                data={"status": "missing_home"},
            )

        # Check if destination is a saved label like 'office' or 'gym'
        saved_dest = await self.memory.get_saved_location(dest.lower())
        if saved_dest:
            dest = saved_dest.raw_address

        res = await self.navigation_service.calculate_route(home_loc.raw_address, dest, mode)
        return ActionResult(
            success=res.source != "error",
            message=res.spoken_summary,
            action_name="navigate_to",
            data=res.to_dict(),
        )

    async def _handle_switch_directions_mode(self, params: dict[str, Any]) -> ActionResult:
        mode = params.get("mode", "driving").strip()
        res = await self.navigation_service.switch_last_route_mode(mode)
        return ActionResult(
            success=res.source != "error",
            message=res.spoken_summary,
            action_name="switch_directions_mode",
            data=res.to_dict(),
        )

    async def _handle_save_location(self, params: dict[str, Any]) -> ActionResult:
        label = params.get("label", "").strip().lower()
        addr = params.get("raw_address", "").strip()
        if not label or not addr:
            return ActionResult(
                success=False,
                message="Please specify both a location label and an address. For example: 'remember this address as home: 123 MG Road'.",
                action_name="save_location",
            )

        # Geocode once at save time
        geo = await self.weather_service.geocode(addr)
        loc = await self.memory.save_location(
            label=label,
            raw_address=addr,
            latitude=geo.latitude if geo else None,
            longitude=geo.longitude if geo else None,
        )
        coords_info = f" ({geo.latitude:.4f}, {geo.longitude:.4f})" if geo else ""
        return ActionResult(
            success=True,
            message=f"I've saved {label.capitalize()} as {addr}{coords_info}.",
            action_name="save_location",
            data=loc.to_dict(),
        )

    async def _handle_get_saved_location(self, params: dict[str, Any]) -> ActionResult:
        label = params.get("label", "").strip().lower()
        if label:
            loc = await self.memory.get_saved_location(label)
            if loc:
                return ActionResult(
                    success=True,
                    message=f"Your saved {loc.label.capitalize()} location is {loc.raw_address}.",
                    action_name="get_saved_location",
                    data=loc.to_dict(),
                )
            return ActionResult(
                success=True,
                message=f"You don't have a location saved for '{label}'. You can save it by saying: 'remember this address as {label}: [address]'.",
                action_name="get_saved_location",
                data={"found": False, "label": label},
            )

        locs = await self.memory.list_saved_locations()
        if not locs:
            return ActionResult(
                success=True,
                message="You have no saved locations. You can save one by saying: 'remember this address as home: [address]'.",
                action_name="get_saved_location",
                data={"locations": [], "count": 0},
            )
        summary = ", ".join(f"{l.label.capitalize()}: {l.raw_address}" for l in locs)
        return ActionResult(
            success=True,
            message=f"Here are your saved locations: {summary}.",
            action_name="get_saved_location",
            data={"locations": [l.to_dict() for l in locs], "count": len(locs)},
        )

    async def _handle_delete_saved_location(self, params: dict[str, Any]) -> ActionResult:
        label = params.get("label", "").strip().lower()
        if not label:
            return ActionResult(
                success=False,
                message="Please specify the name of the saved location to remove.",
                action_name="delete_saved_location",
            )
        deleted = await self.memory.delete_saved_location(label)
        if deleted:
            return ActionResult(
                success=True,
                message=f"Removed saved location '{label}'.",
                action_name="delete_saved_location",
                data={"deleted": True, "label": label},
            )
        return ActionResult(
            success=True,
            message=f"No saved location found for '{label}'.",
            action_name="delete_saved_location",
            data={"deleted": False, "label": label},
        )

    async def _handle_get_current_location(self, params: dict[str, Any]) -> ActionResult:
        """Handle real-time physical/network location detection."""
        force_refresh = params.get("force_refresh", False)
        loc = await self.location_service.detect_current_location(force_refresh=force_refresh)
        if not loc.success:
            return ActionResult(
                success=False,
                message=loc.spoken_description or "Could not detect your current location. Please specify a city name.",
                action_name="get_current_location",
                error=loc.error,
            )

        summary = f"Your current location is {loc.spoken_description}."
        if loc.is_stale:
            summary = loc.spoken_description
        return ActionResult(
            success=True,
            message=summary,
            action_name="get_current_location",
            data=loc.to_dict(),
        )

    async def _handle_save_current_location(self, params: dict[str, Any]) -> ActionResult:
        """Handle detecting current location and confirming before saving to memory."""
        label = params.get("label", "home").strip().lower()
        if not label:
            label = "home"

        force = params.get("force", False) or params.get("confirmed", False)
        loc = await self.location_service.detect_current_location()
        if not loc.success:
            return ActionResult(
                success=False,
                message="Could not detect your current location to save. Please provide the address explicitly.",
                action_name="save_current_location",
                error=loc.error,
            )

        address_to_save = loc.formatted_address or loc.spoken_description
        lat = loc.latitude
        lon = loc.longitude

        if force:
            saved = await self.memory.save_location(label, address_to_save, lat, lon)
            return ActionResult(
                success=True,
                message=f"I've saved {label.capitalize()} as {address_to_save}.",
                action_name="save_current_location",
                data=saved.to_dict() if saved else {},
            )

        # Stage confirmation token
        req = self.automation.confirmation.create_pending(
            action_name="save_current_location",
            action_params={
                "label": label,
                "raw_address": address_to_save,
                "latitude": lat,
                "longitude": lon,
                "confirmed": True,
            },
            prompt_message=f"I detected you're near {address_to_save} — save this as {label.capitalize()}?",
        )
        return ActionResult(
            success=True,
            message=f"I detected you're near {address_to_save}. Please say 'confirm' or 'yes' to save this as your {label.capitalize()} location, or 'cancel' to abort.",
            action_name="save_current_location",
            data={"token": req.token, "label": label, "detected_location": loc.to_dict(), "requires_confirmation": True},
        )


    # -------------------------------------------------------------------------
    # Main Processing Pipeline
    # -------------------------------------------------------------------------
    async def process_command(
        self,
        command_text: str | CommandRequest,
        context: CommandContext | None = None,
    ) -> CommandResponse:
        """Process a raw user command end-to-end through the deterministic and fallback pipeline."""
        start_time = time.perf_counter()
        if isinstance(command_text, CommandRequest):
            req = command_text
        else:
            req = CommandRequest(
                raw_text=str(command_text),
                source="text",
                context=context or CommandContext(),
            )

        # 1. Ephemeral Conversation Buffering
        self.memory.add_conversation_turn(role="user", content=req.raw_text)

        # 2. Event: CommandReceived
        await self.event_bus.publish(CommandReceived(command_text=req.raw_text, source=req.source))

        # 3. Normalization
        normalized = self.normalizer.normalize(req.raw_text)
        await self.event_bus.publish(
            CommandNormalized(raw_text=req.raw_text, normalized_text=normalized)
        )

        # 4. State transition: -> PROCESSING
        if self.state_machine and self.state_machine.can_transition_to(DenverState.PROCESSING):
            await self.state_machine.transition_to(
                DenverState.PROCESSING,
                reason=f"Processing command: '{normalized}'",
            )

        # 5. Intent Routing (Tier 1: Deterministic)
        intent = self.router.route(normalized)
        await self.event_bus.publish(
            CommandRouted(
                intent_name=intent.intent_name,
                action_name=intent.action_name,
                category=intent.category.value,
                confidence=intent.confidence,
                risk_level=intent.risk_level.value,
            )
        )

        # Record command habit
        if normalized:
            await self.memory.record_habit(normalized)

        # 5b. Sleep Mode Gate: Stay dormant unless waking up
        if getattr(self, "_is_sleeping", False):
            if intent.action_name == "wake_up" or "wake up" in normalized or "wake" in normalized:
                self._is_sleeping = False
                res = await self._handle_wake_up({})
                elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
                if self.state_machine and self.state_machine.can_transition_to(DenverState.STANDBY):
                    await self.state_machine.transition_to(DenverState.STANDBY, reason="Woke up from sleep mode")
                resp = CommandResponse(
                    success=True,
                    message=res.message,
                    action_name="wake_up",
                    data=res.data,
                    risk_level=CommandRiskLevel.SAFE,
                    confidence=1.0,
                    latency_ms=elapsed_ms,
                )
                self.memory.add_conversation_turn(role="denver", content=resp.message)
                return resp
            else:
                elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
                if self.state_machine and self.state_machine.can_transition_to(DenverState.STANDBY):
                    await self.state_machine.transition_to(DenverState.STANDBY, reason="Silent while in sleep mode")
                return CommandResponse(
                    success=True,
                    message="",
                    action_name="sleeping",
                    data={"is_sleeping": True},
                    risk_level=CommandRiskLevel.SAFE,
                    confidence=1.0,
                    latency_ms=elapsed_ms,
                )

        # 6. Check for Unsupported/Unknown Intent -> Check Plugins then AI FALLBACK
        if intent.intent_name == "unknown" or intent.action_name == "unknown":
            # Check if an active plugin can handle this command utterance
            plugin_res = self.plugin_registry.dispatch_command(normalized or req.raw_text)
            if plugin_res:
                elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
                if self.state_machine and self.state_machine.can_transition_to(DenverState.STANDBY):
                    await self.state_machine.transition_to(DenverState.STANDBY, reason="Plugin handled command")
                resp = CommandResponse(
                    success=True,
                    message=plugin_res,
                    action_name="plugin_command",
                    data={"plugin_handled": True},
                    risk_level=CommandRiskLevel.LOW,
                    confidence=1.0,
                    latency_ms=elapsed_ms,
                )
                self.memory.add_conversation_turn(role="denver", content=resp.message)
                return resp

            return await self._process_ai_fallback(req, normalized, start_time)

        # 7. Safety Validation
        action_request = ActionRequest(
            action_name=intent.action_name,
            params=intent.params,
            risk_level=intent.risk_level,
            requires_confirmation=intent.requires_confirmation,
        )

        is_safe, safety_err = self.safety.validate(action_request)
        if not is_safe:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.warning("Action '%s' blocked by safety policy: %s", intent.action_name, safety_err)
            if self.state_machine and self.state_machine.can_transition_to(DenverState.STANDBY):
                await self.state_machine.transition_to(DenverState.STANDBY, reason="Safety violation aborted")

            await self.event_bus.publish(
                CommandFailed(action_name=intent.action_name, reason="SafetyBlocked", error=safety_err or "")
            )
            await self.memory.log_audit(
                raw_command=req.raw_text,
                routed_action=intent.action_name,
                provider_used="rules",
                status="blocked",
                latency_ms=elapsed_ms,
            )

            response = CommandResponse(
                success=False,
                message=f"Action '{intent.action_name}' was blocked: {safety_err}",
                action_name=intent.action_name,
                data={"safety_violation": safety_err},
                risk_level=CommandRiskLevel.BLOCKED,
                confidence=intent.confidence,
                latency_ms=elapsed_ms,
                error=safety_err,
            )
            self.memory.add_conversation_turn(role="denver", content=response.message)
            return response

        # 8. State transition: -> EXECUTING
        if self.state_machine and self.state_machine.can_transition_to(DenverState.EXECUTING):
            await self.state_machine.transition_to(
                DenverState.EXECUTING,
                reason=f"Executing action: '{intent.action_name}'",
            )

        # 9. Action Execution
        await self.event_bus.publish(
            CommandExecutionStarted(
                action_name=action_request.action_name,
                risk_level=action_request.risk_level.value,
            )
        )

        result = await self.executor.execute(action_request)
        
        # If application was rejected because target is not in allowlist (e.g. natural language sentence),
        # automatically fallback to AI Multi-Model LLM!
        if (
            not result.success
            and result.error == "ApplicationNotAllowlisted"
            and self.settings.ai_enabled
            and self.provider_router is not None
        ):
            logger.info("Unrecognized application target '%s'; seamlessly falling back to AI Engine.", action_request.params.get("application"))
            return await self._process_ai_fallback(req, normalized, start_time)

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # 10. State transition: -> STANDBY
        if self.state_machine and self.state_machine.can_transition_to(DenverState.STANDBY):
            await self.state_machine.transition_to(DenverState.STANDBY, reason="Execution complete")

        # 11. Structured Audit Log & Events
        status_str = "success" if result.success else "failed"
        await self.memory.log_audit(
            raw_command=req.raw_text,
            routed_action=intent.action_name,
            provider_used="rules",
            status=status_str,
            latency_ms=elapsed_ms,
        )

        if result.success:
            await self.event_bus.publish(
                CommandExecutionCompleted(
                    action_name=intent.action_name,
                    success=True,
                    latency_ms=elapsed_ms,
                )
            )
        else:
            await self.event_bus.publish(
                CommandFailed(
                    action_name=intent.action_name,
                    reason="ExecutionError",
                    error=result.error or "",
                )
            )

        response = CommandResponse(
            success=result.success,
            message=result.message,
            action_name=intent.action_name,
            data=result.data,
            risk_level=intent.risk_level,
            confidence=intent.confidence,
            latency_ms=elapsed_ms,
            error=result.error,
        )
        self.memory.add_conversation_turn(role="denver", content=response.message)
        return response
