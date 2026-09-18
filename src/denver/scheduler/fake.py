"""Fake/Mock scheduler utilities for deterministic, zero-sleep testing."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from denver.scheduler.models import Routine, RoutineExecution, RoutineStatus
from denver.scheduler.scheduler import DenverScheduler


class FakeTimeProvider:
    """Mock time provider allowing simulated time progression."""

    def __init__(self, initial_time: Optional[datetime] = None) -> None:
        self._current_time = initial_time or datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self._current_time

    def advance(self, seconds: float) -> None:
        from datetime import timedelta
        self._current_time += timedelta(seconds=seconds)

    def set_time(self, new_time: datetime) -> None:
        self._current_time = new_time
