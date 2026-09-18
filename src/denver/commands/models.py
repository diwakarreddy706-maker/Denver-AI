"""Domain models and typed schemas for the Denver Command Engine."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CommandRiskLevel(str, Enum):
    """Safety risk classification for requested actions."""

    SAFE = "SAFE"        # Read-only information queries (time, date, status, list)
    LOW = "LOW"          # Low-impact state changes (create note, save preference)
    MEDIUM = "MEDIUM"    # Moderate impact (close app, complete task, delete memory)
    HIGH = "HIGH"        # High-impact system operations (shutdown, restart)
    BLOCKED = "BLOCKED"  # Strictly prohibited operations (arbitrary shell execution, injection)


class CommandCategory(str, Enum):
    """Functional categories for commands."""

    APPLICATION = "application"
    SYSTEM = "system"
    MEMORY = "memory"
    TASK = "task"
    NOTE = "note"
    UTILITY = "utility"
    ROUTINE = "routine"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CommandContext:
    """Contextual metadata surrounding a command execution."""

    user_profile: dict[str, Any] = field(default_factory=dict)
    active_window: str | None = None
    session_id: str | None = None
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class CommandRequest:
    """Incoming user command representation."""

    raw_text: str
    source: str = "text"  # text, voice, cli, hotkey
    session_id: str | None = None
    context: CommandContext = field(default_factory=CommandContext)


@dataclass(frozen=True)
class CommandIntent:
    """Resolved intent classification produced by the router."""

    intent_name: str
    action_name: str
    category: CommandCategory
    confidence: float = 1.0
    params: dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = False
    risk_level: CommandRiskLevel = CommandRiskLevel.SAFE

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent_name,
            "action": self.action_name,
            "category": self.category.value,
            "confidence": self.confidence,
            "params": self.params,
            "requires_confirmation": self.requires_confirmation,
            "risk_level": self.risk_level.value,
        }


@dataclass(frozen=True)
class ActionRequest:
    """Validated action request dispatched to the execution layer."""

    action_name: str
    params: dict[str, Any] = field(default_factory=dict)
    risk_level: CommandRiskLevel = CommandRiskLevel.SAFE
    requires_confirmation: bool = False
    request_id: str | None = None


@dataclass
class ActionResult:
    """Outcome of an action execution."""

    success: bool
    message: str
    action_name: str
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "action": self.action_name,
            "data": self.data,
            "error": self.error,
            "latency_ms": self.latency_ms,
        }


@dataclass
class CommandResponse:
    """Structured response returned by the Denver Command Engine to callers."""

    success: bool
    message: str
    action_name: str | None
    data: dict[str, Any] = field(default_factory=dict)
    risk_level: CommandRiskLevel = CommandRiskLevel.SAFE
    confidence: float = 1.0
    latency_ms: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "action": self.action_name,
            "data": self.data,
            "risk": self.risk_level.value,
            "confidence": self.confidence,
            "latency_ms": self.latency_ms,
            "error": self.error,
        }
