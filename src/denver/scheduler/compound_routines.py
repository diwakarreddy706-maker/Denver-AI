"""Compound Routines & Workflow Definitions Loader for Denver AI Assistant."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from denver.logging.logger import get_logger
from denver.scheduler.models import (
    NotificationPolicy,
    Routine,
    RoutineAction,
    RoutineStatus,
    RoutineTrigger,
    TriggerType,
)

logger = get_logger("scheduler.compound_routines")


@dataclass
class CompoundRoutineDefinition:
    """Pre-configured compound routine structure with natural language trigger phrases."""

    routine_id: str
    name: str
    description: str
    triggers: list[str]
    actions: list[RoutineAction]
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_routine(self) -> Routine:
        """Convert compound routine into a Denver Routine model."""
        return Routine(
            routine_id=self.routine_id,
            name=self.name,
            description=self.description,
            enabled=self.enabled,
            status=RoutineStatus.ACTIVE if self.enabled else RoutineStatus.DISABLED,
            trigger=RoutineTrigger(trigger_type=TriggerType.ONE_TIME),
            actions=self.actions,
            notification_policy=NotificationPolicy.ALWAYS,
            metadata={
                "triggers": self.triggers,
                "is_compound": True,
                **self.metadata,
            },
        )

    def matches_phrase(self, text: str) -> bool:
        """Check if a spoken or written text matches any configured trigger phrases."""
        clean_text = re.sub(r"[^\w\s]", "", text.strip().lower())
        for trig in self.triggers:
            clean_trig = re.sub(r"[^\w\s]", "", trig.strip().lower())
            if clean_text == clean_trig or clean_text == f"start {clean_trig}" or clean_text == f"activate {clean_trig}":
                return True
        return False


class CompoundRoutineLoader:
    """Loads, validates, and discovers compound routines from JSON configuration."""

    def __init__(self, file_path: str | Path | None = None) -> None:
        if file_path is None:
            # Default to data/routines.json relative to project root
            base_dir = Path(__file__).resolve().parent.parent.parent.parent
            self.file_path = base_dir / "data" / "routines.json"
        else:
            self.file_path = Path(file_path)

        self._routines: dict[str, CompoundRoutineDefinition] = {}
        self.load()

    def load(self) -> dict[str, CompoundRoutineDefinition]:
        """Load routines from file path."""
        self._routines.clear()
        if not self.file_path.exists():
            logger.warning("Compound routines file not found at: %s", self.file_path)
            return self._routines

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                payload = json.load(f)

            raw_routines = payload.get("routines", [])
            for item in raw_routines:
                actions = [
                    RoutineAction(
                        action_name=act.get("action_name", ""),
                        params=act.get("params", {}),
                        description=act.get("description", ""),
                    )
                    for act in item.get("actions", [])
                ]
                r_def = CompoundRoutineDefinition(
                    routine_id=item.get("routine_id", ""),
                    name=item.get("name", ""),
                    description=item.get("description", ""),
                    triggers=item.get("triggers", []),
                    actions=actions,
                    enabled=item.get("enabled", True),
                    metadata=item.get("metadata", {}),
                )
                if r_def.routine_id:
                    self._routines[r_def.routine_id] = r_def

            logger.info("Loaded %d compound routines from %s", len(self._routines), self.file_path)
        except Exception as exc:
            logger.error("Failed to load compound routines from %s: %s", self.file_path, exc)

        return self._routines

    def list_routines(self) -> list[CompoundRoutineDefinition]:
        """Return all loaded compound routines."""
        return list(self._routines.values())

    def get_by_id(self, routine_id: str) -> CompoundRoutineDefinition | None:
        """Find routine definition by routine_id."""
        return self._routines.get(routine_id)

    def find_by_name_or_trigger(self, query: str) -> CompoundRoutineDefinition | None:
        """Search compound routine by name, ID, or trigger phrase."""
        clean = query.strip().lower()
        # Direct ID match
        if clean in self._routines:
            return self._routines[clean]

        # Name match
        for r in self._routines.values():
            if r.name.lower() == clean or r.name.lower().replace(" ", "_") == clean:
                return r

        # Trigger match
        for r in self._routines.values():
            if r.matches_phrase(query):
                return r

        return None


_default_loader: CompoundRoutineLoader | None = None


def get_compound_routine_loader() -> CompoundRoutineLoader:
    """Singleton getter for CompoundRoutineLoader."""
    global _default_loader
    if _default_loader is None:
        _default_loader = CompoundRoutineLoader()
    return _default_loader
