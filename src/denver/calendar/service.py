"""Calendar and Meeting Scheduling Service with SQLite persistence and RFC 5545 iCal support."""

from __future__ import annotations

import datetime
import json
import os
import re
import sqlite3
from typing import Any

from denver.calendar.models import CalendarEvent, DaySchedule
from denver.logging.logger import get_logger

logger = get_logger("calendar.service")


def _resolve_datetime_expr(expr: str, default_hour: int = 9) -> datetime.datetime:
    """Heuristic natural language date & time expression resolver."""
    clean = expr.strip().lower()
    now = datetime.datetime.now()

    # Direct ISO/SQL parse attempt
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%m/%d/%Y %H:%M", "%m/%d/%Y"):
        try:
            return datetime.datetime.strptime(clean, fmt)
        except ValueError:
            pass

    target_date = now.date()
    if "tomorrow" in clean:
        target_date = now.date() + datetime.timedelta(days=1)
    elif "today" in clean:
        target_date = now.date()
    elif "yesterday" in clean:
        target_date = now.date() - datetime.timedelta(days=1)
    else:
        # Check weekday names (e.g. "on monday", "friday")
        weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        for idx, day_name in enumerate(weekdays):
            if day_name in clean:
                days_ahead = (idx - now.weekday()) % 7
                if days_ahead == 0 and "next" in clean:
                    days_ahead = 7
                target_date = now.date() + datetime.timedelta(days=days_ahead)
                break

    # Time extraction (e.g. "3 pm", "3:30 pm", "14:00", "at 4")
    time_match = re.search(r"(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", clean)
    hour = default_hour
    minute = 0
    if time_match:
        raw_hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
        meridiem = (time_match.group(3) or "").lower()
        if meridiem == "pm" and raw_hour < 12:
            raw_hour += 12
        elif meridiem == "am" and raw_hour == 12:
            raw_hour = 0
        hour = raw_hour

    return datetime.datetime.combine(target_date, datetime.time(hour=hour, minute=minute))


