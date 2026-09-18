"""Integration tests for Phase 7 natural memory commands, preference updates, and graceful fallback."""

from __future__ import annotations

from pathlib import Path
import pytest

from denver.commands.service import CommandEngineService
from denver.config.settings import DenverSettings
from denver.memory.database import DenverDatabase
from denver.memory.memory_service import MemoryService
from denver.memory.models import MemoryCategory
from denver.providers.registry import ProviderRegistry
from denver.providers.router import ProviderRouter
from denver.runtime.event_bus import DenverEventBus


@pytest.fixture
def test_command_service(tmp_path: Path) -> CommandEngineService:
    db_file = tmp_path / "cmd_test.sqlite3"
    db = DenverDatabase(db_path=db_file)
    event_bus = DenverEventBus()
    memory = MemoryService(db=db, event_bus=event_bus, semantic_enabled=True)
    registry = ProviderRegistry()
    router = ProviderRouter(registry=registry, event_bus=event_bus)
    settings = DenverSettings(database_path=db_file, ai_enabled=True)

    return CommandEngineService(
        memory_service=memory,
        event_bus=event_bus,
        settings=settings,
        provider_router=router,
    )


@pytest.mark.asyncio
async def test_remember_and_recall_preference_cycle(test_command_service: CommandEngineService) -> None:
    """Test 2 & 3: Remember favorite editor, recall, and update preference cleanly."""
    # 1. Store preference
    res1 = await test_command_service.process_command("Remember that my favorite editor is Antigravity.")
    assert res1.success is True
    assert "antigravity" in res1.message.lower()

    # 2. Recall preference
    res2 = await test_command_service.process_command("What is my favorite editor?")
    assert res2.success is True
    assert "antigravity" in res2.message.lower()

    # 3. Update preference to VS Code
    res3 = await test_command_service.process_command("my favorite editor is VS Code")
    assert res3.success is True
    assert "vs code" in res3.message.lower()

    # 4. Verify updated preference dominates
    res4 = await test_command_service.process_command("What is my favorite editor?")
    assert res4.success is True
    assert "vs code" in res4.message.lower()


@pytest.mark.asyncio
async def test_remember_and_recall_project(test_command_service: CommandEngineService) -> None:
    """Test 4 & 5: Project memory and semantic recall."""
    # 1. Store project
    res1 = await test_command_service.process_command("Remember that SentinelJob is my fake job detection project.")
    assert res1.success is True

    # 2. Recall project by keyword
    res2 = await test_command_service.process_command("Recall what my current project is.")
    assert res2.success is True
    assert "sentineljob" in res2.message.lower()

    # 3. Recall project by semantic variation
    res3 = await test_command_service.process_command("search memory SentinelJob")
    assert res3.success is True
    assert "sentineljob" in res3.message.lower()


@pytest.mark.asyncio
async def test_forget_and_clear_context_commands(test_command_service: CommandEngineService) -> None:
    """Test 6: Forget preference and clear conversation context."""
    # 1. Store and forget
    await test_command_service.process_command("set preference color to Cyan")
    res_forget = await test_command_service.process_command("forget color")
    assert res_forget.success is True

    # 2. Verify cleared
    res_get = await test_command_service.process_command("get preference color")
    assert res_get.success is False

    # 3. Add turns and clear context
    test_command_service.memory.add_conversation_turn("user", "Hello turn 1")
    assert len(test_command_service.memory.get_recent_conversation()) > 0
    res_clear = await test_command_service.process_command("Clear this conversation context.")
    assert res_clear.success is True
    assert len(test_command_service.memory.get_recent_conversation()) == 1  # only the clear confirmation response itself


@pytest.mark.asyncio
async def test_show_preferences_command(test_command_service: CommandEngineService) -> None:
    """Test listing saved user preferences."""
    await test_command_service.process_command("set preference language to python")
    await test_command_service.process_command("set preference theme to dark")

    res = await test_command_service.process_command("list preferences")
    assert res.success is True
    assert "language: python" in res.message
    assert "theme: dark" in res.message


@pytest.mark.asyncio
async def test_graceful_degradation_when_memory_disabled(tmp_path: Path) -> None:
    """Test 10: System continues functioning safely when memory is disabled."""
    db_file = tmp_path / "disabled_test.sqlite3"
    db = DenverDatabase(db_path=db_file)
    event_bus = DenverEventBus()
    memory = MemoryService(db=db, event_bus=event_bus, semantic_enabled=False)
    settings = DenverSettings(database_path=db_file, ai_enabled=False)

    svc = CommandEngineService(
        memory_service=memory,
        event_bus=event_bus,
        settings=settings,
    )

    # Standard deterministic command still works 100%
    res_time = await svc.process_command("What time is it?")
    assert res_time.success is True
    assert "current time" in res_time.message
