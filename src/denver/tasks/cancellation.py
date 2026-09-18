"""Cancellation and pause/resume primitives for task execution."""

from __future__ import annotations

import asyncio
from typing import Callable

from denver.tasks.errors import TaskCancelledError, TaskPausedError


class CancellationToken:
    """Thread-safe and asyncio-cooperative cancellation and pause token."""

    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        self._is_cancelled = False
        self._is_paused = False
        self._cancel_reason = ""
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Initially unpaused
        self._callbacks: list[Callable[[], None]] = []

    @property
    def is_cancelled(self) -> bool:
        return self._is_cancelled

    @property
    def is_paused(self) -> bool:
        return self._is_paused

    @property
    def cancel_reason(self) -> str:
        return self._cancel_reason

    def cancel(self, reason: str = "User requested cancellation") -> None:
        """Mark token as cancelled and unblock any pause waiters."""
        self._is_cancelled = True
        self._cancel_reason = reason
        self._pause_event.set()
        for cb in self._callbacks:
            try:
                cb()
            except Exception:
                pass

    def pause(self) -> None:
        """Pause execution."""
        self._is_paused = True
        self._pause_event.clear()

    def resume(self) -> None:
        """Resume execution."""
        self._is_paused = False
        self._pause_event.set()

    def add_callback(self, cb: Callable[[], None]) -> None:
        """Register a callback to run upon cancellation."""
        self._callbacks.append(cb)
        if self._is_cancelled:
            try:
                cb()
            except Exception:
                pass

    async def check_pause_and_cancellation(self) -> None:
        """Asynchronously wait if paused and raise if cancelled."""
        if self._is_cancelled:
            raise TaskCancelledError(f"Task {self.task_id} was cancelled: {self._cancel_reason}")

        if self._is_paused:
            await self._pause_event.wait()

        if self._is_cancelled:
            raise TaskCancelledError(f"Task {self.task_id} was cancelled: {self._cancel_reason}")

    def raise_if_cancelled(self) -> None:
        """Synchronously check cancellation."""
        if self._is_cancelled:
            raise TaskCancelledError(f"Task {self.task_id} was cancelled: {self._cancel_reason}")


class CancellationManager:
    """Manages active cancellation tokens across all running tasks."""

    def __init__(self) -> None:
        self._tokens: dict[str, CancellationToken] = {}

    def get_or_create(self, task_id: str) -> CancellationToken:
        if task_id not in self._tokens:
            self._tokens[task_id] = CancellationToken(task_id)
        return self._tokens[task_id]

    def get(self, task_id: str) -> CancellationToken | None:
        return self._tokens.get(task_id)

    def cancel_task(self, task_id: str, reason: str = "User requested cancellation") -> bool:
        token = self._tokens.get(task_id)
        if token:
            token.cancel(reason)
            return True
        return False

    def pause_task(self, task_id: str) -> bool:
        token = self._tokens.get(task_id)
        if token:
            token.pause()
            return True
        return False

    def resume_task(self, task_id: str) -> bool:
        token = self._tokens.get(task_id)
        if token:
            token.resume()
            return True
        return False

    def is_paused(self, task_id: str) -> bool:
        token = self._tokens.get(task_id)
        return token.is_paused if token else False

    def is_cancelled(self, task_id: str) -> bool:
        token = self._tokens.get(task_id)
        return token.is_cancelled if token else False

    def remove(self, task_id: str) -> None:
        self._tokens.pop(task_id, None)

    def cancel_all(self, reason: str = "System shutdown or global cancellation") -> None:
        for token in list(self._tokens.values()):
            token.cancel(reason)
