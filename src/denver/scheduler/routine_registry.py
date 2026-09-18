"""Routine Registry for Creating, Updating, Validating, and Managing Routines."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from denver.logging.logger import get_logger
from denver.memory.database import DenverDatabase
from denver.runtime.event_bus import DenverEventBus, get_event_bus
from denver.runtime.events import (
    RoutineCreated,
    RoutineDeleted,
    RoutineDisabled,
    RoutineEnabled,
    RoutineUpdated,
)
from denver.scheduler.audit import RoutineAuditLogger
from denver.scheduler.errors import (
    DuplicateRoutineError,
    RoutineNotFoundError,
    RoutineValidationError,
)
from denver.scheduler.models import (
    NotificationPolicy,
    Routine,
    RoutineAction,
    RoutineStatus,
    RoutineTrigger,
    TriggerType,
)
from denver.scheduler.persistence import RoutineRepository
from denver.scheduler.trigger_engine import TriggerEngine

logger = get_logger("scheduler.registry")

# Strict prohibited patterns in routine action payloads
_DANGEROUS_ACTION_PATTERNS = re.compile(
    r"\b(eval|exec|os\.system|subprocess|powershell|cmd\.exe|__import__|importlib)\b",
    re.IGNORECASE,
)


class RoutineRegistry:
    """Manages the lifecycle, persistence, and validation of user routines."""

    def __init__(
        self,
        db: DenverDatabase,
        trigger_engine: TriggerEngine | None = None,
        audit_logger: RoutineAuditLogger | None = None,
        event_bus: DenverEventBus | None = None,
    ) -> None:
        self.db = db
        self.trigger_engine = trigger_engine or TriggerEngine()
        self.audit = audit_logger or RoutineAuditLogger(db)
        self.event_bus = event_bus or get_event_bus()

    def validate_action(self, action: RoutineAction) -> None:
        """Ensure action does not contain prohibited code execution patterns."""
        if not action.action_name or not action.action_name.strip():
            raise RoutineValidationError("Routine action must specify a non-empty 'action_name'.")

        payload_str = action.action_name + " " + str(action.params) + " " + action.description
        if _DANGEROUS_ACTION_PATTERNS.search(payload_str):
            raise RoutineValidationError(
                f"Prohibited code execution or shell pattern detected in action '{action.action_name}'."
            )

    async def create_routine(
        self,
        name: str,
        trigger: RoutineTrigger,
        actions: list[RoutineAction],
        description: str = "",
        enabled: bool = True,
        timezone_str: str = "UTC",
        notification_policy: NotificationPolicy = NotificationPolicy.ON_FAILURE,
        requires_confirmation: bool = False,
        metadata: dict[str, Any] | None = None,
        actor: str = "user",
    ) -> Routine:
        """Validate and create a new scheduled routine."""
        clean_name = name.strip()
        if not clean_name:
            raise RoutineValidationError("Routine name cannot be empty.")

        if not actions:
            raise RoutineValidationError("Routine must contain at least one action.")

        for act in actions:
            self.validate_action(act)

        # Validate trigger bounds
        self.trigger_engine.validate_trigger(trigger)

        # Check for duplicates by name or identical active trigger/action
        existing = await self.get_by_name(clean_name)
        if existing and existing.enabled:
            raise DuplicateRoutineError(f"An active routine named '{clean_name}' already exists.")

        # Compute initial next_run_at
        now_utc = datetime.now(timezone.utc)
        next_run = self.trigger_engine.compute_next_run(trigger, after_dt=now_utc) if enabled else None

        routine_id = f"rtn_{uuid.uuid4().hex[:8]}"
        routine = Routine(
            routine_id=routine_id,
            name=clean_name,
            description=description.strip(),
            enabled=enabled,
            status=RoutineStatus.ACTIVE if enabled else RoutineStatus.DISABLED,
            trigger=trigger,
            actions=actions,
            timezone=timezone_str,
            next_run_at=next_run,
            notification_policy=notification_policy,
            requires_confirmation=requires_confirmation,
            metadata=metadata or {},
            created_at=now_utc,
            updated_at=now_utc,
        )

        def _op(conn) -> Routine:
            repo = RoutineRepository(conn)
            return repo.save(routine)

        saved = await self.db.run_async(_op)
        logger.info("Created routine '%s' (ID: %s, Next Run: %s)", saved.name, saved.routine_id, saved.next_run_at)

        await self.audit.log_event(
            routine_id=saved.routine_id,
            event_type="routine_created",
            actor=actor,
            details={"name": saved.name, "trigger": trigger.to_dict()},
        )
        await self.event_bus.publish(
            RoutineCreated(
                routine_id=saved.routine_id,
                name=saved.name,
                trigger_type=trigger.trigger_type.value,
            )
        )
        return saved

    async def get_routine(self, routine_id: str) -> Routine | None:
        """Fetch routine by ID."""
        if not routine_id:
            return None

        def _op(conn) -> Routine | None:
            repo = RoutineRepository(conn)
            return repo.get(routine_id)

        return await self.db.run_async(_op)

    async def get_by_name(self, name: str) -> Routine | None:
        """Fetch routine by name."""
        if not name:
            return None

        def _op(conn) -> Routine | None:
            repo = RoutineRepository(conn)
            return repo.get_by_name(name)

        return await self.db.run_async(_op)

    async def list_routines(self, enabled_only: bool = False) -> list[Routine]:
        """List routines."""
        def _op(conn) -> list[Routine]:
            repo = RoutineRepository(conn)
            return repo.list_all(enabled_only=enabled_only)

        return await self.db.run_async(_op)

    async def enable_routine(self, routine_id: str, actor: str = "user") -> Routine:
        """Enable a routine and calculate its next execution time."""
        routine = await self.get_routine(routine_id)
        if not routine:
            raise RoutineNotFoundError(f"Routine '{routine_id}' not found.")

        routine.enabled = True
        routine.status = RoutineStatus.ACTIVE
        now_utc = datetime.now(timezone.utc)
        routine.next_run_at = self.trigger_engine.compute_next_run(routine.trigger, after_dt=now_utc)
        routine.updated_at = now_utc

        def _op(conn) -> Routine:
            repo = RoutineRepository(conn)
            return repo.save(routine)

        saved = await self.db.run_async(_op)
        logger.info("Enabled routine '%s' (Next Run: %s)", saved.name, saved.next_run_at)
        await self.audit.log_event(routine_id=routine_id, event_type="routine_enabled", actor=actor)
        await self.event_bus.publish(RoutineEnabled(routine_id=routine_id))
        return saved

    async def disable_routine(self, routine_id: str, actor: str = "user") -> Routine:
        """Disable a routine and clear its next execution time."""
        routine = await self.get_routine(routine_id)
        if not routine:
            raise RoutineNotFoundError(f"Routine '{routine_id}' not found.")

        routine.enabled = False
        routine.status = RoutineStatus.DISABLED
        routine.next_run_at = None
        routine.updated_at = datetime.now(timezone.utc)

        def _op(conn) -> Routine:
            repo = RoutineRepository(conn)
            return repo.save(routine)

        saved = await self.db.run_async(_op)
        logger.info("Disabled routine '%s'", saved.name)
        await self.audit.log_event(routine_id=routine_id, event_type="routine_disabled", actor=actor)
        await self.event_bus.publish(RoutineDisabled(routine_id=routine_id))
        return saved

    async def pause_routine(self, routine_id: str, actor: str = "user") -> Routine:
        """Pause routine without modifying its trigger schedule."""
        routine = await self.get_routine(routine_id)
        if not routine:
            raise RoutineNotFoundError(f"Routine '{routine_id}' not found.")

        routine.status = RoutineStatus.PAUSED
        routine.updated_at = datetime.now(timezone.utc)

        def _op(conn) -> Routine:
            repo = RoutineRepository(conn)
            return repo.save(routine)

        saved = await self.db.run_async(_op)
        await self.audit.log_event(routine_id=routine_id, event_type="routine_paused", actor=actor)
        return saved

    async def resume_routine(self, routine_id: str, actor: str = "user") -> Routine:
        """Resume a paused routine."""
        routine = await self.get_routine(routine_id)
        if not routine:
            raise RoutineNotFoundError(f"Routine '{routine_id}' not found.")

        routine.status = RoutineStatus.ACTIVE
        now_utc = datetime.now(timezone.utc)
        if routine.next_run_at is None or routine.next_run_at <= now_utc:
            routine.next_run_at = self.trigger_engine.compute_next_run(routine.trigger, after_dt=now_utc)
        routine.updated_at = now_utc

        def _op(conn) -> Routine:
            repo = RoutineRepository(conn)
            return repo.save(routine)

        saved = await self.db.run_async(_op)
        await self.audit.log_event(routine_id=routine_id, event_type="routine_resumed", actor=actor)
        return saved

    async def delete_routine(self, routine_id: str, actor: str = "user") -> bool:
        """Delete a routine and its execution history."""
        routine = await self.get_routine(routine_id)
        if not routine:
            raise RoutineNotFoundError(f"Routine '{routine_id}' not found.")

        def _op(conn) -> bool:
            repo = RoutineRepository(conn)
            return repo.delete(routine_id)

        deleted = await self.db.run_async(_op)
        if deleted:
            logger.info("Deleted routine '%s' (%s)", routine.name, routine_id)
            await self.audit.log_event(routine_id=routine_id, event_type="routine_deleted", actor=actor)
            await self.event_bus.publish(RoutineDeleted(routine_id=routine_id))
        return deleted

    async def seed_compound_routines(self, loader: Any | None = None) -> int:
        """Seed pre-configured compound routines from data/routines.json if not already in DB."""
        from denver.scheduler.compound_routines import get_compound_routine_loader
        c_loader = loader or get_compound_routine_loader()
        seeded_count = 0
        for c_def in c_loader.list_routines():
            existing = await self.get_routine(c_def.routine_id)
            if not existing:
                existing_by_name = await self.get_by_name(c_def.name)
                if not existing_by_name:
                    routine = c_def.to_routine()
                    def _op(conn) -> Routine:
                        repo = RoutineRepository(conn)
                        return repo.save(routine)
                    await self.db.run_async(_op)
                    seeded_count += 1
        if seeded_count > 0:
            logger.info("Seeded %d compound routines into database.", seeded_count)
        return seeded_count

