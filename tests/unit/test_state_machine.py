"""Unit tests for Denver State Machine."""

from __future__ import annotations

import unittest
from denver.runtime.event_bus import DenverEventBus
from denver.runtime.events import StateChanged
from denver.runtime.state_machine import DenverStateMachine, InvalidStateTransitionError
from denver.runtime.states import DenverState


class TestDenverStateMachine(unittest.IsolatedAsyncioTestCase):
    """Test suite for Denver State Machine transitions and event publishing."""

    async def asyncSetUp(self) -> None:
        self.event_bus = DenverEventBus()
        self.sm = DenverStateMachine(initial_state=DenverState.BOOTING, event_bus=self.event_bus)
        self.state_events: list[StateChanged] = []

        self.event_bus.subscribe(StateChanged, lambda evt: self.state_events.append(evt))

    async def test_initial_state(self) -> None:
        """Verify initial state is BOOTING."""
        self.assertEqual(self.sm.current_state, DenverState.BOOTING)
        self.assertEqual(len(self.sm.history), 0)

    async def test_valid_transitions_lifecycle(self) -> None:
        """Verify standard lifecycle transitions."""
        # BOOTING -> STANDBY
        await self.sm.transition_to(DenverState.STANDBY, reason="boot completed")
        self.assertEqual(self.sm.current_state, DenverState.STANDBY)
        self.assertEqual(len(self.sm.history), 1)
        self.assertEqual(self.sm.history[0].from_state, DenverState.BOOTING)
        self.assertEqual(self.sm.history[0].to_state, DenverState.STANDBY)
        self.assertEqual(self.sm.history[0].reason, "boot completed")
        self.assertEqual(len(self.state_events), 1)

        # STANDBY -> LISTENING
        await self.sm.transition_to(DenverState.LISTENING, reason="wake word detected")
        self.assertEqual(self.sm.current_state, DenverState.LISTENING)

        # LISTENING -> PROCESSING
        await self.sm.transition_to(DenverState.PROCESSING, reason="speech completed")
        self.assertEqual(self.sm.current_state, DenverState.PROCESSING)

        # PROCESSING -> EXECUTING
        await self.sm.transition_to(DenverState.EXECUTING, reason="action dispatched")
        self.assertEqual(self.sm.current_state, DenverState.EXECUTING)

        # EXECUTING -> SPEAKING
        await self.sm.transition_to(DenverState.SPEAKING, reason="tts active")
        self.assertEqual(self.sm.current_state, DenverState.SPEAKING)

        # SPEAKING -> STANDBY
        await self.sm.transition_to(DenverState.STANDBY, reason="command complete")
        self.assertEqual(self.sm.current_state, DenverState.STANDBY)

        # STANDBY -> SHUTTING_DOWN
        await self.sm.transition_to(DenverState.SHUTTING_DOWN, reason="user requested shutdown")
        self.assertEqual(self.sm.current_state, DenverState.SHUTTING_DOWN)

        # SHUTTING_DOWN -> STOPPED
        await self.sm.transition_to(DenverState.STOPPED, reason="clean exit")
        self.assertEqual(self.sm.current_state, DenverState.STOPPED)

        self.assertEqual(len(self.sm.history), 8)
        self.assertEqual(len(self.state_events), 8)

    async def test_invalid_transition_rejected(self) -> None:
        """Verify illegal state transitions raise InvalidStateTransitionError."""
        # Cannot jump from BOOTING directly to SPEAKING
        with self.assertRaises(InvalidStateTransitionError) as ctx:
            await self.sm.transition_to(DenverState.SPEAKING)
        self.assertEqual(ctx.exception.from_state, DenverState.BOOTING)
        self.assertEqual(ctx.exception.to_state, DenverState.SPEAKING)
        self.assertEqual(self.sm.current_state, DenverState.BOOTING)

        # Transition to STOPPED
        await self.sm.transition_to(DenverState.SHUTTING_DOWN)
        await self.sm.transition_to(DenverState.STOPPED)

        # Cannot transition out of STOPPED
        with self.assertRaises(InvalidStateTransitionError):
            await self.sm.transition_to(DenverState.STANDBY)

    async def test_same_state_transition_is_noop(self) -> None:
        """Verify transitioning to the same state does not create duplicate history."""
        await self.sm.transition_to(DenverState.BOOTING)
        self.assertEqual(len(self.sm.history), 0)
        self.assertEqual(len(self.state_events), 0)


if __name__ == "__main__":
    unittest.main()
