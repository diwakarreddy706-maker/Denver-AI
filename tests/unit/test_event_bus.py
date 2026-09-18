"""Unit tests for Denver Asynchronous Event Bus."""

from __future__ import annotations

import asyncio
import unittest
from denver.runtime.event_bus import DenverEventBus
from denver.runtime.events import ApplicationStarted, DenverEvent, StateChanged
from denver.runtime.states import DenverState


class TestDenverEventBus(unittest.IsolatedAsyncioTestCase):
    """Test suite for Denver Event Bus pub/sub mechanics and isolation."""

    async def asyncSetUp(self) -> None:
        self.bus = DenverEventBus()

    async def asyncTearDown(self) -> None:
        if self.bus.is_running:
            await self.bus.shutdown()

    async def test_publish_and_subscribe(self) -> None:
        """Verify standard event delivery to subscribers."""
        received: list[ApplicationStarted] = []

        async def handler(event: ApplicationStarted) -> None:
            received.append(event)

        self.bus.subscribe(ApplicationStarted, handler)
        evt = ApplicationStarted(version="0.1.0", environment="test")
        await self.bus.publish(evt)

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].version, "0.1.0")
        self.assertEqual(self.bus.published_count, 1)

    async def test_unsubscribe(self) -> None:
        """Verify unregistering event handlers."""
        received: list[DenverEvent] = []

        def handler(event: DenverEvent) -> None:
            received.append(event)

        self.bus.subscribe(ApplicationStarted, handler)
        await self.bus.publish(ApplicationStarted())
        self.assertEqual(len(received), 1)

        unsubscribed = self.bus.unsubscribe(ApplicationStarted, handler)
        self.assertTrue(unsubscribed)

        await self.bus.publish(ApplicationStarted())
        self.assertEqual(len(received), 1)

    async def test_multiple_subscribers(self) -> None:
        """Verify all registered handlers receive events."""
        results: list[int] = []

        async def handler1(_: ApplicationStarted) -> None:
            results.append(1)

        def handler2(_: ApplicationStarted) -> None:
            results.append(2)

        self.bus.subscribe(ApplicationStarted, handler1)
        self.bus.subscribe(ApplicationStarted, handler2)

        await self.bus.publish(ApplicationStarted())
        self.assertEqual(results, [1, 2])

    async def test_handler_failure_isolation(self) -> None:
        """Verify a failing handler does not prevent other handlers from executing or crash the bus."""
        results: list[str] = []

        async def failing_handler(_: StateChanged) -> None:
            raise RuntimeError("Handler intentional failure")

        async def successful_handler(event: StateChanged) -> None:
            results.append(f"{event.from_state}->{event.to_state}")

        self.bus.subscribe(StateChanged, failing_handler)
        self.bus.subscribe(StateChanged, successful_handler)

        event = StateChanged(from_state=DenverState.BOOTING, to_state=DenverState.STANDBY)
        # Should complete without throwing an unhandled exception
        await self.bus.publish(event)

        self.assertEqual(results, ["BOOTING->STANDBY"])

    async def test_wildcard_denver_event_subscription(self) -> None:
        """Verify handlers subscribed to DenverEvent receive all event subclasses."""
        all_events: list[DenverEvent] = []

        self.bus.subscribe(DenverEvent, lambda evt: all_events.append(evt))

        await self.bus.publish(ApplicationStarted())
        await self.bus.publish(StateChanged(from_state=DenverState.BOOTING, to_state=DenverState.STANDBY))

        self.assertEqual(len(all_events), 2)


if __name__ == "__main__":
    unittest.main()
