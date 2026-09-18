"""Authoritative Asynchronous State Machine for Denver AI Assistant."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from denver.logging.logger import get_logger
from denver.runtime.event_bus import DenverEventBus
from denver.runtime.events import StateChanged
from denver.runtime.states import DenverState

logger = get_logger("state_machine")


class InvalidStateTransitionError(ValueError):
    """Raised when an illegal state transition is attempted."""

    def __init__(self, from_state: DenverState, to_state: DenverState, reason: str = "") -> None:
        self.from_state = from_state
        self.to_state = to_state
        msg = f"Cannot transition from {from_state} to {to_state}."
        if reason:
            msg += f" Reason: {reason}"
        super().__init__(msg)


@dataclass(frozen=True)
class StateTransitionRecord:
    """Historical record of an individual state transition."""

    from_state: DenverState
    to_state: DenverState
    timestamp: float = field(default_factory=time.time)
    reason: str = ""


# Explicit transition map defining allowed graph paths
ALLOWED_TRANSITIONS: Mapping[DenverState, frozenset[DenverState]] = {
    DenverState.BOOTING: frozenset({
        DenverState.STANDBY,
        DenverState.ERROR,
        DenverState.SHUTTING_DOWN,
    }),
    DenverState.STANDBY: frozenset({
        DenverState.LISTENING,
        DenverState.PROCESSING,
        DenverState.EXECUTING,
        DenverState.SPEAKING,
        DenverState.OFFLINE,
        DenverState.ERROR,
        DenverState.SHUTTING_DOWN,
    }),
    DenverState.LISTENING: frozenset({
        DenverState.PROCESSING,
        DenverState.STANDBY,
        DenverState.ERROR,
        DenverState.SHUTTING_DOWN,
    }),
    DenverState.PROCESSING: frozenset({
        DenverState.EXECUTING,
        DenverState.SPEAKING,
        DenverState.STANDBY,
        DenverState.ERROR,
        DenverState.SHUTTING_DOWN,
    }),
    DenverState.EXECUTING: frozenset({
        DenverState.SPEAKING,
        DenverState.STANDBY,
        DenverState.ERROR,
        DenverState.SHUTTING_DOWN,
    }),
    DenverState.SPEAKING: frozenset({
        DenverState.STANDBY,
        DenverState.LISTENING,
        DenverState.ERROR,
        DenverState.SHUTTING_DOWN,
    }),
    DenverState.ERROR: frozenset({
        DenverState.STANDBY,
        DenverState.OFFLINE,
        DenverState.SHUTTING_DOWN,
        DenverState.STOPPED,
    }),
    DenverState.OFFLINE: frozenset({
        DenverState.STANDBY,
        DenverState.ERROR,
        DenverState.SHUTTING_DOWN,
    }),
    DenverState.SHUTTING_DOWN: frozenset({
        DenverState.STOPPED,
    }),
    DenverState.STOPPED: frozenset(),  # Terminal state
}


class DenverStateMachine:
    """Async-safe state machine governing all Denver lifecycle and runtime states."""

    def __init__(
        self,
        initial_state: DenverState = DenverState.BOOTING,
        event_bus: DenverEventBus | None = None,
    ) -> None:
        self._state: DenverState = initial_state
        self._event_bus: DenverEventBus | None = event_bus
        self._history: list[StateTransitionRecord] = []
        self._lock = asyncio.Lock()
        self._last_transition_time: float = time.time()

    @property
    def current_state(self) -> DenverState:
        """Current state of the assistant."""
        return self._state

    @property
    def history(self) -> list[StateTransitionRecord]:
        """Chronological record of all state transitions."""
        return list(self._history)

    @property
    def last_transition_time(self) -> float:
        """Timestamp of the most recent state transition."""
        return self._last_transition_time

    def can_transition_to(self, target_state: DenverState) -> bool:
        """Check if transitioning from current state to target state is legal."""
        return target_state in ALLOWED_TRANSITIONS.get(self._state, frozenset())

    async def transition_to(self, target_state: DenverState, reason: str = "") -> None:
        """Safely transition to a target state, recording history and publishing StateChanged."""
        async with self._lock:
            if target_state == self._state:
                logger.debug("Already in state %s; transition no-op.", self._state)
                return

            if not self.can_transition_to(target_state):
                logger.error("Illegal transition rejected: %s -> %s (Reason: %s)", self._state, target_state, reason)
                raise InvalidStateTransitionError(self._state, target_state, reason)

            old_state = self._state
            self._state = target_state
            self._last_transition_time = time.time()

            record = StateTransitionRecord(
                from_state=old_state,
                to_state=target_state,
                timestamp=self._last_transition_time,
                reason=reason,
            )
            self._history.append(record)

            logger.info("State transition: %s -> %s (Reason: '%s')", old_state, target_state, reason)

            if self._event_bus is not None and self._event_bus.is_running:
                event = StateChanged(
                    timestamp=self._last_transition_time,
                    from_state=old_state,
                    to_state=target_state,
                    reason=reason,
                )
                await self._event_bus.publish(event)
