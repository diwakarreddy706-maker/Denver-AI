"""Data models and schemas for Denver Email Automation and Intelligence."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, unique
from typing import Any


@unique
class EmailPriority(str, Enum):
    """Urgency / priority classification for incoming emails."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@unique
class EmailCategory(str, Enum):
    """Categorical classification of emails."""

    WORK = "WORK"
    PERSONAL = "PERSONAL"
    ALERT = "ALERT"
    FINANCIAL = "FINANCIAL"
    NEWSLETTER = "NEWSLETTER"
    SPAM = "SPAM"
    GENERAL = "GENERAL"


@dataclass(frozen=True)
class EmailMessage:
    """Standardized representation of an email message."""

    uid: str
    message_id: str = ""
    sender: str = ""
    sender_name: str = ""
    recipient: str = ""
    subject: str = ""
    date: str = ""
    timestamp: float = field(default_factory=time.time)
    body_text: str = ""
    body_html: str = ""
    has_attachments: bool = False
    attachment_names: tuple[str, ...] = ()
    is_read: bool = False
    flags: tuple[str, ...] = ()

    def snippet(self, max_chars: int = 150) -> str:
        """Return a clean snippet of the email body."""
        clean = " ".join((self.body_text or "").split())
        if len(clean) > max_chars:
            return clean[:max_chars].rstrip() + "..."
        return clean

    def to_dict(self) -> dict[str, Any]:
        """Convert email message to dictionary."""
        return {
            "uid": self.uid,
            "message_id": self.message_id,
            "sender": self.sender,
            "sender_name": self.sender_name,
            "recipient": self.recipient,
            "subject": self.subject,
            "date": self.date,
            "timestamp": self.timestamp,
            "snippet": self.snippet(),
            "has_attachments": self.has_attachments,
            "attachment_names": list(self.attachment_names),
            "is_read": self.is_read,
            "flags": list(self.flags),
        }


@dataclass(frozen=True)
class EmailSummary:
    """AI-powered summary and insights for an email message."""

    uid: str
    subject: str
    sender: str
    sender_name: str = ""
    priority: EmailPriority = EmailPriority.MEDIUM
    category: EmailCategory = EmailCategory.GENERAL
    summary: str = ""
    action_items: tuple[str, ...] = ()
    suggested_reply: str | None = None
    confidence: float = 1.0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Convert email summary to dictionary."""
        return {
            "uid": self.uid,
            "subject": self.subject,
            "sender": self.sender,
            "sender_name": self.sender_name,
            "priority": self.priority.value,
            "category": self.category.value,
            "summary": self.summary,
            "action_items": list(self.action_items),
            "suggested_reply": self.suggested_reply,
            "confidence": self.confidence,
            "created_at": self.created_at,
        }

    def format_display(self) -> str:
        """Format a human-readable display string suitable for assistant output."""
        sender_disp = f"{self.sender_name} <{self.sender}>" if self.sender_name else self.sender
        lines = [
            f"📧 **{self.subject or '(No Subject)'}**",
            f"From: {sender_disp}",
            f"Priority: [{self.priority.value}] | Category: [{self.category.value}]",
            f"Summary: {self.summary}",
        ]
        if self.action_items:
            lines.append("Action Items:")
            for item in self.action_items:
                lines.append(f"  • {item}")
        if self.suggested_reply:
            lines.append(f"Suggested Reply: \"{self.suggested_reply}\"")
        return "\n".join(lines)


@dataclass
class EmailDraft:
    """Represents an email draft staged for composition or sending."""

    to: str
    subject: str
    body: str
    cc: str = ""
    bcc: str = ""
    in_reply_to: str = ""
    references: str = ""
    draft_id: str = field(default_factory=lambda: f"draft-{int(time.time() * 1000)}")
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Convert draft to dictionary."""
        return {
            "draft_id": self.draft_id,
            "to": self.to,
            "subject": self.subject,
            "body": self.body,
            "cc": self.cc,
            "bcc": self.bcc,
            "in_reply_to": self.in_reply_to,
            "references": self.references,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class EmailSendResult:
    """Outcome payload following an email transmission attempt."""

    success: bool
    message: str
    recipient: str
    subject: str
    message_id: str = ""
    timestamp: float = field(default_factory=time.time)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert send result to dictionary."""
        return {
            "success": self.success,
            "message": self.message,
            "recipient": self.recipient,
            "subject": self.subject,
            "message_id": self.message_id,
            "timestamp": self.timestamp,
            "error": self.error,
        }


@dataclass
class EmailMonitorConfig:
    """Configuration settings for email monitoring, sending, and inbox analysis."""

    enabled: bool = True
    imap_server: str = "imap.gmail.com"
    imap_port: int = 993
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_use_tls: bool = True
    username: str = ""
    password: str = ""
    use_ssl: bool = True
    mailbox: str = "INBOX"
    poll_interval_seconds: float = 180.0
    auto_summarize: bool = True
    notify_high_priority_only: bool = False
    max_fetch_count: int = 10
    is_mock: bool = False

    def is_configured(self) -> bool:
        """Check if sufficient credentials are provided to connect to an IMAP/SMTP server."""
        return bool(self.username and self.password and not self.is_mock)

