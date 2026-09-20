"""Unit tests for Phase 7 Context Engine, budgeting, and profile context assembly."""

from __future__ import annotations

from pathlib import Path
import pytest

from denver.context.budget import ContextBudgetConfig, fit_context_budget
from denver.context.engine import ContextEngine
from denver.context.models import ShortTermTurn
from denver.memory.database import DenverDatabase
from denver.memory.memory_service import MemoryService
from denver.memory.models import MemoryCategory, MemoryItem, MemorySearchResult, PrivacyLevel


def test_fit_context_budget_limits() -> None:
    """Verify turn budget and character truncation rules."""
    config = ContextBudgetConfig(max_turns=3, max_chars=100, max_memories=2)

    turns = [
        ShortTermTurn(role="user", content=f"Message {i} " + "x" * 20)
        for i in range(10)
    ]
    memories = [
        MemorySearchResult(
            memory=MemoryItem(id=i, category="fact", key=f"k{i}", content=f"Memory {i}"),
            final_score=1.0 - i * 0.1,
        )
        for i in range(5)
    ]

    pruned_turns, pruned_mems, applied = fit_context_budget(turns, memories, config)
    assert applied is True
    assert len(pruned_turns) <= 3
    assert len(pruned_mems) <= 2
    # Ensure total character length is strictly within budget
    total_len = sum(len(t.content) for t in pruned_turns) + sum(len(m.memory.content) for m in pruned_mems)
    assert total_len <= config.max_chars


@pytest.mark.asyncio
async def test_context_engine_build_context(tmp_path: Path) -> None:
    """Verify ContextEngine end-to-end context assembly with preferences and memories."""
    db_file = tmp_path / "ctx_test.sqlite3"
    db = DenverDatabase(db_path=db_file)
    memory = MemoryService(db=db, semantic_enabled=True)

    # Populate preferences and memories
    await memory.set_preference("editor", "Antigravity")
    await memory.set_preference("language", "English")
    await memory.remember(
        content="SentinelJob is an AI-based Fake Job Detection Platform",
        category=MemoryCategory.PROJECT,
        key="sentinel_proj",
    )
    memory.add_conversation_turn(role="user", content="Hello Denver")
    memory.add_conversation_turn(role="denver", content="Hello! How can I assist you today?")

    engine = ContextEngine(
        memory_service=memory,
        budget_config=ContextBudgetConfig(max_turns=5, max_chars=5000, max_memories=5),
    )

    bundle = await engine.build_context(query="Tell me about SentinelJob project")
    assert bundle.total_characters > 0
    assert "Antigravity" in bundle.context_string
    assert "SentinelJob" in bundle.context_string
    assert bundle.user_profile.preferred_editor == "Antigravity"
    assert bundle.memories_used_count >= 1
    assert len(bundle.short_term_context) == 2


@pytest.mark.asyncio
async def test_context_engine_active_screen_context(tmp_path: Path) -> None:
    """Verify that active screen context is correctly formatted into the context string."""
    db_file = tmp_path / "ctx_screen_test.sqlite3"
    db = DenverDatabase(db_path=db_file)
    memory = MemoryService(db=db, semantic_enabled=False)

    engine = ContextEngine(memory_service=memory)

    screen_ctx = {
        "analysis_text": "Terminal window displays 'ModuleNotFoundError: No module named requests'",
        "focus_mode": "error_diagnosis",
        "timestamp": 1234567.89,
    }

    bundle = await engine.build_context(
        query="Why did my script fail?",
        active_screen_context=screen_ctx,
    )

    assert "[ACTIVE SCREEN CONTEXT (ERROR_DIAGNOSIS MODE)]" in bundle.context_string
    assert "ModuleNotFoundError: No module named requests" in bundle.context_string

