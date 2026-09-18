"""Data models for Denver Context Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from denver.memory.models import MemorySearchResult


@dataclass(frozen=True)
class ShortTermTurn:
    """A single conversational turn in the short-term context buffer."""

    role: str  # 'user', 'denver', 'system'
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
        }


@dataclass
class UserProfileContext:
    """Structured user profile attributes explicitly stored or configured."""

    name: str = "User"
    language: str = "en"
    preferred_editor: str | None = None
    custom_attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "language": self.language,
            "preferred_editor": self.preferred_editor,
            "custom_attributes": self.custom_attributes,
        }


@dataclass
class ContextBundle:
    """Complete assembled context bundle prepared for AI prompt generation."""

    short_term_context: list[ShortTermTurn]
    relevant_memories: list[MemorySearchResult]
    user_profile: UserProfileContext
    preferences: dict[str, str]
    context_string: str
    total_characters: int
    retrieval_reasons: list[str] = field(default_factory=list)
    privacy_decisions: dict[str, Any] = field(default_factory=dict)
    memories_used_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "short_term_turns": [t.to_dict() for t in self.short_term_context],
            "relevant_memories": [m.to_dict() for m in self.relevant_memories],
            "user_profile": self.user_profile.to_dict(),
            "preferences": self.preferences,
            "context_string_preview": self.context_string[:200] + "..." if len(self.context_string) > 200 else self.context_string,
            "total_characters": self.total_characters,
            "retrieval_reasons": self.retrieval_reasons,
            "privacy_decisions": self.privacy_decisions,
            "memories_used_count": self.memories_used_count,
        }
