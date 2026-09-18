"""Unit tests for Compound Routines & Preconfigured Workflows in Denver."""

import pytest
import pytest_asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from denver.commands.models import CommandCategory, CommandRequest, CommandRiskLevel
from denver.commands.router import IntentRouter
from denver.commands.service import CommandEngineService
from denver.memory.database import DenverDatabase
from denver.memory.memory_service import MemoryService
from denver.scheduler.compound_routines import (
    CompoundRoutineDefinition,
    CompoundRoutineLoader,
    get_compound_routine_loader,
)
from denver.scheduler.models import RoutineAction, RoutineStatus
from denver.scheduler.routine_registry import RoutineRegistry


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_routines.sqlite3"
    db = DenverDatabase(db_path=str(db_file))
    return db


@pytest_asyncio.fixture
async def initialized_db(temp_db):
    await temp_db.initialize()
    return temp_db


def test_compound_routine_loader_defaults():
    loader = CompoundRoutineLoader()
    routines = loader.list_routines()
    assert len(routines) >= 5
    ids = [r.routine_id for r in routines]
    assert "rtn_coding_mode" in ids
    assert "rtn_meeting_mode" in ids
    assert "rtn_morning_briefing" in ids
    assert "rtn_focus_mode" in ids
    assert "rtn_wrap_up_work" in ids


def test_compound_routine_phrase_matching():
    loader = CompoundRoutineLoader()
    coding = loader.get_by_id("rtn_coding_mode")
    assert coding is not None
    assert coding.matches_phrase("coding mode")
    assert coding.matches_phrase("start coding mode")
    assert coding.matches_phrase("dev mode")
    assert coding.matches_phrase("start dev mode")
    assert not coding.matches_phrase("play video games")


def test_compound_routine_to_routine_conversion():
    c_def = CompoundRoutineDefinition(
        routine_id="rtn_test",
        name="Test Routine",
        description="A test routine",
        triggers=["test mode"],
        actions=[
            RoutineAction(action_name="get_time", params={}, description="Check time")
        ],
        enabled=True,
    )
    routine = c_def.to_routine()
    assert routine.routine_id == "rtn_test"
    assert routine.name == "Test Routine"
    assert routine.status == RoutineStatus.ACTIVE
    assert len(routine.actions) == 1
    assert routine.actions[0].action_name == "get_time"
    assert routine.metadata.get("is_compound") is True


@pytest.mark.asyncio
async def test_routine_registry_seeding(initialized_db):
    registry = RoutineRegistry(db=initialized_db)
    seeded = await registry.seed_compound_routines()
    assert seeded >= 5

    # Second seed should be idempotent and return 0
    second_seeded = await registry.seed_compound_routines()
    assert second_seeded == 0

    all_routines = await registry.list_routines(enabled_only=False)
    names = [r.name for r in all_routines]
    assert "Coding Mode" in names
    assert "Meeting Mode" in names
    assert "Morning Briefing" in names


def test_intent_router_compound_triggers():
    router = IntentRouter()
    
    intent1 = router.route("start coding mode")
    assert intent1.action_name == "run_routine_now"
    assert intent1.category == CommandCategory.ROUTINE
    assert intent1.params.get("routine_id") == "coding mode"

    intent2 = router.route("morning briefing")
    assert intent2.action_name == "run_routine_now"
    assert intent2.params.get("routine_id") == "morning briefing"

    intent3 = router.route("focus mode")
    assert intent3.action_name == "run_routine_now"
    assert intent3.params.get("routine_id") == "focus mode"

    intent4 = router.route("wrap up work")
    assert intent4.action_name == "run_routine_now"
    assert intent4.params.get("routine_id") == "wrap up work"

    intent5 = router.route("trigger routine coding mode")
    assert intent5.action_name == "run_routine_now"
    assert intent5.params.get("routine_id") == "coding mode"


@pytest.mark.asyncio
async def test_command_service_runs_compound_routine(initialized_db):
    memory = MemoryService(db=initialized_db, privacy_mode=False)
    registry = RoutineRegistry(db=initialized_db)
    await registry.seed_compound_routines()

    service = CommandEngineService(
        memory_service=memory,
        routine_registry=registry,
    )

    req = CommandRequest(raw_text="start morning briefing")
    res = await service.process_command(req)
    assert res.success is True
    assert "Morning Briefing" in res.message
    assert res.action_name == "run_routine_now"
    assert res.data.get("actions") is not None
    assert len(res.data["actions"]) >= 4
