"""UI Controller & Qt Async Event Bridge for Denver Cockpit."""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, Callable

try:
    from PySide6.QtCore import QObject, QTimer, Signal
    _PYSIDE_AVAILABLE = True
except ImportError:
    _PYSIDE_AVAILABLE = False
    QObject = object  # type: ignore
    Signal = lambda *args: None  # type: ignore

from denver.commands.models import CommandResponse
from denver.logging.logger import get_logger
from denver.runtime.events import (
    ApplicationStarted,
    ApplicationStopped,
    ApplicationStopping,
    AutomationConfirmationRequired,
    CommandExecutionCompleted,
    CommandExecutionStarted,
    CommandFailed,
    DenverEvent,
    SpeechStarted,
    SpeechStopped,
    StateChanged,
    WakeWordDetected,
)
from denver.runtime.states import DenverState
from denver.ui.state import ActivityItem, CockpitState, ConfirmationItem

logger = get_logger("ui.controller")


class QtEventBridge(QObject):
    """Thread-safe Qt Signal emitter dispatching Denver events to the GUI thread."""

    if _PYSIDE_AVAILABLE:
        state_changed = Signal(object, str)
        activity_added = Signal(object)
        telemetry_updated = Signal(object)
        voice_state_changed = Signal(str, bool, bool)
        ai_providers_updated = Signal(dict)
        automation_updated = Signal(dict)
        memory_updated = Signal(dict)
        confirmation_required = Signal(object)
        confirmation_cleared = Signal()
        plugins_updated = Signal(list)
        repair_completed = Signal(int, int, str)


