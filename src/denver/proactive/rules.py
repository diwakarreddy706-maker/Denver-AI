"""Rule evaluators and heuristic triggers for Denver Proactive Intelligence."""

from __future__ import annotations

import abc
import time
from typing import Sequence

from denver.proactive.models import (
    ProactiveContext,
    ProactiveSuggestion,
    SuggestionCategory,
    SuggestionPriority,
)


class ProactiveRule(abc.ABC):
    """Abstract contract for context-aware autonomous trigger rules."""

    @property
    @abc.abstractmethod
    def rule_id(self) -> str:
        """Unique identifier for this rule."""

    @property
    @abc.abstractmethod
    def category(self) -> SuggestionCategory:
        """Category domain for cooldown grouping."""

    @abc.abstractmethod
    def evaluate(self, context: ProactiveContext) -> list[ProactiveSuggestion]:
        """Evaluate context and produce suggestions if criteria are satisfied."""


class BatteryHealthRule(ProactiveRule):
    """Monitors battery power levels to prevent unexpected workstation shutdowns."""

    @property
    def rule_id(self) -> str:
        return "rule_battery_health"

    @property
    def category(self) -> SuggestionCategory:
        return SuggestionCategory.HEALTH

    def evaluate(self, context: ProactiveContext) -> list[ProactiveSuggestion]:
        suggestions: list[ProactiveSuggestion] = []
        if context.battery_percent is None:
            return suggestions

        # Critical threshold: <= 15% and not plugged in
        if context.battery_percent <= 15.0 and context.battery_power_plugged is False:
            suggestions.append(
                ProactiveSuggestion(
                    id=f"sug_bat_crit_{int(time.time())}",
                    category=SuggestionCategory.HEALTH,
                    priority=SuggestionPriority.CRITICAL,
                    title="Battery Critically Low",
                    message=f"Battery level is at {int(context.battery_percent)}%. Please connect your charger immediately to prevent shutdown.",
                    suggested_action="system_summary",
                    confidence=1.0,
                )
            )
        # Warning threshold: <= 25% and not plugged in
        elif context.battery_percent <= 25.0 and context.battery_power_plugged is False:
            suggestions.append(
                ProactiveSuggestion(
                    id=f"sug_bat_warn_{int(time.time())}",
                    category=SuggestionCategory.HEALTH,
                    priority=SuggestionPriority.HIGH,
                    title="Low Battery Warning",
                    message=f"Battery is down to {int(context.battery_percent)}%. Consider plugging in your power adapter soon.",
                    confidence=0.95,
                )
            )

        return suggestions


class FocusFatigueRule(ProactiveRule):
    """Detects prolonged continuous screen focus and encourages ergonomics/hydration breaks."""

    def __init__(self, break_threshold_seconds: float = 3600.0) -> None:
        self.break_threshold_seconds = break_threshold_seconds

    @property
    def rule_id(self) -> str:
        return "rule_focus_fatigue"

    @property
    def category(self) -> SuggestionCategory:
        return SuggestionCategory.FATIGUE

    def evaluate(self, context: ProactiveContext) -> list[ProactiveSuggestion]:
        suggestions: list[ProactiveSuggestion] = []
        if context.continuous_work_seconds >= self.break_threshold_seconds:
            mins = int(context.continuous_work_seconds // 60)
            suggestions.append(
                ProactiveSuggestion(
                    id=f"sug_fatigue_{int(time.time())}",
                    category=SuggestionCategory.FATIGUE,
                    priority=SuggestionPriority.MEDIUM,
                    title="Ergonomics & Hydration Break",
                    message=f"You've been focused continuously for {mins} minutes. A quick 5-minute stretch and water break will recharge your energy.",
                    confidence=0.9,
                )
            )
        return suggestions


class RoutineOpportunityRule(ProactiveRule):
    """Suggests curated macro routines based on active development tools and time of day."""

    @property
    def rule_id(self) -> str:
        return "rule_routine_opportunity"

    @property
    def category(self) -> SuggestionCategory:
        return SuggestionCategory.ROUTINE

    def evaluate(self, context: ProactiveContext) -> list[ProactiveSuggestion]:
        suggestions: list[ProactiveSuggestion] = []
        proc = (context.active_window_process or "").lower()
        title = (context.active_window_title or "").lower()

        # Development environment suggestion
        if any(ide in proc or ide in title for ide in ["code", "pycharm", "visual studio", "sublime", "nvim"]):
            suggestions.append(
                ProactiveSuggestion(
                    id=f"sug_coding_mode_{int(time.time())}",
                    category=SuggestionCategory.ROUTINE,
                    priority=SuggestionPriority.LOW,
                    title="Activate Coding Mode",
                    message="Detected active IDE. Would you like me to trigger 'Coding Mode' to open project dashboards and optimize volume?",
                    suggested_action="run_routine_now",
                    suggested_params={"routine_id": "rtn_coding_mode"},
                    confidence=0.85,
                )
            )

        # End-of-day wrap-up suggestion (e.g. after 6 PM)
        if context.current_hour >= 18 and context.continuous_work_seconds > 1800:
            suggestions.append(
                ProactiveSuggestion(
                    id=f"sug_wrap_up_{int(time.time())}",
                    category=SuggestionCategory.ROUTINE,
                    priority=SuggestionPriority.LOW,
                    title="Wrap Up Work Session",
                    message="It's past 6 PM. Would you like to run 'Wrap Up Work' to save a daily summary note and audit system resources?",
                    suggested_action="run_routine_now",
                    suggested_params={"routine_id": "rtn_wrap_up_work"},
                    confidence=0.85,
                )
            )

        return suggestions


class PendingTaskReminderRule(ProactiveRule):
    """Proactively alerts on overdue or queued priority tasks."""

    @property
    def rule_id(self) -> str:
        return "rule_pending_tasks"

    @property
    def category(self) -> SuggestionCategory:
        return SuggestionCategory.TASK

    def evaluate(self, context: ProactiveContext) -> list[ProactiveSuggestion]:
        suggestions: list[ProactiveSuggestion] = []
        if context.pending_tasks_count > 0:
            top_task = context.pending_tasks_summary[0] if context.pending_tasks_summary else "pending action items"
            suggestions.append(
                ProactiveSuggestion(
                    id=f"sug_task_remind_{int(time.time())}",
                    category=SuggestionCategory.TASK,
                    priority=SuggestionPriority.MEDIUM,
                    title="Pending Tasks Reminder",
                    message=f"You have {context.pending_tasks_count} pending task(s). Next up: '{top_task}'.",
                    suggested_action="list_tasks",
                    confidence=0.8,
                )
            )
        return suggestions


class SystemResourceRule(ProactiveRule):
    """Monitors system memory saturation and CPU bottlenecks."""

    @property
    def rule_id(self) -> str:
        return "rule_system_resources"

    @property
    def category(self) -> SuggestionCategory:
        return SuggestionCategory.SYSTEM

    def evaluate(self, context: ProactiveContext) -> list[ProactiveSuggestion]:
        suggestions: list[ProactiveSuggestion] = []
        if context.memory_percent is not None and context.memory_percent >= 90.0:
            suggestions.append(
                ProactiveSuggestion(
                    id=f"sug_mem_high_{int(time.time())}",
                    category=SuggestionCategory.SYSTEM,
                    priority=SuggestionPriority.HIGH,
                    title="High Memory Usage Alert",
                    message=f"System RAM utilization is at {int(context.memory_percent)}%. Consider closing background browser tabs or idle processes.",
                    suggested_action="system_summary",
                    confidence=0.95,
                )
            )
        return suggestions
