"""Task planner for decomposing user intents into validated execution DAGs."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from denver.logging.logger import get_logger
from denver.tasks.errors import PlanValidationError
from denver.tasks.models import FailurePolicy, TaskPlan, TaskProposal, TaskStep
from denver.tasks.plan_validator import PlanValidator

logger = get_logger("tasks.planner")


class TaskPlanner:
    """Creates strongly-typed, validated TaskPlan instances from proposals or direct inputs."""

    def __init__(self, validator: PlanValidator | None = None) -> None:
        self.validator = validator or PlanValidator()

    def create_plan_from_proposal(self, task_id: str, proposal: TaskProposal) -> TaskPlan:
        """Construct a TaskPlan from an untrusted TaskProposal and validate it."""
        plan_id = f"plan_{uuid.uuid4().hex[:10]}"
        steps: list[TaskStep] = []

        for idx, step_dict in enumerate(proposal.steps, start=1):
            step_id = str(step_dict.get("step_id") or f"step_{idx}")
            action_name = str(step_dict.get("action_name", ""))
            params = step_dict.get("params", {})
            if not isinstance(params, dict):
                params = {}
            depends_on = step_dict.get("depends_on", [])
            if not isinstance(depends_on, list):
                depends_on = []
            timeout_sec = float(step_dict.get("timeout_seconds", 60.0))
            requires_appr = bool(step_dict.get("requires_approval", False))
            desc = str(step_dict.get("description", ""))

            step = TaskStep(
                step_id=step_id,
                action_name=action_name,
                params=params,
                depends_on=[str(d) for d in depends_on],
                timeout_seconds=timeout_sec,
                requires_approval=requires_appr,
                description=desc,
            )
            steps.append(step)

        plan = TaskPlan(
            plan_id=plan_id,
            task_id=task_id,
            steps=steps,
            status="proposed",
            failure_policy=proposal.suggested_policy,
            max_retries=1,
            timeout_seconds=600.0,
            concurrency_limit=2,
        )

        # Validate strictly before returning
        self.validator.validate(plan)
        return plan

    def plan_from_action_list(
        self,
        task_id: str,
        actions: list[dict[str, Any]],
        failure_policy: FailurePolicy = FailurePolicy.STOP_ON_FAILURE,
    ) -> TaskPlan:
        """Create a sequential or DAG plan directly from an action list."""
        proposal = TaskProposal(
            task_title="User Defined Workflow",
            task_description="Workflow plan composed from action sequence",
            steps=actions,
            suggested_policy=failure_policy,
        )
        return self.create_plan_from_proposal(task_id, proposal)

    def parse_ai_response(self, task_id: str, response_text: str) -> TaskPlan:
        """Safely parse AI-generated JSON task proposals (Untrusted AI Proposal Boundary)."""
        # Attempt to extract JSON from code block or raw text
        cleaned = response_text.strip()
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
        if json_match:
            raw_json = json_match.group(1)
        else:
            # Try to locate outer braces
            start_idx = cleaned.find("{")
            end_idx = cleaned.rfind("}")
            if start_idx != -1 and end_idx != -1:
                raw_json = cleaned[start_idx : end_idx + 1]
            else:
                raise PlanValidationError("Failed to parse AI response: No valid JSON found.")

        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise PlanValidationError(f"Invalid JSON in AI task proposal: {exc}")

        title = str(data.get("title", "AI Generated Task"))
        description = str(data.get("description", ""))
        steps_raw = data.get("steps", [])
        if not isinstance(steps_raw, list) or not steps_raw:
            raise PlanValidationError("AI task proposal must contain a non-empty 'steps' list.")

        policy_str = str(data.get("failure_policy", "stop_on_failure"))
        try:
            policy = FailurePolicy(policy_str)
        except ValueError:
            policy = FailurePolicy.STOP_ON_FAILURE

        proposal = TaskProposal(
            task_title=title,
            task_description=description,
            steps=steps_raw,
            confidence=float(data.get("confidence", 0.9)),
            reasoning=str(data.get("reasoning", "")),
            suggested_policy=policy,
        )

        return self.create_plan_from_proposal(task_id, proposal)
