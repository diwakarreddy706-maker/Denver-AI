"""Unit tests for Denver Proactive Morning & Evening Audio Briefings (Step 7)."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from denver.automation.executor import AutomationExecutor
from denver.briefing.models import (
    AudioBriefing,
    BriefingSection,
    BriefingType,
)
from denver.briefing.service import BriefingService, get_briefing_service
from denver.commands.router import IntentRouter
from denver.commands.service import CommandEngineService, CommandRequest


def test_briefing_models():
    """Verify BriefingSection and AudioBriefing data models and script generation."""
    s1 = BriefingSection(
        name="weather",
        title="Weather",
        icon="☀️",
        text="22°C Clear sky",
        spoken_text="The weather is 22 degrees and sunny.",
    )
    s2 = BriefingSection(
        name="schedule",
        title="Schedule",
        icon="📅",
        text="2 meetings today.",
        spoken_text="You have 2 meetings scheduled.",
    )

    briefing = AudioBriefing(
        briefing_type=BriefingType.MORNING,
        greeting="Good morning, Diwakar!",
        sections=[s1, s2],
        audio_played=True,
        audio_voice="Ryan",
    )

    # Verify spoken script composition
    assert "Good morning, Diwakar!" in briefing.spoken_script
    assert "The weather is 22 degrees and sunny." in briefing.spoken_script
    assert "You have 2 meetings scheduled." in briefing.spoken_script

    # Verify display formatting
    display = briefing.format_display()
    assert "Morning Briefing" in display
    assert "☀️ Weather" in display
    assert "📅 Schedule" in display
    assert "Spoken audio narrated via Ryan" in display

    # Verify dictionary serialization
    d = briefing.to_dict()
    assert d["briefing_type"] == "morning"
    assert d["audio_played"] is True
    assert len(d["sections"]) == 2


@pytest.mark.asyncio
async def test_morning_briefing_generation():
    """Verify multi-pillar aggregation for morning briefing."""
    service = BriefingService()

    briefing = await service.generate_morning_briefing(speak_audio=False)
    assert briefing.briefing_type == BriefingType.MORNING
    assert "Good morning" in briefing.greeting
    assert len(briefing.sections) >= 3

    section_names = [s.name for s in briefing.sections]
    assert "weather" in section_names
    assert "schedule" in section_names
    assert "inbox" in section_names


@pytest.mark.asyncio
async def test_evening_briefing_generation():
    """Verify multi-pillar aggregation for evening wrap-up briefing."""
    service = BriefingService()

    briefing = await service.generate_evening_briefing(speak_audio=False)
    assert briefing.briefing_type == BriefingType.EVENING
    assert "Good evening" in briefing.greeting
    assert len(briefing.sections) >= 3

    section_names = [s.name for s in briefing.sections]
    assert "schedule" in section_names
    assert "inbox" in section_names
    assert "reflection" in section_names


@pytest.mark.asyncio
async def test_audio_narration_integration():
    """Verify audio narration triggers voice preview playback."""
    service = BriefingService()

    with patch("denver.audio.get_voice_manager") as mock_vm_getter:
        mock_vm = MagicMock()
        mock_vm.preview_voice = AsyncMock(return_value=(True, "Narration played successfully"))
        mock_vm.active_voice.name = "Christopher"
        mock_vm_getter.return_value = mock_vm

        briefing = await service.generate_morning_briefing(speak_audio=True)
        assert briefing.audio_played is True
        assert briefing.audio_voice == "Christopher"
        mock_vm.preview_voice.assert_awaited_once()


@pytest.mark.asyncio
async def test_automation_executor_briefings():
    """Verify AutomationExecutor executes morning_briefing and evening_briefing actions."""
    from denver.automation.models import AutomationRequest
    executor = AutomationExecutor()

    # 1. Morning briefing (no audio for headless testing)
    req_morning = AutomationRequest(
        action_name="morning_briefing",
        params={"audio": False},
    )
    res_morning = await executor.execute(req_morning)
    assert res_morning.success is True
    assert res_morning.action == "morning_briefing"
    assert "Morning Briefing" in res_morning.message

    # 2. Evening briefing
    req_evening = AutomationRequest(
        action_name="evening_briefing",
        params={"audio": False},
    )
    res_evening = await executor.execute(req_evening)
    assert res_evening.success is True
    assert res_evening.action == "evening_briefing"
    assert "Evening Briefing" in res_evening.message


@pytest.mark.asyncio
async def test_command_service_briefings():
    """Verify CommandEngineService processes briefing commands."""
    executor = AutomationExecutor()
    memory_mock = MagicMock()
    memory_mock.record_habit = AsyncMock()
    memory_mock.log_audit = AsyncMock()
    service = CommandEngineService(memory_service=memory_mock, automation_executor=executor)

    # 1. Morning briefing command
    res1 = await service.process_command(CommandRequest(raw_text="play morning briefing"))
    assert res1.success is True
    assert res1.action_name == "morning_briefing"
    assert "Morning Briefing" in res1.message

    # 2. Evening briefing command
    res2 = await service.process_command(CommandRequest(raw_text="evening audio briefing"))
    assert res2.success is True
    assert res2.action_name == "evening_briefing"
    assert "Evening Briefing" in res2.message


def test_intent_router_briefings():
    """Verify natural language routing for morning and evening briefings."""
    router = IntentRouter()

    # 1. Morning briefing triggers
    i1 = router.route("morning audio briefing")
    assert i1.action_name == "morning_briefing"

    i2 = router.route("play morning briefing")
    assert i2.action_name == "morning_briefing"

    i3 = router.route("give me my morning briefing")
    assert i3.action_name == "morning_briefing"

    i4 = router.route("listen to morning briefing")
    assert i4.action_name == "morning_briefing"

    # 2. Evening briefing triggers
    i5 = router.route("evening briefing")
    assert i5.action_name == "evening_briefing"

    i6 = router.route("evening audio briefing")
    assert i6.action_name == "evening_briefing"

    i7 = router.route("good evening")
    assert i7.action_name == "evening_briefing"

    i8 = router.route("evening wrap up")
    assert i8.action_name == "evening_briefing"

    # 3. Verify compound routine "morning briefing" regression preservation
    i_routine = router.route("morning briefing")
    assert i_routine.action_name == "run_routine_now"
    assert i_routine.params.get("routine_id") == "morning briefing"
