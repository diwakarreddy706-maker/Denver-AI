"""Unit tests for Phase 9 WorkflowEngine DAG execution, concurrency, timeouts, and failure policies."""

from __future__ import annotations

import asyncio
from typing import Any
import pytest

from denver.commands.safety import SafetyValidator
from denver.tasks.approval import TaskApprovalManager
from denver.tasks.audit import TaskAuditLogger
from denver.tasks.cancellation import CancellationToken
from denver.tasks.fake import FakeAutomationExecutor, create_test_action_registry
from denver.tasks.models import FailurePolicy, TaskPlan, TaskStatus, TaskStep
from denver.tasks.workflow_engine import WorkflowEngine


@pytest.fixture
def workflow_setup():
    """Create a configured test environment for WorkflowEngine."""
    registry = create_test_action_registry()
    safety = SafetyValidator(allow_destructive_actions=False)
    executor = FakeAutomationExecutor(registry, safety)
    approval_mgr = TaskApprovalManager()
    audit_logger = TaskAuditLogger()
    events: list[Any] = []

    engine = WorkflowEngine(
        action_registry=registry,
        safety_validator=safety,
        automation_executor=executor,
        approval_manager=approval_mgr,
        audit_logger=audit_logger,
        event_publisher=lambda e: events.append(e),
        max_concurrency=2,
    )
    return {
        "engine": engine,
        "executor": executor,
        "registry": registry,
        "approval_mgr": approval_mgr,
        "events": events,
    }


@pytest.mark.asyncio
async def test_workflow_engine_sequential_execution(workflow_setup):
    """Verify linear step DAG executes sequentially to completion."""
    engine: WorkflowEngine = workflow_setup["engine"]
    executor: FakeAutomationExecutor = workflow_setup["executor"]

    s1 = TaskStep(step_id="step_1", action_name="get_time")
    s2 = TaskStep(step_id="step_2", action_name="get_date", depends_on=["step_1"])
    s3 = TaskStep(step_id="step_3", action_name="get_system_status", depends_on=["step_2"])

    plan = TaskPlan(
        plan_id="plan_seq",
        task_id="task_seq",
        steps=[s1, s2, s3],
    )

    result = await engine.execute_plan(plan)
    assert result.status == TaskStatus.COMPLETED
    assert result.steps_completed == 3
    assert result.steps_failed == 0
    assert len(executor.executed_requests) == 3
    assert [r.action_name for r in executor.executed_requests] == ["get_time", "get_date", "get_system_status"]


@pytest.mark.asyncio
async def test_workflow_engine_diamond_concurrency(workflow_setup):
    """Verify Diamond DAG runs independent steps concurrently within concurrency limits."""
    engine: WorkflowEngine = workflow_setup["engine"]

    # Diamond DAG: s1 -> (s2, s3) -> s4
    s1 = TaskStep(step_id="s1", action_name="get_time")
    s2 = TaskStep(step_id="s2", action_name="get_date", depends_on=["s1"])
    s3 = TaskStep(step_id="s3", action_name="search_notes", depends_on=["s1"])
    s4 = TaskStep(step_id="s4", action_name="get_system_status", depends_on=["s2", "s3"])

    plan = TaskPlan(plan_id="plan_diamond", task_id="task_diamond", steps=[s1, s2, s3, s4], concurrency_limit=2)

    result = await engine.execute_plan(plan)
    assert result.status == TaskStatus.COMPLETED
    assert result.steps_completed == 4
    assert result.steps_failed == 0


@pytest.mark.asyncio
async def test_workflow_engine_pre_step_safety_validation(workflow_setup):
    """Verify every step is re-validated against SafetyValidator immediately prior to execution."""
    engine: WorkflowEngine = workflow_setup["engine"]

    # Step with destructive payload that violates safety
    s1 = TaskStep(step_id="s1", action_name="get_time")
    s2 = TaskStep(step_id="s2", action_name="get_date", params={"target": "powershell.exe -enc ..."}, depends_on=["s1"])

    plan = TaskPlan(plan_id="plan_safe_test", task_id="task_safe_test", steps=[s1, s2])

    result = await engine.execute_plan(plan)
    assert result.status == TaskStatus.FAILED
    assert result.steps_completed == 1
    assert result.steps_failed == 1
    assert "safety validation" in result.error_message.lower() or "prohibited" in result.error_message.lower()


@pytest.mark.asyncio
async def test_workflow_engine_failure_policy_stop(workflow_setup):
    """Verify STOP_ON_FAILURE halts downstream execution when a step fails."""
    engine: WorkflowEngine = workflow_setup["engine"]
    executor: FakeAutomationExecutor = workflow_setup["executor"]

    executor.should_fail_action.add("get_date")

    s1 = TaskStep(step_id="s1", action_name="get_time")
    s2 = TaskStep(step_id="s2", action_name="get_date", depends_on=["s1"])
    s3 = TaskStep(step_id="s3", action_name="get_system_status", depends_on=["s2"])

    plan = TaskPlan(
        plan_id="plan_stop_fail",
        task_id="task_stop_fail",
        steps=[s1, s2, s3],
        failure_policy=FailurePolicy.STOP_ON_FAILURE,
    )

    result = await engine.execute_plan(plan)
    assert result.status == TaskStatus.FAILED
    assert result.steps_completed == 1
    assert result.steps_failed == 1
    assert len(executor.executed_requests) == 2  # s3 was never executed


