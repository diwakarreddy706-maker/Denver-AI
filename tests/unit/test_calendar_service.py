"""Unit tests for Denver Calendar and Meeting Scheduling Subsystem (Step 2)."""

import datetime
import pytest
import sqlite3
from unittest.mock import AsyncMock, MagicMock

from denver.automation.executor import AutomationExecutor
from denver.automation.models import AutomationRequest
from denver.calendar.models import CalendarEvent, DaySchedule
from denver.calendar.service import CalendarService, _resolve_datetime_expr
from denver.commands.models import CommandRequest
from denver.commands.router import IntentRouter
from denver.commands.service import CommandEngineService


# -----------------------------------------------------------------------------
# 1. Models & Formats
# -----------------------------------------------------------------------------

def test_calendar_models_and_formatting():
    ev = CalendarEvent(
        id=1,
        title="Engineering Sync",
        start_time="2026-10-02 14:00:00",
        end_time="2026-10-02 15:00:00",
        location="Room 402",
        description="Sprint demo and review",
        attendees=["alice@domain.com", "bob@domain.com"],
    )
    assert ev.starts_at_dt().hour == 14
    assert ev.ends_at_dt().hour == 15
    assert ev.format_time_span() == "2:00 PM – 3:00 PM"
    disp = ev.format_display()
    assert "Engineering Sync" in disp
    assert "Room 402" in disp
    assert "2:00 PM" in disp

    schedule = DaySchedule(date_str="2026-10-02", events=[ev])
    briefing = schedule.format_briefing()
    assert "📅 Schedule for 2026-10-02" in briefing
    assert "Engineering Sync" in briefing


# -----------------------------------------------------------------------------
# 2. Service CRUD Operations
# -----------------------------------------------------------------------------

def test_calendar_service_crud():
    conn = sqlite3.connect(":memory:")
    service = CalendarService(conn)

    # 1. Create events
    ev1 = service.create_event(
        title="Weekly Standup",
        start_time="2026-10-02 09:30:00",
        end_time="2026-10-02 10:00:00",
        location="Google Meet",
    )
    assert ev1.id is not None
    assert ev1.title == "Weekly Standup"

    future_dt = datetime.datetime.now() + datetime.timedelta(hours=2)
    ev2 = service.create_event(
        title="Product Roadmap",
        start_time=future_dt,
        location="Boardroom A",
    )
    assert ev2.id is not None

    # 2. Query by date
    day = service.get_events_for_date(datetime.date(2026, 10, 2))
    assert len(day.events) >= 1
    assert any(e.title == "Weekly Standup" for e in day.events)

    # 3. Next meeting
    next_ev = service.get_next_meeting(from_time=datetime.datetime.now())
    assert next_ev is not None
    assert next_ev.title == "Product Roadmap"

    # 4. Search
    found = service.search_events("Roadmap")
    assert len(found) == 1
    assert found[0].title == "Product Roadmap"

    # 5. Delete by ID
    assert service.delete_event(event_id=ev1.id) is True
    assert service.get_event_by_id(ev1.id) is None


# -----------------------------------------------------------------------------
# 3. Natural Date & Time Resolver
# -----------------------------------------------------------------------------

def test_calendar_natural_language_date_resolver():
    dt_today = _resolve_datetime_expr("today at 3 PM")
    assert dt_today.hour == 15
    assert dt_today.minute == 0
    assert dt_today.date() == datetime.date.today()

    dt_tomorrow = _resolve_datetime_expr("tomorrow at 10:30 AM")
    assert dt_tomorrow.hour == 10
    assert dt_tomorrow.minute == 30
    assert dt_tomorrow.date() == datetime.date.today() + datetime.timedelta(days=1)

    dt_direct = _resolve_datetime_expr("2026-11-20 16:45:00")
    assert dt_direct.year == 2026
    assert dt_direct.month == 11
    assert dt_direct.day == 20
    assert dt_direct.hour == 16
    assert dt_direct.minute == 45


# -----------------------------------------------------------------------------
# 4. iCalendar (RFC 5545) Import & Export
# -----------------------------------------------------------------------------

