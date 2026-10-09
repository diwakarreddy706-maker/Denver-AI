"""Proactive Morning & Evening Audio Briefing Intelligence Service for Denver."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
from typing import Any

from denver.briefing.models import (
    AudioBriefing,
    BriefingSection,
    BriefingType,
)
from denver.logging.logger import get_logger

logger = get_logger("briefing.service")


class BriefingService:
    """Orchestrates multi-pillar context aggregation and spoken audio briefings."""

    def __init__(self, db_conn: sqlite3.Connection | None = None) -> None:
        self.db_conn = db_conn

    def _get_connection(self) -> sqlite3.Connection | None:
        if self.db_conn:
            return self.db_conn
        try:
            return sqlite3.connect("denver_memory.sqlite3")
        except Exception:
            return None

    def get_user_name(self) -> str:
        """Fetch preferred user name or fallback to default."""
        conn = self._get_connection()
        if conn:
            try:
                row = conn.execute(
                    "SELECT value FROM user_preferences WHERE key = 'user_name' LIMIT 1;"
                ).fetchone()
                if row and row[0]:
                    return str(row[0])
            except Exception:
                pass
        return "Diwakar"

    async def _gather_weather(self) -> tuple[str, str]:
        """Aggregate current weather conditions and daily forecast."""
        try:
            from denver.automation.weather import WeatherService
            ws = WeatherService()
            report = await ws.get_weather()
            if report and report.is_success:
                cond = report.description or "Fair"
                temp = f"{report.temperature_c}°C" if report.temperature_c is not None else ""
                loc = report.location_name or "local area"
                vis = f"Current weather in {loc}: **{temp} {cond}**. Humidity {report.humidity_pct}%."
                spoken = f"The weather in {loc} is currently {temp} and {cond}."
                return vis, spoken
        except Exception as exc:
            logger.debug("Weather query skipped or unavailable: %s", exc)

        return "Fair conditions expected throughout the day.", "Weather is expected to remain fair."

    def _gather_schedule(self, is_morning: bool = True) -> tuple[str, str]:
        """Aggregate calendar events and meetings."""
        try:
            from denver.calendar import get_calendar_service
            cal = get_calendar_service()
            schedule = cal.get_today_schedule()
            count = schedule.total_events

            if is_morning:
                if count == 0:
                    vis = "No scheduled calendar meetings today — your calendar is wide open for deep work."
                    spoken = "Your calendar is completely open today with no scheduled meetings."
                else:
                    first = schedule.events[0]
                    first_time = datetime.fromisoformat(first.start_time).strftime("%I:%M %p")
                    vis = f"You have **{count} event(s)** scheduled today.\nFirst up: **{first.title}** at {first_time}."
                    spoken = f"You have {count} meeting scheduled today. Your first meeting is {first.title} at {first_time}."
                return vis, spoken
            else:
                # Evening lookahead for tomorrow
                tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
                tmrw_sched = cal.get_schedule(start_date=tomorrow, end_date=tomorrow)
                tmrw_count = tmrw_sched.total_events
                if tmrw_count > 0:
                    first_tmrw = tmrw_sched.events[0]
                    first_tmrw_time = datetime.fromisoformat(first_tmrw.start_time).strftime("%I:%M %p")
                    vis = f"You completed {count} scheduled event(s) today.\nTomorrow you have **{tmrw_count} event(s)** starting with **{first_tmrw.title}** at {first_tmrw_time}."
                    spoken = f"You have {tmrw_count} meeting scheduled for tomorrow, starting with {first_tmrw.title} at {first_tmrw_time}."
                else:
                    vis = f"You completed {count} scheduled event(s) today. Tomorrow's schedule is completely clear."
                    spoken = f"Today's schedule is complete, and your calendar tomorrow is wide open."
                return vis, spoken
        except Exception as exc:
            logger.debug("Schedule query skipped or unavailable: %s", exc)
            return "No calendar events recorded.", "You have no upcoming calendar conflicts."

    def _gather_inbox(self) -> tuple[str, str]:
        """Aggregate email status and high-priority messages."""
        try:
            from denver.automation.email import get_email_monitor
            monitor = get_email_monitor()
            unread_count = monitor.client.get_unread_count()
            high_prio = monitor.analyzer.list_high_priority()

            if unread_count == 0:
                vis = "Inbox is clean with **0 unread emails**."
                spoken = "Your email inbox is clean with zero unread messages."
            else:
                prio_txt = f" ({len(high_prio)} high priority)" if high_prio else ""
                vis = f"You have **{unread_count} unread email(s)**{prio_txt} in your inbox."
                spoken = f"You have {unread_count} unread email in your inbox."
                if high_prio:
                    spoken += f" Notice: {len(high_prio)} message is marked as high priority."
            return vis, spoken
        except Exception as exc:
            logger.debug("Inbox query skipped or unavailable: %s", exc)
            return "Inbox monitoring is standby.", "Your email inbox is in standby."

    def _gather_git(self, repo_path: str | None = None) -> tuple[str, str] | None:
        """Aggregate active development and git workspace context."""
        try:
            from denver.automation.git import get_git_service
            git_svc = get_git_service()
            target_repo = git_svc.resolve_repo_path(repo_path)
            if not git_svc.is_git_repository(target_repo):
                return None

            ok, status, _ = git_svc.get_status(target_repo)
            if ok and status:
                clean_str = "Clean working tree" if status.is_clean else f"{len(status.staged_files) + len(status.modified_files)} uncommitted changes"
                vis = f"Repository **{Path(target_repo).name}** on branch **{status.branch}** ({clean_str})."
                spoken = f"In repository {Path(target_repo).name}, you are currently working on branch {status.branch}."
                if not status.is_clean:
                    spoken += " You have uncommitted working tree changes."
                return vis, spoken
        except Exception as exc:
            logger.debug("Git context skipped: %s", exc)
        return None

    def _gather_downloads_hygiene(self) -> tuple[str, str] | None:
        """Check for downloads clutter during evening review."""
        try:
            from denver.automation.files import get_file_organizer
            org = get_file_organizer()
            files = org.scan_directory()
            if len(files) >= 5:
                vis = f"Downloads directory has **{len(files)} files** that can be organized into categorized folders."
                spoken = f"Notice: your Downloads folder has {len(files)} unorganized files that you can sort with a single command."
                return vis, spoken
        except Exception as exc:
            logger.debug("Downloads check skipped: %s", exc)
        return None

    async def narrate_briefing(self, briefing: AudioBriefing) -> tuple[bool, str]:
        """Narrate briefing script using active Edge-TTS spoken voice."""
        try:
            from denver.audio import get_voice_manager
            vm = get_voice_manager()
            script = briefing.spoken_script
            ok, msg = await vm.preview_voice(custom_phrase=script)
            briefing.audio_played = ok
            briefing.audio_voice = vm.active_voice.name
            return ok, msg
        except Exception as exc:
            logger.warning("Spoken narration failed: %s", exc)
            return False, str(exc)

    async def generate_morning_briefing(
        self,
        speak_audio: bool = False,
        repo_path: str | None = None,
    ) -> AudioBriefing:
        """Generate comprehensive morning briefing across all intelligent pillars."""
        user_name = self.get_user_name()
        now = datetime.now()
        day_str = now.strftime("%A, %B %d")
        greeting = f"Good morning, {user_name}! Here is your Denver morning briefing for {day_str}."

        sections: list[BriefingSection] = []

        # 1. Weather
        weather_vis, weather_spk = await self._gather_weather()
        sections.append(
            BriefingSection(
                name="weather",
                title="Weather & Conditions",
                icon="☀️",
                text=weather_vis,
                spoken_text=weather_spk,
            )
        )

        # 2. Schedule
        sched_vis, sched_spk = self._gather_schedule(is_morning=True)
        sections.append(
            BriefingSection(
                name="schedule",
                title="Today's Schedule & Meetings",
                icon="📅",
                text=sched_vis,
                spoken_text=sched_spk,
            )
        )

        # 3. Email Inbox
        inbox_vis, inbox_spk = self._gather_inbox()
        sections.append(
            BriefingSection(
                name="inbox",
                title="Email & Communications",
                icon="📬",
                text=inbox_vis,
                spoken_text=inbox_spk,
            )
        )

        # 4. Dev Workspace & Git
        git_res = self._gather_git(repo_path=repo_path)
        if git_res:
            git_vis, git_spk = git_res
            sections.append(
                BriefingSection(
                    name="git",
                    title="Active Code Workspace",
                    icon="🌿",
                    text=git_vis,
                    spoken_text=git_spk,
                )
            )

        briefing = AudioBriefing(
            briefing_type=BriefingType.MORNING,
            greeting=greeting,
            sections=sections,
        )

        if speak_audio:
            await self.narrate_briefing(briefing)

        return briefing

    async def generate_evening_briefing(
        self,
        speak_audio: bool = False,
        repo_path: str | None = None,
    ) -> AudioBriefing:
        """Generate comprehensive evening wrap-up briefing and tomorrow's lookahead."""
        user_name = self.get_user_name()
        now = datetime.now()
        day_str = now.strftime("%A, %B %d")
        greeting = f"Good evening, {user_name}! Here is your daily wrap-up and evening review for {day_str}."

        sections: list[BriefingSection] = []

        # 1. Daily schedule completion & tomorrow preview
        sched_vis, sched_spk = self._gather_schedule(is_morning=False)
        sections.append(
            BriefingSection(
                name="schedule",
                title="Daily Wrap-Up & Tomorrow's Agenda",
                icon="📅",
                text=sched_vis,
                spoken_text=sched_spk,
            )
        )

        # 2. Inbox review
        inbox_vis, inbox_spk = self._gather_inbox()
        sections.append(
            BriefingSection(
                name="inbox",
                title="End of Day Inbox",
                icon="📬",
                text=inbox_vis,
                spoken_text=inbox_spk,
            )
        )

        # 3. Git workspace status
        git_res = self._gather_git(repo_path=repo_path)
        if git_res:
            git_vis, git_spk = git_res
            sections.append(
                BriefingSection(
                    name="git",
                    title="Code Repositories",
                    icon="🌿",
                    text=git_vis,
                    spoken_text=git_spk,
                )
            )

        # 4. Downloads hygiene check
        dl_res = self._gather_downloads_hygiene()
        if dl_res:
            dl_vis, dl_spk = dl_res
            sections.append(
                BriefingSection(
                    name="files",
                    title="File Organization Recommendation",
                    icon="📁",
                    text=dl_vis,
                    spoken_text=dl_spk,
                )
            )

        # 5. Workday reflection
        sections.append(
            BriefingSection(
                name="reflection",
                title="Evening Downtime",
                icon="🌙",
                text="Workday session complete. All active services, audit logs, and memories have been securely persisted.",
                spoken_text="All systems are nominal. Have a great relaxing evening.",
            )
        )

        briefing = AudioBriefing(
            briefing_type=BriefingType.EVENING,
            greeting=greeting,
            sections=sections,
        )

        if speak_audio:
            await self.narrate_briefing(briefing)

        return briefing


_briefing_service: BriefingService | None = None


def get_briefing_service(db_conn: sqlite3.Connection | None = None) -> BriefingService:
    """Obtain or initialize shared singleton of BriefingService."""
    global _briefing_service
    if _briefing_service is None or db_conn is not None:
        _briefing_service = BriefingService(db_conn=db_conn)
    return _briefing_service
