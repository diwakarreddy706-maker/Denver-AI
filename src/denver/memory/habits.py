"""Learned Habits Engine & Pattern Inference Subsystem for Denver Memory (Pillar 3)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from denver.logging.logger import get_logger
from denver.memory.database import DenverDatabase
from denver.memory.models import LearnedHabit
from denver.memory.repositories import LearnedHabitsRepository

logger = get_logger("habits")


class LearnedHabitsEngine:
    """Infers recurring usage habits, projects, tools, and work hours to personalize Denver's behavior."""

    def __init__(self, db: DenverDatabase, repo: LearnedHabitsRepository | None = None) -> None:
        self.db = db
        self._repo = repo

    def _get_repo(self, conn: Any) -> LearnedHabitsRepository:
        return LearnedHabitsRepository(conn)

    async def record_observation(
        self,
        category: str,
        habit_key: str,
        habit_value: str,
        confidence_boost: float = 0.1,
    ) -> LearnedHabit:
        """Record an observed usage pattern, incrementing frequency and confidence."""
        def _record(conn: Any) -> LearnedHabit:
            repo = self._get_repo(conn)
            return repo.record_observation(
                category=category,
                habit_key=habit_key,
                habit_value=habit_value,
                confidence_boost=confidence_boost,
            )

        habit = await self.db.run_async(_record)
        logger.debug(
            "Recorded habit observation: [%s] '%s' -> '%s' (freq: %d, conf: %.2f)",
            habit.category,
            habit.habit_key,
            habit.habit_value,
            habit.frequency,
            habit.confidence,
        )
        return habit

    async def get_habit(self, habit_key: str) -> LearnedHabit | None:
        """Retrieve a specific learned habit by its unique key."""
        def _get(conn: Any) -> LearnedHabit | None:
            repo = self._get_repo(conn)
            return repo.get_habit(habit_key)

        return await self.db.run_async(_get)

    async def list_habits(
        self,
        category: str | None = None,
        min_confidence: float = 0.0,
        limit: int = 50,
    ) -> list[LearnedHabit]:
        """List learned habits matching category or confidence thresholds."""
        def _list(conn: Any) -> list[LearnedHabit]:
            repo = self._get_repo(conn)
            return repo.list_habits(category=category, min_confidence=min_confidence, limit=limit)

        return await self.db.run_async(_list)

    async def delete_habit(self, habit_id: int) -> bool:
        """Delete a habit by ID."""
        def _del(conn: Any) -> bool:
            repo = self._get_repo(conn)
            return repo.delete_habit(habit_id)

        return await self.db.run_async(_del)

    async def clear_habits(self) -> int:
        """Clear all learned habits."""
        def _clear(conn: Any) -> int:
            repo = self._get_repo(conn)
            return repo.clear_habits()

        return await self.db.run_async(_clear)

    async def get_habit_suggestions(self, min_confidence: float = 0.6) -> list[str]:
        """Generate actionable natural-language proactive suggestions based on high-confidence habits."""
        habits = await self.list_habits(min_confidence=min_confidence)
        suggestions: list[str] = []

        for h in habits:
            cat = h.category.lower()
            if cat in ("project", "workspace"):
                suggestions.append(f"You frequently work on {h.habit_value}. Would you like to resume your workspace?")
            elif cat in ("app", "editor", "tool"):
                suggestions.append(f"Your primary tool is {h.habit_value}. Ready to open it?")
            elif cat in ("routine", "macro"):
                suggestions.append(f"You often run the '{h.habit_value}' routine during your sessions.")
            elif cat in ("work_hours", "schedule"):
                suggestions.append(f"Detected primary active hours: {h.habit_value}.")

        return suggestions

    async def format_prompt_habits(self, min_confidence: float = 0.6) -> str:
        """Format an authoritative markdown block of learned habits for LLM prompt context."""
        habits = await self.list_habits(min_confidence=min_confidence, limit=10)
        if not habits:
            return ""

        lines = ["[LEARNED USER HABITS & PATTERNS]"]
        lines.append("The following behavioral patterns and preferences have been learned from past usage:")
        for h in habits:
            lines.append(f"- [{h.category.upper()}] {h.habit_key}: {h.habit_value} (Confidence: {int(h.confidence * 100)}%, Observed {h.frequency}x)")

        return "\n".join(lines)
