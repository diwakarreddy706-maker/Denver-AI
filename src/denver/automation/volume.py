"""Safe Windows Volume and Audio Control for Denver."""

from __future__ import annotations

from typing import Any

from denver.automation.models import AutomationResult, AutomationRisk, VolumeCommand
from denver.automation.windows import (
    VK_VOLUME_DOWN,
    VK_VOLUME_MUTE,
    VK_VOLUME_UP,
    WindowsNativeAPI,
)
from denver.logging.logger import get_logger

logger = get_logger("automation.volume")


class VolumeController:
    """Controls Windows endpoint audio levels and mute states via native APIs."""

    def __init__(self, native_api: WindowsNativeAPI | None = None) -> None:
        self.api = native_api or WindowsNativeAPI()
        self._approx_volume = 50  # baseline state tracking

    def get_volume(self) -> AutomationResult:
        """Query current volume state."""
        return AutomationResult(
            success=True,
            action="get_volume",
            message=f"System audio volume is operational.",
            data={"approx_volume": self._approx_volume},
            risk_level=AutomationRisk.LOW,
        )

    def set_volume(self, value_pct: int) -> AutomationResult:
        """Set volume to target percentage (0-100)."""
        clamped = max(0, min(100, int(value_pct)))
        diff = clamped - self._approx_volume

        if diff > 0:
            steps = max(1, diff // 2)
            self.api.send_volume_key(VK_VOLUME_UP, times=steps)
        elif diff < 0:
            steps = max(1, abs(diff) // 2)
            self.api.send_volume_key(VK_VOLUME_DOWN, times=steps)

        self._approx_volume = clamped
        logger.info("Adjusted system volume to ~%d%%", clamped)
        return AutomationResult(
            success=True,
            action="set_volume",
            message=f"Volume set to {clamped} percent.",
            data={"volume": clamped},
            risk_level=AutomationRisk.MEDIUM,
        )

    def increase_volume(self, step: int = 10) -> AutomationResult:
        """Increase system volume by step percentage."""
        steps = max(1, step // 2)
        self.api.send_volume_key(VK_VOLUME_UP, times=steps)
        self._approx_volume = min(100, self._approx_volume + step)
        logger.info("Increased system volume by %d%%", step)
        return AutomationResult(
            success=True,
            action="increase_volume",
            message=f"Increased volume.",
            data={"step": step, "approx_volume": self._approx_volume},
            risk_level=AutomationRisk.MEDIUM,
        )

    def decrease_volume(self, step: int = 10) -> AutomationResult:
        """Decrease system volume by step percentage."""
        steps = max(1, step // 2)
        self.api.send_volume_key(VK_VOLUME_DOWN, times=steps)
        self._approx_volume = max(0, self._approx_volume - step)
        logger.info("Decreased system volume by %d%%", step)
        return AutomationResult(
            success=True,
            action="decrease_volume",
            message=f"Decreased volume.",
            data={"step": step, "approx_volume": self._approx_volume},
            risk_level=AutomationRisk.MEDIUM,
        )

    def mute(self) -> AutomationResult:
        """Toggle or engage volume mute."""
        self.api.send_volume_key(VK_VOLUME_MUTE, times=1)
        logger.info("Toggled audio mute.")
        return AutomationResult(
            success=True,
            action="mute_volume",
            message="Muted audio.",
            data={"is_muted": True},
            risk_level=AutomationRisk.MEDIUM,
        )

    def unmute(self) -> AutomationResult:
        """Unmute system audio."""
        # Sending volume up unmutes on Windows
        self.api.send_volume_key(VK_VOLUME_UP, times=1)
        logger.info("Unmuted audio.")
        return AutomationResult(
            success=True,
            action="unmute_volume",
            message="Unmuted audio.",
            data={"is_muted": False},
            risk_level=AutomationRisk.MEDIUM,
        )
