"""Central Action Registry for Denver AI Assistant."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping

from denver.commands.models import ActionResult, CommandCategory, CommandRiskLevel
from denver.logging.logger import get_logger

logger = get_logger("registry")

ActionHandler = Callable[[dict[str, Any]], Awaitable[ActionResult] | ActionResult]


@dataclass
class ActionDefinition:
    """Complete metadata and execution contract for an individual registered action."""

    name: str
    description: str
    category: CommandCategory
    risk_level: CommandRiskLevel
    handler: ActionHandler
    schema: dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = False
    enabled: bool = True


class ActionRegistry:
    """Thread-safe catalog of all registered actions and handlers."""

    def __init__(self) -> None:
        self._actions: dict[str, ActionDefinition] = {}

    def register(self, action: ActionDefinition) -> None:
        """Register a new action definition. Rejects duplicate names to maintain integrity."""
        if not action.name:
            raise ValueError("Action name must be non-empty.")

        normalized_name = action.name.strip().lower()
        if normalized_name in self._actions:
            raise ValueError(f"Action '{normalized_name}' is already registered in Denver Action Registry.")

        self._actions[normalized_name] = action
        logger.debug("Registered action '%s' [%s] with risk level %s", normalized_name, action.category.value, action.risk_level.value)

    def unregister(self, name: str) -> bool:
        """Remove an action from the registry."""
        normalized_name = name.strip().lower()
        if normalized_name in self._actions:
            del self._actions[normalized_name]
            logger.debug("Unregistered action '%s'", normalized_name)
            return True
        return False

    def get(self, name: str) -> ActionDefinition | None:
        """Retrieve an action definition by name."""
        return self._actions.get(name.strip().lower())

    def has_action(self, name: str) -> bool:
        """Check if an action is present in the registry."""
        return name.strip().lower() in self._actions

    def list_actions(self, category: CommandCategory | None = None) -> list[ActionDefinition]:
        """List registered action definitions, optionally filtered by category."""
        if category:
            return [a for a in self._actions.values() if a.category == category]
        return list(self._actions.values())

    def enable_action(self, name: str) -> bool:
        """Enable an action."""
        action = self.get(name)
        if action:
            action.enabled = True
            return True
        return False

    def disable_action(self, name: str) -> bool:
        """Disable an action."""
        action = self.get(name)
        if action:
            action.enabled = False
            return True
        return False

    def clear(self) -> None:
        """Clear all registered actions."""
        self._actions.clear()
