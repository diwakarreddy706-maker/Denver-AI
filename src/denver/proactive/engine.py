"""Autonomous Proactive Intelligence Engine for Denver.

Monitors contextual signals, evaluates trigger rules, enforces category-based
cooldowns, and dispatches actionable suggestions without interrupting flow.
"""

from __future__ import annotations

import collections
import time
from typing import Any, Callable

from denver.logging.logger import get_logger
from denver.proactive.models import (
    ProactiveContext,
    ProactiveSuggestion,
    SuggestionCategory,
    SuggestionPriority,
)
from denver.proactive.rules import (
    BatteryHealthRule,
    FocusFatigueRule,
    PendingTaskReminderRule,
    ProactiveRule,
    RoutineOpportunityRule,
    SystemResourceRule,
)
from denver.runtime.event_bus import DenverEventBus, get_event_bus

logger = get_logger("proactive.engine")


class ProactiveIntelligenceEngine:
    """Evaluates context telemetry against rules and emits throttled proactive suggestions."""

    def __init__(
        self,
        event_bus: DenverEventBus | None = None,
        enabled: bool = True,
        rules: list[ProactiveRule] | None = None,
    ) -> None:
        self.event_bus = event_bus or get_event_bus()
        self.enabled = enabled
        self._rules: list[ProactiveRule] = rules if rules is not None else [
            BatteryHealthRule(),
            FocusFatigueRule(),
            RoutineOpportunityRule(),
            PendingTaskReminderRule(),
            SystemResourceRule(),
        ]

        # Cooldown intervals in seconds to prevent spam
        self._cooldowns: dict[SuggestionCategory, float] = {
            SuggestionCategory.HEALTH: 300.0,    # 5 minutes
            SuggestionCategory.FATIGUE: 1800.0,  # 30 minutes
            SuggestionCategory.ROUTINE: 3600.0,  # 60 minutes
            SuggestionCategory.TASK: 1800.0,     # 30 minutes
            SuggestionCategory.SYSTEM: 600.0,    # 10 minutes
            SuggestionCategory.WORKFLOW: 1200.0, # 20 minutes
        }

        # Tracks last trigger timestamp per rule
        self._last_triggered: dict[str, float] = {}

        # Active pending suggestions
        self._active_suggestions: list[ProactiveSuggestion] = []
        self._history: collections.deque[ProactiveSuggestion] = collections.deque(maxlen=100)
        self._listeners: list[Callable[[ProactiveSuggestion], None]] = []

    @property
    def is_enabled(self) -> bool:
        return self.enabled

    def set_enabled(self, enabled: bool) -> None:
        """Toggle proactive intelligence engine."""
        self.enabled = enabled
        logger.info("Proactive Intelligence engine set to: %s", "ENABLED" if enabled else "DISABLED")

    def register_rule(self, rule: ProactiveRule) -> None:
        """Add custom proactive rule."""
        self._rules.append(rule)

    def register_listener(self, callback: Callable[[ProactiveSuggestion], None]) -> None:
        """Add callback for when a suggestion is emitted."""
        self._listeners.append(callback)

    def set_category_cooldown(self, category: SuggestionCategory, seconds: float) -> None:
        """Configure category cooldown duration."""
        self._cooldowns[category] = max(0.0, seconds)

    def evaluate(self, context: ProactiveContext) -> list[ProactiveSuggestion]:
        """Evaluate context against all registered rules respecting cooldown timers."""
        if not self.enabled:
            return []

        now = time.time()
        new_suggestions: list[ProactiveSuggestion] = []

        for rule in self._rules:
            rule_id = rule.rule_id
            cooldown = self._cooldowns.get(rule.category, 600.0)
            last_time = self._last_triggered.get(rule_id, 0.0)

            # Check if cooldown has elapsed
            if now - last_time < cooldown:
                continue

            try:
                matches = rule.evaluate(context)
                if matches:
                    self._last_triggered[rule_id] = now
                    for sug in matches:
                        new_suggestions.append(sug)
                        self._active_suggestions.append(sug)
                        self._history.append(sug)
                        # Notify listeners
                        for listener in self._listeners:
                            try:
                                listener(sug)
                            except Exception as exc:  # pylint: disable=broad-except
                                logger.debug("Listener callback failed: %s", exc)
            except Exception as exc:  # pylint: disable=broad-except
                logger.error("Error evaluating rule '%s': %s", rule_id, exc)

        return new_suggestions

    def get_active_suggestions(self) -> list[ProactiveSuggestion]:
        """Retrieve all currently active, non-dismissed suggestions."""
        return [s for s in self._active_suggestions if not s.dismissed and not s.accepted]

    def dismiss_suggestion(self, suggestion_id: str | None = None) -> int:
        """Dismiss a specific suggestion or all active suggestions."""
        dismissed_count = 0
        for s in self._active_suggestions:
            if suggestion_id is None or s.id == suggestion_id:
                if not s.dismissed:
                    s.dismissed = True
                    dismissed_count += 1
        return dismissed_count

    def accept_suggestion(self, suggestion_id: str) -> ProactiveSuggestion | None:
        """Mark a suggestion as accepted and return it."""
        for s in self._active_suggestions:
            if s.id == suggestion_id:
                s.accepted = True
                return s
        return None

    def clear(self) -> None:
        """Clear active suggestions and cooldown history."""
        self._active_suggestions.clear()
        self._last_triggered.clear()
