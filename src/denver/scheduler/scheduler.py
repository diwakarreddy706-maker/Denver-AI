"""Denver Proactive Intelligence & Scheduled Routines: Main Scheduler Engine.

Deterministic, bounded, async background loop executing scheduled user routines.
Adheres strictly to Phase 8 safety boundaries:
- Zero autonomous capability.
- Sleep-until-next-run with safe wakeups.
- Concurrency limiting and global pause enforcement.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from denver.config.settings import DenverSettings
from denver.runtime.event_bus import DenverEventBus, get_event_bus
from denver.runtime.events import (
    SchedulerPaused,
    SchedulerResumed,
    SchedulerStarted,
    SchedulerStopped,
)
from denver.scheduler.errors import (
    RoutineNotFoundError,
    SchedulerDisabledError,
)
from denver.scheduler.execution_coordinator import RoutineExecutionCoordinator
from denver.scheduler.models import (
    Routine,
    RoutineExecution,
    RoutineStatus,
    TriggerType,
)
from denver.scheduler.persistence import RoutineRepository
from denver.scheduler.routine_registry import RoutineRegistry
from denver.scheduler.trigger_engine import TriggerEngine

logger = logging.getLogger(__name__)


class DenverScheduler:
    """Core scheduler service managing the async lifecycle of routine execution."""

    def __init__(
        self,
        settings: DenverSettings,
        registry: RoutineRegistry,
        coordinator: RoutineExecutionCoordinator,
        event_bus: DenverEventBus | None = None,
        trigger_engine: TriggerEngine | None = None,
    ) -> None:
        self.settings = settings
        self.registry = registry
        self.coordinator = coordinator
        self.event_bus = event_bus or get_event_bus()
        self.trigger_engine = trigger_engine or TriggerEngine()

        self._enabled: bool = bool(settings.scheduler_enabled)
        self._paused: bool = bool(settings.scheduler_global_pause)
        self._running: bool = False
        self._loop_task: asyncio.Task[None] | None = None
        self._wakeup_event: asyncio.Event = asyncio.Event()

    @property
    def is_enabled(self) -> bool:
        """Check if scheduler is enabled in configuration."""
        return self._enabled

    @property
    def is_paused(self) -> bool:
        """Check if scheduler is globally paused."""
        return self._paused

    @property
    def is_running(self) -> bool:
        """Check if scheduler background loop is running."""
        return self._running

    async def start(self) -> None:
        """Start the scheduler background loop."""
        if not self._enabled:
            logger.info("DenverScheduler is disabled in configuration. Not starting.")
            return

        if self._running:
            return

        self._running = True
        self._loop_task = asyncio.create_task(self._run_loop(), name="denver-scheduler-loop")
        active = await self.registry.list_routines(enabled_only=True)
        await self.event_bus.publish(SchedulerStarted(active_routines=len(active)))
        logger.info("DenverScheduler background service started.")

    async def stop(self) -> None:
        """Stop the scheduler background loop cleanly."""
        if not self._running:
            return

        self._running = False
        self._wakeup_event.set()

        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None

        await self.event_bus.publish(SchedulerStopped())
        logger.info("DenverScheduler background service stopped.")

    async def pause(self) -> None:
        """Globally pause routine execution."""
        if self._paused:
            return
        self._paused = True
        self._wakeup_event.set()
        await self.event_bus.publish(SchedulerPaused())
        logger.info("DenverScheduler paused globally.")

    async def resume(self) -> None:
        """Resume routine execution after global pause."""
        if not self._paused:
            return
        self._paused = False
        self._wakeup_event.set()
        await self.event_bus.publish(SchedulerResumed())
        logger.info("DenverScheduler resumed.")

    def enable(self) -> None:
        """Enable scheduler service."""
        self._enabled = True

    def disable(self) -> None:
        """Disable scheduler service."""
        self._enabled = False

    def notify_schedule_change(self) -> None:
        """Signal the scheduler loop that a routine was added/updated to recalculate sleep time."""
        self._wakeup_event.set()

    async def run_routine_now(self, routine_id: str) -> RoutineExecution:
        """Manually trigger immediate execution of a routine, bypassing schedule time."""
        if not self._enabled:
            raise SchedulerDisabledError("Scheduler is disabled.")

        routine = await self.registry.get_routine(routine_id)
        if not routine:
            raise RoutineNotFoundError(f"Routine {routine_id} not found.")

        logger.info("Manually triggering routine %s (%s)", routine.routine_id, routine.name)
        execution = await self.coordinator.execute_routine(routine, trigger_type="manual", force=True)
        return execution

    async def _run_loop(self) -> None:
        """Main scheduler async loop with deterministic sleep and wakeups."""
        logger.debug("Scheduler async loop entered.")
        while self._running:
            try:
                self._wakeup_event.clear()

                if not self._enabled or self._paused:
                    # Sleep waiting for unpause/enable wakeup
                    try:
                        await asyncio.wait_for(self._wakeup_event.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        pass
                    continue

                now = datetime.now(timezone.utc)
                due_routines = await self._get_due_routines(now)

                for routine in due_routines:
                    if not self._running or self._paused or not self._enabled:
                        break

                    # Dispatch routine execution as a bounded task
                    asyncio.create_task(
                        self._process_due_routine(routine, now),
                        name=f"routine-exec-{routine.routine_id}",
                    )

                # Determine sleep duration until next due routine
                next_due_dt = await self._get_earliest_next_run()
                sleep_seconds = 5.0  # default poll interval
                if next_due_dt:
                    diff = (next_due_dt - datetime.now(timezone.utc)).total_seconds()
                    if diff > 0:
                        sleep_seconds = min(diff, 60.0)  # capped at 60s for safety
                    else:
                        sleep_seconds = 0.5

                try:
                    await asyncio.wait_for(self._wakeup_event.wait(), timeout=max(sleep_seconds, 0.1))
                except asyncio.TimeoutError:
                    pass

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("Unexpected error in DenverScheduler loop: %s", e)
                try:
                    await asyncio.sleep(2.0)
                except asyncio.CancelledError:
                    break

    async def _get_due_routines(self, reference_now: datetime) -> list[Routine]:
        """Fetch all enabled routines whose next_run_at is due."""
        active = await self.registry.list_routines(enabled_only=True)
        due = []
        for r in active:
            if r.status == RoutineStatus.ACTIVE and r.next_run_at and r.next_run_at <= reference_now:
                due.append(r)
        return due

    async def _process_due_routine(self, routine: Routine, reference_now: datetime) -> None:
        """Execute a due routine and calculate its next scheduled run time."""
        try:
            execution = await self.coordinator.execute_routine(routine, trigger_type="scheduled")

            # Compute next run time
            now_after_run = datetime.now(timezone.utc)
            next_run = self.trigger_engine.compute_next_run(
                trigger=routine.trigger,
                after_dt=now_after_run,
            )

            routine.last_run_at = now_after_run
            routine.last_status = execution.status.value
            routine.updated_at = now_after_run

            if next_run:
                routine.next_run_at = next_run
            else:
                # One-time routine completed
                routine.enabled = False
                routine.status = RoutineStatus.COMPLETED
                routine.next_run_at = None

            def _save_routine(conn) -> Routine:
                repo = RoutineRepository(conn)
                return repo.save(routine)

            await self.registry.db.run_async(_save_routine)

        except Exception as e:
            logger.exception("Failed processing due routine %s: %s", routine.routine_id, e)

    async def _get_earliest_next_run(self) -> datetime | None:
        """Find the earliest next_run_at among all active routines."""
        active = await self.registry.list_routines(enabled_only=True)
        upcoming = [r.next_run_at for r in active if r.status == RoutineStatus.ACTIVE and r.next_run_at is not None]
        if not upcoming:
            return None
        return min(upcoming)

    async def get_health_status(self) -> dict[str, Any]:
        """Return diagnostic health metrics for DenverHealthService."""
        all_routines = await self.registry.list_routines(enabled_only=False)
        active_routines = [r for r in all_routines if r.enabled and r.status == RoutineStatus.ACTIVE]
        earliest_next = await self._get_earliest_next_run()

        return {
            "enabled": self._enabled,
            "running": self._running,
            "paused": self._paused,
            "total_routines": len(all_routines),
            "active_routines": len(active_routines),
            "next_run_at": earliest_next.isoformat() if earliest_next else None,
            "max_concurrency": self.coordinator._semaphore._value,
        }
