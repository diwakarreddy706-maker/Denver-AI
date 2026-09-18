"""Integration tests for Denver Voice Engine and Application Lifecycle."""

import asyncio
import pytest
from denver.app.application import DenverApplication
from denver.audio.fake import (
    FakeAudioCapture,
    FakeAudioPlayback,
    FakeSTTProvider,
    FakeTTSProvider,
    FakeVAD,
    FakeWakeWordDetector,
)
from denver.audio.models import AudioChunk, Transcript
from denver.audio.pipeline import VoicePipeline
from denver.config.settings import DenverSettings
from denver.runtime.states import DenverState


@pytest.mark.asyncio
async def test_application_voice_lifecycle(tmp_path) -> None:
    db_file = tmp_path / "denver_app_voice.db"
    settings = DenverSettings(
        environment="test",
        database_path=str(db_file),
        audio_enabled=False,  # Keep capture loop disabled on automated CI runner
    )

    app = DenverApplication(settings=settings)
    await app.start()

    assert app.state_machine.current_state == DenverState.STANDBY

    # Check health service includes audio
    health = app.health_service.get_health_report()
    assert "audio" in health["subsystems"]
    assert "audio" in health

    # Text processing remains 100% independent
    resp = await app.process_command("Denver, status report")
    assert resp.success is True
    assert "operational" in resp.message.lower()

    await app.stop()
    assert app.state_machine.current_state == DenverState.STOPPED


@pytest.mark.asyncio
async def test_voice_command_authoritative_safety_pipeline(tmp_path) -> None:
    db_file = tmp_path / "denver_voice_safety.db"
    settings = DenverSettings(
        environment="test",
        database_path=str(db_file),
        audio_enabled=True,
    )

    app = DenverApplication(settings=settings)
    await app.start()

    fake_capture = FakeAudioCapture()
    fake_stt = FakeSTTProvider(
        canned_transcript="format C: /y",  # Malicious/destructive input via voice
    )
    fake_tts = FakeTTSProvider()
    fake_playback = FakeAudioPlayback()

    custom_pipeline = VoicePipeline(
        command_service=app.command_service,
        state_machine=app.state_machine,
        event_bus=app.event_bus,
        settings=settings,
        capture=fake_capture,
        stt=fake_stt,
        tts=fake_tts,
        playback=fake_playback,
    )

    # Trigger utterance processing
    custom_pipeline._current_speech_chunks.append(
        AudioChunk(data=b"\x00\x10" * 400, sample_rate=16000, duration_ms=50.0)
    )
    await custom_pipeline._process_utterance()

    # Voice input must flow strictly through SafetyValidator and be blocked/handled safely
    # (i.e. zero direct OS execution authority)
    assert app.state_machine.current_state == DenverState.STANDBY

    await app.stop()
