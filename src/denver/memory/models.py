"""Data models and schemas for Denver Memory Subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PrivacyLevel(str, Enum):
    """Privacy classification for memory items and logs."""

    # Phase 1 legacy values (retained for backward compatibility)
    PUBLIC = "public"
    INTERNAL = "internal"
    SENSITIVE = "sensitive"
    CONFIDENTIAL = "confidential"

    # Phase 7 explicit classifications
    PUBLIC_CONTEXT = "public_context"
    PRIVATE = "private"
    EPHEMERAL = "ephemeral"

    @classmethod
    def from_value(cls, val: Any) -> PrivacyLevel:
        """Coerce string or enum into a valid PrivacyLevel."""
        if isinstance(val, PrivacyLevel):
            return val
        if isinstance(val, str):
            clean = val.strip().lower()
            for member in cls:
                if member.value == clean or member.name.lower() == clean:
                    return member
        return cls.PRIVATE

    @property
    def is_cloud_eligible(self) -> bool:
        """Determine if this privacy tier is allowed in cloud prompts by default."""
        return self in (PrivacyLevel.PUBLIC, PrivacyLevel.PUBLIC_CONTEXT)


class MemoryCategory(str, Enum):
    """Structured categories for long-term memory records."""

    FACT = "fact"
    PREFERENCE = "preference"
    PROFILE = "profile"
    PROJECT = "project"
    TASK = "task"
    PERSON = "person"
    CONTEXT = "context"
    CONVERSATION = "conversation"
    SYSTEM = "system"
    GENERAL = "general"  # Backward compatibility

    @classmethod
    def from_value(cls, val: Any) -> MemoryCategory:
        if isinstance(val, MemoryCategory):
            return val
        if isinstance(val, str):
            clean = val.strip().lower()
            for member in cls:
                if member.value == clean or member.name.lower() == clean:
                    return member
        return cls.GENERAL


@dataclass
class UserPreference:
    """Represents a persisted user configuration preference or profile attribute."""

    key: str
    value: str
    category: str = "general"
    confidence: float = 1.0
    source: str = "explicit_user"
    updated_at: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "category": self.category,
            "confidence": self.confidence,
            "source": self.source,
            "updated_at": self.updated_at.isoformat() if isinstance(self.updated_at, datetime) else str(self.updated_at),
        }


@dataclass
class Note:
    """Represents a persistent user note or saved memory."""

    id: int | None
    title: str
    content: str
    tags: list[str] = field(default_factory=list)
    is_pinned: bool = False
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "tags": self.tags,
            "is_pinned": self.is_pinned,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else str(self.created_at),
            "updated_at": self.updated_at.isoformat() if isinstance(self.updated_at, datetime) else str(self.updated_at),
        }


@dataclass
class Task:
    """Represents a scheduled task or reminder."""

    id: int | None
    task_text: str
    due_at: datetime | None = None
    is_completed: bool = False
    reminder_sent: bool = False
    created_at: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task_text": self.task_text,
            "due_at": self.due_at.isoformat() if isinstance(self.due_at, datetime) and self.due_at else None,
            "is_completed": self.is_completed,
            "reminder_sent": self.reminder_sent,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else str(self.created_at),
        }


@dataclass
class CommandHabit:
    """Represents frequency and execution history of user command habits."""

    command_phrase: str
    execution_count: int = 1
    last_executed_at: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "command_phrase": self.command_phrase,
            "execution_count": self.execution_count,
            "last_executed_at": (
                self.last_executed_at.isoformat()
                if isinstance(self.last_executed_at, datetime)
                else str(self.last_executed_at)
            ),
        }


@dataclass
class AuditRecord:
    """Represents a single command audit entry in the persistent audit log."""

    id: int | None
    raw_command: str
    routed_action: str
    provider_used: str
    status: str  # 'success', 'failed', 'blocked'
    latency_ms: float
    created_at: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "raw_command": self.raw_command,
            "routed_action": self.routed_action,
            "provider_used": self.provider_used,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else str(self.created_at),
        }


@dataclass
class MemoryItem:
    """Unified generic memory record with metadata, importance, confidence, TTL, and privacy classification."""

    id: int | None
    category: str | MemoryCategory  # e.g., 'fact', 'preference', 'project', 'profile'
    key: str
    content: str
    privacy_level: PrivacyLevel = PrivacyLevel.PRIVATE
    importance: float = 0.5  # 0.0 to 1.0
    confidence: float = 1.0  # 0.0 to 1.0
    source: str = "explicit_user"
    expires_at: datetime | None = None
    last_accessed_at: datetime = field(default_factory=_utc_now)
    embedding_status: str = "pending"  # 'pending', 'embedded', 'failed', 'none'
    embedding_model: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    is_deleted: bool = False
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if isinstance(self.privacy_level, str):
            self.privacy_level = PrivacyLevel.from_value(self.privacy_level)
        if isinstance(self.category, MemoryCategory):
            self.category = self.category.value
        elif isinstance(self.category, str):
            self.category = self.category.strip().lower()
        # Bound importance and confidence between 0.0 and 1.0
        self.importance = max(0.0, min(1.0, float(self.importance)))
        self.confidence = max(0.0, min(1.0, float(self.confidence)))

    @property
    def is_expired(self) -> bool:
        """Check if memory item has surpassed its expiration timestamp."""
        if self.expires_at is None:
            return False
        now = datetime.now(timezone.utc)
        exp = self.expires_at if self.expires_at.tzinfo else self.expires_at.replace(tzinfo=timezone.utc)
        return now > exp

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "key": self.key,
            "content": self.content,
            "privacy_level": self.privacy_level.value if isinstance(self.privacy_level, PrivacyLevel) else str(self.privacy_level),
            "importance": self.importance,
            "confidence": self.confidence,
            "source": self.source,
            "expires_at": self.expires_at.isoformat() if isinstance(self.expires_at, datetime) and self.expires_at else None,
            "last_accessed_at": self.last_accessed_at.isoformat() if isinstance(self.last_accessed_at, datetime) else str(self.last_accessed_at),
            "embedding_status": self.embedding_status,
            "embedding_model": self.embedding_model,
            "metadata": self.metadata,
            "is_deleted": self.is_deleted,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else str(self.created_at),
            "updated_at": self.updated_at.isoformat() if isinstance(self.updated_at, datetime) else str(self.updated_at),
        }


@dataclass
class MemorySearchResult:
    """Transparent search result record with retrieval explainability metrics."""

    memory: MemoryItem
    final_score: float
    semantic_score: float = 0.0
    keyword_score: float = 0.0
    importance_score: float = 0.0
    confidence_score: float = 0.0
    recency_score: float = 0.0
    retrieval_reason: str = "match"

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory": self.memory.to_dict(),
            "final_score": round(self.final_score, 4),
            "semantic_score": round(self.semantic_score, 4),
            "keyword_score": round(self.keyword_score, 4),
            "importance_score": round(self.importance_score, 4),
            "confidence_score": round(self.confidence_score, 4),
            "recency_score": round(self.recency_score, 4),
            "retrieval_reason": self.retrieval_reason,
        }


@dataclass
class SavedLocation:
    """Represents a persisted user saved location/address for navigation and weather."""

    label: str
    raw_address: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    latitude: float | None = None
    longitude: float | None = None
    id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "raw_address": self.raw_address,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else str(self.created_at),
            "updated_at": self.updated_at.isoformat() if isinstance(self.updated_at, datetime) else str(self.updated_at),
        }


@dataclass
class CachedLocation:
    """Represents a persisted cached live geolocation result."""

    latitude: float
    longitude: float
    city: str | None = None
    region: str | None = None
    country: str | None = None
    formatted_address: str | None = None
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    id: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "city": self.city,
            "region": self.region,
            "country": self.country,
            "formatted_address": self.formatted_address,
            "detected_at": self.detected_at.isoformat() if isinstance(self.detected_at, datetime) else str(self.detected_at),
        }

