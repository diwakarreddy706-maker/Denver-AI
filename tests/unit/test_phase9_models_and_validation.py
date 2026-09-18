"""Unit tests for Phase 9 domain models, serialization, and PlanValidator DAG analysis."""

from __future__ import annotations

import pytest

from denver.commands.models import CommandCategory, CommandRiskLevel
from denver.commands.registry import ActionDefinition, ActionRegistry
from denver.commands.safety import SafetyValidator
from denver.tasks.errors import (
    ActionNotFoundError,
    CircularDependencyError,
    InvalidStepDependencyError,
    MaxDepthExceededError,
    MaxStepsExceededError,
    PlanValidationError,
)
from denver.tasks.models import (
    FailurePolicy,
    StepExecution,
    StepStatus,
    Task,
    TaskExecution,
    TaskOrigin,
    TaskPlan,
    TaskPriority,
    TaskProgress,
    TaskProposal,
    TaskResult,
    TaskStatus,
    TaskStep,
)
from denver.tasks.plan_validator import PlanValidator


def test_task_models_serialization():
    """Verify serialization and deserialization of Task, TaskStep, TaskPlan, and Telemetry models."""
    step = TaskStep(
        step_id="step_1",
        action_name="get_time",
        params={"format": "24h"},
        depends_on=[],
        timeout_seconds=30.0,
        requires_approval=False,
        description="Query time",
    )
    s_dict = step.to_dict()
    assert s_dict["step_id"] == "step_1"
    assert s_dict["action_name"] == "get_time"
    rebuilt_step = TaskStep.from_dict(s_dict)
    assert rebuilt_step.step_id == step.step_id
    assert rebuilt_step.params == step.params

    plan = TaskPlan(
        plan_id="plan_123",
        task_id="task_456",
        steps=[step],
        status="proposed",
        failure_policy=FailurePolicy.STOP_ON_FAILURE,
        max_retries=1,
        timeout_seconds=300.0,
        concurrency_limit=2,
    )
    p_dict = plan.to_dict()
    assert p_dict["plan_id"] == "plan_123"
    assert len(p_dict["steps"]) == 1
    rebuilt_plan = TaskPlan.from_dict(p_dict)
    assert rebuilt_plan.plan_id == plan.plan_id
    assert len(rebuilt_plan.steps) == 1
    assert rebuilt_plan.get_step("step_1") is not None

    task = Task(
        task_id="task_456",
        title="Morning Diagnostics",
        description="Run health and diagnostic checks",
        origin=TaskOrigin.USER_CHAT,
        priority=TaskPriority.HIGH,
        status=TaskStatus.READY,
        current_plan_id="plan_123",
    )
    t_dict = task.to_dict()
    rebuilt_task = Task.from_dict(t_dict)
    assert rebuilt_task.task_id == task.task_id
    assert rebuilt_task.title == task.title
    assert rebuilt_task.priority == TaskPriority.HIGH
    assert rebuilt_task.status == TaskStatus.READY

    step_exec = StepExecution(
        step_execution_id="sexec_1",
        execution_id="exec_1",
        step_id="step_1",
        status=StepStatus.COMPLETED,
        result_data={"output": "12:00"},
        duration_ms=45.2,
    )
    se_dict = step_exec.to_dict()
    rebuilt_se = StepExecution.from_dict(se_dict)
    assert rebuilt_se.step_execution_id == "sexec_1"
    assert rebuilt_se.status == StepStatus.COMPLETED

    task_exec = TaskExecution(
        execution_id="exec_1",
        task_id="task_456",
        plan_id="plan_123",
        status=TaskStatus.COMPLETED,
        step_executions=[step_exec],
    )
    te_dict = task_exec.to_dict()
    rebuilt_te = TaskExecution.from_dict(te_dict)
    assert rebuilt_te.execution_id == "exec_1"
    assert len(rebuilt_te.step_executions) == 1


def test_plan_validator_valid_dag():
    """Verify validation passes for valid linear, branched, and diamond DAG workflows."""
    registry = ActionRegistry()
    registry.register(ActionDefinition(name="get_time", description="", category=CommandCategory.UTILITY, risk_level=CommandRiskLevel.SAFE, handler=lambda p: "ok"))
    registry.register(ActionDefinition(name="get_date", description="", category=CommandCategory.UTILITY, risk_level=CommandRiskLevel.SAFE, handler=lambda p: "ok"))
    registry.register(ActionDefinition(name="get_system_status", description="", category=CommandCategory.SYSTEM, risk_level=CommandRiskLevel.SAFE, handler=lambda p: "ok"))

    validator = PlanValidator(action_registry=registry, safety_validator=SafetyValidator())

    # Diamond DAG: s1 -> (s2, s3) -> s4
    s1 = TaskStep(step_id="s1", action_name="get_time")
    s2 = TaskStep(step_id="s2", action_name="get_date", depends_on=["s1"])
    s3 = TaskStep(step_id="s3", action_name="get_system_status", depends_on=["s1"])
    s4 = TaskStep(step_id="s4", action_name="get_time", depends_on=["s2", "s3"])

    plan = TaskPlan(
        plan_id="p1",
        task_id="t1",
        steps=[s1, s2, s3, s4],
    )

    validator.validate(plan)  # Should succeed without exception


