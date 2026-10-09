"""Unit tests for Pillar 4: Metacognitive Loop (Plan -> Act -> Verify -> Adapt)."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from denver.automation.models import WindowInfo
from denver.commands.models import ActionResult, CommandCategory, CommandRequest
from denver.commands.router import IntentRouter
from denver.commands.service import CommandEngineService
from denver.config.settings import DenverSettings
from denver.core.metacognition import (
    MetacognitiveExecutionResult,
    MetacognitiveLoop,
    MetacognitivePlan,
    MetacognitivePlanner,
    PlanStep,
    StateVerifier,
    VerificationResult,
)
from denver.core.self_model import DenverSelfModel
from denver.memory.database import DenverDatabase
from denver.memory.memory_service import MemoryService


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_metacog.sqlite3"
        db = DenverDatabase(db_path)
        db.initialize_sync()
        yield db
        db.close_sync()


def test_metacognitive_planner_decomposition():
    # 1. Compound: Open VS Code and write note
    plan1 = MetacognitivePlanner.create_plan("Open VS Code and write a summary note")
    assert plan1.goal == "Open VS Code and write a summary note"
    assert len(plan1.steps) == 2
    assert plan1.steps[0].action_name == "open_application"
    assert plan1.steps[0].params["application"] == "Code"
    assert plan1.steps[0].expected_state["type"] == "app_running"
    assert plan1.steps[0].fallback_action == "open_browser"
    assert plan1.steps[1].action_name == "create_note"

    # 2. Compound: Mute audio and lock laptop
    plan2 = MetacognitivePlanner.create_plan("mute audio and lock laptop")
    assert len(plan2.steps) == 2
    assert plan2.steps[0].action_name == "mute_volume"
    assert plan2.steps[1].action_name == "lock_workstation"

    # 3. Focus window
    plan3 = MetacognitivePlanner.create_plan("focus chrome")
    assert len(plan3.steps) == 1
    assert plan3.steps[0].action_name == "focus_window"
    assert plan3.steps[0].expected_state["type"] == "window_focused"

    # 4. Atomic fallback
    plan4 = MetacognitivePlanner.create_plan("what is the weather today")
    assert len(plan4.steps) == 1
    assert plan4.steps[0].action_name == "atomic_command"


@pytest.mark.asyncio
async def test_state_verifier_file_exists():
    with tempfile.TemporaryDirectory() as tmpdir:
        existing_file = Path(tmpdir) / "output.txt"
        existing_file.write_text("hello", encoding="utf-8")
        missing_file = Path(tmpdir) / "absent.txt"

        verifier = StateVerifier()

        # Existing file check
        step_pass = PlanStep(
            id=1,
            action_name="save_file",
            expected_state={"type": "file_exists", "path": str(existing_file)},
        )
        res_pass = await verifier.verify_step(step_pass)
        assert res_pass.verified is True
        assert res_pass.check_type == "file_exists"

        # Missing file check
        step_fail = PlanStep(
            id=2,
            action_name="save_file",
            expected_state={"type": "file_exists", "path": str(missing_file)},
        )
        res_fail = await verifier.verify_step(step_fail)
        assert res_fail.verified is False
        assert "does not exist on disk" in res_fail.error_message


@pytest.mark.asyncio
async def test_state_verifier_custom_predicate():
    verifier = StateVerifier()

    step_true = PlanStep(
        id=1,
        action_name="custom_check",
        expected_state={"type": "custom", "verifier_fn": lambda: True},
    )
    res_true = await verifier.verify_step(step_true)
    assert res_true.verified is True

    step_false = PlanStep(
        id=2,
        action_name="custom_check",
        expected_state={"type": "custom", "verifier_fn": lambda: False},
    )
    res_false = await verifier.verify_step(step_false)
    assert res_false.verified is False


@pytest.mark.asyncio
async def test_state_verifier_window_focused_with_mock():
    mock_api = MagicMock()
    mock_api.get_foreground_window.return_value = WindowInfo(
        handle=12345,
        title="main.py - Denver - Visual Studio Code",
        process_name="Code.exe",
        process_id=999,
        is_visible=True,
    )

    verifier = StateVerifier(native_api=mock_api)

    step_match = PlanStep(
        id=1,
        action_name="focus_window",
        expected_state={"type": "window_focused", "process": "code.exe"},
    )
    res_match = await verifier.verify_step(step_match)
    assert res_match.verified is True

    step_mismatch = PlanStep(
        id=2,
        action_name="focus_window",
        expected_state={"type": "window_focused", "process": "notepad.exe"},
    )
    res_mismatch = await verifier.verify_step(step_mismatch)
    assert res_mismatch.verified is False
    assert "notepad.exe" in res_mismatch.error_message


@pytest.mark.asyncio
async def test_metacognitive_loop_happy_path():
    executed_actions = []

    async def mock_executor(action_name: str, params: dict):
        executed_actions.append((action_name, params))
        return ActionResult(success=True, message=f"Executed {action_name}", action_name=action_name)

    verifier = StateVerifier()
    loop = MetacognitiveLoop(action_executor=mock_executor, state_verifier=verifier)

    plan = MetacognitivePlan(
        goal="Test plan",
        steps=[
            PlanStep(id=1, action_name="mute_volume", description="Step 1"),
            PlanStep(id=2, action_name="lock_workstation", description="Step 2"),
        ],
    )

    result = await loop.run(plan)
    assert result.success is True
    assert result.completed_steps == 2
    assert result.total_steps == 2
    assert len(executed_actions) == 2
    assert "successfully executed and verified" in result.final_message


@pytest.mark.asyncio
async def test_metacognitive_loop_adaptation_with_fallback():
    executed_actions = []

    async def mock_executor(action_name: str, params: dict):
        executed_actions.append(action_name)
        if action_name == "open_application":
            # Primary action fails
            return ActionResult(success=False, message="Executable not found", action_name=action_name, error="FileNotFound")
        if action_name == "open_browser":
            # Fallback action succeeds
            return ActionResult(success=True, message="Opened in browser", action_name=action_name)
        return ActionResult(success=True, message="OK", action_name=action_name)

    self_model = DenverSelfModel()
    loop = MetacognitiveLoop(action_executor=mock_executor, self_model=self_model)

    plan = MetacognitivePlan(
        goal="Open IDE with fallback",
        steps=[
            PlanStep(
                id=1,
                action_name="open_application",
                params={"application": "NonExistentApp"},
                description="Launch primary IDE",
                fallback_action="open_browser",
                fallback_params={"target": "https://github.com"},
            )
        ],
    )

    result = await loop.run(plan)
    assert result.success is True
    assert result.completed_steps == 1
    assert len(result.remediations_applied) == 1
    assert "adapted with fallback 'open_browser'" in result.remediations_applied[0]
    assert executed_actions == ["open_application", "open_browser"]


@pytest.mark.asyncio
async def test_metacognitive_loop_unrecoverable_failure_halts_honestly():
    async def mock_failing_executor(action_name: str, params: dict):
        return ActionResult(success=False, message="Permission denied", action_name=action_name, error="PermissionDenied")

    self_model = DenverSelfModel()
    loop = MetacognitiveLoop(action_executor=mock_failing_executor, self_model=self_model)

    plan = MetacognitivePlan(
        goal="Privileged task",
        steps=[
            PlanStep(
                id=1,
                action_name="modify_registry",
                params={},
                description="Elevated modify",
            ),
            PlanStep(
                id=2,
                action_name="subsequent_step",
                params={},
                description="Should never run",
            ),
        ],
    )

    result = await loop.run(plan)
    assert result.success is False
    assert result.completed_steps == 0
    assert result.failure_diagnosis is not None
    assert "Permission was denied" in result.failure_diagnosis
    assert "halted at step 1" in result.final_message


def test_command_router_metacognitive_intents():
    router = IntentRouter()

    # 1. Explain plan
    res1 = router.route("explain plan for open vs code and write note")
    assert res1.action_name == "explain_plan"
    assert res1.category == CommandCategory.UTILITY
    assert "open vs code and write note" in res1.params["instruction"]

    res2 = router.route("plan for mute audio and lock laptop")
    assert res2.action_name == "explain_plan"

    # 2. Metacognitive execute
    res3 = router.route("metacognitive execute open vs code and write note")
    assert res3.action_name == "metacognitive_execute"
    assert res3.category == CommandCategory.TASK

    res4 = router.route("verified execute mute audio and lock laptop")
    assert res4.action_name == "metacognitive_execute"


@pytest.mark.asyncio
async def test_command_service_metacognitive_execution(temp_db):
    settings = DenverSettings(ai_enabled=False)
    mem_service = MemoryService(temp_db)
    service = CommandEngineService(memory_service=mem_service, settings=settings)

    # 1. Explain plan
    r1 = await service.process_command("explain plan for mute audio and lock laptop")
    assert r1.success is True
    assert "Metacognitive Pre-Flight Plan" in r1.message
    assert "mute_volume" in r1.message

    # 2. Verified execute
    r2 = await service.process_command("verified execute mute audio and lock laptop")
    assert r2.success is True
    assert "successfully executed" in r2.message.lower()
