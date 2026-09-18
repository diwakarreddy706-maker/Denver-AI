"""Action Executor and Dispatcher for Denver AI Assistant."""

from __future__ import annotations

import inspect
import time
from typing import Any

from denver.commands.models import ActionRequest, ActionResult
from denver.commands.registry import ActionRegistry
from denver.logging.logger import get_logger

logger = get_logger("executor")


class ActionExecutor:
    """Executes registered actions within safe isolated boundaries."""

    def __init__(self, registry: ActionRegistry) -> None:
        self.registry = registry

    async def execute(self, action_request: ActionRequest) -> ActionResult:
        """Execute action handler from registry and capture structured outcome."""
        action_name = action_request.action_name.strip().lower()
        action_def = self.registry.get(action_name)

        if not action_def:
            return ActionResult(
                success=False,
                message=f"Action '{action_name}' is not registered in the system.",
                action_name=action_name,
                error="ActionNotFound",
            )

        if not action_def.enabled:
            return ActionResult(
                success=False,
                message=f"Action '{action_name}' is currently disabled.",
                action_name=action_name,
                error="ActionDisabled",
            )

        start_time = time.perf_counter()
        try:
            handler = action_def.handler
            if inspect.iscoroutinefunction(handler):
                result = await handler(action_request.params)
            else:
                result = handler(action_request.params)

            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

            if isinstance(result, ActionResult):
                result.latency_ms = elapsed_ms
                return result

            # If handler returned a dict or primitive
            return ActionResult(
                success=True,
                message=f"Action '{action_name}' executed successfully.",
                action_name=action_name,
                data=result if isinstance(result, dict) else {"result": result},
                latency_ms=elapsed_ms,
            )

        except Exception as exc:  # pylint: disable=broad-except
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error("Error executing action handler '%s': %s", action_name, exc, exc_info=True)
            return ActionResult(
                success=False,
                message=f"Error executing action '{action_name}': {exc}",
                action_name=action_name,
                error=str(exc),
                latency_ms=elapsed_ms,
            )