def test_plan_validator_detects_cycles():
    """Verify PlanValidator detects circular dependency cycles using Kahn's algorithm."""
    validator = PlanValidator()

    # Cycle: s1 -> s2 -> s3 -> s1
    s1 = TaskStep(step_id="s1", action_name="a1", depends_on=["s3"])
    s2 = TaskStep(step_id="s2", action_name="a2", depends_on=["s1"])
    s3 = TaskStep(step_id="s3", action_name="a3", depends_on=["s2"])

    plan = TaskPlan(plan_id="p_cycle", task_id="t1", steps=[s1, s2, s3])

    with pytest.raises(CircularDependencyError):
        validator.validate(plan)


def test_plan_validator_detects_self_reference():
    """Verify PlanValidator rejects self-referential steps."""
    validator = PlanValidator()
    s1 = TaskStep(step_id="s1", action_name="a1", depends_on=["s1"])
    plan = TaskPlan(plan_id="p_self", task_id="t1", steps=[s1])

    with pytest.raises(CircularDependencyError):
        validator.validate(plan)


def test_plan_validator_detects_missing_dependency():
    """Verify PlanValidator rejects non-existent step dependencies."""
    validator = PlanValidator()
    s1 = TaskStep(step_id="s1", action_name="a1", depends_on=["non_existent_step"])
    plan = TaskPlan(plan_id="p_miss", task_id="t1", steps=[s1])

    with pytest.raises(InvalidStepDependencyError):
        validator.validate(plan)


def test_plan_validator_detects_duplicate_step_id():
    """Verify PlanValidator rejects duplicate step IDs."""
    validator = PlanValidator()
    s1 = TaskStep(step_id="step_dup", action_name="a1")
    s2 = TaskStep(step_id="step_dup", action_name="a2")
    plan = TaskPlan(plan_id="p_dup", task_id="t1", steps=[s1, s2])

    with pytest.raises(PlanValidationError):
        validator.validate(plan)


def test_plan_validator_enforces_max_steps():
    """Verify PlanValidator rejects plans exceeding the step count limit (max 20)."""
    validator = PlanValidator(max_steps=5)
    steps = [TaskStep(step_id=f"s{i}", action_name="a") for i in range(6)]
    plan = TaskPlan(plan_id="p_max", task_id="t1", steps=steps)

    with pytest.raises(MaxStepsExceededError):
        validator.validate(plan)


def test_plan_validator_enforces_max_depth():
    """Verify PlanValidator calculates DAG depth and enforces max depth limit (max 10)."""
    validator = PlanValidator(max_depth=3)
    # Linear chain of length 4: s1 -> s2 -> s3 -> s4 (depth 4)
    s1 = TaskStep(step_id="s1", action_name="a")
    s2 = TaskStep(step_id="s2", action_name="a", depends_on=["s1"])
    s3 = TaskStep(step_id="s3", action_name="a", depends_on=["s2"])
    s4 = TaskStep(step_id="s4", action_name="a", depends_on=["s3"])
    plan = TaskPlan(plan_id="p_depth", task_id="t1", steps=[s1, s2, s3, s4])

    with pytest.raises(MaxDepthExceededError):
        validator.validate(plan)


def test_plan_validator_rejects_unregistered_action():
    """Verify PlanValidator verifies action existence against ActionRegistry."""
    registry = ActionRegistry()
    registry.register(ActionDefinition(name="registered_action", description="", category=CommandCategory.UTILITY, risk_level=CommandRiskLevel.SAFE, handler=lambda p: "ok"))
    validator = PlanValidator(action_registry=registry)

    s1 = TaskStep(step_id="s1", action_name="unregistered_action")
    plan = TaskPlan(plan_id="p_unreg", task_id="t1", steps=[s1])

    with pytest.raises(ActionNotFoundError):
        validator.validate(plan)


def test_plan_validator_rejects_dangerous_parameters():
    """Verify PlanValidator evaluates SafetyValidator on step parameters."""
    registry = ActionRegistry()
    registry.register(ActionDefinition(name="open_browser", description="", category=CommandCategory.APPLICATION, risk_level=CommandRiskLevel.LOW, handler=lambda p: "ok"))
    validator = PlanValidator(action_registry=registry, safety_validator=SafetyValidator(allow_destructive_actions=False))

    s1 = TaskStep(step_id="s1", action_name="open_browser", params={"target": "cmd.exe /c format c:"})
    plan = TaskPlan(plan_id="p_danger", task_id="t1", steps=[s1])

    with pytest.raises(PlanValidationError):
        validator.validate(plan)
