"""Deterministic Memory Deduplication and Memory Correction Engine."""

from __future__ import annotations

import difflib
import re
from typing import Sequence

from denver.memory.embeddings import cosine_similarity
from denver.memory.models import MemoryItem


def normalize_text(text: str) -> str:
    """Normalize text for consistent comparison."""
    if not text:
        return ""
    # Strip whitespace, lower case, collapse extra spaces and punctuation
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    return " ".join(cleaned.split())


class MemoryDeduplicator:
    """Detects exact duplicates and near-duplicates to update existing memory records cleanly."""

    def __init__(
        self,
        exact_threshold: float = 1.0,
        similarity_threshold: float = 0.85,
        vector_threshold: float = 0.88,
    ) -> None:
        self.exact_threshold = exact_threshold
        self.similarity_threshold = similarity_threshold
        self.vector_threshold = vector_threshold

    def find_duplicate(
        self,
        new_content: str,
        category: str,
        key: str,
        existing_items: Sequence[MemoryItem],
        new_embedding: list[float] | None = None,
        embeddings_map: dict[int, list[float]] | None = None,
    ) -> tuple[MemoryItem | None, str]:
        """Check if new memory matches an existing memory item.

        Returns (matching_item, match_type) where match_type is 'exact_key', 'exact_text', 'near_text', or 'vector'.
        """
        norm_new = normalize_text(new_content)
        norm_key = key.strip().lower()
        clean_cat = category.strip().lower()

        # 1. Exact Category + Key match
        for item in existing_items:
            if item.is_deleted:
                continue
            item_cat = item.category.value if hasattr(item.category, "value") else str(item.category).lower()
            if item_cat == clean_cat and item.key.strip().lower() == norm_key:
                return item, "exact_key"

        # 2. Exact Normalized Content Match within same category
        for item in existing_items:
            if item.is_deleted:
                continue
            item_cat = item.category.value if hasattr(item.category, "value") else str(item.category).lower()
            if item_cat == clean_cat:
                if normalize_text(item.content) == norm_new:
                    return item, "exact_text"

        # 3. String ratio near-duplicate match
        for item in existing_items:
            if item.is_deleted:
                continue
            item_cat = item.category.value if hasattr(item.category, "value") else str(item.category).lower()
            if item_cat == clean_cat:
                ratio = difflib.SequenceMatcher(None, norm_new, normalize_text(item.content)).ratio()
                if ratio >= self.similarity_threshold:
                    return item, f"near_text_{ratio:.2f}"

        # 4. Vector cosine similarity match if embeddings are present
        if new_embedding and embeddings_map:
            for item in existing_items:
                if item.is_deleted or item.id is None:
                    continue
                item_cat = item.category.value if hasattr(item.category, "value") else str(item.category).lower()
                if item_cat == clean_cat and item.id in embeddings_map:
                    sim = cosine_similarity(new_embedding, embeddings_map[item.id])
                    if sim >= self.vector_threshold:
                        return item, f"vector_{sim:.2f}"

        return None, "none"
