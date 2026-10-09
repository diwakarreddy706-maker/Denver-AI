"""Unit tests for Denver Spoken Voice Profile Selector (Edge-TTS, Step 4)."""

import sqlite3
from unittest.mock import AsyncMock, MagicMock

import pytest

from denver.audio.models import TTSResult
from denver.audio.voice_manager import VoiceProfileManager
from denver.audio.voices import (
    VOICE_CATALOG,
    VoiceProfile,
    find_voice,
    list_available_voices,
)
from denver.automation.executor import AutomationExecutor
from denver.commands.router import IntentRouter
from denver.commands.service import CommandEngineService, CommandRequest


def test_voice_catalog_and_profiles():
    """Verify curated voice catalog contents, properties, and serialization."""
    voices = list_available_voices()
    assert len(voices) >= 8

    # Default voice check
    ryan = voices[0]
    assert ryan.name == "Ryan"
    assert ryan.locale == "en-GB"
    assert ryan.gender == "Male"
    assert "en-GB-RyanNeural" in ryan.voice_id

    d = ryan.to_dict()
    assert d["voice_id"] == "en-GB-RyanNeural"
    assert d["name"] == "Ryan"
    assert "Ryan (en-GB Male)" in ryan.display_label()


def test_voice_fuzzy_search():
    """Verify exact and fuzzy voice lookups by name, ID, and descriptive phrases."""
    # 1. By ID
    v1 = find_voice("en-US-ChristopherNeural")
    assert v1 is not None and v1.name == "Christopher"

    # 2. By Name
    assert find_voice("christopher").name == "Christopher"
    assert find_voice("jenny").name == "Jenny"
    assert find_voice("sonia").name == "Sonia"
    assert find_voice("nat").name == "Nat"
    assert find_voice("neerja").name == "Neerja"

    # 3. By Descriptors
    v_british_f = find_voice("british female")
    assert v_british_f is not None and v_british_f.name == "Sonia"

    v_us_m = find_voice("american male deep")
    assert v_us_m is not None and v_us_m.name == "Christopher"

    v_au = find_voice("australian")
    assert v_au is not None and v_au.name == "Nat"

    # 4. Unknown lookup
    assert find_voice("martian robot 9000") is None


def test_voice_manager_switching_and_persistence():
    """Verify voice switching, preference storage in SQLite, and startup reloading."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE user_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            confidence REAL DEFAULT 1.0,
            source TEXT DEFAULT 'explicit_user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_memory_category_key UNIQUE (category, key)
        );
        """
    )

    manager = VoiceProfileManager(db_conn=conn)
    assert manager.active_voice.name == "Ryan"

    # 1. Switch voice to Christopher
    ok, profile, msg = manager.set_voice("Christopher")
    assert ok is True
    assert profile.name == "Christopher"
    assert "Christopher" in msg
    assert manager.active_voice.name == "Christopher"

    # Verify persisted to SQLite
    cursor = conn.execute("SELECT value FROM user_preferences WHERE category = 'voice' AND key = 'voice_id';")
    row = cursor.fetchone()
    assert row is not None and row[0] == "en-US-ChristopherNeural"

    # 2. Re-initialize manager and verify preference loads
    reloaded_manager = VoiceProfileManager(db_conn=conn)
    assert reloaded_manager.active_voice.name == "Christopher"


def test_voice_speed_and_pitch_adjustments():
    """Verify natural language speed and pitch parsing with preference persistence."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE user_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            confidence REAL DEFAULT 1.0,
            source TEXT DEFAULT 'explicit_user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_memory_category_key UNIQUE (category, key)
        );
        """
    )
    manager = VoiceProfileManager(db_conn=conn)

    # 1. Speed: "fast" -> +15%
    ok, rate, msg = manager.set_speed("fast")
    assert ok is True
    assert rate == "+15%"

    # Speed: "slower" -> -15%
    ok, rate, _ = manager.set_speed("slower")
    assert rate == "-15%"

    # Speed: "+25%"
    ok, rate, _ = manager.set_speed("+25%")
    assert rate == "+25%"

    # Speed: "1.2x"
    ok, rate, _ = manager.set_speed("1.2x")
    assert rate == "+20%"

    # Speed: "normal" -> +0%
    ok, rate, _ = manager.set_speed("normal")
    assert rate == "+0%"

    # 2. Pitch: "deep" -> -10Hz
    ok, pitch, _ = manager.set_pitch("deep")
    assert ok is True
    assert pitch == "-10Hz"

    # Pitch: "high" -> +10Hz
    ok, pitch, _ = manager.set_pitch("high")
    assert pitch == "+10Hz"

    # Pitch: "normal" -> +0Hz
    ok, pitch, _ = manager.set_pitch("normal")
    assert pitch == "+0Hz"


