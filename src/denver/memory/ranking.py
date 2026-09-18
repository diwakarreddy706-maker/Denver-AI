"""Multi-Factor Deterministic Ranking and Retrieval Explainability Engine."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Sequence

from denver.memory.models import MemoryItem, MemorySearchResult


def compute_recency_score(updated_at: datetime | None, half_life_days: float = 30.0) -> float:
    """Calculate exponential recency decay score in [0.0, 1.0]."""
    if not updated_at:
        return 0.5
    now = datetime.now(timezone.utc)
    dt = updated_at if updated_at.tzinfo else updated_at.replace(tzinfo=timezone.utc)
    delta_seconds = max(0.0, (now - dt).total_seconds())
    delta_days = delta_seconds / 86400.0
    decay = math.exp(-0.693 * delta_days / half_life_days)
    return max(0.0, min(1.0, decay))


class MemoryRanker:
    """Combines semantic similarity, lexical relevance, importance, confidence, and recency."""

    def __init__(
        self,
        weight_semantic: float = 0.45,
        weight_keyword: float = 0.25,
        weight_importance: float = 0.15,
        weight_confidence: float = 0.10,
        weight_recency: float = 0.05,
    ) -> None:
        self.w_semantic = weight_semantic
        self.w_keyword = weight_keyword
        self.w_importance = weight_importance
        self.w_confidence = weight_confidence
        self.w_recency = weight_recency

    def rank_candidate(
        self,
        item: MemoryItem,
        semantic_score: float = 0.0,
        keyword_score: float = 0.0,
    ) -> MemorySearchResult:
        """Compute final combined score and explainability metrics for a memory candidate."""
        recency_score = compute_recency_score(item.updated_at)
        importance_score = item.importance
        confidence_score = item.confidence

        final_score = (
            (semantic_score * self.w_semantic)
            + (keyword_score * self.w_keyword)
            + (importance_score * self.w_importance)
            + (confidence_score * self.w_confidence)
            + (recency_score * self.w_recency)
        )

        reasons = []
        if semantic_score > 0.6:
            reasons.append(f"high semantic match ({semantic_score:.2f})")
        elif semantic_score > 0.3:
            reasons.append(f"semantic match ({semantic_score:.2f})")

        if keyword_score > 0.5:
            reasons.append(f"strong keyword match ({keyword_score:.2f})")
        elif keyword_score > 0.1:
            reasons.append("keyword overlap")

        if importance_score >= 0.8:
            reasons.append("high importance")

        if confidence_score >= 0.9:
            reasons.append("high confidence")

        if not reasons:
            reasons.append("context relevance")

        reason_str = ", ".join(reasons)

        return MemorySearchResult(
            memory=item,
            final_score=final_score,
            semantic_score=semantic_score,
            keyword_score=keyword_score,
            importance_score=importance_score,
            confidence_score=confidence_score,
            recency_score=recency_score,
            retrieval_reason=reason_str,
        )

    def rank_all(
        self,
        candidates: Sequence[tuple[MemoryItem, float, float]],  # (item, semantic_score, keyword_score)
        top_k: int = 10,
        min_score: float = 0.1,
    ) -> list[MemorySearchResult]:
        """Rank candidates and return top_k results above min_score threshold."""
        results = [
            self.rank_candidate(item, sem, kw)
            for item, sem, kw in candidates
        ]
        filtered = [r for r in results if r.final_score >= min_score]
        filtered.sort(key=lambda r: r.final_score, reverse=True)
        return filtered[:top_k]
