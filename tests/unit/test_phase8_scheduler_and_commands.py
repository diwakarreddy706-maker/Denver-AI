"""Unit tests for Phase 8 DenverScheduler Engine, Commands, and Lifecycle."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from denver.commands.router import IntentRouter
from denver.commands.service import CommandEngineService
from denver.config.settings import DenverSettings
from denver.memory.database import DenverDatabase
from denver.memory.memory_service import MemoryService
from denver.runtime.event_bus import DenverEventBus
from denver.scheduler.execution_coordinator import RoutineExecutionCoordinator
from denver.scheduler.models import (
    RoutineAction,
    RoutineStatus,
    RoutineTrigger,
    TriggerType,
)
from denver.scheduler.routine_registry import RoutineRegistry
from denver.scheduler.scheduler import DenverScheduler


@pytest.fixture
async def app_components(tmp_path):
    db_file = tmp_path / "test_phase8_sched.sqlite3"
    db = DenverDatabase(db_path=str(db_file))
    await db.initialize()

    event_bus = DenverEventBus()
    memory_service = MemoryService(db=db, event_bus=event_bus)
    settings = DenverSettings(scheduler_enabled=True, scheduler_global_pause=False)

    registry = RoutineRegistry(db=db, event_bus=event_bus)
    command_service = CommandEngineService(
        memory_service=memory_service,
        event_bus=event_bus,
        settings=settings,
        routine_registry=registry,
    )
    coordinator = RoutineExecutionCoordinator(
        db=db,
        action_registry=command_service.registry,
        safety_validator=command_service.safety,
        event_bus=event_bus,
    )
    scheduler = DenverScheduler(
        settings=settings,
        registry=registry,
        coordinator=coordinator,
        event_bus=event_bus,
    )
    command_service.scheduler = scheduler

    yield {
        "db": db,
        "event_bus": event_bus,
        "memory": memory_service,
        "registry": registry,
        "coordinator": coordinator,
        "scheduler": scheduler,
        "command_service": command_service,
    }

    await scheduler.stop()
    await db.close()


def test_scheduler_intent_routing() -> None:
    router = IntentRouter()

    # List routines
    intent = router.route("list routines")
    assert intent.action_name == "list_routines"
    assert intent.category.value == "routine"

    # Pause routines
    intent = router.route("pause all routines")
    assert intent.action_name == "pause_scheduler"

    # Resume routines
    intent = router.route("resume scheduler")
    assert intent.action_name == "resume_scheduler"

    # Pause specific routine
    intent = router.route("pause routine rtn_abc123")
    assert intent.action_name == "pause_routine"
    assert intent.params["routine_id"] == "rtn_abc123"

    # Run routine now
    intent = router.route("run routine rtn_abc123 now")
    assert intent.action_name == "run_routine_now"
    assert intent.params["routine_id"] == "rtn_abc123"

    # Create reminder
    intent = router.route("remind me at 18:30 to stretch")
    assert intent.action_name == "create_reminder"
    assert intent.params["time"] == "18:30"
    assert intent.params["message"] == "stretch"


@pytest.mark.asyncio
async def test_scheduler_lifecycle_and_pause_resume(app_components) -> None:
    scheduler = app_components["scheduler"]
    assert scheduler.is_enabled is True
    assert scheduler.is_paused is False

    await scheduler.start()
    assert scheduler.is_running is True

    await scheduler.pause()
    assert scheduler.is_paused is True

    await scheduler.resume()
    assert scheduler.is_paused is False

    await scheduler.stop()
    assert scheduler.is_running is False


@pytest.mark.asyncio
async def test_scheduler_command_execution_pipeline(app_components) -> None:
    command_service = app_components["command_service"]
    registry = app_components["registry"]
    scheduler = app_components["scheduler"]

    await scheduler.start()

    # 1. Create a reminder through command
    resp = await command_service.process_command("remind me at 09:00 to drink water")
    assert resp.success is True
    assert "Reminder scheduled" in resp.message

    # 2. List routines
    resp = await command_service.process_command("list routines")
    assert resp.success is True
    assert "drink water" in resp.message

    # 3. Pause all routines
    resp = await command_service.process_command("pause all routines")
    assert resp.success is True
    assert scheduler.is_paused is True

    # 4. Resume routines
    resp = await command_service.process_command("resume scheduler")
    assert resp.success is True
    assert scheduler.is_paused is False