def test_calendar_ics_import_and_export():
    conn = sqlite3.connect(":memory:")
    service = CalendarService(conn)

    sample_ics = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Example Corp//EN
BEGIN:VEVENT
UID:uid-1001@corp.com
DTSTART:20261005T140000Z
DTEND:20261005T150000Z
SUMMARY:Q4 Executive Briefing
LOCATION:Conference Hall B
DESCRIPTION:Review quarterly revenue targets
END:VEVENT
BEGIN:VEVENT
UID:uid-1002@corp.com
DTSTART:20261006T110000Z
SUMMARY:Architecture Design Review
LOCATION:Zoom
END:VEVENT
END:VCALENDAR"""

    count = service.import_ics(sample_ics)
    assert count == 2

    imported = service.search_events("Executive Briefing")
    assert len(imported) == 1
    assert imported[0].location == "Conference Hall B"

    # Test export
    exported = service.export_ics()
    assert "BEGIN:VCALENDAR" in exported
    assert "SUMMARY:Q4 Executive Briefing" in exported
    assert "END:VCALENDAR" in exported


# -----------------------------------------------------------------------------
# 5. Intent Router Pattern Matching
# -----------------------------------------------------------------------------

def test_calendar_router_intents():
    router = IntentRouter()

    # Schedule / Calendar view
    i1 = router.route("show calendar")
    assert i1.action_name == "get_today_schedule"

    i2 = router.route("what is my schedule today")
    assert i2.action_name == "get_today_schedule"

    i3 = router.route("view schedule tomorrow")
    assert i3.action_name == "get_today_schedule"
    assert i3.params["date"] == "tomorrow"

    # Next meeting
    i4 = router.route("what is my next meeting")
    assert i4.action_name == "get_next_meeting"

    i5 = router.route("upcoming meetings")
    assert i5.action_name == "get_next_meeting"

    # Create event
    i6 = router.route("schedule meeting Sprint Review at 4 PM")
    assert i6.action_name == "create_calendar_event"
    assert i6.params["title"] == "Sprint Review"
    assert i6.params["date_expr"] == "4 PM"

    i7 = router.route("add calendar event Team Lunch on Friday at 1 PM")
    assert i7.action_name == "create_calendar_event"
    assert i7.params["title"] == "Team Lunch"

    # Delete event
    i8 = router.route("cancel meeting Sprint Review")
    assert i8.action_name == "delete_calendar_event"
    assert i8.params["title"] == "Sprint Review"

    # Search
    i9 = router.route("search calendar for Architecture")
    assert i9.action_name == "search_calendar_events"
    assert i9.params["query"] == "Architecture"


# -----------------------------------------------------------------------------
# 6. CommandEngineService & AutomationExecutor Integration
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_calendar_service_and_executor_integration():
    executor = AutomationExecutor()
    memory_mock = MagicMock()
    memory_mock.record_habit = AsyncMock()
    memory_mock.log_audit = AsyncMock()
    service = CommandEngineService(memory_service=memory_mock, automation_executor=executor)

    # 1. Schedule event via CommandEngineService
    res_create = await service.process_command(CommandRequest(raw_text="schedule meeting Team Alignment at 2 PM"))
    assert res_create.success is True
    assert res_create.action_name == "create_calendar_event"
    assert "team alignment" in res_create.message.lower()

    # 2. View calendar schedule
    res_sched = await service.process_command(CommandRequest(raw_text="show calendar"))
    assert res_sched.success is True
    assert res_sched.action_name == "get_today_schedule"
    assert "Schedule for" in res_sched.message

    # 3. Query next meeting
    res_next = await service.process_command(CommandRequest(raw_text="what is my next meeting"))
    assert res_next.success is True
    assert res_next.action_name == "get_next_meeting"

    # 4. Search calendar
    res_search = await service.process_command(CommandRequest(raw_text="search calendar for Alignment"))
    assert res_search.success is True
    assert res_search.action_name == "search_calendar_events"
    assert "team alignment" in res_search.message.lower()

    # 5. Delete meeting
    res_del = await service.process_command(CommandRequest(raw_text="cancel meeting Team Alignment"))
    assert res_del.success is True
    assert res_del.action_name == "delete_calendar_event"
