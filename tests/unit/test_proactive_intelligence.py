"""Unit tests for Denver Autonomous Proactive Intelligence Subsystem."""

import time
import pytest
from pathlib import Path

from denver.commands.router import IntentRouter
from denver.commands.service import CommandEngineService
from denver.memory.database import DenverDatabase
from denver.memory.memory_service import MemoryService
from denver.proactive.engine import ProactiveIntelligenceEngine
from denver.proactive.models import (
    ProactiveContext,
    ProactiveSuggestion,
    SuggestionCategory,
    SuggestionPriority,
)
from denver.proactive.rules import (
    BatteryHealthRule,
    FocusFatigueRule,
    PendingTaskReminderRule,
    RoutineOpportunityRule,
    SystemResourceRule,
)


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_proactive.sqlite3"
    return DenverDatabase(db_path=str(db_file))


@pytest.fixture
def memory_service(temp_db):
    return MemoryService(db=temp_db, privacy_mode=False)


def test_battery_health_rule():
    """Verify battery rule triggers warnings and critical alerts properly."""
    rule = BatteryHealthRule()

    # Normal battery / plugged in -> No suggestions
    ctx_normal = ProactiveContext(battery_percent=85.0, battery_power_plugged=False)
    assert len(rule.evaluate(ctx_normal)) == 0

    ctx_plugged = ProactiveContext(battery_percent=12.0, battery_power_plugged=True)
    assert len(rule.evaluate(ctx_plugged)) == 0

    # Warning threshold (20% unplugged)
    ctx_warn = ProactiveContext(battery_percent=20.0, battery_power_plugged=False)
    sug_warn = rule.evaluate(ctx_warn)
    assert len(sug_warn) == 1
    assert sug_warn[0].priority == SuggestionPriority.HIGH
    assert sug_warn[0].category == SuggestionCategory.HEALTH
    assert "20%" in sug_warn[0].message

    # Critical threshold (10% unplugged)
    ctx_crit = ProactiveContext(battery_percent=10.0, battery_power_plugged=False)
    sug_crit = rule.evaluate(ctx_crit)
    assert len(sug_crit) == 1
    assert sug_crit[0].priority == SuggestionPriority.CRITICAL
    assert "Critically Low" in sug_crit[0].title


def test_focus_fatigue_rule():
    """Verify focus fatigue rule suggests breaks after continuous activity."""
    rule = FocusFatigueRule(break_threshold_seconds=3600.0)

    # 30 mins work -> no suggestion
    assert len(rule.evaluate(ProactiveContext(continuous_work_seconds=1800.0))) == 0

    # 75 mins work -> break suggestion
    sugs = rule.evaluate(ProactiveContext(continuous_work_seconds=4500.0))
    assert len(sugs) == 1
    assert sugs[0].category == SuggestionCategory.FATIGUE
    assert "75 minutes" in sugs[0].message


def test_routine_opportunity_rule():
    """Verify routine rule suggests Coding Mode and Wrap Up Work."""
    rule = RoutineOpportunityRule()

    # Active VS Code process
    ctx_code = ProactiveContext(active_window_process="Code.exe", active_window_title="main.py - Denver")
    sugs = rule.evaluate(ctx_code)
    assert len(sugs) == 1
    assert sugs[0].category == SuggestionCategory.ROUTINE
    assert sugs[0].suggested_params.get("routine_id") == "rtn_coding_mode"

    # End of day (7 PM / 19:00) with substantial continuous work
    ctx_wrap = ProactiveContext(current_hour=19, continuous_work_seconds=3600.0)
    sugs_wrap = rule.evaluate(ctx_wrap)
    assert len(sugs_wrap) >= 1
    assert any(s.suggested_params.get("routine_id") == "rtn_wrap_up_work" for s in sugs_wrap)


