"""Domain models and schemas for Denver Calendar and Meeting Intelligence."""

from __future__ import annotations

import datetime
import json
import time
from dataclasses import dataclass, field
from typing import Any


def _parse_iso_or_sql_dt(dt_str: str) -> datetime.datetime:
    """Parse various timestamp strings into datetime object."""
    clean = dt_str.strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S"):
        try:
            return datetime.datetime.strptime(clean, fmt)
        except ValueError:
            continue
    # Fallback to fromisoformat
    try:
        return datetime.datetime.fromisoformat(dt_str)
    except Exception:
        return datetime.datetime.now()


@dataclass
class CalendarEvent:
    """Standardized representation of a scheduled calendar event or meeting."""

    title: str
    start_time: str
    end_time: str | None = None
    location: str = ""
    description: str = ""
    attendees: list[str] = field(default_factory=list)
    is_all_day: bool = False
    reminder_minutes: int = 15
    reminder_sent: bool = False
    source: str = "local"
    id: int | None = None
    created_at: str = ""
    updated_at: str = ""

    def starts_at_dt(self) -> datetime.datetime:
        """Return Python datetime representation of start_time."""
        return _parse_iso_or_sql_dt(self.start_time)

    def ends_at_dt(self) -> datetime.datetime | None:
        """Return Python datetime representation of end_time."""
        if not self.end_time:
            return None
        return _parse_iso_or_sql_dt(self.end_time)

    def is_today(self, ref_date: datetime.date | None = None) -> bool:
        """Determine if this event takes place on target date (defaults to today)."""
        ref = ref_date or datetime.date.today()
        return self.starts_at_dt().date() == ref

    def is_upcoming(self, ref_dt: datetime.datetime | None = None) -> bool:
        """Determine if this event begins after the reference datetime (defaults to now)."""
        ref = ref_dt or datetime.datetime.now()
        return self.starts_at_dt() >= ref

    def format_time_span(self) -> str:
        """Format a human-readable time interval (e.g. '03:00 PM – 04:00 PM')."""
        if self.is_all_day:
            return "All Day"
        st = self.starts_at_dt()
        st_str = st.strftime("%I:%M %p").lstrip("0")
        if self.end_time:
            et = self.ends_at_dt()
            if et:
                et_str = et.strftime("%I:%M %p").lstrip("0")
                return f"{st_str} – {et_str}"
        return st_str

    def format_display(self) -> str:
        """Return an assistant-friendly display string for speech or display."""
        time_part = self.format_time_span()
        loc_part = f" at {self.location}" if self.location else ""
        return f"• {self.title} ({time_part}{loc_part})"

    def to_dict(self) -> dict[str, Any]:
        """Convert event instance to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "time_span": self.format_time_span(),
            "location": self.location,
            "description": self.description,
            "attendees": self.attendees,
            "is_all_day": self.is_all_day,
            "reminder_minutes": self.reminder_minutes,
            "reminder_sent": self.reminder_sent,
            "source": self.source,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class DaySchedule:
    """Aggregated schedule overview for a specific calendar date."""

    date_str: str
    events: list[CalendarEvent]

    def format_briefing(self) -> str:
        """Generate formatted spoken/text schedule briefing."""
        if not self.events:
            return f"You have no meetings or events scheduled for {self.date_str}."
        count_str = "1 event" if len(self.events) == 1 else f"{len(self.events)} events"
        lines = [f"📅 Schedule for {self.date_str} ({count_str}):"]
        for ev in sorted(self.events, key=lambda e: e.starts_at_dt()):
            lines.append(f"  {ev.format_display()}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Convert schedule to dictionary."""
        return {
            "date": self.date_str,
            "count": len(self.events),
            "events": [e.to_dict() for e in self.events],
        }