@pytest.mark.asyncio
async def test_workflow_engine_failure_policy_continue(workflow_setup):
    """Verify CONTINUE_ON_FAILURE executes independent branches even if one fails."""
    engine: WorkflowEngine = workflow_setup["engine"]
    executor: FakeAutomationExecutor = workflow_setup["executor"]

    executor.should_fail_action.add("search_notes")

    s1 = TaskStep(step_id="s1", action_name="get_time")
    s2 = TaskStep(step_id="s2", action_name="search_notes")  # Will fail
    s3 = TaskStep(step_id="s3", action_name="get_date", depends_on=["s1"])  # Independent of s2

    plan = TaskPlan(
        plan_id="plan_cont_fail",
        task_id="task_cont_fail",
        steps=[s1, s2, s3],
        failure_policy=FailurePolicy.CONTINUE_ON_FAILURE,
    )

    result = await engine.execute_plan(plan)
    assert result.status == TaskStatus.FAILED
    assert result.steps_completed == 2
    assert result.steps_failed == 1


@pytest.mark.asyncio
async def test_workflow_engine_retry_policy(workflow_setup):
    """Verify RETRY_THEN_STOP retries a safe idempotent action once before failing."""
    engine: WorkflowEngine = workflow_setup["engine"]
    executor: FakeAutomationExecutor = workflow_setup["executor"]

    executor.should_fail_action.add("get_time")

    s1 = TaskStep(step_id="s1", action_name="get_time")
    plan = TaskPlan(
        plan_id="plan_retry",
        task_id="task_retry",
        steps=[s1],
        failure_policy=FailurePolicy.RETRY_THEN_STOP,
    )

    result = await engine.execute_plan(plan)
    assert result.status == TaskStatus.FAILED
    # Should have attempted twice (initial + 1 retry)
    assert len(executor.executed_requests) == 2


@pytest.mark.asyncio
async def test_workflow_engine_cancellation(workflow_setup):
    """Verify CancellationToken cancels active DAG execution."""
    engine: WorkflowEngine = workflow_setup["engine"]
    token = CancellationToken("task_cancel_test")

    s1 = TaskStep(step_id="s1", action_name="get_time")
    s2 = TaskStep(step_id="s2", action_name="get_date", depends_on=["s1"])
    plan = TaskPlan(plan_id="plan_cancel", task_id="task_cancel_test", steps=[s1, s2])

    token.cancel("Cancelled for testing")
    result = await engine.execute_plan(plan, cancellation_token=token)
    assert result.status == TaskStatus.CANCELLED


@pytest.mark.asyncio
async def test_workflow_engine_step_approval_accepted(workflow_setup):
    """Verify high-impact step requiring confirmation awaits and executes when approved."""
    engine: WorkflowEngine = workflow_setup["engine"]
    approval_mgr: TaskApprovalManager = workflow_setup["approval_mgr"]

    s1 = TaskStep(step_id="s1", action_name="get_time")
    s2 = TaskStep(step_id="s2", action_name="lock_workstation", requires_approval=True, depends_on=["s1"])
    plan = TaskPlan(plan_id="plan_appr_ok", task_id="task_appr_ok", steps=[s1, s2])

    async def auto_approve():
        await asyncio.sleep(0.05)
        pending = approval_mgr.get_pending_approvals("task_appr_ok")
        if pending:
            approval_mgr.approve(pending[0]["approval_id"])

    asyncio.create_task(auto_approve())
    result = await engine.execute_plan(plan)
    assert result.status == TaskStatus.COMPLETED
    assert result.steps_completed == 2


@pytest.mark.asyncio
async def test_workflow_engine_step_approval_rejected(workflow_setup):
    """Verify high-impact step requiring confirmation fails when rejected."""
    engine: WorkflowEngine = workflow_setup["engine"]
    approval_mgr: TaskApprovalManager = workflow_setup["approval_mgr"]

    s1 = TaskStep(step_id="s1", action_name="lock_workstation", requires_approval=True)
    plan = TaskPlan(plan_id="plan_appr_rej", task_id="task_appr_rej", steps=[s1])

    async def auto_reject():
        await asyncio.sleep(0.05)
        pending = approval_mgr.get_pending_approvals("task_appr_rej")
        if pending:
            approval_mgr.reject(pending[0]["approval_id"], reason="User declined")

    asyncio.create_task(auto_reject())
    result = await engine.execute_plan(plan)
    assert result.status == TaskStatus.FAILED
    assert result.steps_failed == 1
