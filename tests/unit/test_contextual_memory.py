"""Unit tests for Contextual Memory & Conversational Recall in Denver."""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from denver.commands.models import CommandCategory, CommandRequest
from denver.commands.router import IntentRouter
from denver.commands.service import CommandEngineService
from denver.context.budget import ContextBudgetConfig
from denver.context.engine import ContextEngine
from denver.memory.database import DenverDatabase
from denver.memory.memory_service import MemoryService
from denver.memory.models import MemoryCategory


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_memory.sqlite3"
    db = DenverDatabase(db_path=str(db_file))
    return db


@pytest_asyncio.fixture
async def initialized_db(temp_db):
    await temp_db.initialize()
    return temp_db


@pytest.mark.asyncio
async def test_memory_category_auto_detection(initialized_db):
    memory = MemoryService(db=initialized_db, privacy_mode=False)
    service = CommandEngineService(memory_service=memory)

    # 1. Project detection
    res1 = await service.process_command(
        CommandRequest(raw_text="remember that my primary project is Denver Assistant")
    )
    assert res1.success is True
    assert res1.data.get("category") == "project"

    # 2. Workflow detection
    res2 = await service.process_command(
        CommandRequest(raw_text="remember that I entered deep work focus mode")
    )
    assert res2.success is True
    assert res2.data.get("category") == "workflow"

    # 3. Preference detection
    res3 = await service.process_command(
        CommandRequest(raw_text="remember that my preferred theme is dark")
    )
    assert res3.success is True
    assert res3.data.get("category") == "preference"

    # Verify preference was also saved in preferences table
    pref = await memory.get_preference("theme")
    assert pref is not None
    assert pref.value == "dark"


@pytest.mark.asyncio
async def test_memory_recall_and_fallback(initialized_db):
    memory = MemoryService(db=initialized_db, privacy_mode=False)
    service = CommandEngineService(memory_service=memory)

    # Store a memory
    await service.process_command(
        CommandRequest(raw_text="remember that my repository is hosted on GitHub")
    )

    # Direct recall
    res = await service.process_command(
        CommandRequest(raw_text="what do you know about GitHub")
    )
    assert res.success is True
    assert "github" in res.message.lower()

    # Preference fallback recall
    await memory.set_preference(key="editor", value="VS Code", category="general")
    pref_res = await service.process_command(
        CommandRequest(raw_text="what do you know about editor")
    )
    assert pref_res.success is True
    assert "VS Code" in pref_res.message


def test_intent_router_contextual_queries():
    router = IntentRouter()

    intent1 = router.route("what was I working on")
    assert intent1.action_name == "recall_memory"
    assert intent1.category == CommandCategory.MEMORY

    intent2 = router.route("what did I do today")
    assert intent2.action_name == "recall_memory"
    assert intent2.category == CommandCategory.MEMORY

    intent3 = router.route("tell me about Denver project")
    assert intent3.action_name == "recall_memory"
    assert intent3.params.get("query") == "Denver project"


@pytest.mark.asyncio
async def test_context_engine_bundle_enrichment(initialized_db):
    memory = MemoryService(db=initialized_db, privacy_mode=False)
    
    # Add preference and conversation turn
    await memory.set_preference("user_name", "Diwakar")
    await memory.set_preference("editor", "VS Code")
    memory.add_conversation_turn("user", "Hello Denver")
    memory.add_conversation_turn("denver", "Hello Diwakar! How can I assist you?")
    await memory.remember(content="Working on AI assistant routines", category=MemoryCategory.PROJECT)

    engine = ContextEngine(memory_service=memory)
    bundle = await engine.build_context(query="routines", is_cloud=False)

    assert bundle.user_profile.name == "Diwakar"
    assert bundle.user_profile.preferred_editor == "VS Code"
    assert len(bundle.short_term_context) >= 2
    assert "[SYSTEM CONTEXT: USER PROFILE & MEMORY]" in bundle.context_string
    assert "Diwakar" in bundle.context_string
