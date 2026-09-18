"""Unit tests for Phase 9 SQLite Persistence, Task Planner, Task Registry, Command Routing, and Health diagnostics."""

from __future__ import annotations

import sqlite3
import pytest

from denver.commands.registry import ActionRegistry
from denver.commands.safety import SafetyValidator
from denver.commands.service import CommandEngineService
from denver.health.health_service import DenverHealthService
from denver.memory.database import DenverDatabase
from denver.memory.memory_service import MemoryService
from denver.memory.migrations import MigrationManager
from denver.tasks.approval import TaskApprovalManager
from denver.tasks.audit import TaskAuditLogger
from denver.tasks.fake import FakeAutomationExecutor, create_test_action_registry
from denver.tasks.models import FailurePolicy, Task, TaskOrigin, TaskPlan, TaskPriority, TaskStatus, TaskStep
from denver.tasks.persistence import TaskPersistence
from denver.tasks.plan_validator import PlanValidator
from denver.tasks.planner import TaskPlanner
from denver.tasks.task_registry import TaskRegistry
from denver.tasks.workflow_engine import WorkflowEngine


@pytest.fixture
def sqlite_db(tmp_path):
    """Create a temporary SQLite database with all migrations applied up to v4."""
    db_file = tmp_path / "test_denver_phase9.sqlite3"
    conn = sqlite3.connect(str(db_file))
    mgr = MigrationManager(conn)
    mgr.apply_pending_migrations()
    assert mgr.get_current_version() >= 4
    yield conn
    conn.close()


def test_sqlite_migration_v4_applied(sqlite_db):
    """Verify Migration v4 created all required Phase 9 tables and indexes."""
    cursor = sqlite_db.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {row[0] for row in cursor.fetchall()}
    assert "orchestrated_tasks" in tables
    assert "task_plans" in tables
    assert "task_steps" in tables
    assert "task_executions" in tables
    assert "step_executions" in tables
    assert "task_audit" in tables


def test_task_persistence_crud(sqlite_db):
    """Verify TaskPersistence correctly performs CRUD operations for tasks and plans."""
    persistence = TaskPersistence(connection_factory=lambda: sqlite_db)

    # 1. Create task
    task = Task(
        task_id="t_pers_1",
        title="Persisted Task",
        description="Testing DB write",
        origin=TaskOrigin.USER_CHAT,
        priority=TaskPriority.HIGH,
        status=TaskStatus.DRAFT,
    )
    saved = persistence.create_task(task)
    assert saved.task_id == "t_pers_1"

    # 2. Get task
    fetched = persistence.get_task("t_pers_1")
    assert fetched is not None
    assert fetched.title == "Persisted Task"
    assert fetched.priority == TaskPriority.HIGH

    # 3. List tasks
    all_tasks = persistence.list_tasks()
    assert len(all_tasks) == 1

    # 4. Save & get plan
    step1 = TaskStep(step_id="s1", action_name="get_time")
    step2 = TaskStep(step_id="s2", action_name="get_date", depends_on=["s1"])
    plan = TaskPlan(
        plan_id="p_pers_1",
        task_id="t_pers_1",
        steps=[step1, step2],
        failure_policy=FailurePolicy.STOP_ON_FAILURE,
    )
    persistence.save_plan(plan)
    fetched_plan = persistence.get_plan("p_pers_1")
    assert fetched_plan is not None
    assert len(fetched_plan.steps) == 2
    assert fetched_plan.steps[1].depends_on == ["s1"]

    # 5. Update task status
    persistence.update_task_status("t_pers_1", TaskStatus.RUNNING, current_plan_id="p_pers_1")
    updated_task = persistence.get_task("t_pers_1")
    assert updated_task.status == TaskStatus.RUNNING
    assert updated_task.current_plan_id == "p_pers_1"

    # 6. Delete task
    assert persistence.delete_task("t_pers_1")
    assert persistence.get_task("t_pers_1") is None


def test_task_planner_parsing():
    """Verify TaskPlanner creates plans from action lists and untrusted AI JSON responses."""
    registry = create_test_action_registry()
    validator = PlanValidator(action_registry=registry, safety_validator=SafetyValidator())
    planner = TaskPlanner(validator=validator)

    # 1. From action list
    actions = [
        {"step_id": "step_1", "action_name": "get_time"},
        {"step_id": "step_2", "action_name": "get_system_status", "depends_on": ["step_1"]},
    ]
    plan = planner.plan_from_action_list("t_plan_1", actions)
    assert len(plan.steps) == 2
    assert plan.steps[0].action_name == "get_time"

    # 2. From AI JSON response
    ai_json = """
    ```json
    {
        "title": "System Diagnostic Routine",
        "description": "Checks system telemetry and time",
        "failure_policy": "stop_on_failure",
        "steps": [
            {"step_id": "s1", "action_name": "get_time"},
            {"step_id": "s2", "action_name": "get_date", "depends_on": ["s1"]}
        ]
    }
    ```
    """
    ai_plan = planner.parse_ai_response("t_ai_1", ai_json)
    assert len(ai_plan.steps) == 2
    assert ai_plan.steps[1].step_id == "s2"


