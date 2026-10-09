"""Denver Calendar and Meeting Intelligence Subsystem."""

from __future__ import annotations

from denver.calendar.models import CalendarEvent, DaySchedule
from denver.calendar.service import CalendarService

_global_calendar: CalendarService | None = None


def get_calendar_service(force_new: bool = False) -> CalendarService:
    """Get or initialize singleton CalendarService instance."""
    global _global_calendar
    if _global_calendar is None or force_new:
        try:
            from denver.config.settings import get_settings

            s = get_settings()
            db_path = getattr(s, "database_path", "denver_memory.sqlite3")
        except Exception:
            db_path = "denver_memory.sqlite3"
        _global_calendar = CalendarService(db_path)
    return _global_calendar


__all__ = [
    "CalendarEvent",
    "DaySchedule",
    "CalendarService",
    "get_calendar_service",
]
