"""Central Desktop Automation Executor coordinating allowlisted subsystems."""

from __future__ import annotations

import time
from typing import Any

from denver.automation.applications import ApplicationController
from denver.automation.browser import BrowserController
from denver.automation.confirmation import ConfirmationManager
from denver.automation.errors import AutomationError, ConfirmationInvalidError
from denver.automation.models import (
    AutomationAction,
    AutomationRequest,
    AutomationResult,
    AutomationRisk,
)
from denver.automation.registry import AutomationRegistry
from denver.automation.screenshot import ScreenshotController
from denver.automation.system import SystemController
from denver.automation.volume import VolumeController
from denver.automation.windows import WindowsNativeAPI
from denver.automation.windows_manager import WindowManager
from denver.logging.logger import get_logger
from denver.runtime.event_bus import DenverEventBus, get_event_bus
from denver.runtime.events import (
    ApplicationClosed,
    ApplicationOpened,
    AutomationCompleted,
    AutomationConfirmationExpired,
    AutomationConfirmationReceived,
    AutomationConfirmationRequired,
    AutomationFailed,
    AutomationRequested,
    AutomationStarted,
    ScreenshotCaptured,
    SpotifyPlaybackChanged,
    VolumeChanged,
    WindowActionPerformed,
)

logger = get_logger("automation.executor")


