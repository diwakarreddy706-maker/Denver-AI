"""Denver Email Automation and Continuous Inbox Intelligence Subsystem."""

from __future__ import annotations

from typing import Any

from denver.automation.email.analyzer import EmailAnalyzer
from denver.automation.email.client import EmailClient
from denver.automation.email.models import (
    EmailCategory,
    EmailDraft,
    EmailMessage,
    EmailMonitorConfig,
    EmailPriority,
    EmailSendResult,
    EmailSummary,
)
from denver.automation.email.monitor import EmailMonitor
from denver.logging.logger import get_logger

logger = get_logger("automation.email")

_global_monitor: EmailMonitor | None = None


def get_email_monitor(
    config: EmailMonitorConfig | None = None,
    client: EmailClient | None = None,
    analyzer: EmailAnalyzer | None = None,
    force_new: bool = False,
) -> EmailMonitor:
    """Get or initialize the global EmailMonitor instance."""
    global _global_monitor
    if _global_monitor is not None and not force_new:
        if config is not None or client is not None or analyzer is not None:
            logger.warning(
                "get_email_monitor called with custom config/client/analyzer, but a global "
                "monitor instance already exists. The passed arguments were ignored. "
                "Pass force_new=True to replace the existing instance."
            )
    if _global_monitor is None or force_new:
        if config is None:
            # Attempt to populate from DenverSettings
            try:
                from denver.config.settings import get_settings

                s = get_settings()
                config = EmailMonitorConfig(
                    enabled=getattr(s, "email_enabled", True),
                    imap_server=getattr(s, "email_imap_server", "imap.gmail.com"),
                    imap_port=getattr(s, "email_imap_port", 993),
                    smtp_server=getattr(s, "email_smtp_server", "smtp.gmail.com"),
                    smtp_port=getattr(s, "email_smtp_port", 587),
                    smtp_use_tls=getattr(s, "email_smtp_use_tls", True),
                    username=getattr(s, "email_username", ""),
                    password=getattr(s, "email_password", ""),
                    poll_interval_seconds=getattr(s, "email_poll_interval_seconds", 180.0),
                    is_mock=getattr(s, "email_mock_mode", False),
                )
            except Exception:
                config = EmailMonitorConfig()

        _global_monitor = EmailMonitor(config=config, client=client, analyzer=analyzer)
    return _global_monitor


__all__ = [
    "EmailCategory",
    "EmailDraft",
    "EmailMessage",
    "EmailMonitorConfig",
    "EmailPriority",
    "EmailSendResult",
    "EmailSummary",
    "EmailClient",
    "EmailAnalyzer",
    "EmailMonitor",
    "get_email_monitor",
]

