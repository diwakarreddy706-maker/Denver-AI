"""Unit tests for Pillar 3: Evolving Memory, User Corrections & Learned Habits."""

import os
import tempfile
from pathlib import Path
import pytest

from denver.commands.models import CommandCategory, CommandRequest
from denver.commands.router import IntentRouter
from denver.commands.service import CommandEngineService
from denver.config.settings import DenverSettings
from denver.context.engine import ContextEngine
from denver.memory.corrections import UserCorrectionStore
from denver.memory.database import DenverDatabase
from denver.memory.habits import LearnedHabitsEngine
from denver.memory.memory_service import MemoryService
from denver.memory.models import LearnedHabit, UserCorrection
from denver.memory.repositories import LearnedHabitsRepository, UserCorrectionsRepository


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_memory.sqlite3"
        db = DenverDatabase(db_path)
        db.initialize_sync()
        yield db
        db.close_sync()


@pytest.mark.asyncio
async def test_user_corrections_repository(temp_db):
    conn = temp_db.connect_sync()
    repo = UserCorrectionsRepository(conn)

    # 1. Add correction
    corr = repo.add_correction(
        pattern="use Chrome",
        correction="Use Brave instead of Chrome",
        target_domain="browser",
        priority=15,
    )
    assert corr.id is not None
    assert corr.pattern == "use Chrome"
    assert corr.correction == "Use Brave instead of Chrome"
    assert corr.target_domain == "browser"
    assert corr.priority == 15
    assert corr.is_active is True

    # 2. Get active corrections
    active = repo.get_active_corrections()
    assert len(active) == 1
    assert active[0].correction == "Use Brave instead of Chrome"

    # Filter by domain
    browser_active = repo.get_active_corrections(target_domain="browser")
    assert len(browser_active) == 1
    other_active = repo.get_active_corrections(target_domain="database")
    # general also matches if present, but here target_domain is browser
    assert len(other_active) == 0

    # 3. Deactivate correction
    deactivated = repo.deactivate_correction(corr.id)
    assert deactivated is True
    assert len(repo.get_active_corrections()) == 0
    assert len(repo.list_corrections(include_inactive=True)) == 1

    # 4. Delete correction
    deleted = repo.delete_correction(corr.id)
    assert deleted is True
    assert len(repo.list_corrections(include_inactive=True)) == 0


@pytest.mark.asyncio
async def test_user_correction_store_and_prompt_formatting(temp_db):
    store = UserCorrectionStore(temp_db)

    # Add 2 corrections
    await store.add_correction(
        pattern="open Chrome",
        correction="Open Brave instead of Chrome",
        target_domain="application",
        priority=12,
    )
    await store.add_correction(
        pattern="pip install",
        correction="Use poetry instead of pip",
        target_domain="development",
        priority=15,
    )

    active = await store.get_active_corrections()
    assert len(active) == 2
    # Ordered by priority DESC
    assert active[0].priority == 15
    assert active[1].priority == 12

    prompt_overrides = await store.format_prompt_overrides()
    assert "[ACTIVE CORRECTIONS & OVERRIDES]" in prompt_overrides
    assert "Use poetry instead of pip" in prompt_overrides
    assert "Open Brave instead of Chrome" in prompt_overrides


def test_user_correction_detection_patterns():
    # 1. "No, use X instead of Y"
    match1 = UserCorrectionStore.detect_correction("No, use Brave instead of Chrome")
    assert match1 is not None
    assert match1["correction"] == "Use Brave instead of Chrome"
    assert match1["target_domain"] == "application"

    # 2. "Don't play music when I ask to code"
    match2 = UserCorrectionStore.detect_correction("Don't play music when I ask to code")
    assert match2 is not None
    assert match2["correction"] == "Do not play music when ask to code"

    # 3. "Remember that I use poetry, not pip"
    match3 = UserCorrectionStore.detect_correction("Remember that I use poetry, not pip")
    assert match3 is not None
    assert match3["correction"] == "Use poetry instead of pip"

    # 4. "Correction: always use dark theme"
    match4 = UserCorrectionStore.detect_correction("Correction: always use dark theme")
    assert match4 is not None
    assert match4["correction"] == "always use dark theme"

    # 5. "Actually, use VS Code rather than Notepad"
    match5 = UserCorrectionStore.detect_correction("Actually, use VS Code rather than Notepad")
    assert match5 is not None
    assert match5["correction"] == "Use VS Code instead of Notepad"

    # Non-correction input
    non_match = UserCorrectionStore.detect_correction("What is the time right now?")
    assert non_match is None