def test_pending_task_and_resource_rules():
    """Verify pending task reminder and high memory usage rules."""
    task_rule = PendingTaskReminderRule()
    ctx_task = ProactiveContext(pending_tasks_count=2, pending_tasks_summary=["Fix auth bug", "Deploy API"])
    sugs_task = task_rule.evaluate(ctx_task)
    assert len(sugs_task) == 1
    assert sugs_task[0].category == SuggestionCategory.TASK
    assert "Fix auth bug" in sugs_task[0].message

    sys_rule = SystemResourceRule()
    ctx_mem = ProactiveContext(memory_percent=94.0)
    sugs_mem = sys_rule.evaluate(ctx_mem)
    assert len(sugs_mem) == 1
    assert sugs_mem[0].category == SuggestionCategory.SYSTEM
    assert "94%" in sugs_mem[0].message


def test_proactive_engine_cooldown_and_lifecycle():
    """Verify rate-limiting cooldown, listener callbacks, and dismissal."""
    engine = ProactiveIntelligenceEngine()
    engine.set_category_cooldown(SuggestionCategory.HEALTH, 60.0)

    received_events = []
    engine.register_listener(lambda s: received_events.append(s))

    ctx = ProactiveContext(battery_percent=12.0, battery_power_plugged=False)

    # First evaluation emits suggestion
    sugs1 = engine.evaluate(ctx)
    assert len(sugs1) == 1
    assert len(received_events) == 1
    assert len(engine.get_active_suggestions()) == 1

    # Immediate second evaluation throttled by cooldown (0 new suggestions)
    sugs2 = engine.evaluate(ctx)
    assert len(sugs2) == 0
    assert len(received_events) == 1

    # Dismiss active suggestions
    count = engine.dismiss_suggestion()
    assert count == 1
    assert len(engine.get_active_suggestions()) == 0

    # Toggle enabled off
    engine.set_enabled(False)
    assert not engine.is_enabled
    assert len(engine.evaluate(ctx)) == 0


def test_proactive_router_intents():
    """Verify IntentRouter matches proactive intelligence trigger phrases."""
    router = IntentRouter()

    # Get suggestions
    i1 = router.route("any suggestions")
    assert i1.action_name == "get_proactive_suggestions"

    i2 = router.route("what are your suggestions")
    assert i2.action_name == "get_proactive_suggestions"

    i3 = router.route("proactive briefing")
    assert i3.action_name == "get_proactive_suggestions"

    # Enable mode
    i4 = router.route("enable proactive mode")
    assert i4.action_name == "set_proactive_mode"
    assert i4.params.get("enabled") is True

    # Disable mode
    i5 = router.route("disable proactive mode")
    assert i5.action_name == "set_proactive_mode"
    assert i5.params.get("enabled") is False

    # Dismiss
    i6 = router.route("dismiss suggestions")
    assert i6.action_name == "dismiss_proactive_suggestions"


@pytest.mark.asyncio
async def test_proactive_command_service_end_to_end(memory_service):
    """Verify end-to-end command flow for proactive recommendations."""
    service = CommandEngineService(memory_service=memory_service)

    # Create a pending task in memory
    await memory_service.create_task("Finish building autonomous agent feature")

    # Query proactive suggestions
    res = await service.process_command("any suggestions")
    assert res.success is True
    assert "proactive suggestions" in res.message.lower()
    assert len(res.data.get("suggestions", [])) >= 1

    # Disable proactive mode
    res_disable = await service.process_command("disable proactive mode")
    assert res_disable.success is True
    assert "disabled" in res_disable.message.lower()
    assert not service.proactive_engine.is_enabled

    # Re-enable proactive mode
    res_enable = await service.process_command("enable proactive mode")
    assert res_enable.success is True
    assert "enabled" in res_enable.message.lower()
    assert service.proactive_engine.is_enabled

    # Dismiss suggestions
    res_dismiss = await service.process_command("dismiss suggestions")
    assert res_dismiss.success is True
    assert "dismissed" in res_dismiss.message.lower()
