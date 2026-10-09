"""Continuous Background Email Monitor and Watcher Service for Denver."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from denver.automation.email.analyzer import EmailAnalyzer
from denver.automation.email.client import EmailClient
from denver.automation.email.models import EmailMessage, EmailMonitorConfig, EmailSummary
from denver.logging.logger import get_logger
from denver.runtime.event_bus import DenverEventBus, get_event_bus
from denver.runtime.events import (
    EmailMonitoringStateChanged,
    EmailReceived,
    EmailSummarized,
)

logger = get_logger("automation.email.monitor")


class EmailMonitor:
    """Continuous background watcher that polls inbox, summarizes new messages, and publishes events."""

    def __init__(
        self,
        config: EmailMonitorConfig | None = None,
        client: EmailClient | None = None,
        analyzer: EmailAnalyzer | None = None,
        event_bus: DenverEventBus | None = None,
    ) -> None:
        self.config = config or EmailMonitorConfig()
        self.client = client or EmailClient(self.config)
        self.analyzer = analyzer or EmailAnalyzer()
        self.event_bus = event_bus or get_event_bus()

        self._task: asyncio.Task[None] | None = None
        self._is_running: bool = False
        self._seen_uids: set[str] = set()
        self._recent_summaries: list[EmailSummary] = []
        self._last_poll_time: float = 0.0
        self._total_checked: int = 0
        self._lock = asyncio.Lock()

    @property
    def is_running(self) -> bool:
        """Return True if background monitoring loop is active."""
        return self._is_running

    async def start(self) -> bool:
        """Start the continuous email monitoring background task.

        Note: The background task initiates an immediate check_now() cycle on start.
        Callers seeking the initial batch of summaries should inspect
        `monitor.get_status()["recent_summaries"]` or listen to published
        EmailReceived / EmailSummarized events rather than immediately issuing a
        redundant check_now(), which may find the new emails already deduplicated.
        """
        async with self._lock:
            if self._is_running:
                logger.info("Email monitor is already running.")
                return True

            self._is_running = True
            self._task = asyncio.create_task(self._poll_loop(), name="denver-email-monitor")
            logger.info(
                "Started email monitor background task (interval=%.1fs, server=%s)",
                self.config.poll_interval_seconds,
                self.config.imap_server,
            )

            await self.event_bus.publish(
                EmailMonitoringStateChanged(
                    is_active=True,
                    poll_interval_seconds=self.config.poll_interval_seconds,
                    server=self.config.imap_server,
                )
            )
            return True

    async def stop(self) -> bool:
        """Stop the continuous email monitoring background task."""
        async with self._lock:
            if not self._is_running:
                return False

            self._is_running = False
            if self._task and not self._task.done():
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
                self._task = None

            await self.client.disconnect()
            logger.info("Stopped email monitor background task.")

            await self.event_bus.publish(
                EmailMonitoringStateChanged(
                    is_active=False,
                    poll_interval_seconds=self.config.poll_interval_seconds,
                    server=self.config.imap_server,
                )
            )
            return True

    async def _poll_loop(self) -> None:
        """Background continuous execution loop."""
        # Initial immediate check upon starting (populates _recent_summaries and dedup cache)
        try:
            await self.check_now()
        except Exception as exc:
            logger.warning("Initial email poll encountered error: %s", exc)

        while self._is_running:
            try:
                await asyncio.sleep(self.config.poll_interval_seconds)
                if not self._is_running:
                    break
                await self.check_now()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Error during email polling cycle: %s", exc)

    async def check_now(self, limit: int = 10) -> list[EmailSummary]:
        """Perform an immediate check for new/unread emails and analyze them."""
        self._last_poll_time = time.time()
        logger.debug("Executing email inbox check...")

        unread_messages = await self.client.fetch_unread(limit=limit)
        self._total_checked += len(unread_messages)

        new_messages = [msg for msg in unread_messages if msg.uid not in self._seen_uids]
        if not new_messages:
            logger.debug("No new unseen emails found.")
            return []

        logger.info("Found %d new unseen email(s). Analyzing content...", len(new_messages))
        new_summaries: list[EmailSummary] = []

        for msg in new_messages:
            self._seen_uids.add(msg.uid)

            # 1. Publish EmailReceived event
            await self.event_bus.publish(
                EmailReceived(
                    uid=msg.uid,
                    sender=msg.sender,
                    sender_name=msg.sender_name,
                    subject=msg.subject,
                    date=msg.date,
                    snippet=msg.snippet(),
                    has_attachments=msg.has_attachments,
                )
            )

            # 2. Analyze & summarize
            summary = await self.analyzer.analyze_message(msg)
            new_summaries.append(summary)

            # Store in recent cache (keep last 50)
            self._recent_summaries.insert(0, summary)
            if len(self._recent_summaries) > 50:
                self._recent_summaries.pop()

            # 3. Publish EmailSummarized event
            await self.event_bus.publish(
                EmailSummarized(
                    uid=summary.uid,
                    sender=summary.sender,
                    sender_name=summary.sender_name,
                    subject=summary.subject,
                    priority=summary.priority.value,
                    category=summary.category.value,
                    summary=summary.summary,
                    action_items=list(summary.action_items),
                    suggested_reply=summary.suggested_reply,
                )
            )

        return new_summaries

    def get_status(self) -> dict[str, Any]:
        """Return operational telemetry and status of the email monitor."""
        return {
            "is_running": self._is_running,
            "is_configured": self.config.is_configured(),
            "server": self.config.imap_server,
            "port": self.config.imap_port,
            "poll_interval_seconds": self.config.poll_interval_seconds,
            "last_poll_time": self._last_poll_time,
            "seen_emails_count": len(self._seen_uids),
            "total_checked_count": self._total_checked,
            "recent_summaries_count": len(self._recent_summaries),
            "recent_summaries": [s.to_dict() for s in self._recent_summaries[:5]],
        }