class UIController:
    """Orchestrates communication between Denver backend services and Cockpit GUI."""

    def __init__(
        self,
        app_instance: Any | None = None,
        bridge: QtEventBridge | None = None,
        event_loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        self.app = app_instance
        self.bridge = bridge or (QtEventBridge() if _PYSIDE_AVAILABLE else None)
        self.event_loop = event_loop
        self.state = CockpitState()
        self._subscribed = False

        # Setup telemetry polling timer (1500 ms)
        if _PYSIDE_AVAILABLE:
            self._telemetry_timer = QTimer()
            self._telemetry_timer.timeout.connect(self.poll_telemetry)
            self._telemetry_timer.start(1500)

    def bind_event_bus(self) -> None:
        """Subscribe to Denver asynchronous EventBus events."""
        if not self.app or not hasattr(self.app, "event_bus") or self._subscribed:
            return

        eb = self.app.event_bus

        async def _on_state_changed(event: StateChanged) -> None:
            self.state.current_state = event.to_state
            self.state.state_reason = event.reason
            if self.bridge and hasattr(self.bridge, "state_changed"):
                self.bridge.state_changed.emit(event.to_state, event.reason)

        async def _on_speech_started(event: SpeechStarted) -> None:
            self.state.microphone_active = True
            self.state.voice_state = "LISTENING"
            if self.bridge and hasattr(self.bridge, "voice_state_changed"):
                self.bridge.voice_state_changed.emit("LISTENING", True, True)

        async def _on_speech_stopped(event: SpeechStopped) -> None:
            self.state.microphone_active = False
            self.state.voice_state = "PROCESSING"
            if self.bridge and hasattr(self.bridge, "voice_state_changed"):
                self.bridge.voice_state_changed.emit("PROCESSING", False, True)

        async def _on_wakeword(event: WakeWordDetected) -> None:
            self.state.voice_state = "WAKE WORD"
            if self.bridge and hasattr(self.bridge, "voice_state_changed"):
                self.bridge.voice_state_changed.emit("WAKE WORD", True, True)

        async def _on_conf_req(event: AutomationConfirmationRequired) -> None:
            token = getattr(event, "token", "") or getattr(event, "confirmation_token", "")
            desc = getattr(event, "prompt_message", "") or getattr(event, "description", "Confirmation required")
            timeout = getattr(event, "timeout_seconds", 30.0)
            item = ConfirmationItem(
                token=token,
                action_name=event.action_name,
                description=desc,
                expires_at=time.time() + timeout,
            )
            self.state.pending_confirmation = item
            if self.bridge and hasattr(self.bridge, "confirmation_required"):
                self.bridge.confirmation_required.emit(item)

        eb.subscribe(StateChanged, _on_state_changed)
        eb.subscribe(SpeechStarted, _on_speech_started)
        eb.subscribe(SpeechStopped, _on_speech_stopped)
        eb.subscribe(WakeWordDetected, _on_wakeword)
        eb.subscribe(AutomationConfirmationRequired, _on_conf_req)
        self._subscribed = True
        logger.debug("Bound UIController to Denver EventBus.")

    def submit_command(self, command_text: str) -> None:
        """Submit a user text command asynchronously without blocking the Qt GUI thread."""
        text = command_text.strip()
        if not text:
            return

        logger.info("Submitting command from Cockpit UI: '%s'", text)

        # Transition state to PROCESSING
        self.state.current_state = DenverState.PROCESSING
        if self.bridge and hasattr(self.bridge, "state_changed"):
            self.bridge.state_changed.emit(DenverState.PROCESSING, f"Processing '{text}'")

        if self.app and hasattr(self.app, "process_command"):
            try:
                running_loop = asyncio.get_running_loop()
            except RuntimeError:
                running_loop = None

            if running_loop is not None and running_loop == self.event_loop:
                task = running_loop.create_task(self.app.process_command(text))

                def _task_done(t: Any) -> None:
                    try:
                        resp: CommandResponse = t.result()
                        self._handle_command_response(text, resp)
                    except Exception as exc:  # pylint: disable=broad-except
                        logger.error("Command execution error in task: %s", exc)
                        self._handle_command_error(text, str(exc))

                task.add_done_callback(_task_done)
            elif self.event_loop and self.event_loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self.app.process_command(text),
                    self.event_loop,
                )

                def _done_callback(fut: Any) -> None:
                    try:
                        resp: CommandResponse = fut.result()
                        self._handle_command_response(text, resp)
                    except Exception as exc:  # pylint: disable=broad-except
                        logger.error("Command execution error in background task: %s", exc)
                        self._handle_command_error(text, str(exc))

                future.add_done_callback(_done_callback)
            else:
                from denver.commands.models import CommandRiskLevel
                dummy_resp = CommandResponse(
                    success=True,
                    message=f"Received: {text}",
                    action_name="custom",
                    risk_level=CommandRiskLevel.SAFE,
                    latency_ms=5.0,
                )
                self._handle_command_response(text, dummy_resp)
        else:
            from denver.commands.models import CommandRiskLevel
            dummy_resp = CommandResponse(
                success=True,
                message=f"Received: {text}",
                action_name="custom",
                risk_level=CommandRiskLevel.SAFE,
                latency_ms=5.0,
            )
            self._handle_command_response(text, dummy_resp)

    async def submit_command_async(self, command_text: str) -> ActivityItem:
        """Submit command and await completion directly (ideal for async tests & pipelines)."""
        text = command_text.strip()
        if not text:
            return ActivityItem()

        self.state.current_state = DenverState.PROCESSING
        if self.bridge and hasattr(self.bridge, "state_changed"):
            self.bridge.state_changed.emit(DenverState.PROCESSING, f"Processing '{text}'")

        if self.app and hasattr(self.app, "process_command"):
            try:
                resp = await self.app.process_command(text)
                self._handle_command_response(text, resp)
            except Exception as exc:  # pylint: disable=broad-except
                self._handle_command_error(text, str(exc))
        else:
            from denver.commands.models import CommandRiskLevel
            dummy_resp = CommandResponse(
                success=True,
                message=f"Received: {text}",
                action_name="custom",
                risk_level=CommandRiskLevel.SAFE,
                latency_ms=5.0,
            )
            self._handle_command_response(text, dummy_resp)

        return self.state.activity_history[-1] if self.state.activity_history else ActivityItem()

    def _handle_command_response(self, query: str, response: CommandResponse) -> None:
        risk_str = response.risk_level.value if hasattr(response.risk_level, "value") else str(response.risk_level)
        item = ActivityItem(
            command_text=query,
            action_name=response.action_name or "general",
            response_text=response.message,
            risk_level=risk_str,
            success=response.success,
            latency_ms=response.latency_ms,
            error=response.error,
        )
        self.state.add_activity(item)

        # Check if response generated a confirmation
        if response.data and "confirmation_token" in response.data:
            conf_item = ConfirmationItem(
                token=response.data["confirmation_token"],
                action_name=response.action_name or "high_risk_action",
                description=response.message,
                expires_at=response.data.get("expires_at", time.time() + 30.0),
            )
            self.state.pending_confirmation = conf_item
            if self.bridge and hasattr(self.bridge, "confirmation_required"):
                self.bridge.confirmation_required.emit(conf_item)

        if self.bridge and hasattr(self.bridge, "activity_added"):
            self.bridge.activity_added.emit(item)

        # Restore STANDBY state
        self.state.current_state = DenverState.STANDBY
        if self.bridge and hasattr(self.bridge, "state_changed"):
            self.bridge.state_changed.emit(DenverState.STANDBY, "Ready")

    def _handle_command_error(self, query: str, error_msg: str) -> None:
        item = ActivityItem(
            command_text=query,
            action_name="error",
            response_text=f"Execution error: {error_msg}",
            risk_level="SAFE",
            success=False,
            latency_ms=0.0,
            error=error_msg,
        )
        self.state.add_activity(item)
        if self.bridge and hasattr(self.bridge, "activity_added"):
            self.bridge.activity_added.emit(item)

        self.state.current_state = DenverState.STANDBY
        if self.bridge and hasattr(self.bridge, "state_changed"):
            self.bridge.state_changed.emit(DenverState.STANDBY, "Ready")

    def poll_telemetry(self) -> None:
        """Poll Denver HealthService in a background thread to maintain 60+ FPS UI responsiveness."""
        if not self.app or not hasattr(self.app, "health_service"):
            return
        if getattr(self, "_polling_in_progress", False):
            return
        self._polling_in_progress = True

        def _worker() -> None:
            try:
                report = self.app.health_service.get_health_report()

                # Update telemetry
                telem = report.get("telemetry", {})
                cpu_info = telem.get("cpu", {})
                mem_info = telem.get("memory", {})

                self.state.cpu_percent = cpu_info.get("usage_percent")
                self.state.ram_percent = mem_info.get("usage_percent")
                self.state.ram_used_gb = mem_info.get("used_gb")
                self.state.ram_total_gb = mem_info.get("total_gb")
                self.state.uptime_seconds = report.get("uptime_seconds", 0.0)
                self.state.uptime_formatted = report.get("uptime_formatted", "00:00:00")

                # Update Subsystems
                if "ai_providers" in report and isinstance(report["ai_providers"], dict):
                    providers = report["ai_providers"].get("providers", {})
                    self.state.ai_providers = providers
                    if self.bridge and hasattr(self.bridge, "ai_providers_updated"):
                        self.bridge.ai_providers_updated.emit(providers)

                if "automation" in report and isinstance(report["automation"], dict):
                    auto = report["automation"]
                    self.state.automation_status = {
                        "applications": auto.get("applications", "READY"),
                        "windows": auto.get("windows", "READY"),
                        "volume": auto.get("volume", "READY"),
                        "browser": auto.get("browser", "READY"),
                        "screenshot": auto.get("screenshot", "READY"),
                        "system": auto.get("system", "READY"),
                    }
                    if self.bridge and hasattr(self.bridge, "automation_updated"):
                        self.bridge.automation_updated.emit(self.state.automation_status)

                if "memory" in report and isinstance(report["memory"], dict):
                    self.state.memory_stats = report["memory"]
                    if self.bridge and hasattr(self.bridge, "memory_updated"):
                        self.bridge.memory_updated.emit(report["memory"])

                if "audio" in report and isinstance(report["audio"], dict):
                    audio_info = report["audio"]
                    mic_active = bool(audio_info.get("capture_active", False))
                    mic_avail = audio_info.get("status") != "UNAVAILABLE"
                    v_state = "LISTENING" if mic_active else "STANDBY"
                    if self.bridge and hasattr(self.bridge, "voice_state_changed"):
                        self.bridge.voice_state_changed.emit(v_state, mic_active, mic_avail)

                # Update Plugins
                plugins_list = self.get_plugins()
                if self.bridge and hasattr(self.bridge, "plugins_updated"):
                    self.bridge.plugins_updated.emit(plugins_list)

                if self.bridge and hasattr(self.bridge, "telemetry_updated"):
                    self.bridge.telemetry_updated.emit(self.state)

            except Exception as exc:  # pylint: disable=broad-except
                logger.debug("Telemetry polling encountered transient error: %s", exc)
            finally:
                self._polling_in_progress = False

        threading.Thread(target=_worker, daemon=True, name="denver-ui-telemetry").start()

    def get_plugins(self) -> list[dict[str, Any]]:
        """Get discovered and registered plugins metadata."""
        if self.app and hasattr(self.app, "command_service") and hasattr(self.app.command_service, "plugin_registry"):
            return self.app.command_service.plugin_registry.list_plugins()
        return []

    def toggle_plugin(self, plugin_id: str, enable: bool) -> bool:
        """Enable or disable a plugin via PluginRegistry and refresh UI."""
        logger.info("UI toggling plugin '%s' -> %s", plugin_id, enable)
        if self.app and hasattr(self.app, "command_service") and hasattr(self.app.command_service, "plugin_registry"):
            reg = self.app.command_service.plugin_registry
            success = reg.enable_plugin(plugin_id) if enable else reg.disable_plugin(plugin_id)
            if self.bridge and hasattr(self.bridge, "plugins_updated"):
                self.bridge.plugins_updated.emit(reg.list_plugins())
            return success
        return False

    def reload_plugins(self) -> int:
        """Reload all discovered plugins from disk and refresh UI."""
        logger.info("UI reloading all plugins...")
        if self.app and hasattr(self.app, "command_service") and hasattr(self.app.command_service, "plugin_registry"):
            reg = self.app.command_service.plugin_registry
            count = reg.reload_all() if hasattr(reg, "reload_all") else reg.discover_and_load_all()
            if self.bridge and hasattr(self.bridge, "plugins_updated"):
                self.bridge.plugins_updated.emit(reg.list_plugins())
            return count
        return 0

    def trigger_system_repair(self) -> None:
        """Execute self-healing diagnostics and automated repair asynchronously."""
        logger.info("UI triggering System Auto-Repair...")

        def _worker() -> None:
            try:
                from denver.health.repair import SystemRepairManager
                settings = getattr(self.app, "settings", None)
                manager = SystemRepairManager(settings=settings)
                report = manager.run_repair(dry_run=False)

                # Post an activity item documenting the auto-repair
                summary_msg = report.format_spoken_summary()
                item = ActivityItem(
                    command_text="System Auto-Repair",
                    action_name="system_repair",
                    response_text=f"Auto-Repair completed: {summary_msg} (Fixed {report.issues_fixed} / {report.issues_detected} detected issues).",
                    risk_level="SAFE",
                    success=True,
                    latency_ms=12.0,
                )
                self.state.add_activity(item)
                if self.bridge and hasattr(self.bridge, "activity_added"):
                    self.bridge.activity_added.emit(item)
                if self.bridge and hasattr(self.bridge, "repair_completed"):
                    self.bridge.repair_completed.emit(report.issues_fixed, report.issues_detected, summary_msg)
            except Exception as exc:
                logger.error("Auto-Repair encountered error: %s", exc)
                if self.bridge and hasattr(self.bridge, "repair_completed"):
                    self.bridge.repair_completed.emit(0, 1, f"Repair failed: {exc}")

        threading.Thread(target=_worker, daemon=True, name="denver-ui-repair").start()

    def confirm_action(self, token: str) -> None:
        """Dispatch confirmation command for high-risk action token."""
        self.state.pending_confirmation = None
        if self.bridge and hasattr(self.bridge, "confirmation_cleared"):
            self.bridge.confirmation_cleared.emit()
        self.submit_command(f"Denver, confirm {token}")

    def cancel_action(self, token: str) -> None:
        """Cancel pending confirmation token."""
        self.state.pending_confirmation = None
        if self.bridge and hasattr(self.bridge, "confirmation_cleared"):
            self.bridge.confirmation_cleared.emit()
        self.submit_command("Denver, cancel action")

    def trigger_voice_listening(self) -> None:
        """Activate voice listening mode from GUI push-to-talk button or visualizer click."""
        if not self.app or not hasattr(self.app, "voice_pipeline") or not self.app.voice_pipeline:
            return
        logger.info("Triggering voice listening mode via GUI push-to-talk.")
        if self.event_loop and self.event_loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self.app.voice_pipeline.trigger_listening(),
                self.event_loop,
            )
        else:
            self.state.microphone_active = True
            self.state.voice_state = "LISTENING"
            if self.bridge and hasattr(self.bridge, "voice_state_changed"):
                self.bridge.voice_state_changed.emit("LISTENING", True, True)
