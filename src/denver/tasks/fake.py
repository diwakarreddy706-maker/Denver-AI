"""Test fakes and mock executors for fast, zero-delay task testing."""

from __future__ import annotations

from typing import Any

from denver.automation.executor import AutomationExecutor
from denver.automation.models import AutomationRequest, AutomationResult
from denver.commands.models import ActionRequest, ActionResult, CommandCategory, CommandRiskLevel
from denver.commands.registry import ActionDefinition, ActionRegistry
from denver.commands.safety import SafetyValidator


class FakeAutomationExecutor(AutomationExecutor):
    """Zero-delay automation executor for deterministic unit testing."""

    def __init__(self, action_registry: ActionRegistry | None = None, safety_validator: SafetyValidator | None = None) -> None:
        self.action_registry = action_registry
        self.safety_validator = safety_validator
        self.executed_requests: list[Any] = []
        self.should_fail_action: set[str] = set()

    async def execute(self, request: Any) -> AutomationResult:
        self.executed_requests.append(request)
        action_name = getattr(request, "action_name", str(request))
        if action_name in self.should_fail_action:
            return AutomationResult(
                action=action_name,
                success=False,
                message=f"Simulated failure for {action_name}",
                error=f"Simulated failure for {action_name}",
            )
        params = getattr(request, "params", {})
        return AutomationResult(
            action=action_name,
            success=True,
            message=f"Executed {action_name} successfully",
            data={"echo_params": params},
        )


def create_test_action_registry() -> ActionRegistry:
    """Create an ActionRegistry with common test actions."""
    from denver.commands.models import CommandCategory, CommandRiskLevel
    registry = ActionRegistry()

    async def dummy_handler(params: dict[str, Any]) -> str:
        return "ok"

    actions = [
        ("get_time", "Get system time", CommandCategory.UTILITY, CommandRiskLevel.SAFE),
        ("get_date", "Get current date", CommandCategory.UTILITY, CommandRiskLevel.SAFE),
        ("get_system_status", "Get system diagnostic metrics", CommandCategory.SYSTEM, CommandRiskLevel.SAFE),
        ("search_notes", "Search user notes", CommandCategory.NOTE, CommandRiskLevel.SAFE),
        ("create_note", "Create a new note", CommandCategory.NOTE, CommandRiskLevel.LOW),
        ("send_notification", "Send a desktop notification", CommandCategory.UTILITY, CommandRiskLevel.LOW),
        ("lock_workstation", "Lock the desktop workstation", CommandCategory.SYSTEM, CommandRiskLevel.HIGH),
    ]

    for name, desc, cat, risk in actions:
        registry.register(
            ActionDefinition(
                name=name,
                description=desc,
                category=cat,
                risk_level=risk,
                handler=dummy_handler,
            )
        )

    return registry