@pytest.mark.asyncio
async def test_voice_preview():
    """Verify voice preview synthesis call."""
    mock_tts = MagicMock()
    mock_tts.synthesize = AsyncMock(return_value=TTSResult(
        success=True,
        audio_data=b"mock-audio-bytes",
        format="mp3",
    ))
    mock_pipeline = MagicMock()
    mock_pipeline.tts = mock_tts
    mock_pipeline.playback = MagicMock()
    mock_pipeline.playback.play = AsyncMock()

    manager = VoiceProfileManager(audio_pipeline=mock_pipeline, tts_provider=mock_tts)

    ok, msg = await manager.preview_voice("Jenny")
    assert ok is True
    assert "Jenny" in msg
    mock_tts.synthesize.assert_called_once()
    mock_pipeline.playback.play.assert_called_once()


def test_voice_router_intents():
    """Verify natural language voice routing in IntentRouter."""
    router = IntentRouter()

    # Switch voice
    i1 = router.route("switch voice to Christopher")
    assert i1.action_name == "switch_voice"
    assert "christopher" in i1.params["voice"].lower()

    i1b = router.route("change voice to Jenny")
    assert i1b.action_name == "switch_voice"
    assert "jenny" in i1b.params["voice"].lower()

    i1c = router.route("use British female voice")
    assert i1c.action_name == "switch_voice"
    assert "british female" in i1c.params["voice"].lower()

    # List voices
    i2 = router.route("list voices")
    assert i2.action_name == "list_voices"

    i2b = router.route("show available voices")
    assert i2b.action_name == "list_voices"

    # Set speed
    i3 = router.route("set voice speed to fast")
    assert i3.action_name == "set_voice_speed"
    assert i3.params["speed"] == "fast"

    i3b = router.route("make the voice slower")
    assert i3b.action_name == "set_voice_speed"
    assert i3b.params["speed"] == "slower"

    # Set pitch
    i4 = router.route("set voice pitch to deep")
    assert i4.action_name == "set_voice_pitch"
    assert i4.params["pitch"] == "deep"

    # Preview voice
    i5 = router.route("preview voice Sonia")
    assert i5.action_name == "preview_voice"
    assert "sonia" in i5.params["voice"].lower()

    # Voice settings
    i6 = router.route("what is my current voice setting")
    assert i6.action_name == "get_voice_settings"


@pytest.mark.asyncio
async def test_voice_command_engine_integration():
    """Verify voice profile command execution through CommandEngineService and AutomationExecutor."""
    executor = AutomationExecutor()
    memory_mock = MagicMock()
    memory_mock.record_habit = AsyncMock()
    memory_mock.log_audit = AsyncMock()
    service = CommandEngineService(memory_service=memory_mock, automation_executor=executor)

    # 1. List voices
    res_list = await service.process_command(CommandRequest(raw_text="list voices"))
    assert res_list.success is True
    assert res_list.action_name == "list_voices"
    assert "Ryan" in res_list.message
    assert "Christopher" in res_list.message

    # 2. Switch voice to Christopher
    res_switch = await service.process_command(CommandRequest(raw_text="switch voice to Christopher"))
    assert res_switch.success is True
    assert res_switch.action_name == "switch_voice"
    assert "Christopher" in res_switch.message

    # 3. Set speed to faster
    res_speed = await service.process_command(CommandRequest(raw_text="set voice speed to fast"))
    assert res_speed.success is True
    assert res_speed.action_name == "set_voice_speed"
    assert "+15%" in res_speed.message

    # 4. Set pitch to deep
    res_pitch = await service.process_command(CommandRequest(raw_text="set voice pitch to deep"))
    assert res_pitch.success is True
    assert res_pitch.action_name == "set_voice_pitch"
    assert "-10Hz" in res_pitch.message

    # 5. Query voice settings
    res_settings = await service.process_command(CommandRequest(raw_text="show voice settings"))
    assert res_settings.success is True
    assert res_settings.action_name == "get_voice_settings"
    assert "Christopher" in res_settings.message
    assert "+15%" in res_settings.message
