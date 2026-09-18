"""Hybrid Semantic & Lexical Memory Search Coordinator."""

from __future__ import annotations

import difflib
import re
from typing import Sequence

from denver.memory.embeddings import EmbeddingManager, cosine_similarity
from denver.memory.expiration import ExpirationManager
from denver.memory.models import MemoryCategory, MemoryItem, MemorySearchResult, PrivacyLevel
from denver.memory.ranking import MemoryRanker


def _lexical_similarity(query: str, text: str) -> float:
    """Compute lexical score based on word token intersection and SequenceMatcher ratio."""
    if not query or not text:
        return 0.0
    q_words = set(re.findall(r"\b\w+\b", query.lower()))
    t_words = set(re.findall(r"\b\w+\b", text.lower()))
    if not q_words or not t_words:
        return 0.0

    overlap = len(q_words & t_words) / len(q_words)
    ratio = difflib.SequenceMatcher(None, query.lower(), text.lower()).ratio()
    return max(overlap, ratio)


class MemorySearchCoordinator:
    """Coordinates hybrid vector and lexical retrieval over active memory records."""

    def __init__(
        self,
        embedding_manager: EmbeddingManager,
        ranker: MemoryRanker | None = None,
    ) -> None:
        self.embedding_manager = embedding_manager
        self.ranker = ranker or MemoryRanker()

    async def search(
        self,
        query: str,
        active_items: Sequence[MemoryItem],
        embeddings_map: dict[int, list[float]],
        category: str | MemoryCategory | None = None,
        allowed_privacy: set[PrivacyLevel] | None = None,
        top_k: int = 8,
        min_score: float = 0.15,
    ) -> list[MemorySearchResult]:
        """Perform hybrid search over candidate items."""
        if not query or not query.strip():
            return []

        # 1. Filter out expired/deleted items
        valid_items = ExpirationManager.filter_active(active_items)

        # 2. Filter by category if specified
        if category:
            cat_str = category.value if isinstance(category, MemoryCategory) else str(category).lower()
            valid_items = [
                i for i in valid_items
                if (i.category.value if hasattr(i.category, "value") else str(i.category).lower()) == cat_str
            ]

        # 3. Filter by privacy level if specified
        if allowed_privacy:
            valid_items = [i for i in valid_items if i.privacy_level in allowed_privacy]

        if not valid_items:
            return []

        # 4. Generate query embedding
        query_vec, _ = await self.embedding_manager.embed(query)

        # 5. Score candidates
        scored_candidates: list[tuple[MemoryItem, float, float]] = []
        for item in valid_items:
            # Semantic score
            sem_score = 0.0
            if item.id and item.id in embeddings_map:
                sem_score = max(0.0, cosine_similarity(query_vec, embeddings_map[item.id]))

            # Lexical score (checking content + key)
            kw_content = _lexical_similarity(query, item.content)
            kw_key = _lexical_similarity(query, item.key)
            kw_score = max(kw_content, kw_key)

            scored_candidates.append((item, sem_score, kw_score))

        # 6. Rank candidates
        return self.ranker.rank_all(scored_candidates, top_k=top_k, min_score=min_score)