@pytest.mark.asyncio
async def test_learned_habits_repository(temp_db):
    conn = temp_db.connect_sync()
    repo = LearnedHabitsRepository(conn)

    # 1. First observation
    h1 = repo.record_observation(
        category="app",
        habit_key="primary_editor",
        habit_value="VS Code",
        confidence_boost=0.1,
    )
    assert h1.frequency == 1
    assert h1.confidence == 0.5

    # 2. Second observation (frequency increment + confidence boost)
    h2 = repo.record_observation(
        category="app",
        habit_key="primary_editor",
        habit_value="VS Code",
        confidence_boost=0.15,
    )
    assert h2.frequency == 2
    assert h2.confidence == 0.65

    # 3. Query habits
    habits = repo.list_habits(category="app")
    assert len(habits) == 1
    assert habits[0].habit_value == "VS Code"

    # 4. Delete habit
    assert repo.delete_habit(h2.id) is True
    assert len(repo.list_habits()) == 0


@pytest.mark.asyncio
async def test_learned_habits_engine_and_suggestions(temp_db):
    engine = LearnedHabitsEngine(temp_db)

    # Record habits with high confidence
    await engine.record_observation("project", "recent_project", "Denver AI", confidence_boost=0.3)
    await engine.record_observation("project", "recent_project", "Denver AI", confidence_boost=0.3)
    await engine.record_observation("app", "primary_tool", "Code.exe", confidence_boost=0.3)
    await engine.record_observation("app", "primary_tool", "Code.exe", confidence_boost=0.3)

    suggestions = await engine.get_habit_suggestions(min_confidence=0.6)
    assert len(suggestions) == 2
    assert any("Denver AI" in s for s in suggestions)
    assert any("Code.exe" in s for s in suggestions)

    prompt_habits = await engine.format_prompt_habits()
    assert "[LEARNED USER HABITS & PATTERNS]" in prompt_habits
    assert "Denver AI" in prompt_habits
    assert "Code.exe" in prompt_habits


@pytest.mark.asyncio
async def test_context_engine_injection_with_evolving_memory(temp_db):
    mem_service = MemoryService(temp_db)
    context_engine = ContextEngine(memory_service=mem_service)

    # Add a correction
    await mem_service.add_user_correction(
        pattern="use Chrome",
        correction="Use Brave instead of Chrome",
        target_domain="browser",
        priority=20,
    )

    # Add a habit
    await mem_service.record_learned_habit(
        category="tool",
        habit_key="package_manager",
        habit_value="poetry",
        confidence_boost=0.3,
    )
    await mem_service.record_learned_habit(
        category="tool",
        habit_key="package_manager",
        habit_value="poetry",
        confidence_boost=0.3,
    )

    bundle = await context_engine.build_context(query="open browser")
    assert "[ACTIVE CORRECTIONS & OVERRIDES]" in bundle.context_string
    assert "Use Brave instead of Chrome" in bundle.context_string
    assert "[LEARNED USER HABITS & PATTERNS]" in bundle.context_string
    assert "poetry" in bundle.context_string


def test_command_router_evolving_memory_intents():
    router = IntentRouter()

    # List corrections
    res1 = router.route("what corrections have you learned")
    assert res1.action_name == "list_corrections"
    assert res1.category == CommandCategory.MEMORY

    res2 = router.route("show my corrections")
    assert res2.action_name == "list_corrections"

    # Clear correction
    res3 = router.route("clear correction 42")
    assert res3.action_name == "clear_correction"
    assert res3.params["correction_id"] == 42

    res4 = router.route("delete correction 7")
    assert res4.action_name == "clear_correction"
    assert res4.params["correction_id"] == 7

    # List habits
    res5 = router.route("what are my habits")
    assert res5.action_name == "list_habits"
    assert res5.category == CommandCategory.MEMORY

    res6 = router.route("show learned habits")
    assert res6.action_name == "list_habits"


@pytest.mark.asyncio
async def test_command_service_evolving_memory_execution(temp_db):
    settings = DenverSettings(ai_enabled=False)
    mem_service = MemoryService(temp_db)
    service = CommandEngineService(memory_service=mem_service, settings=settings)


    # 1. List corrections when empty
    r1 = await service.process_command("what corrections have you learned")
    assert r1.success is True
    assert "no learned corrections" in r1.message.lower()

    # 2. Issue explicit correction utterance
    r2 = await service.process_command("No, use Brave instead of Chrome")
    assert r2.success is True
    assert r2.action_name == "record_user_correction"
    assert "recorded this correction" in r2.message.lower()

    # 3. List corrections again (should contain the newly recorded correction)
    r3 = await service.process_command("list user corrections")
    assert r3.success is True
    assert "use brave instead of chrome" in r3.message.lower()


    # 4. Clear the correction
    corr_id = r2.data["id"]
    r4 = await service.process_command(f"clear correction {corr_id}")
    assert r4.success is True
    assert f"Correction #{corr_id} has been cleared" in r4.message

    # 5. List habits
    r5 = await service.process_command("what are my habits")
    assert r5.success is True
    assert r5.action_name == "list_habits"

