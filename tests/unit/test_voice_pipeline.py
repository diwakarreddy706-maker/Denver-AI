"""Unit tests for Denver VoicePipeline orchestrator and barge-in flow."""

import asyncio
import pytest
from denver.audio.fake import (
    FakeAudioCapture,
    FakeAudioPlayback,
    FakeSTTProvider,
    FakeTTSProvider,
    FakeVAD,
    FakeWakeWordDetector,
)
from denver.audio.models import (
    AudioChunk,
    AudioFormat,
    Transcript,
    VoiceActivityState,
)
from denver.audio.pipeline import VoicePipeline
from denver.commands.service import CommandEngineService
from denver.config.settings import DenverSettings
from denver.memory.database import DenverDatabase
from denver.memory.memory_service import MemoryService
from denver.runtime.event_bus import DenverEventBus
from denver.runtime.events import BargeInDetected, TranscriptProduced, WakeWordDetected
from denver.runtime.state_machine import DenverStateMachine
from denver.runtime.states import DenverState


@pytest.fixture
async def voice_env(tmp_path):
    event_bus = DenverEventBus()
    state_machine = DenverStateMachine(initial_state=DenverState.STANDBY, event_bus=event_bus)

    db_path = str(tmp_path / "denver_voice_test.db")
    db = DenverDatabase(db_path=db_path)
    await db.initialize()

    memory_service = MemoryService(db=db, event_bus=event_bus)
    settings = DenverSettings(audio_enabled=True, wake_word_enabled=True, tts_enabled=True)

    command_service = CommandEngineService(
        memory_service=memory_service,
        state_machine=state_machine,
        event_bus=event_bus,
        settings=settings,
    )

    fake_capture = FakeAudioCapture()
    fake_vad = FakeVAD()
    fake_wakeword = FakeWakeWordDetector(wake_word="Denver")
    fake_stt = FakeSTTProvider(canned_transcript="Denver, what time is it?")
    fake_tts = FakeTTSProvider()
    fake_playback = FakeAudioPlayback()

    pipeline = VoicePipeline(
        command_service=command_service,
        state_machine=state_machine,
        event_bus=event_bus,
        settings=settings,
        capture=fake_capture,
        vad=fake_vad,
        wakeword=fake_wakeword,
        stt=fake_stt,
        tts=fake_tts,
        playback=fake_playback,
    )

    yield {
        "pipeline": pipeline,
        "capture": fake_capture,
        "vad": fake_vad,
        "wakeword": fake_wakeword,
        "stt": fake_stt,
        "tts": fake_tts,
        "playback": fake_playback,
        "state_machine": state_machine,
        "event_bus": event_bus,
        "db": db,
    }

    await pipeline.stop()
    await db.close()


@pytest.mark.asyncio
async def test_voice_pipeline_start_and_status(voice_env) -> None:
    pipeline = voice_env["pipeline"]
    assert not pipeline.is_running

    started = await pipeline.start()
    assert started is True
    assert pipeline.is_running

    status = pipeline.get_status()
    assert status.status in {"READY", "DEGRADED"}
    assert status.capture_active is True

    await pipeline.stop()
    assert not pipeline.is_running


@pytest.mark.asyncio
async def test_voice_pipeline_barge_in_handling(voice_env) -> None:
    pipeline = voice_env["pipeline"]
    state_machine = voice_env["state_machine"]
    playback = voice_env["playback"]
    event_bus = voice_env["event_bus"]

    barge_in_events = []
    event_bus.subscribe(BargeInDetected, lambda e: barge_in_events.append(e))

    # Manually transition to SPEAKING
    await state_machine.transition_to(DenverState.SPEAKING, reason="Testing barge-in")
    playback._is_playing = True

    chunk = AudioChunk(data=b"\x00\x60" * 400, sample_rate=16000, duration_ms=50.0, energy=0.15)
    await pipeline._handle_barge_in(chunk)

    assert not playback.is_playing
    assert state_machine.current_state == DenverState.LISTENING
    assert len(barge_in_events) == 1
    assert barge_in_events[0].energy > 0


@pytest.mark.asyncio
async def test_voice_pipeline_speech_processing_turn(voice_env) -> None:
    pipeline = voice_env["pipeline"]
    state_machine = voice_env["state_machine"]
    stt = voice_env["stt"]
    event_bus = voice_env["event_bus"]

    transcripts = []
    event_bus.subscribe(TranscriptProduced, lambda e: transcripts.append(e))

    await state_machine.transition_to(DenverState.LISTENING, reason="Starting speech turn")

    # Feed speech chunks to pipeline
    chunk1 = AudioChunk(data=b"\x00\x20" * 400, sample_rate=16000, duration_ms=50.0)
    chunk2 = AudioChunk(data=b"\x00\x30" * 400, sample_rate=16000, duration_ms=50.0)
    pipeline._current_speech_chunks.extend([chunk1, chunk2])

    await pipeline._process_utterance()

    assert len(transcripts) == 1
    assert transcripts[0].text == "Denver, what time is it?"
    assert state_machine.current_state == DenverState.STANDBY