class CalendarService:
    """Manages scheduled events, meeting lookups, day agendas, and iCalendar imports."""

    def __init__(self, db_conn_or_path: sqlite3.Connection | str = "denver_memory.sqlite3") -> None:
        if isinstance(db_conn_or_path, sqlite3.Connection):
            self._conn = db_conn_or_path
            self._owns_conn = False
        else:
            self._conn = sqlite3.connect(str(db_conn_or_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._owns_conn = True

        self._ensure_table()

    def _ensure_table(self) -> None:
        """Ensure calendar_events table and indexes are available."""
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS calendar_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP,
                location TEXT DEFAULT '',
                description TEXT DEFAULT '',
                attendees TEXT DEFAULT '[]',
                is_all_day BOOLEAN DEFAULT 0,
                reminder_minutes INTEGER DEFAULT 15,
                reminder_sent BOOLEAN DEFAULT 0,
                source TEXT DEFAULT 'local',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_calendar_start ON calendar_events(start_time);
            CREATE INDEX IF NOT EXISTS idx_calendar_title ON calendar_events(title);
            """
        )
        self._conn.commit()

    def create_event(
        self,
        title: str,
        start_time: str | datetime.datetime,
        end_time: str | datetime.datetime | None = None,
        location: str = "",
        description: str = "",
        attendees: list[str] | None = None,
        is_all_day: bool = False,
        reminder_minutes: int = 15,
        source: str = "local",
    ) -> CalendarEvent:
        """Create and persist a new calendar event."""
        if isinstance(start_time, datetime.datetime):
            st_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
        else:
            st_str = str(start_time)

        et_str: str | None = None
        if isinstance(end_time, datetime.datetime):
            et_str = end_time.strftime("%Y-%m-%d %H:%M:%S")
        elif end_time:
            et_str = str(end_time)

        att_json = json.dumps(attendees or [])
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO calendar_events (
                title, start_time, end_time, location, description, attendees,
                is_all_day, reminder_minutes, source, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP);
            """,
            (title.strip(), st_str, et_str, location.strip(), description.strip(), att_json, int(is_all_day), reminder_minutes, source),
        )
        self._conn.commit()
        event_id = cur.lastrowid

        logger.info("Created calendar event #%d: '%s' starting at %s", event_id, title, st_str)
        return self.get_event_by_id(event_id) or CalendarEvent(
            id=event_id,
            title=title,
            start_time=st_str,
            end_time=et_str,
            location=location,
            description=description,
            attendees=attendees or [],
            is_all_day=is_all_day,
            reminder_minutes=reminder_minutes,
            source=source,
        )

    def get_event_by_id(self, event_id: int) -> CalendarEvent | None:
        """Retrieve single calendar event by primary key ID."""
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM calendar_events WHERE id = ?;", (event_id,))
        row = cur.fetchone()
        if not row:
            return None
        return self._row_to_event(row)

    def get_events_for_date(self, target_date: datetime.date | str | None = None) -> DaySchedule:
        """Retrieve all events occurring on a specific date (defaults to today)."""
        if target_date is None:
            t_date = datetime.date.today()
        elif isinstance(target_date, str):
            t_date = _resolve_datetime_expr(target_date).date()
        else:
            t_date = target_date

        date_prefix = t_date.strftime("%Y-%m-%d")
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT * FROM calendar_events
            WHERE DATE(start_time) = DATE(?)
            ORDER BY start_time ASC;
            """,
            (date_prefix,),
        )
        events = [self._row_to_event(r) for r in cur.fetchall()]
        return DaySchedule(date_str=date_prefix, events=events)

    def get_upcoming_events(self, limit: int = 5, from_time: datetime.datetime | None = None) -> list[CalendarEvent]:
        """Fetch chronologically ordered upcoming events starting from now or specified time."""
        ref = from_time or datetime.datetime.now()
        ref_str = ref.strftime("%Y-%m-%d %H:%M:%S")
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT * FROM calendar_events
            WHERE start_time >= ?
            ORDER BY start_time ASC
            LIMIT ?;
            """,
            (ref_str, limit),
        )
        return [self._row_to_event(r) for r in cur.fetchall()]

    def get_next_meeting(self, from_time: datetime.datetime | None = None) -> CalendarEvent | None:
        """Retrieve the immediate next upcoming event or meeting."""
        upcomings = self.get_upcoming_events(limit=1, from_time=from_time)
        return upcomings[0] if upcomings else None

    def search_events(self, query: str) -> list[CalendarEvent]:
        """Search events by keyword in title, location, or description."""
        like_q = f"%{query.strip()}%"
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT * FROM calendar_events
            WHERE title LIKE ? OR location LIKE ? OR description LIKE ?
            ORDER BY start_time DESC
            LIMIT 20;
            """,
            (like_q, like_q, like_q),
        )
        return [self._row_to_event(r) for r in cur.fetchall()]

    def delete_event(self, event_id: int | None = None, title: str | None = None) -> bool:
        """Delete an event by ID or title."""
        cur = self._conn.cursor()
        if event_id is not None:
            cur.execute("DELETE FROM calendar_events WHERE id = ?;", (event_id,))
        elif title:
            cur.execute("DELETE FROM calendar_events WHERE LOWER(title) = LOWER(?);", (title.strip(),))
        else:
            return False
        self._conn.commit()
        return cur.rowcount > 0

    def import_ics(self, ics_content_or_path: str) -> int:
        """Parse and import RFC 5545 iCalendar data into local database."""
        text = ics_content_or_path
        if os.path.isfile(ics_content_or_path):
            with open(ics_content_or_path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()

        events_data = self._parse_ics_text(text)
        imported_count = 0
        for ev in events_data:
            self.create_event(
                title=ev.get("summary", "Untitled Event"),
                start_time=ev.get("start", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                end_time=ev.get("end"),
                location=ev.get("location", ""),
                description=ev.get("description", ""),
                source="ics_import",
            )
            imported_count += 1
        return imported_count

    def export_ics(self, limit: int = 50) -> str:
        """Export stored calendar events into standard RFC 5545 iCalendar string."""
        events = self.get_upcoming_events(limit=limit, from_time=datetime.datetime.now() - datetime.timedelta(days=7))
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Denver AI Assistant//EN",
            "CALSCALE:GREGORIAN",
        ]
        for ev in events:
            lines.append("BEGIN:VEVENT")
            st_dt = ev.starts_at_dt()
            lines.append(f"DTSTART:{st_dt.strftime('%Y%m%dT%H%M%SZ')}")
            if ev.end_time:
                et_dt = ev.ends_at_dt()
                if et_dt:
                    lines.append(f"DTEND:{et_dt.strftime('%Y%m%dT%H%M%SZ')}")
            lines.append(f"SUMMARY:{ev.title}")
            if ev.location:
                lines.append(f"LOCATION:{ev.location}")
            if ev.description:
                lines.append(f"DESCRIPTION:{ev.description}")
            lines.append(f"UID:denver-{ev.id}@{ev.source}")
            lines.append("END:VEVENT")
        lines.append("END:VCALENDAR")
        return "\r\n".join(lines)

    @staticmethod
    def _parse_ics_text(text: str) -> list[dict[str, Any]]:
        """Extract VEVENT blocks and key properties from RFC 5545 iCalendar stream."""
        events: list[dict[str, Any]] = []
        raw_events = re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, flags=re.DOTALL | re.IGNORECASE)
        for raw in raw_events:
            ev: dict[str, Any] = {}
            for line in raw.splitlines():
                line = line.strip()
                if not line or ":" not in line:
                    continue
                k, v = line.split(":", 1)
                k = k.split(";")[0].upper()
                if k == "SUMMARY":
                    ev["summary"] = v
                elif k == "LOCATION":
                    ev["location"] = v
                elif k == "DESCRIPTION":
                    ev["description"] = v
                elif k == "DTSTART":
                    ev["start"] = _resolve_datetime_expr(v)
                elif k == "DTEND":
                    ev["end"] = _resolve_datetime_expr(v)
            if "summary" in ev:
                events.append(ev)
        return events

    @staticmethod
    def _row_to_event(row: Any) -> CalendarEvent:
        """Convert SQLite database row tuple/Row into CalendarEvent."""
        column_names = [
            "id", "title", "start_time", "end_time", "location", "description",
            "attendees", "is_all_day", "reminder_minutes", "reminder_sent",
            "source", "created_at", "updated_at"
        ]
        if hasattr(row, "keys"):
            d = {k: row[k] for k in row.keys()}
        else:
            d = {col: row[idx] for idx, col in enumerate(column_names) if idx < len(row)}
        att_raw = d.get("attendees", "[]")
        try:
            attendees = json.loads(att_raw) if isinstance(att_raw, str) else list(att_raw)
        except Exception:
            attendees = []

        return CalendarEvent(
            id=d.get("id"),
            title=d.get("title", ""),
            start_time=d.get("start_time", ""),
            end_time=d.get("end_time"),
            location=d.get("location", ""),
            description=d.get("description", ""),
            attendees=attendees,
            is_all_day=bool(d.get("is_all_day", 0)),
            reminder_minutes=int(d.get("reminder_minutes", 15)),
            reminder_sent=bool(d.get("reminder_sent", 0)),
            source=d.get("source", "local"),
            created_at=str(d.get("created_at", "")),
            updated_at=str(d.get("updated_at", "")),
        )

    def close(self) -> None:
        """Close connection if owned."""
        if self._owns_conn:
            try:
                self._conn.close()
            except Exception:
                pass