class AutomationExecutor:
    """Orchestrates safe, allowlisted Windows desktop actions with confirmation gates."""

    def __init__(
        self,
        registry: AutomationRegistry | None = None,
        applications: ApplicationController | None = None,
        windows: WindowManager | None = None,
        volume: VolumeController | None = None,
        browser: BrowserController | None = None,
        screenshot: ScreenshotController | None = None,
        system: SystemController | None = None,
        confirmation: ConfirmationManager | None = None,
        spotify: Any | None = None,
        event_bus: DenverEventBus | None = None,
        allow_high_risk_actions: bool = False,
    ) -> None:
        from denver.automation.clipboard import ClipboardController
        from denver.automation.keyboard import KeyboardController
        from denver.automation.spotify import SpotifyController

        self.registry = registry or AutomationRegistry()
        self.applications = applications or ApplicationController(self.registry)
        self.windows = windows or WindowManager()
        self.volume = volume or VolumeController()
        self.browser = browser or BrowserController(self.registry)
        self.screenshot = screenshot or ScreenshotController()
        self.system = system or SystemController()
        self.clipboard = ClipboardController()
        self.keyboard = KeyboardController()
        self.spotify = spotify or SpotifyController()
        self.confirmation = confirmation or ConfirmationManager()
        self.event_bus = event_bus or get_event_bus()
        self.allow_high_risk_actions = allow_high_risk_actions

    async def execute(self, request: AutomationRequest) -> AutomationResult:
        """Process and execute an automation request through safety and confirmation checks."""
        start_time = time.perf_counter()
        action_name = request.action_name.strip().lower()

        await self.event_bus.publish(
            AutomationRequested(
                action_name=action_name,
                target=request.target,
                risk_level="LOW",
            )
        )

        # 1. High-Risk Action Confirmation Gate
        if action_name in {"lock_workstation"}:
            if not self.allow_high_risk_actions and not request.params.get("force", False):
                if not request.confirmation_token:
                    # Issue confirmation requirement
                    prompt = "Locking your workstation requires confirmation. Proceed?"
                    req = self.confirmation.create_pending(
                        action_name=action_name,
                        action_params=request.params,
                        prompt_message=prompt,
                    )
                    await self.event_bus.publish(
                        AutomationConfirmationRequired(
                            token=req.token,
                            action_name=action_name,
                            target=request.target,
                            prompt_message=prompt,
                        )
                    )
                    return AutomationResult(
                        success=True,
                        action=action_name,
                        target=request.target,
                        message=prompt,
                        data={"confirmation_token": req.token, "expires_at": req.expires_at},
                        risk_level=AutomationRisk.HIGH,
                        requires_confirmation=True,
                        confirmation_token=req.token,
                    )

                # Validate and consume supplied confirmation token
                try:
                    self.confirmation.validate_and_consume(request.confirmation_token, expected_action=action_name)
                    await self.event_bus.publish(
                        AutomationConfirmationReceived(
                            token=request.confirmation_token,
                            action_name=action_name,
                        )
                    )
                except ConfirmationInvalidError as exc:
                    logger.warning("Confirmation rejected for '%s': %s", action_name, exc)
                    await self.event_bus.publish(
                        AutomationFailed(
                            action_name=action_name,
                            target=request.target,
                            error=str(exc),
                            reason="ConfirmationInvalid",
                        )
                    )
                    return AutomationResult(
                        success=False,
                        action=action_name,
                        target=request.target,
                        message=f"Confirmation error: {exc}",
                        risk_level=AutomationRisk.HIGH,
                        error=str(exc),
                    )

        await self.event_bus.publish(
            AutomationStarted(action_name=action_name, target=request.target)
        )

        # 2. Dispatch to dedicated sub-controller
        res: AutomationResult
        try:
            if action_name == "open_application":
                app_name = request.params.get("application") or request.target
                res = self.applications.launch(app_name)
                if res.success:
                    await self.event_bus.publish(
                        ApplicationOpened(
                            app_id=res.data.get("app_id", app_name),
                            display_name=res.target,
                            pid=res.data.get("pid"),
                        )
                    )

            elif action_name == "close_application":
                app_name = request.params.get("application") or request.target
                res = self.applications.close(app_name)
                if res.success:
                    await self.event_bus.publish(
                        ApplicationClosed(
                            app_id=res.data.get("app_id", app_name),
                            display_name=res.target,
                            terminated_processes=res.data.get("terminated_instances", 0),
                        )
                    )

            elif action_name == "send_whatsapp_message":
                msg = request.params.get("message", "")
                phone = request.params.get("phone", "")
                contact = request.params.get("contact", "") or request.params.get("recipient", "")
                res = self.applications.send_whatsapp_message(message=msg, phone=phone, contact_name=contact)
                if res.success:
                    await self.event_bus.publish(
                        ApplicationOpened(
                            app_id="whatsapp",
                            display_name="WhatsApp",
                        )
                    )

            elif action_name == "minimize_window":
                win_query = request.params.get("window") or request.target
                res = self.windows.minimize_window(win_query)
                if res.success:
                    await self.event_bus.publish(
                        WindowActionPerformed(operation="minimize", window_title=res.target)
                    )

            elif action_name == "maximize_window":
                win_query = request.params.get("window") or request.target
                res = self.windows.maximize_window(win_query)
                if res.success:
                    await self.event_bus.publish(
                        WindowActionPerformed(operation="maximize", window_title=res.target)
                    )

            elif action_name == "restore_window":
                win_query = request.params.get("window") or request.target
                res = self.windows.restore_window(win_query)
                if res.success:
                    await self.event_bus.publish(
                        WindowActionPerformed(operation="restore", window_title=res.target)
                    )

            elif action_name == "focus_window":
                win_query = request.params.get("window") or request.target
                res = self.windows.focus_window(win_query)
                if res.success:
                    await self.event_bus.publish(
                        WindowActionPerformed(operation="focus", window_title=res.target)
                    )

            elif action_name == "show_desktop":
                res = self.windows.show_desktop()
                if res.success:
                    await self.event_bus.publish(
                        WindowActionPerformed(operation="show_desktop", window_title="")
                    )

            elif action_name in {"open_browser", "open_website"}:
                url_target = request.params.get("url") or request.params.get("target") or request.target
                res = self.browser.open_url(url_target)

            elif action_name == "get_volume":
                res = self.volume.get_volume()

            elif action_name == "set_volume":
                val = request.params.get("value", 50)
                res = self.volume.set_volume(int(val))
                if res.success:
                    await self.event_bus.publish(VolumeChanged(operation="set", new_volume=int(val)))

            elif action_name == "increase_volume":
                step = request.params.get("step", 10)
                res = self.volume.increase_volume(int(step))
                if res.success:
                    await self.event_bus.publish(VolumeChanged(operation="increase"))

            elif action_name == "decrease_volume":
                step = request.params.get("step", 10)
                res = self.volume.decrease_volume(int(step))
                if res.success:
                    await self.event_bus.publish(VolumeChanged(operation="decrease"))

            elif action_name == "mute_volume":
                res = self.volume.mute()
                if res.success:
                    await self.event_bus.publish(VolumeChanged(operation="mute", is_muted=True))

            elif action_name == "unmute_volume":
                res = self.volume.unmute()
                if res.success:
                    await self.event_bus.publish(VolumeChanged(operation="unmute", is_muted=False))

            elif action_name == "take_screenshot":
                filename = request.params.get("filename")
                res = self.screenshot.capture(filename)
                if res.success:
                    await self.event_bus.publish(
                        ScreenshotCaptured(
                            file_path=res.data.get("file_path", ""),
                            file_size_bytes=res.data.get("file_size_bytes", 0),
                            width=res.data.get("width", 0),
                            height=res.data.get("height", 0),
                        )
                    )

            elif action_name == "get_system_summary":
                res = self.system.get_system_summary()

            elif action_name == "lock_workstation":
                res = self.system.lock_workstation()

            elif action_name == "read_clipboard":
                res = self.clipboard.read_clipboard()

            elif action_name == "write_clipboard":
                text = request.params.get("text", "")
                res = self.clipboard.write_clipboard(text)

            elif action_name == "type_text":
                text = request.params.get("text", "")
                res = self.keyboard.type_text(text)

            elif action_name == "press_key":
                key = request.params.get("key", "")
                res = self.keyboard.press_key(key)

            elif action_name == "scroll_window":
                direction = request.params.get("direction", "down")
                steps = int(request.params.get("steps", 5) or 5)
                res = self.keyboard.scroll(direction=direction, amount=steps)

            elif action_name == "spotify_play_pause":
                res = self.spotify.play_pause()
                if res.success:
                    await self.event_bus.publish(SpotifyPlaybackChanged(action="play_pause", query=""))

            elif action_name == "spotify_next_track":
                res = self.spotify.next_track()
                if res.success:
                    await self.event_bus.publish(SpotifyPlaybackChanged(action="next_track", query=""))

            elif action_name == "spotify_previous_track":
                res = self.spotify.previous_track()
                if res.success:
                    await self.event_bus.publish(SpotifyPlaybackChanged(action="previous_track", query=""))

            elif action_name == "spotify_play_query":
                q = request.params.get("query", "") or request.target
                res = self.spotify.play_query(q)
                if res.success:
                    await self.event_bus.publish(SpotifyPlaybackChanged(action="play_query", query=q))

            else:
                res = AutomationResult(
                    success=False,
                    action=action_name,
                    target=request.target,
                    message=f"Automation action '{action_name}' is not recognized.",
                    risk_level=AutomationRisk.LOW,
                    error="UnrecognizedAutomationAction",
                )

        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Automation execution error on '%s': %s", action_name, exc)
            res = AutomationResult(
                success=False,
                action=action_name,
                target=request.target,
                message=f"Action execution error: {exc}",
                risk_level=AutomationRisk.LOW,
                error=str(exc),
            )

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        if res.success:
            await self.event_bus.publish(
                AutomationCompleted(action_name=action_name, target=request.target, latency_ms=elapsed_ms)
            )
        else:
            await self.event_bus.publish(
                AutomationFailed(
                    action_name=action_name,
                    target=request.target,
                    error=res.error or "",
                    reason=res.error or "ActionExecutionFailed",
                )
            )

        return res

    def get_health_status(self) -> dict[str, Any]:
        """Produce comprehensive diagnostics for desktop automation modules."""
        return {
            "status": "READY",
            "platform": "windows",
            "applications": "READY",
            "windows": "READY" if self.windows.api.is_available else "UNAVAILABLE",
            "volume": "READY" if self.volume.api.is_available else "UNAVAILABLE",
            "browser": "READY",
            "screenshot": "READY",
            "system": "READY",
            "allowlisted_apps_count": len(self.registry.list_applications()),
            "known_sites_count": len(self.registry.list_known_sites()),
        }
