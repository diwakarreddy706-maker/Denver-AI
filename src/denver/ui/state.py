"""Observable Presentation State Model for Denver Cockpit."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from denver.runtime.states import DenverState


@dataclass
class ActivityItem:
    """Represents a single command or event entry in the Cockpit activity feed."""

    timestamp: float = field(default_factory=time.time)
    formatted_time: str = ""
    command_text: str = ""
    action_name: str = "custom"
    response_text: str = ""
    risk_level: str = "SAFE"
    success: bool = True
    latency_ms: float = 0.0
    error: str | None = None

    def __post_init__(self) -> None:
        if not self.formatted_time:
            self.formatted_time = time.strftime("%H:%M:%S", time.localtime(self.timestamp))


@dataclass
class ConfirmationItem:
    """Represents an active security confirmation request in the Cockpit."""

    token: str
    action_name: str
    description: str
    expires_at: float
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    @property
    def seconds_remaining(self) -> float:
        return max(0.0, self.expires_at - time.time())


@dataclass
class CockpitState:
    """Unified observable state model for Denver Cockpit GUI."""

    current_state: DenverState = DenverState.BOOTING
    state_reason: str = "Initializing Denver Core..."

    # Voice / Audio status
    voice_state: str = "INITIALIZING"
    microphone_available: bool = False
    microphone_active: bool = False
    stt_available: bool = False
    tts_available: bool = False
    current_transcript: str = ""
    current_response: str = ""

    # Telemetry
    cpu_percent: float | None = None
    ram_percent: float | None = None
    ram_used_gb: float | None = None
    ram_total_gb: float | None = None
    battery_percent: int | None = None
    battery_charging: bool | None = None
    network_connected: bool = True
    uptime_seconds: float = 0.0
    uptime_formatted: str = "00:00:00"

    # Subsystem Health
    ai_providers: dict[str, str] = field(default_factory=lambda: {
        "ollama": "UNAVAILABLE",
        "lmstudio": "UNAVAILABLE",
        "groq": "NOT_CONFIGURED",
        "gemini": "NOT_CONFIGURED",
    })
    automation_status: dict[str, str] = field(default_factory=lambda: {
        "applications": "READY",
        "windows": "READY",
        "volume": "READY",
        "browser": "READY",
        "screenshot": "READY",
        "system": "READY",
    })
    memory_status: dict[str, Any] = field(default_factory=lambda: {
        "database": "READY",
        "wal_mode": True,
        "memories_count": 0,
        "notes_count": 0,
        "tasks_count": 0,
        "privacy_mode": False,
    })

    # Activity Feed (capped to last 50 items)
    activity_history: list[ActivityItem] = field(default_factory=list)
    pending_confirmation: ConfirmationItem | None = None
    last_error: str | None = None

    def add_activity(self, item: ActivityItem) -> None:
        """Add an activity entry, maintaining maximum history depth."""
        self.activity_history.append(item)
        if len(self.activity_history) > 50:
            self.activity_history.pop(0)
