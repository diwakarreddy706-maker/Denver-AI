"""SQLite persistence repositories for Denver tasks, plans, and executions."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from denver.logging.logger import get_logger
from denver.tasks.models import (
    FailurePolicy,
    StepExecution,
    StepStatus,
    Task,
    TaskExecution,
    TaskOrigin,
    TaskPlan,
    TaskPriority,
    TaskStatus,
    TaskStep,
)

logger = get_logger("tasks.persistence")


class TaskPersistence:
    """Consolidated SQLite repository for tasks, plans, and execution telemetry."""

    def __init__(self, connection_factory: Any) -> None:
        self.connection_factory = connection_factory

    def _get_conn(self) -> sqlite3.Connection:
        if callable(self.connection_factory):
            return self.connection_factory()
        return self.connection_factory

    # ---------------------------------------------------------
    # Task CRUD
    # ---------------------------------------------------------

    def create_task(self, task: Task) -> Task:
        conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO orchestrated_tasks (task_id, title, description, origin, priority, status, current_plan_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                task.task_id,
                task.title,
                task.description,
                task.origin.value if isinstance(task.origin, TaskOrigin) else str(task.origin),
                task.priority.value if isinstance(task.priority, TaskPriority) else str(task.priority),
                task.status.value if isinstance(task.status, TaskStatus) else str(task.status),
                task.current_plan_id,
                task.created_at.isoformat() if isinstance(task.created_at, datetime) else str(task.created_at),
                task.updated_at.isoformat() if isinstance(task.updated_at, datetime) else str(task.updated_at),
            ),
        )
        conn.commit()
        return task

    def get_task(self, task_id: str) -> Task | None:
        conn = self._get_conn()
        cursor = conn.execute(
            """
            SELECT task_id, title, description, origin, priority, status, current_plan_id, created_at, updated_at
            FROM orchestrated_tasks
            WHERE task_id = ?;
            """,
            (task_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return Task(
            task_id=row[0],
            title=row[1],
            description=row[2] or "",
            origin=TaskOrigin(row[3]) if row[3] in TaskOrigin.__members__.values() else TaskOrigin.USER_CHAT,
            priority=TaskPriority(row[4]) if row[4] in TaskPriority.__members__.values() else TaskPriority.MEDIUM,
            status=TaskStatus(row[5]) if row[5] in TaskStatus.__members__.values() else TaskStatus.DRAFT,
            current_plan_id=row[6],
            created_at=datetime.fromisoformat(row[7]) if row[7] else datetime.now(timezone.utc),
            updated_at=datetime.fromisoformat(row[8]) if row[8] else datetime.now(timezone.utc),
        )

    def list_tasks(self, status: TaskStatus | None = None, limit: int = 50) -> list[Task]:
        conn = self._get_conn()
        if status:
            cursor = conn.execute(
                """
                SELECT task_id, title, description, origin, priority, status, current_plan_id, created_at, updated_at
                FROM orchestrated_tasks
                WHERE status = ?
                ORDER BY created_at DESC
                LIMIT ?;
                """,
                (status.value if isinstance(status, TaskStatus) else str(status), limit),
            )
        else:
            cursor = conn.execute(
                """
                SELECT task_id, title, description, origin, priority, status, current_plan_id, created_at, updated_at
                FROM orchestrated_tasks
                ORDER BY created_at DESC
                LIMIT ?;
                """,
                (limit,),
            )
        rows = cursor.fetchall()
        tasks = []
        for row in rows:
            tasks.append(
                Task(
                    task_id=row[0],
                    title=row[1],
                    description=row[2] or "",
                    origin=TaskOrigin(row[3]) if row[3] in [e.value for e in TaskOrigin] else TaskOrigin.USER_CHAT,
                    priority=TaskPriority(row[4]) if row[4] in [e.value for e in TaskPriority] else TaskPriority.MEDIUM,
                    status=TaskStatus(row[5]) if row[5] in [e.value for e in TaskStatus] else TaskStatus.DRAFT,
                    current_plan_id=row[6],
                    created_at=datetime.fromisoformat(row[7]) if row[7] else datetime.now(timezone.utc),
                    updated_at=datetime.fromisoformat(row[8]) if row[8] else datetime.now(timezone.utc),
                )
            )
        return tasks

    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        current_plan_id: str | None = None,
    ) -> bool:
        conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat()
        if current_plan_id is not None:
            cursor = conn.execute(
                """
                UPDATE orchestrated_tasks
                SET status = ?, current_plan_id = ?, updated_at = ?
                WHERE task_id = ?;
                """,
                (status.value if isinstance(status, TaskStatus) else str(status), current_plan_id, now, task_id),
            )
        else:
            cursor = conn.execute(
                """
                UPDATE orchestrated_tasks
                SET status = ?, updated_at = ?
                WHERE task_id = ?;
                """,
                (status.value if isinstance(status, TaskStatus) else str(status), now, task_id),
            )
        conn.commit()
        return cursor.rowcount > 0

    def delete_task(self, task_id: str) -> bool:
        conn = self._get_conn()
        cursor = conn.execute("DELETE FROM orchestrated_tasks WHERE task_id = ?;", (task_id,))
        conn.commit()
        return cursor.rowcount > 0

    # ---------------------------------------------------------
    # Task Plan CRUD
    # ---------------------------------------------------------

    def save_plan(self, plan: TaskPlan) -> TaskPlan:
        conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT OR REPLACE INTO task_plans (plan_id, task_id, status, failure_policy, max_retries, timeout_seconds, concurrency_limit, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                plan.plan_id,
                plan.task_id,
                plan.status,
                plan.failure_policy.value if isinstance(plan.failure_policy, FailurePolicy) else str(plan.failure_policy),
                plan.max_retries,
                plan.timeout_seconds,
                plan.concurrency_limit,
                plan.created_at.isoformat() if isinstance(plan.created_at, datetime) else str(plan.created_at),
                now,
            ),
        )

        # Remove existing steps if any and re-insert
        conn.execute("DELETE FROM task_steps WHERE plan_id = ?;", (plan.plan_id,))
        for step in plan.steps:
            conn.execute(
                """
                INSERT INTO task_steps (step_id, plan_id, action_name, params, depends_on, timeout_seconds, requires_approval, description, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    step.step_id,
                    plan.plan_id,
                    step.action_name,
                    json.dumps(step.params),
                    json.dumps(step.depends_on),
                    step.timeout_seconds,
                    1 if step.requires_approval else 0,
                    step.description,
                    now,
                ),
            )

        conn.commit()
        return plan

    def get_plan(self, plan_id: str) -> TaskPlan | None:
        conn = self._get_conn()
        cursor = conn.execute(
            """
            SELECT plan_id, task_id, status, failure_policy, max_retries, timeout_seconds, concurrency_limit, created_at, updated_at
            FROM task_plans
            WHERE plan_id = ?;
            """,
            (plan_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        step_cursor = conn.execute(
            """
            SELECT step_id, action_name, params, depends_on, timeout_seconds, requires_approval, description
            FROM task_steps
            WHERE plan_id = ?
            ORDER BY id ASC;
            """,
            (plan_id,),
        )
        steps: list[TaskStep] = []
        for s_row in step_cursor.fetchall():
            try:
                params = json.loads(s_row[2])
            except Exception:
                params = {}
            try:
                depends_on = json.loads(s_row[3])
            except Exception:
                depends_on = []
            steps.append(
                TaskStep(
                    step_id=s_row[0],
                    action_name=s_row[1],
                    params=params,
                    depends_on=depends_on,
                    timeout_seconds=float(s_row[4]),
                    requires_approval=bool(s_row[5]),
                    description=s_row[6] or "",
                )
            )

        policy_raw = row[3]
        try:
            policy = FailurePolicy(policy_raw)
        except ValueError:
            policy = FailurePolicy.STOP_ON_FAILURE

        return TaskPlan(
            plan_id=row[0],
            task_id=row[1],
            steps=steps,
            status=row[2],
            failure_policy=policy,
            max_retries=int(row[4]),
            timeout_seconds=float(row[5]),
            concurrency_limit=int(row[6]),
            created_at=datetime.fromisoformat(row[7]) if row[7] else datetime.now(timezone.utc),
            updated_at=datetime.fromisoformat(row[8]) if row[8] else datetime.now(timezone.utc),
        )

    # ---------------------------------------------------------
    # Task Execution CRUD
    # ---------------------------------------------------------

    def create_execution(self, execution: TaskExecution) -> TaskExecution:
        conn = self._get_conn()
        conn.execute(
            """
            INSERT INTO task_executions (execution_id, task_id, plan_id, status, started_at, completed_at, error_summary, result_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                execution.execution_id,
                execution.task_id,
                execution.plan_id,
                execution.status.value if isinstance(execution.status, TaskStatus) else str(execution.status),
                execution.started_at.isoformat() if isinstance(execution.started_at, datetime) else str(execution.started_at),
                execution.completed_at.isoformat() if execution.completed_at else None,
                execution.error_summary,
                json.dumps(execution.result_data),
            ),
        )
        conn.commit()
        return execution

    def update_execution(
        self,
        execution_id: str,
        status: TaskStatus,
        completed_at: datetime | None = None,
        error_summary: str = "",
        result_data: dict[str, Any] | None = None,
    ) -> bool:
        conn = self._get_conn()
        result_json = json.dumps(result_data or {})
        completed_str = completed_at.isoformat() if completed_at else None
        cursor = conn.execute(
            """
            UPDATE task_executions
            SET status = ?, completed_at = ?, error_summary = ?, result_data = ?
            WHERE execution_id = ?;
            """,
            (status.value if isinstance(status, TaskStatus) else str(status), completed_str, error_summary, result_json, execution_id),
        )
        conn.commit()
        return cursor.rowcount > 0

    def save_step_execution(self, step_exec: StepExecution) -> StepExecution:
        conn = self._get_conn()
        conn.execute(
            """
            INSERT OR REPLACE INTO step_executions (step_execution_id, execution_id, step_id, status, started_at, completed_at, attempt_count, result_data, error_message, duration_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                step_exec.step_execution_id,
                step_exec.execution_id,
                step_exec.step_id,
                step_exec.status.value if isinstance(step_exec.status, StepStatus) else str(step_exec.status),
                step_exec.started_at.isoformat() if isinstance(step_exec.started_at, datetime) else str(step_exec.started_at),
                step_exec.completed_at.isoformat() if step_exec.completed_at else None,
                step_exec.attempt_count,
                json.dumps(step_exec.result_data),
                step_exec.error_message,
                step_exec.duration_ms,
            ),
        )
        conn.commit()
        return step_exec

    def list_executions_for_task(self, task_id: str, limit: int = 20) -> list[TaskExecution]:
        conn = self._get_conn()
        cursor = conn.execute(
            """
            SELECT execution_id, task_id, plan_id, status, started_at, completed_at, error_summary, result_data
            FROM task_executions
            WHERE task_id = ?
            ORDER BY started_at DESC
            LIMIT ?;
            """,
            (task_id, limit),
        )
        executions: list[TaskExecution] = []
        for row in cursor.fetchall():
            exec_id = row[0]
            try:
                res_data = json.loads(row[7])
            except Exception:
                res_data = {}

            # Fetch step executions
            s_cursor = conn.execute(
                """
                SELECT step_execution_id, execution_id, step_id, status, started_at, completed_at, attempt_count, result_data, error_message, duration_ms
                FROM step_executions
                WHERE execution_id = ?
                ORDER BY started_at ASC;
                """,
                (exec_id,),
            )
            step_execs: list[StepExecution] = []
            for s in s_cursor.fetchall():
                try:
                    s_res = json.loads(s[7])
                except Exception:
                    s_res = {}
                step_execs.append(
                    StepExecution(
                        step_execution_id=s[0],
                        execution_id=s[1],
                        step_id=s[2],
                        status=StepStatus(s[3]) if s[3] in [e.value for e in StepStatus] else StepStatus.PENDING,
                        started_at=datetime.fromisoformat(s[4]) if s[4] else datetime.now(timezone.utc),
                        completed_at=datetime.fromisoformat(s[5]) if s[5] else None,
                        attempt_count=int(s[6]),
                        result_data=s_res,
                        error_message=s[8] or "",
                        duration_ms=float(s[9]),
                    )
                )

            status_raw = row[3]
            try:
                t_status = TaskStatus(status_raw)
            except ValueError:
                t_status = TaskStatus.RUNNING

            executions.append(
                TaskExecution(
                    execution_id=exec_id,
                    task_id=row[1],
                    plan_id=row[2],
                    status=t_status,
                    started_at=datetime.fromisoformat(row[4]) if row[4] else datetime.now(timezone.utc),
                    completed_at=datetime.fromisoformat(row[5]) if row[5] else None,
                    error_summary=row[6] or "",
                    result_data=res_data,
                    step_executions=step_execs,
                )
            )
        return executions
