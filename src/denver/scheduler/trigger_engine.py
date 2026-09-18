"""Deterministic Trigger Calculation Engine for Denver Scheduler."""

from __future__ import annotations

import re
from datetime import datetime, time as dtime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from denver.logging.logger import get_logger
from denver.scheduler.errors import InvalidTriggerError, TriggerIntervalTooShortError
from denver.scheduler.models import RoutineTrigger, TriggerType

logger = get_logger("scheduler.trigger_engine")

MIN_INTERVAL_SECONDS = 300.0  # 5 minutes safety minimum


def _parse_time_string(time_str: str) -> dtime:
    """Parse HH:MM or HH:MM:SS string safely."""
    time_str = time_str.strip()
    m = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$", time_str)
    if not m:
        raise InvalidTriggerError(f"Invalid time format: '{time_str}'. Expected HH:MM or HH:MM:SS.")
    hours = int(m.group(1))
    minutes = int(m.group(2))
    seconds = int(m.group(3) or 0)
    if not (0 <= hours <= 23 and 0 <= minutes <= 59 and 0 <= seconds <= 59):
        raise InvalidTriggerError(f"Time values out of range: '{time_str}'.")
    return dtime(hour=hours, minute=minutes, second=seconds)


def _get_zoneinfo(tz_name: str) -> timezone | ZoneInfo:
    """Resolve ZoneInfo or default to UTC."""
    if not tz_name or tz_name.upper() == "UTC":
        return timezone.utc
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        logger.warning("Unknown timezone '%s', defaulting to UTC.", tz_name)
        return timezone.utc


class TriggerEngine:
    """Computes exact, deterministic next execution timestamps for routine triggers."""

    def __init__(self, min_interval_seconds: float = MIN_INTERVAL_SECONDS) -> None:
        self.min_interval_seconds = min_interval_seconds

    def validate_trigger(self, trigger: RoutineTrigger) -> None:
        """Validate trigger configuration and safety bounds."""
        if trigger.trigger_type == TriggerType.ONE_TIME:
            if not trigger.run_at:
                raise InvalidTriggerError("ONE_TIME trigger requires 'run_at' datetime.")
        elif trigger.trigger_type == TriggerType.DAILY:
            if not trigger.time_of_day:
                raise InvalidTriggerError("DAILY trigger requires 'time_of_day' string (HH:MM).")
            _parse_time_string(trigger.time_of_day)
        elif trigger.trigger_type == TriggerType.WEEKLY:
            if not trigger.time_of_day:
                raise InvalidTriggerError("WEEKLY trigger requires 'time_of_day' string (HH:MM).")
            _parse_time_string(trigger.time_of_day)
            if not trigger.days_of_week:
                raise InvalidTriggerError("WEEKLY trigger requires at least one day in 'days_of_week' (0-6).")
            for day in trigger.days_of_week:
                if not (0 <= day <= 6):
                    raise InvalidTriggerError(f"Invalid weekday '{day}'. Must be 0 (Monday) to 6 (Sunday).")
        elif trigger.trigger_type == TriggerType.INTERVAL:
            if trigger.interval_seconds is None or trigger.interval_seconds <= 0:
                raise InvalidTriggerError("INTERVAL trigger requires a positive 'interval_seconds'.")
            if trigger.interval_seconds < self.min_interval_seconds:
                raise TriggerIntervalTooShortError(
                    f"Interval {trigger.interval_seconds}s is shorter than minimum allowed {self.min_interval_seconds}s (5 minutes)."
                )

    def compute_next_run(
        self,
        trigger: RoutineTrigger,
        after_dt: datetime | None = None,
    ) -> datetime | None:
        """Compute the next valid execution timestamp strictly after `after_dt` (in UTC)."""
        self.validate_trigger(trigger)
        now_utc = after_dt or datetime.now(timezone.utc)
        if now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=timezone.utc)
        else:
            now_utc = now_utc.astimezone(timezone.utc)

        tz = _get_zoneinfo(trigger.timezone)

        # 1. ONE_TIME Trigger
        if trigger.trigger_type == TriggerType.ONE_TIME:
            assert trigger.run_at is not None
            target_utc = trigger.run_at
            if target_utc.tzinfo is None:
                target_utc = target_utc.replace(tzinfo=timezone.utc)
            else:
                target_utc = target_utc.astimezone(timezone.utc)
            return target_utc if target_utc > now_utc else None

        # 2. INTERVAL Trigger
        if trigger.trigger_type == TriggerType.INTERVAL:
            assert trigger.interval_seconds is not None
            delta = timedelta(seconds=max(trigger.interval_seconds, self.min_interval_seconds))
            return now_utc + delta

        # 3. DAILY Trigger
        if trigger.trigger_type == TriggerType.DAILY:
            assert trigger.time_of_day is not None
            target_time = _parse_time_string(trigger.time_of_day)
            local_now = now_utc.astimezone(tz)

            candidate_local = datetime.combine(local_now.date(), target_time, tzinfo=tz)
            if candidate_local <= local_now:
                candidate_local += timedelta(days=1)
            return candidate_local.astimezone(timezone.utc)

        # 4. WEEKLY Trigger
        if trigger.trigger_type == TriggerType.WEEKLY:
            assert trigger.time_of_day is not None
            target_time = _parse_time_string(trigger.time_of_day)
            local_now = now_utc.astimezone(tz)
            sorted_days = sorted(set(trigger.days_of_week))

            for day_offset in range(8):
                candidate_date = local_now.date() + timedelta(days=day_offset)
                if candidate_date.weekday() in sorted_days:
                    candidate_local = datetime.combine(candidate_date, target_time, tzinfo=tz)
                    if candidate_local > local_now:
                        return candidate_local.astimezone(timezone.utc)

        return None
