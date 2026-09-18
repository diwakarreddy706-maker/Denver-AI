"""Notification Dispatcher & Rate Limiter for Scheduled Routines."""

from __future__ import annotations

import time
from typing import Any

from denver.logging.logger import get_logger, mask_sensitive_data
from denver.runtime.event_bus import DenverEventBus, get_event_bus
from denver.runtime.events import RoutineNotificationSent
from denver.scheduler.models import NotificationPolicy

logger = get_logger("scheduler.notifications")


class RoutineNotificationService:
    """Dispatches routine execution notifications with storm prevention and rate limiting."""

    def __init__(
        self,
        event_bus: DenverEventBus | None = None,
        rate_limit_seconds: float = 10.0,
    ) -> None:
        self.event_bus = event_bus or get_event_bus()
        self.rate_limit_seconds = rate_limit_seconds
        self._last_notification_times: dict[str, float] = {}

    def should_notify(self, policy: NotificationPolicy, success: bool) -> bool:
        """Evaluate if a notification is permitted based on routine policy."""
        if policy == NotificationPolicy.NEVER:
            return False
        if policy == NotificationPolicy.ALWAYS:
            return True
        if policy == NotificationPolicy.ON_FAILURE:
            return not success
        return False

    def is_rate_limited(self, routine_id: str) -> bool:
        """Check if notification is rate-limited to avoid user spam."""
        now = time.time()
        last = self._last_notification_times.get(routine_id, 0.0)
        if (now - last) < self.rate_limit_seconds:
            return True
        return False

    async def notify(
        self,
        routine_id: str,
        title: str,
        message: str,
        policy: NotificationPolicy = NotificationPolicy.ALWAYS,
        success: bool = True,
        force: bool = False,
    ) -> bool:
        """Dispatch a notification if allowed by policy and rate limits."""
        if not force and not self.should_notify(policy, success):
            return False

        if not force and self.is_rate_limited(routine_id):
            logger.debug("Notification for routine '%s' dropped due to rate limit.", routine_id)
            return False

        clean_title = mask_sensitive_data(title)
        clean_msg = mask_sensitive_data(message)
        self._last_notification_times[routine_id] = time.time()

        logger.info("[ROUTINE NOTIFICATION] [%s] %s: %s", routine_id, clean_title, clean_msg)
        await self.event_bus.publish(
            RoutineNotificationSent(
                routine_id=routine_id,
                title=clean_title,
                message=clean_msg,
                status="sent",
            )
        )
        return True
