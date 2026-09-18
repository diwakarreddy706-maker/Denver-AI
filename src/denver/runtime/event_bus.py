"""Asynchronous Event Bus for Denver AI Assistant."""

from __future__ import annotations

import asyncio
import inspect
from collections import defaultdict
from typing import Any, Awaitable, Callable, Type, TypeVar

from denver.logging.logger import get_logger
from denver.runtime.events import DenverEvent

logger = get_logger("event_bus")

E = TypeVar("E", bound=DenverEvent)
EventHandler = Callable[[Any], Awaitable[None] | None]


class DenverEventBus:
    """Asynchronous-safe pub/sub event bus with handler failure isolation."""

    def __init__(self) -> None:
        self._subscribers: dict[Type[DenverEvent], list[EventHandler]] = defaultdict(list)
        self._lock = asyncio.Lock()
        self._published_count: int = 0
        self._is_running: bool = True
        self._pending_tasks: set[asyncio.Task[Any]] = set()

    @property
    def published_count(self) -> int:
        """Total number of events published during this lifecycle."""
        return self._published_count

    @property
    def is_running(self) -> bool:
        """Whether the event bus is actively accepting events."""
        return self._is_running

    def subscribe(self, event_type: Type[E], handler: EventHandler) -> None:
        """Register a handler for a specific event type."""
        if not callable(handler):
            raise TypeError(f"Handler must be callable, got {type(handler)}")
        if handler not in self._subscribers[event_type]:
            self._subscribers[event_type].append(handler)
            logger.debug("Subscribed %s to %s", getattr(handler, "__name__", str(handler)), event_type.__name__)

    def unsubscribe(self, event_type: Type[E], handler: EventHandler) -> bool:
        """Unregister a handler from a specific event type."""
        if event_type in self._subscribers and handler in self._subscribers[event_type]:
            self._subscribers[event_type].remove(handler)
            logger.debug("Unsubscribed %s from %s", getattr(handler, "__name__", str(handler)), event_type.__name__)
            return True
        return False

    async def publish(self, event: DenverEvent) -> None:
        """Publish an event to all registered subscribers asynchronously."""
        if not self._is_running:
            logger.warning("EventBus is stopped; ignored event %s", event.event_name)
            return

        self._published_count += 1
        event_cls = type(event)
        handlers = list(self._subscribers.get(event_cls, []))

        # Also notify wildcard subscribers registered for base DenverEvent
        if event_cls is not DenverEvent:
            handlers.extend(self._subscribers.get(DenverEvent, []))

        if not handlers:
            return

        for handler in handlers:
            try:
                if inspect.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    res = handler(event)
                    if inspect.isawaitable(res):
                        await res
            except Exception as exc:  # pylint: disable=broad-except
                # Isolate subscriber failure: log exception, do not crash bus or other handlers
                logger.exception(
                    "Error executing event handler %s for event %s: %s",
                    getattr(handler, "__name__", str(handler)),
                    event.event_name,
                    exc,
                )

    def publish_nowait(self, event: DenverEvent) -> asyncio.Task[None] | None:
        """Publish an event in the background without blocking the caller."""
        if not self._is_running:
            return None
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(self.publish(event))
            self._pending_tasks.add(task)
            task.add_done_callback(self._pending_tasks.discard)
            return task
        except RuntimeError:
            logger.warning("No running asyncio loop; dropping background event %s", event.event_name)
            return None

    async def shutdown(self, timeout: float = 2.0) -> None:
        """Gracefully shut down event bus and await pending background tasks."""
        self._is_running = False
        logger.debug("Shutting down DenverEventBus with %d pending tasks...", len(self._pending_tasks))
        if self._pending_tasks:
            done, pending = await asyncio.wait(self._pending_tasks, timeout=timeout)
            for task in pending:
                task.cancel()
        self._subscribers.clear()
        logger.debug("DenverEventBus shutdown complete.")


_global_event_bus: DenverEventBus | None = None


def get_event_bus() -> DenverEventBus:
    """Get or create the global default DenverEventBus instance."""
    global _global_event_bus
    if _global_event_bus is None or not _global_event_bus.is_running:
        _global_event_bus = DenverEventBus()
    return _global_event_bus
