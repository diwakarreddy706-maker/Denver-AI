"""Unit tests for Phase 7 embedding providers, deduplication, ranking, and hybrid search."""

from __future__ import annotations

from datetime import datetime, timezone
import pytest

from denver.memory.deduplication import MemoryDeduplicator
from denver.memory.embeddings import (
    DeterministicLexicalEmbedder,
    EmbeddingManager,
    cosine_similarity,
)
from denver.memory.models import MemoryCategory, MemoryItem, PrivacyLevel
from denver.memory.ranking import MemoryRanker, compute_recency_score
from denver.memory.search import MemorySearchCoordinator


@pytest.mark.asyncio
async def test_deterministic_lexical_embedder() -> None:
    """Verify deterministic lexical embedder is 100% stable and computes cosine similarity."""
    embedder = DeterministicLexicalEmbedder(dimension=128)
    assert embedder.dimension == 128
    assert embedder.name == "deterministic_lexical"

    v1 = await embedder.embed_text("SentinelJob fake job detector")
    v2 = await embedder.embed_text("SentinelJob fake job detector")
    assert v1 == v2
    assert len(v1) == 128

    # Related query should have high cosine similarity
    v3 = await embedder.embed_text("fake job detection platform SentinelJob")
    sim_related = cosine_similarity(v1, v3)
    assert sim_related > 0.6

    # Unrelated query should have lower similarity
    v4 = await embedder.embed_text("cooking pasta with tomato sauce")
    sim_unrelated = cosine_similarity(v1, v4)
    assert sim_unrelated < sim_related


@pytest.mark.asyncio
async def test_embedding_manager_fallback() -> None:
    """Verify EmbeddingManager uses fallback when primary is None or unavailable."""
    mgr = EmbeddingManager(primary_provider=None, enabled=True)
    vec, model = await mgr.embed("Test text")
    assert len(vec) == 128
    assert model == "denver-lexical-v1"

    health = await mgr.get_health_status()
    assert health["enabled"] is True
    assert health["fallback"]["status"] == "READY"


def test_memory_deduplicator() -> None:
    """Verify deduplication detects exact key, exact text, near text, and vector matches."""
    dedup = MemoryDeduplicator()

    item1 = MemoryItem(
        id=1,
        category="preference",
        key="editor",
        content="User prefers Antigravity editor.",
    )
    item2 = MemoryItem(
        id=2,
        category="fact",
        key="fact_python",
        content="Denver runs on Python 3.14.7 runtime.",
    )
    existing = [item1, item2]

    # Exact key match
    match, m_type = dedup.find_duplicate("New content", "preference", "editor", existing)
    assert match == item1
    assert m_type == "exact_key"

    # Exact text match
    match, m_type = dedup.find_duplicate("User prefers Antigravity editor.", "preference", "new_key", existing)
    assert match == item1
    assert m_type == "exact_text"

    # Near text match
    match, m_type = dedup.find_duplicate("Denver runs on Python 3.14 runtime", "fact", "other_key", existing)
    assert match == item2
    assert "near_text" in m_type

    # Unrelated item should not match
    match, m_type = dedup.find_duplicate("Completely different topic", "fact", "new_key", existing)
    assert match is None
    assert m_type == "none"


def test_memory_ranker_explainability() -> None:
    """Verify transparent multi-factor ranking and reason generation."""
    ranker = MemoryRanker(
        weight_semantic=0.45,
        weight_keyword=0.25,
        weight_importance=0.15,
        weight_confidence=0.10,
        weight_recency=0.05,
    )

    item = MemoryItem(
        id=1,
        category="project",
        key="sentinel",
        content="SentinelJob detects fake internships and jobs",
        importance=0.9,
        confidence=1.0,
    )

    result = ranker.rank_candidate(item, semantic_score=0.8, keyword_score=0.6)
    assert result.final_score > 0.5
    assert result.semantic_score == 0.8
    assert result.keyword_score == 0.6
    assert result.importance_score == 0.9
    assert result.confidence_score == 1.0
    assert "semantic match" in result.retrieval_reason
    assert "importance" in result.retrieval_reason


@pytest.mark.asyncio
async def test_hybrid_search_coordinator() -> None:
    """Verify search coordinator filters expired/deleted items and ranks results."""
    embedder = DeterministicLexicalEmbedder()
    mgr = EmbeddingManager(fallback_provider=embedder)
    coordinator = MemorySearchCoordinator(embedding_manager=mgr)

    item1 = MemoryItem(
        id=1,
        category=MemoryCategory.PROJECT,
        key="fjd",
        content="SentinelJob AI platform for fake job and internship detection",
        importance=0.9,
        confidence=1.0,
    )
    item2 = MemoryItem(
        id=2,
        category=MemoryCategory.PREFERENCE,
        key="editor",
        content="User prefers Antigravity editor for development",
        importance=0.8,
        confidence=1.0,
    )
    item3 = MemoryItem(
        id=3,
        category=MemoryCategory.FACT,
        key="old_exp",
        content="Temporary testing fact",
        is_deleted=True,
    )

    items = [item1, item2, item3]
    emb1 = await embedder.embed_text(item1.content)
    emb2 = await embedder.embed_text(item2.content)
    embeddings_map = {1: emb1, 2: emb2}

    # Query for fake job detection
    results = await coordinator.search(
        query="fake job detection",
        active_items=items,
        embeddings_map=embeddings_map,
        top_k=5,
    )
    assert len(results) >= 1
    assert results[0].memory.id == 1
    assert results[0].memory.key == "fjd"
    assert all(r.memory.id != 3 for r in results)  # deleted item excluded