@pytest.mark.asyncio
async def test_task_registry_and_command_service_integration(sqlite_db, tmp_path):
    """Verify full end-to-end task workflow integration with CommandEngineService."""
    persistence = TaskPersistence(connection_factory=lambda: sqlite_db)
    registry = create_test_action_registry()
    safety = SafetyValidator(allow_destructive_actions=False)
    executor = FakeAutomationExecutor(registry, safety)
    approval_mgr = TaskApprovalManager()
    audit_logger = TaskAuditLogger(connection_factory=lambda: sqlite_db)
    validator = PlanValidator(action_registry=registry, safety_validator=safety)
    planner = TaskPlanner(validator=validator)

    engine = WorkflowEngine(
        action_registry=registry,
        safety_validator=safety,
        automation_executor=executor,
        persistence=persistence,
        approval_manager=approval_mgr,
        audit_logger=audit_logger,
        max_concurrency=2,
    )

    task_reg = TaskRegistry(
        engine=engine,
        persistence=persistence,
        planner=planner,
        validator=validator,
        approval_manager=approval_mgr,
        audit_logger=audit_logger,
        enabled=True,
    )

    db_obj = DenverDatabase(db_path=str(tmp_path / "test_denver_cmd.sqlite3"))
    mem_service = MemoryService(db=db_obj)

    cmd_service = CommandEngineService(
        memory_service=mem_service,
        task_registry=task_reg,
        workflow_engine=engine,
    )

    # 1. Create and plan task via command
    task = task_reg.create_task(title="E2E Workflow Test")
    actions = [
        {"step_id": "s1", "action_name": "get_time"},
        {"step_id": "s2", "action_name": "get_system_status", "depends_on": ["s1"]},
    ]
    plan = task_reg.plan_task(task.task_id, actions)

    # 2. Test show_task_status command
    res_status = await cmd_service.process_command(f"task status {task.task_id}")
    assert res_status.success
    assert task.task_id in res_status.message

    # 3. Test run_task command
    res_run = await cmd_service.process_command(f"run task {task.task_id}")
    assert res_run.success
    assert "completed" in res_run.message.lower()

    # 4. Test show_task_history command
    res_hist = await cmd_service.process_command(f"task history {task.task_id}")
    assert res_hist.success
    assert "execution" in res_hist.message.lower()

    # 5. Test pause_all and resume_all commands
    res_p_all = await cmd_service.process_command("pause all tasks")
    assert res_p_all.success
    assert task_reg.is_global_paused is True

    res_r_all = await cmd_service.process_command("resume all tasks")
    assert res_r_all.success
    assert task_reg.is_global_paused is False

    # 6. Test disable and enable commands
    res_dis = await cmd_service.process_command("disable tasks")
    assert res_dis.success
    assert task_reg.enabled is False

    res_en = await cmd_service.process_command("enable tasks")
    assert res_en.success
    assert task_reg.enabled is True

    # 7. Test delete_task command
    res_del = await cmd_service.process_command(f"delete task {task.task_id}")
    assert res_del.success


def test_health_service_task_orchestration_status(sqlite_db):
    """Verify DenverHealthService reports real-time task orchestration readiness."""
    persistence = TaskPersistence(connection_factory=lambda: sqlite_db)
    registry = create_test_action_registry()
    safety = SafetyValidator()
    executor = FakeAutomationExecutor(registry, safety)
    engine = WorkflowEngine(action_registry=registry, safety_validator=safety, automation_executor=executor)
    task_reg = TaskRegistry(engine=engine, persistence=persistence, enabled=True)

    health = DenverHealthService(task_registry=task_reg)
    subsystems = health.get_subsystems_status()
    assert subsystems.get("task_orchestration") == "READY"

    task_reg.pause_all_tasks()
    assert health.get_subsystems_status().get("task_orchestration") == "PAUSED"

    task_reg.disable()
    assert health.get_subsystems_status().get("task_orchestration") == "DISABLED"
