"""Denver Runtime States."""

from __future__ import annotations

from enum import Enum, unique


@unique
class DenverState(str, Enum):
    """Authoritative lifecycle and operating states of Denver AI Assistant."""

    BOOTING = "BOOTING"
    STANDBY = "STANDBY"
    LISTENING = "LISTENING"
    PROCESSING = "PROCESSING"
    EXECUTING = "EXECUTING"
    SPEAKING = "SPEAKING"
    ERROR = "ERROR"
    OFFLINE = "OFFLINE"
    SHUTTING_DOWN = "SHUTTING_DOWN"
    STOPPED = "STOPPED"

    def __str__(self) -> str:
        return self.value
