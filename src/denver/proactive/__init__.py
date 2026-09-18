"""Autonomous Proactive Intelligence Subsystem for Denver."""

from denver.proactive.engine import ProactiveIntelligenceEngine
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

__all__ = [
    "BatteryHealthRule",
    "FocusFatigueRule",
    "PendingTaskReminderRule",
    "ProactiveContext",
    "ProactiveIntelligenceEngine",
    "ProactiveRule",
    "ProactiveSuggestion",
    "RoutineOpportunityRule",
    "SuggestionCategory",
    "SuggestionPriority",
    "SystemResourceRule",
]
