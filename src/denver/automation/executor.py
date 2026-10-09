"""Central Desktop Automation Executor coordinating allowlisted subsystems."""

from __future__ import annotations

from pathlib import Path
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
        terminal_fix: Any | None = None,
        email_monitor: Any | None = None,
        event_bus: DenverEventBus | None = None,
        allow_high_risk_actions: bool = False,
        settings: Any | None = None,
    ) -> None:
        from denver.automation.clipboard import ClipboardController
        from denver.automation.keyboard import KeyboardController
        from denver.automation.spotify import SpotifyController
        from denver.automation.terminal_fix import TerminalFixController

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
        self.terminal_fix = terminal_fix or TerminalFixController()
        self.email_monitor = email_monitor
        self.confirmation = confirmation or ConfirmationManager()
        self.event_bus = event_bus or get_event_bus()
        self.allow_high_risk_actions = allow_high_risk_actions
        self.settings = settings

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
        if action_name in {"lock_workstation", "execute_terminal_fix"}:
            if not self.allow_high_risk_actions and not request.params.get("force", False):
                if not request.confirmation_token:
                    cmd = request.params.get("command", "") or request.target
                    if action_name == "execute_terminal_fix":
                        is_safe, val_err, _ = self.terminal_fix.validate_fix_command(cmd)
                        if not is_safe:
                            logger.warning("Terminal fix validation failed: %s", val_err)
                            return AutomationResult(
                                success=False,
                                action=action_name,
                                target=cmd,
                                message=f"Terminal fix rejected by security validator: {val_err}",
                                risk_level=AutomationRisk.HIGH,
                                error=val_err,
                            )
                        prompt = f"Execute terminal fix: `{cmd}`?"
                    else:
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
                        data={
                            "confirmation_token": req.token,
                            "expires_at": req.expires_at,
                            "command": cmd if action_name == "execute_terminal_fix" else None,
                        },
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

            elif action_name == "execute_terminal_fix":
                cmd = request.params.get("command", "") or request.target
                timeout = float(request.params.get("timeout", 60.0))
                cwd = request.params.get("cwd")
                res = self.terminal_fix.execute_fix(command=cmd, timeout_seconds=timeout, cwd=cwd)

            elif action_name in {"check_emails", "summarize_emails"}:
                limit = int(request.params.get("limit", 5))
                monitor = self._get_email_monitor()
                summaries = await monitor.check_now(limit=limit)
                if not summaries:
                    # If no new emails in monitor, fetch recent/unread directly from client
                    messages = await monitor.client.fetch_unread(limit=limit)
                    summaries = await monitor.analyzer.analyze_batch(messages)

                formatted = "\n\n".join(s.format_display() for s in summaries) if summaries else "Your inbox has no new unread emails."
                res = AutomationResult(
                    success=True,
                    action=action_name,
                    target="inbox",
                    message=formatted,
                    data={"count": len(summaries), "summaries": [s.to_dict() for s in summaries]},
                )

            elif action_name == "read_latest_email":
                monitor = self._get_email_monitor()
                messages = await monitor.client.fetch_recent(limit=1)
                if not messages:
                    res = AutomationResult(
                        success=True,
                        action=action_name,
                        target="inbox",
                        message="No emails found in your inbox.",
                        data={"count": 0},
                    )
                else:
                    summary = await monitor.analyzer.analyze_message(messages[0])
                    res = AutomationResult(
                        success=True,
                        action=action_name,
                        target=messages[0].subject,
                        message=summary.format_display(),
                        data={"summary": summary.to_dict(), "message": messages[0].to_dict()},
                    )

            elif action_name == "start_email_monitor":
                monitor = self._get_email_monitor()
                started = await monitor.start()
                res = AutomationResult(
                    success=started,
                    action=action_name,
                    target="email_monitor",
                    message="Continuous email monitoring started." if started else "Email monitoring is already active.",
                    data=monitor.get_status(),
                )

            elif action_name == "stop_email_monitor":
                monitor = self._get_email_monitor()
                stopped = await monitor.stop()
                res = AutomationResult(
                    success=stopped,
                    action=action_name,
                    target="email_monitor",
                    message="Continuous email monitoring stopped." if stopped else "Email monitoring is not active.",
                    data=monitor.get_status(),
                )

            elif action_name == "get_email_monitor_status":
                monitor = self._get_email_monitor()
                res = AutomationResult(
                    success=True,
                    action=action_name,
                    target="email_monitor",
                    message="Email monitor status retrieved.",
                    data=monitor.get_status(),
                )

            elif action_name == "draft_email":
                monitor = self._get_email_monitor()
                to = str(request.params.get("to", ""))
                subject = str(request.params.get("subject", "No Subject"))
                body = str(request.params.get("body", ""))
                cc = str(request.params.get("cc", ""))
                bcc = str(request.params.get("bcc", ""))
                draft = monitor.client.create_draft(to=to, subject=subject, body=body, cc=cc, bcc=bcc)
                res = AutomationResult(
                    success=True,
                    action=action_name,
                    target=to,
                    message=f"Email draft '{draft.draft_id}' created for {to}: '{subject}'.",
                    data=draft.to_dict(),
                )

            elif action_name == "send_email":
                monitor = self._get_email_monitor()
                to = str(request.params.get("to", ""))
                subject = str(request.params.get("subject", "No Subject"))
                body = str(request.params.get("body", ""))
                cc = str(request.params.get("cc", ""))
                bcc = str(request.params.get("bcc", ""))
                draft_id = request.params.get("draft_id")
                send_res = await monitor.client.send_email(
                    to=to,
                    subject=subject,
                    body=body,
                    cc=cc,
                    bcc=bcc,
                    draft_id=draft_id,
                )
                res = AutomationResult(
                    success=send_res.success,
                    action=action_name,
                    target=to,
                    message=send_res.message,
                    data=send_res.to_dict(),
                    error=send_res.error,
                )

            elif action_name == "reply_to_email":
                monitor = self._get_email_monitor()
                body = str(request.params.get("body", ""))
                uid = request.params.get("uid")
                recipient = request.params.get("recipient") or request.params.get("to")
                orig_subject = request.params.get("subject")
                reply_res = await monitor.client.reply_to_email(
                    body=body,
                    uid=uid,
                    recipient=recipient,
                    original_subject=orig_subject,
                )
                res = AutomationResult(
                    success=reply_res.success,
                    action=action_name,
                    target=reply_res.recipient,
                    message=reply_res.message,
                    data=reply_res.to_dict(),
                    error=reply_res.error,
                )

            elif action_name in {"get_today_schedule", "show_calendar"}:
                cal = self._get_calendar_service()
                target_date = request.params.get("date")
                schedule = cal.get_events_for_date(target_date)
                res = AutomationResult(
                    success=True,
                    action="get_today_schedule",
                    target="calendar",
                    message=schedule.format_briefing(),
                    data=schedule.to_dict(),
                )

            elif action_name == "create_calendar_event":
                cal = self._get_calendar_service()
                title = str(request.params.get("title", "Meeting"))
                ev_start_time = request.params.get("start_time") or request.params.get("time")
                if not ev_start_time:
                    from denver.calendar.service import _resolve_datetime_expr
                    ev_start_time = _resolve_datetime_expr(str(request.params.get("date_expr", "today at 10 AM")))
                ev_end_time = request.params.get("end_time")
                location = str(request.params.get("location", ""))
                description = str(request.params.get("description", ""))
                event = cal.create_event(
                    title=title,
                    start_time=ev_start_time,
                    end_time=ev_end_time,
                    location=location,
                    description=description,
                )
                res = AutomationResult(
                    success=True,
                    action=action_name,
                    target=title,
                    message=f"Scheduled '{event.title}' on {event.starts_at_dt().strftime('%A, %b %d at %I:%M %p')}.",
                    data=event.to_dict(),
                )

            elif action_name == "get_next_meeting":
                cal = self._get_calendar_service()
                next_ev = cal.get_next_meeting()
                if next_ev:
                    msg = f"Your next meeting is '{next_ev.title}' at {next_ev.format_time_span()} on {next_ev.starts_at_dt().strftime('%A, %b %d')}."
                    res = AutomationResult(
                        success=True,
                        action=action_name,
                        target=next_ev.title,
                        message=msg,
                        data=next_ev.to_dict(),
                    )
                else:
                    res = AutomationResult(
                        success=True,
                        action=action_name,
                        target="calendar",
                        message="You have no upcoming meetings scheduled.",
                        data={"has_upcoming": False},
                    )

            elif action_name == "delete_calendar_event":
                cal = self._get_calendar_service()
                event_id = request.params.get("event_id") or request.params.get("id")
                title = request.params.get("title")
                deleted = cal.delete_event(event_id=int(event_id) if event_id else None, title=title)
                res = AutomationResult(
                    success=deleted,
                    action=action_name,
                    target=str(event_id or title),
                    message=f"Calendar event '{event_id or title}' removed." if deleted else f"Calendar event '{event_id or title}' not found.",
                    data={"deleted": deleted},
                )

            elif action_name == "search_calendar_events":
                cal = self._get_calendar_service()
                query = str(request.params.get("query", ""))
                events = cal.search_events(query)
                formatted = "\n".join(e.format_display() for e in events) if events else f"No events found matching '{query}'."
                res = AutomationResult(
                    success=True,
                    action=action_name,
                    target=query,
                    message=formatted,
                    data={"count": len(events), "events": [e.to_dict() for e in events]},
                )

            elif action_name == "import_calendar_ics":
                cal = self._get_calendar_service()
                content = str(request.params.get("ics_data") or request.params.get("path", ""))
                count = cal.import_ics(content)
                res = AutomationResult(
                    success=True,
                    action=action_name,
                    target="ics_import",
                    message=f"Successfully imported {count} event(s) into your calendar.",
                    data={"imported_count": count},
                )

            # Step 3: Local Document & PDF Semantic RAG
            elif action_name == "index_document":
                rag = self._get_rag_service()
                path = str(request.params.get("path") or request.params.get("file_path") or request.target)
                meta = await rag.index_file(path)
                res = AutomationResult(
                    success=True,
                    action=action_name,
                    target=path,
                    message=f"Indexed document '{meta.file_name}' ({meta.file_type.upper()}) into {meta.chunk_count} chunk(s).",
                    data=meta.to_dict(),
                )

            elif action_name == "search_documents":
                rag = self._get_rag_service()
                query = str(request.params.get("query") or request.target)
                top_k = int(request.params.get("top_k", 5))
                file_filter = request.params.get("file_filter")
                results = await rag.search(query=query, top_k=top_k, file_filter=file_filter)
                if results:
                    formatted = "\n\n".join(
                        f"[{i}] {r.file_name}" + (f" (Page {r.page})" if r.page else "") + f" [Match: {int(r.score * 100)}%]:\n{r.snippet}"
                        for i, r in enumerate(results, start=1)
                    )
                    msg = f"Found {len(results)} matching document excerpt(s):\n\n{formatted}"
                else:
                    msg = f"No document matches found for '{query}'."
                res = AutomationResult(
                    success=True,
                    action=action_name,
                    target=query,
                    message=msg,
                    data={"count": len(results), "results": [r.to_dict() for r in results]},
                )

            elif action_name == "ask_document":
                rag = self._get_rag_service()
                query = str(request.params.get("query") or request.target)
                file_filter = request.params.get("file_filter")
                ans = await rag.ask(query=query, file_filter=file_filter)
                res = AutomationResult(
                    success=True,
                    action=action_name,
                    target=query,
                    message=ans.format_display(),
                    data=ans.to_dict(),
                )

            elif action_name == "list_documents":
                rag = self._get_rag_service()
                docs = rag.list_documents()
                if docs:
                    lines = [f"- {d['file_name']}: {d['chunk_count']} chunk(s) (indexed {d['indexed_at']})" for d in docs]
                    msg = f"Indexed Documents ({len(docs)}):\n" + "\n".join(lines)
                else:
                    msg = "No documents have been indexed yet. Use 'index document <path>' to add files."
                res = AutomationResult(
                    success=True,
                    action=action_name,
                    target="documents",
                    message=msg,
                    data={"count": len(docs), "documents": docs},
                )

            elif action_name == "delete_document":
                rag = self._get_rag_service()
                target = str(request.params.get("path") or request.params.get("file_name") or request.target)
                deleted = rag.delete_document(target)
                res = AutomationResult(
                    success=deleted,
                    action=action_name,
                    target=target,
                    message=f"Removed indexed document '{target}'." if deleted else f"Document '{target}' was not found in index.",
                    data={"deleted": deleted},
                )

            # Step 4: Spoken Voice Profile Selector (Edge-TTS)
            elif action_name == "switch_voice":
                vm = self._get_voice_manager()
                target_voice = str(request.params.get("voice") or request.params.get("name") or request.target)
                ok, profile, msg = vm.set_voice(target_voice)
                res = AutomationResult(
                    success=ok,
                    action=action_name,
                    target=target_voice,
                    message=msg,
                    data=profile.to_dict() if profile else {},
                )

            elif action_name == "list_voices":
                from denver.audio.voices import list_available_voices
                vm = self._get_voice_manager()
                voices = list_available_voices()
                active_id = vm.active_voice.voice_id
                lines = [
                    f"- {'[ACTIVE] ' if v.voice_id == active_id else ''}{v.name} ({v.locale} {v.gender}) — {v.tone}"
                    for v in voices
                ]
                msg = f"Available Spoken Voices ({len(voices)}):\n" + "\n".join(lines)
                res = AutomationResult(
                    success=True,
                    action=action_name,
                    target="voices",
                    message=msg,
                    data={"voices": [v.to_dict() for v in voices], "active_voice": vm.active_voice.to_dict()},
                )

            elif action_name == "set_voice_speed":
                vm = self._get_voice_manager()
                speed = str(request.params.get("speed") or request.params.get("rate") or request.target)
                ok, rate, msg = vm.set_speed(speed)
                res = AutomationResult(
                    success=ok,
                    action=action_name,
                    target=rate,
                    message=msg,
                    data={"rate": rate},
                )

            elif action_name == "set_voice_pitch":
                vm = self._get_voice_manager()
                pitch = str(request.params.get("pitch") or request.target)
                ok, pitch_val, msg = vm.set_pitch(pitch)
                res = AutomationResult(
                    success=ok,
                    action=action_name,
                    target=pitch_val,
                    message=msg,
                    data={"pitch": pitch_val},
                )

            elif action_name == "preview_voice":
                vm = self._get_voice_manager()
                voice_arg = request.params.get("voice") or request.target
                phrase_arg = request.params.get("phrase")
                ok, msg = await vm.preview_voice(voice_query=str(voice_arg) if voice_arg and voice_arg != "preview_voice" else None, custom_phrase=phrase_arg)
                res = AutomationResult(
                    success=ok,
                    action=action_name,
                    target=str(voice_arg or "active"),
                    message=msg,
                    data={"voice": vm.active_voice.name},
                )

            elif action_name == "get_voice_settings":
                vm = self._get_voice_manager()
                status = vm.get_status()
                v = vm.active_voice
                msg = f"Current Voice: {v.name} ({v.locale} {v.gender}, {v.tone})\nSpeed: {vm.active_rate} | Pitch: {vm.active_pitch}"
                res = AutomationResult(
                    success=True,
                    action=action_name,
                    target="voice_settings",
                    message=msg,
                    data=status,
                )

            # Step 5: File System Assistant & Downloads Organizer
            elif action_name == "organize_downloads":
                org = self._get_file_organizer()
                target_dir = request.params.get("path") or request.params.get("target_dir")
                dry_run = bool(request.params.get("dry_run", False))
                summary = org.organize_directory(target_dir=target_dir, dry_run=dry_run)
                res = AutomationResult(
                    success=True,
                    action=action_name,
                    target=summary.target_directory,
                    message=summary.format_display(),
                    data=summary.to_dict(),
                )

            elif action_name == "find_large_files":
                org = self._get_file_organizer()
                target_dir = request.params.get("path") or request.params.get("target_dir")
                min_size_mb = float(request.params.get("min_size_mb", 50.0))
                limit = int(request.params.get("limit", 10))
                large_files = org.find_large_files(target_dir=target_dir, min_size_mb=min_size_mb, limit=limit)
                if large_files:
                    lines = [f"- {f.name} ({f.format_size()}) [{f.category}]" for f in large_files]
                    msg = f"Found {len(large_files)} large file(s) (>={min_size_mb} MB):\n" + "\n".join(lines)
                else:
                    msg = f"No files larger than {min_size_mb} MB found in {org.get_target_directory(target_dir)}."
                res = AutomationResult(
                    success=True,
                    action=action_name,
                    target=str(org.get_target_directory(target_dir)),
                    message=msg,
                    data={"count": len(large_files), "files": [f.to_dict() for f in large_files]},
                )

            elif action_name == "find_duplicate_files":
                org = self._get_file_organizer()
                target_dir = request.params.get("path") or request.params.get("target_dir")
                dups = org.find_duplicates(target_dir=target_dir)
                if dups:
                    blocks = []
                    for i, grp in enumerate(dups, start=1):
                        file_names = ", ".join(Path(p).name for p in grp.files)
                        blocks.append(f"[{i}] {grp.count} copies ({round(grp.size_bytes / 1024, 1)} KB): {file_names}")
                    msg = f"Found {len(dups)} duplicate file group(s):\n\n" + "\n".join(blocks)
                else:
                    msg = f"No duplicate files found in {org.get_target_directory(target_dir)}."
                res = AutomationResult(
                    success=True,
                    action=action_name,
                    target=str(org.get_target_directory(target_dir)),
                    message=msg,
                    data={"count": len(dups), "groups": [g.to_dict() for g in dups]},
                )

            elif action_name == "clean_temp_files":
                org = self._get_file_organizer()
                target_dir = request.params.get("path") or request.params.get("target_dir")
                count, bytes_freed, msg = org.clean_temp_files(target_dir=target_dir)
                res = AutomationResult(
                    success=True,
                    action=action_name,
                    target=str(org.get_target_directory(target_dir)),
                    message=msg,
                    data={"cleaned_count": count, "bytes_freed": bytes_freed},
                )

            elif action_name == "undo_file_organization":
                org = self._get_file_organizer()
                ok, reverted_count, msg = org.undo_last_organization()
                res = AutomationResult(
                    success=ok,
                    action=action_name,
                    target="undo",
                    message=msg,
                    data={"reverted_count": reverted_count},
                )

            # Step 6: Local Git & Dev Workflow Actions
            elif action_name == "git_status":
                git_svc = self._get_git_service()
                repo = request.params.get("repo_path") or request.params.get("path")
                ok, status_res, msg = git_svc.get_status(repo_path=repo)
                res = AutomationResult(
                    success=ok,
                    action=action_name,
                    target=str(git_svc.resolve_repo_path(repo)),
                    message=msg,
                    data=status_res.to_dict() if status_res else {},
                )

            elif action_name == "git_branches":
                git_svc = self._get_git_service()
                repo = request.params.get("repo_path") or request.params.get("path")
                ok, branches, msg = git_svc.get_branches(repo_path=repo)
                res = AutomationResult(
                    success=ok,
                    action=action_name,
                    target=str(git_svc.resolve_repo_path(repo)),
                    message=msg,
                    data={"branches": [b.to_dict() for b in branches], "count": len(branches)},
                )

            elif action_name == "git_log":
                git_svc = self._get_git_service()
                repo = request.params.get("repo_path") or request.params.get("path")
                limit = int(request.params.get("limit", 5))
                ok, commits, msg = git_svc.get_log(limit=limit, repo_path=repo)
                res = AutomationResult(
                    success=ok,
                    action=action_name,
                    target=str(git_svc.resolve_repo_path(repo)),
                    message=msg,
                    data={"commits": [c.to_dict() for c in commits], "count": len(commits)},
                )

            elif action_name == "git_diff":
                git_svc = self._get_git_service()
                repo = request.params.get("repo_path") or request.params.get("path")
                staged = bool(request.params.get("staged", False))
                ok, diff_res, msg = git_svc.get_diff_summary(staged=staged, repo_path=repo)
                res = AutomationResult(
                    success=ok,
                    action=action_name,
                    target=str(git_svc.resolve_repo_path(repo)),
                    message=msg,
                    data=diff_res.to_dict() if diff_res else {},
                )

            elif action_name == "git_create_branch":
                git_svc = self._get_git_service()
                repo = request.params.get("repo_path") or request.params.get("path")
                branch_name = str(request.params.get("branch") or request.params.get("name") or request.params.get("branch_name", "")).strip()
                checkout = bool(request.params.get("checkout", True))
                ok, msg = git_svc.create_branch(branch_name=branch_name, checkout=checkout, repo_path=repo)
                res = AutomationResult(
                    success=ok,
                    action=action_name,
                    target=branch_name,
                    message=msg,
                    data={"branch": branch_name, "checkout": checkout},
                )

            elif action_name == "git_switch_branch":
                git_svc = self._get_git_service()
                repo = request.params.get("repo_path") or request.params.get("path")
                branch_name = str(request.params.get("branch") or request.params.get("name") or request.params.get("branch_name", "")).strip()
                ok, msg = git_svc.switch_branch(branch_name=branch_name, repo_path=repo)
                res = AutomationResult(
                    success=ok,
                    action=action_name,
                    target=branch_name,
                    message=msg,
                    data={"branch": branch_name},
                )

            elif action_name == "git_commit":
                git_svc = self._get_git_service()
                repo = request.params.get("repo_path") or request.params.get("path")
                commit_msg = str(request.params.get("message") or "").strip()
                stage_all = bool(request.params.get("stage_all", False) or request.params.get("all", False))
                ok, msg = git_svc.commit(message=commit_msg, stage_all=stage_all, repo_path=repo)
                res = AutomationResult(
                    success=ok,
                    action=action_name,
                    target=str(git_svc.resolve_repo_path(repo)),
                    message=msg,
                    data={"message": commit_msg, "stage_all": stage_all},
                )

            # Step 7: Proactive Morning & Evening Audio Briefings
            elif action_name == "morning_briefing":
                briefing_svc = self._get_briefing_service()
                speak_audio = bool(request.params.get("audio", True) and not request.params.get("no_audio", False))
                repo = request.params.get("repo_path") or request.params.get("path")
                briefing = await briefing_svc.generate_morning_briefing(speak_audio=speak_audio, repo_path=repo)
                res = AutomationResult(
                    success=True,
                    action=action_name,
                    target="morning_briefing",
                    message=briefing.format_display(),
                    data=briefing.to_dict(),
                )

            elif action_name == "evening_briefing":
                briefing_svc = self._get_briefing_service()
                speak_audio = bool(request.params.get("audio", True) and not request.params.get("no_audio", False))
                repo = request.params.get("repo_path") or request.params.get("path")
                briefing = await briefing_svc.generate_evening_briefing(speak_audio=speak_audio, repo_path=repo)
                res = AutomationResult(
                    success=True,
                    action=action_name,
                    target="evening_briefing",
                    message=briefing.format_display(),
                    data=briefing.to_dict(),
                )


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

    def _get_email_monitor(self) -> Any:
        """Get or lazily instantiate email monitoring service."""
        if self.email_monitor is None:
            from denver.automation.email import get_email_monitor
            self.email_monitor = get_email_monitor()
        settings = getattr(self, "settings", None)
        if settings and getattr(settings, "email_mock_mode", False):
            self.email_monitor.config.is_mock = True
            self.email_monitor.client.config.is_mock = True
        return self.email_monitor

    def _get_calendar_service(self) -> Any:
        """Get or lazily instantiate calendar scheduling service."""
        if not hasattr(self, "_calendar_service") or self._calendar_service is None:
            from denver.calendar import get_calendar_service
            self._calendar_service = get_calendar_service()
        return self._calendar_service

    def _get_rag_service(self) -> Any:
        """Get or lazily instantiate Document RAG service."""
        if not hasattr(self, "_rag_service") or self._rag_service is None:
            from denver.rag import get_rag_service
            self._rag_service = get_rag_service()
        return self._rag_service

    def _get_voice_manager(self) -> Any:
        """Get or lazily instantiate VoiceProfileManager."""
        if not hasattr(self, "_voice_manager") or self._voice_manager is None:
            from denver.audio import get_voice_manager
            self._voice_manager = get_voice_manager()
        return self._voice_manager

    def _get_file_organizer(self) -> Any:
        """Get or lazily instantiate FileOrganizerService."""
        if not hasattr(self, "_file_organizer") or self._file_organizer is None:
            from denver.automation.files import get_file_organizer
            self._file_organizer = get_file_organizer()
        return self._file_organizer

    def _get_git_service(self) -> Any:
        """Get or lazily instantiate GitDevService."""
        if not hasattr(self, "_git_service") or self._git_service is None:
            from denver.automation.git import get_git_service
            self._git_service = get_git_service()
        return self._git_service

    def _get_briefing_service(self) -> Any:
        """Get or lazily instantiate BriefingService."""
        if not hasattr(self, "_briefing_service") or self._briefing_service is None:
            from denver.briefing import get_briefing_service
            self._briefing_service = get_briefing_service()
        return self._briefing_service

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
            "email": "READY",
            "calendar": "READY",
            "allowlisted_apps_count": len(self.registry.list_applications()),
            "known_sites_count": len(self.registry.list_known_sites()),
        }

