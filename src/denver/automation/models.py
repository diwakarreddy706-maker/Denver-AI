"""Typed contracts and data models for Denver Desktop Automation Subsystem."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, unique
from pathlib import Path
from typing import Any


@unique
class AutomationRisk(str, Enum):
    """Risk tiers for system automation actions."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    BLOCKED = "BLOCKED"

    def to_command_risk(self) -> Any:
        from denver.commands.models import CommandRiskLevel
        if self == AutomationRisk.LOW:
            return CommandRiskLevel.LOW
        if self == AutomationRisk.MEDIUM:
            return CommandRiskLevel.MEDIUM
        if self == AutomationRisk.HIGH:
            return CommandRiskLevel.HIGH
        if self == AutomationRisk.BLOCKED:
            return CommandRiskLevel.BLOCKED
        return CommandRiskLevel.HIGH


@dataclass(frozen=True)
class ApplicationTarget:
    """Allowlisted application definition."""

    app_id: str
    display_name: str
    executable: str = ""
    executable_name: str = ""
    aliases: tuple[str, ...] = ()
    process_names: tuple[str, ...] = ()
    launch_args: tuple[str, ...] = ()
    is_uri_scheme: bool = False
    is_allowlisted: bool = True
    category: str = "general"
    description: str = ""

    def __post_init__(self) -> None:
        if not self.executable and self.executable_name:
            object.__setattr__(self, "executable", self.executable_name)
        elif not self.executable_name and self.executable:
            object.__setattr__(self, "executable_name", self.executable)

    def matches(self, query: str) -> bool:
        import re
        q = query.strip().lower()
        if q == self.app_id.lower() or q == self.display_name.lower():
            return True
        for alias in self.aliases:
            if q == alias.lower():
                return True
        
        # Strip common natural language articles and suffixes
        clean_q = re.sub(r"^(?:the|my|a|an)\s+", "", q).strip()
        clean_q = re.sub(r"\s+(?:app|application|program)$", "", clean_q).strip()
        if clean_q:
            if clean_q == self.app_id.lower() or clean_q == self.display_name.lower():
                return True
            for alias in self.aliases:
                if clean_q == alias.lower():
                    return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "app_id": self.app_id,
            "display_name": self.display_name,
            "executable": self.executable,
            "executable_name": self.executable_name,
            "aliases": list(self.aliases),
            "is_allowlisted": self.is_allowlisted,
            "category": self.category,
            "description": self.description,
        }


@dataclass(frozen=True)
class WindowTarget:
    """Target criteria for window management."""

    title_query: str = ""
    operation: str = "focus"
    query: str = ""
    exact_match: bool = False
    handle: int | None = None
    process_name: str | None = None

    def __post_init__(self) -> None:
        if not self.query and self.title_query:
            object.__setattr__(self, "query", self.title_query)
        elif not self.title_query and self.query:
            object.__setattr__(self, "title_query", self.query)


@dataclass(frozen=True)
class WindowInfo:
    """Discovered window metadata."""

    hwnd: int = 0
    title: str = ""
    process_name: str = ""
    handle: int = 0
    process_id: int = 0
    is_visible: bool = True
    is_minimized: bool = False
    is_maximized: bool = False

    def __post_init__(self) -> None:
        if not self.handle and self.hwnd:
            object.__setattr__(self, "handle", self.hwnd)
        elif not self.hwnd and self.handle:
            object.__setattr__(self, "hwnd", self.handle)

    def to_dict(self) -> dict[str, Any]:
        return {
            "hwnd": self.hwnd,
            "handle": self.handle,
            "title": self.title,
            "process_id": self.process_id,
            "process_name": self.process_name,
            "is_visible": self.is_visible,
            "is_minimized": self.is_minimized,
            "is_maximized": self.is_maximized,
        }


@dataclass(frozen=True)
class VolumeCommand:
    """Parameters for audio volume control."""

    action: str = "set"
    level_percent: int | None = None
    step_percent: int = 10
    operation: str = "set"
    value: int | None = None
    step: int = 10

    def __post_init__(self) -> None:
        if not self.operation and self.action:
            object.__setattr__(self, "operation", self.action)
        if self.value is None and self.level_percent is not None:
            object.__setattr__(self, "value", self.level_percent)
        if self.level_percent is None and self.value is not None:
            object.__setattr__(self, "level_percent", self.value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "operation": self.operation,
            "level_percent": self.level_percent,
            "value": self.value,
            "step_percent": self.step_percent,
            "step": self.step,
        }


@dataclass(frozen=True)
class BrowserTarget:
    """Safe URL and browser target specification."""

    url: str
    site_name: str = ""
    browser_name: str = "default"
    aliases: tuple[str, ...] = ()
    is_allowlisted: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "site_name": self.site_name,
            "browser_name": self.browser_name,
            "aliases": list(self.aliases),
            "is_allowlisted": self.is_allowlisted,
        }


@dataclass(frozen=True)
class ScreenshotResult:
    """Metadata generated from a screenshot capture."""

    file_path: Path | str
    file_size_bytes: int
    width: int
    height: int
    timestamp: float = field(default_factory=time.time)
    format: str = "PNG"

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": str(self.file_path),
            "file_size_bytes": self.file_size_bytes,
            "width": self.width,
            "height": self.height,
            "timestamp": self.timestamp,
            "format": self.format,
        }


@dataclass(frozen=True)
class ConfirmationRequirement:
    """Pending confirmation bound to an exact high-risk action request."""

    token: str
    action_name: str
    action_params: dict[str, Any]
    prompt_message: str
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    is_consumed: bool = False

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at


@dataclass(frozen=True)
class AutomationAction:
    """Complete specification of a registered automation capability."""

    action_id: str
    action_type: str
    description: str = ""
    target: str = ""
    risk_level: AutomationRisk = AutomationRisk.LOW
    requires_confirmation: bool = False
    parameters_schema: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AutomationRequest:
    """Unified request structure for automation operations."""

    action_name: str
    target: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 10.0
    confirmation_token: str | None = None


@dataclass
class AutomationResult:
    """Structured result returned by the automation engine."""

    success: bool
    action: str
    target: str = ""
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    risk_level: AutomationRisk = AutomationRisk.LOW
    requires_confirmation: bool = False
    confirmation_token: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "action": self.action,
            "target": self.target,
            "message": self.message,
            "data": self.data,
            "risk_level": self.risk_level.value,
            "requires_confirmation": self.requires_confirmation,
            "confirmation_token": self.confirmation_token,
            "error": self.error,
        }
