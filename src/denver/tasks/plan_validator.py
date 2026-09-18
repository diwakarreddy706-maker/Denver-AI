"""Validation and DAG integrity analysis for Denver Task Plans."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from denver.commands.models import ActionRequest
from denver.commands.registry import ActionRegistry
from denver.commands.safety import SafetyValidator
from denver.logging.logger import get_logger
from denver.tasks.errors import (
    ActionNotFoundError,
    CircularDependencyError,
    InvalidStepDependencyError,
    MaxDepthExceededError,
    MaxStepsExceededError,
    PlanValidationError,
)
from denver.tasks.models import TaskPlan, TaskStep

logger = get_logger("tasks.validator")


class PlanValidator:
    """Validates structural DAG integrity, bounded limits, action registry, and safety."""

    def __init__(
        self,
        action_registry: ActionRegistry | None = None,
        safety_validator: SafetyValidator | None = None,
        max_steps: int = 20,
        max_depth: int = 10,
    ) -> None:
        self.action_registry = action_registry
        self.safety_validator = safety_validator
        self.max_steps = max_steps
        self.max_depth = max_depth

    def validate(self, plan: TaskPlan) -> None:
        """Thoroughly validate a TaskPlan. Raises PlanValidationError on any violation."""
        if not plan.steps:
            raise PlanValidationError(f"Task plan '{plan.plan_id}' contains no steps.")

        if len(plan.steps) > self.max_steps:
            raise MaxStepsExceededError(
                f"Task plan '{plan.plan_id}' has {len(plan.steps)} steps, exceeding limit of {self.max_steps}."
            )

        # Check step ID uniqueness
        seen_step_ids: set[str] = set()
        step_map: dict[str, TaskStep] = {}
        for step in plan.steps:
            if not step.step_id or not isinstance(step.step_id, str):
                raise PlanValidationError("Task step missing valid step_id.")
            if step.step_id in seen_step_ids:
                raise PlanValidationError(f"Duplicate step_id '{step.step_id}' found in plan.")
            seen_step_ids.add(step.step_id)
            step_map[step.step_id] = step

        # Check dependency integrity & build adjacency graph
        in_degree: dict[str, int] = {s_id: 0 for s_id in seen_step_ids}
        adj_list: dict[str, list[str]] = defaultdict(list)

        for step in plan.steps:
            for dep in step.depends_on:
                if dep == step.step_id:
                    raise CircularDependencyError(
                        f"Step '{step.step_id}' cannot depend on itself."
                    )
                if dep not in seen_step_ids:
                    raise InvalidStepDependencyError(
                        f"Step '{step.step_id}' depends on non-existent step '{dep}'."
                    )
                adj_list[dep].append(step.step_id)
                in_degree[step.step_id] += 1

        # Check DAG acyclicity using Kahn's algorithm
        queue = deque([s_id for s_id, deg in in_degree.items() if deg == 0])
        visited_count = 0

        while queue:
            node = queue.popleft()
            visited_count += 1
            for neighbor in adj_list[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited_count != len(plan.steps):
            raise CircularDependencyError(
                f"Task plan '{plan.plan_id}' contains a circular dependency cycle."
            )

        # Calculate max depth / longest path in DAG
        depth = self._calculate_max_depth(plan.steps, adj_list)
        if depth > self.max_depth:
            raise MaxDepthExceededError(
                f"Task plan depth ({depth}) exceeds maximum permitted depth ({self.max_depth})."
            )

        # Action registry and safety verification
        for step in plan.steps:
            self._validate_step_action(step)

        logger.debug("Plan '%s' validated successfully (%d steps, depth %d).", plan.plan_id, len(plan.steps), depth)

    def _calculate_max_depth(self, steps: list[TaskStep], adj_list: dict[str, list[str]]) -> int:
        """Compute the longest path length in the DAG."""
        memo: dict[str, int] = {}

        def get_depth(node: str) -> int:
            if node in memo:
                return memo[node]
            neighbors = adj_list.get(node, [])
            if not neighbors:
                memo[node] = 1
                return 1
            max_child = max(get_depth(child) for child in neighbors)
            memo[node] = 1 + max_child
            return memo[node]

        all_depths = [get_depth(step.step_id) for step in steps]
        return max(all_depths) if all_depths else 0

    def _validate_step_action(self, step: TaskStep) -> None:
        """Validate step action registration and safety."""
        if not step.action_name or not isinstance(step.action_name, str):
            raise PlanValidationError(f"Step '{step.step_id}' has invalid action_name.")

        if self.action_registry:
            action = self.action_registry.get(step.action_name)
            if not action:
                raise ActionNotFoundError(
                    f"Step '{step.step_id}' references unknown action '{step.action_name}'."
                )

        if self.safety_validator:
            # Check if safety validator rejects params or command
            req = ActionRequest(action_name=step.action_name, params=step.params)
            is_valid, reason = self.safety_validator.validate(req)
            if not is_valid:
                raise PlanValidationError(
                    f"Step '{step.step_id}' failed safety validation: {reason}"
                )
