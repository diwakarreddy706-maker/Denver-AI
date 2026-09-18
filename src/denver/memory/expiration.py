"""Memory Expiration and Lifecycle TTL Management."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from denver.memory.models import MemoryCategory, MemoryItem, PrivacyLevel


def compute_expiration_for_category(
    category: str | MemoryCategory,
    privacy_level: PrivacyLevel = PrivacyLevel.PRIVATE,
    default_ttl_hours: float | None = None,
) -> datetime | None:
    """Compute default expiration timestamp based on category and privacy tier."""
    now = datetime.now(timezone.utc)
    cat_val = category.value if isinstance(category, MemoryCategory) else str(category).lower()
    priv_val = privacy_level.value if isinstance(privacy_level, PrivacyLevel) else str(privacy_level).lower()

    if priv_val == "ephemeral":
        # Ephemeral defaults to 2 hours
        return datetime.fromtimestamp(now.timestamp() + 2 * 3600, tz=timezone.utc)

    if cat_val == "conversation":
        # Conversation context defaults to 24 hours
        return datetime.fromtimestamp(now.timestamp() + 24 * 3600, tz=timezone.utc)

    if cat_val in ("fact", "preference", "profile", "project"):
        # Long-term memories do not expire by default
        return None

    if default_ttl_hours is not None and default_ttl_hours > 0:
        return datetime.fromtimestamp(now.timestamp() + default_ttl_hours * 3600, tz=timezone.utc)

    return None


class ExpirationManager:
    """Filters active memories and executes safe TTL pruning."""

    @staticmethod
    def is_active(item: MemoryItem) -> bool:
        """Check if item is not deleted and not expired."""
        if item.is_deleted:
            return False
        return not item.is_expired

    @staticmethod
    def filter_active(items: Sequence[MemoryItem]) -> list[MemoryItem]:
        """Filter out expired or soft-deleted memories."""
        return [item for item in items if ExpirationManager.is_active(item)]
