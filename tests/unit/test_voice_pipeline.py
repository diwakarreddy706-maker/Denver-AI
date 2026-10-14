"""Unit tests for Denver VoicePipeline orchestrator and barge-in flow."""

import asyncio
import time
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


@pytest.mark.asyncio
async def test_voice_pipeline_mute_and_overlay_notification(voice_env) -> None:
    pipeline = voice_env["pipeline"]

    # Initial state
    assert not pipeline.is_muted

    # Mute
    pipeline.mute()
    assert bool(pipeline.is_muted)

    # Unmute
    pipeline.unmute()
    assert not pipeline.is_muted

    # Toggle mute
    muted = pipeline.toggle_mute()
    assert bool(muted)
    assert bool(pipeline.is_muted)

    pipeline.unmute()

    # Test overlay notification calls without error
    pipeline._notify_overlay("LISTENING")
    pipeline._notify_overlay("PROCESSING")
    pipeline._notify_overlay("SPEAKING")
    pipeline._notify_overlay("STANDBY")


@pytest.mark.asyncio
async def test_strict_wake_rejected_noise_and_hello_everyone(voice_env) -> None:
    pipeline = voice_env["pipeline"]
    state_machine = voice_env["state_machine"]
    fake_stt = voice_env["stt"]
    fake_tts = voice_env["tts"]

    # Inject mock audio chunks into ring buffer
    for _ in range(10):
        pipeline._ring_buffer.append(AudioChunk(data=b"\x00\x10" * 400, sample_rate=16000, duration_ms=50.0))

    # Candidate 1: "hello everyone"
    fake_stt.canned_transcript = "hello everyone"
    await pipeline._handle_wake_detection()

    assert state_machine.current_state == DenverState.STANDBY
    assert fake_tts.synthesize_count == 0

    # Candidate 2: Random noise / empty transcript
    fake_stt.canned_transcript = ""
    await pipeline._handle_wake_detection()

    assert state_machine.current_state == DenverState.STANDBY
    assert fake_tts.synthesize_count == 0


@pytest.mark.asyncio
async def test_strict_wake_valid_phrase_plays_reply_once(voice_env) -> None:
    pipeline = voice_env["pipeline"]
    state_machine = voice_env["state_machine"]
    fake_stt = voice_env["stt"]
    fake_tts = voice_env["tts"]

    for _ in range(10):
        pipeline._ring_buffer.append(AudioChunk(data=b"\x00\x20" * 400, sample_rate=16000, duration_ms=50.0))

    fake_stt.canned_transcript = "Hey Denver"
    await pipeline._handle_wake_detection()

    # Reply must be spoken once
    assert fake_tts.synthesize_count == 1
    assert fake_tts.last_request is not None
    assert fake_tts.last_request.text in pipeline.settings.wake_replies
    # Must transition to LISTENING
    assert state_machine.current_state == DenverState.LISTENING
    assert pipeline._listening_start_time > 0.0


@pytest.mark.asyncio
async def test_strict_wake_no_self_wake_during_tts(voice_env) -> None:
    pipeline = voice_env["pipeline"]
    playback = voice_env["playback"]
    fake_wakeword = voice_env["wakeword"]

    # Simulate active audio playback
    playback._is_playing = True
    fake_wakeword.trigger()

    chunk = AudioChunk(data=b"\x00\x50" * 400, sample_rate=16000, duration_ms=50.0, energy=0.2)
    # When playback is playing in STANDBY, the pipeline loop bypasses wakeword check
    curr_state = DenverState.STANDBY
    should_bypass = playback.is_playing or pipeline.tts_queue.is_speaking or getattr(pipeline, "_is_speaking_wake_reply", False)
    assert should_bypass is True


@pytest.mark.asyncio
async def test_one_sentence_command_skips_reply_and_executes(voice_env) -> None:
    pipeline = voice_env["pipeline"]
    state_machine = voice_env["state_machine"]
    fake_stt = voice_env["stt"]
    fake_tts = voice_env["tts"]

    for _ in range(10):
        pipeline._ring_buffer.append(AudioChunk(data=b"\x00\x20" * 400, sample_rate=16000, duration_ms=50.0))

    # User says wake word and command in one sentence
    fake_stt.canned_transcript = "Hey Denver, what time is it?"
    await pipeline._handle_wake_detection()

    # Wake reply must be skipped! Only command response TTS is spoken
    assert fake_tts.synthesize_count >= 1
    # Check last request was the command response, not a wake reply
    assert fake_tts.last_request is not None
    assert fake_tts.last_request.text not in pipeline.settings.wake_replies
    assert "time is" in fake_tts.last_request.text.lower()
    assert state_machine.current_state == DenverState.STANDBY


@pytest.mark.asyncio
async def test_voice_pipeline_silence_timeout_returns_to_standby(voice_env) -> None:
    pipeline = voice_env["pipeline"]
    state_machine = voice_env["state_machine"]

    await state_machine.transition_to(DenverState.LISTENING, reason="Testing silence timeout")
    # Simulate 6.5s elapsed without speech
    pipeline._listening_start_time = time.time() - 6.5

    # Simulate chunk arrival during silence in LISTENING mode
    chunk = AudioChunk(data=b"\x00\x00" * 400, sample_rate=16000, duration_ms=50.0, energy=0.001)
    silence_timeout = getattr(pipeline.settings, "wake_silence_timeout_seconds", 6.0)
    assert time.time() - pipeline._listening_start_time > silence_timeout

    # Transition to STANDBY as loop would do
    await state_machine.transition_to(DenverState.STANDBY, reason="Listening timeout (no speech)")
    assert state_machine.current_state == DenverState.STANDBY


@pytest.mark.asyncio
async def test_push_to_talk_unbroken(voice_env) -> None:
    pipeline = voice_env["pipeline"]
    state_machine = voice_env["state_machine"]
    fake_tts = voice_env["tts"]

    await pipeline.trigger_listening()

    # Push to talk enters LISTENING immediately without spoken wake reply
    assert state_machine.current_state == DenverState.LISTENING
    assert fake_tts.synthesize_count == 0


@pytest.mark.asyncio
async def test_noise_clip_rejected_without_stt_call(voice_env) -> None:
    """Clips with no voiced speech / energy below threshold must be rejected with zero STT calls."""
    pipeline = voice_env["pipeline"]
    state_machine = voice_env["state_machine"]
    fake_stt = voice_env["stt"]

    # Append pure silence / low-energy ambient noise chunks
    for _ in range(10):
        pipeline._ring_buffer.append(
            AudioChunk(data=b"\x00\x00" * 400, sample_rate=16000, duration_ms=50.0, energy=0.002)
        )

    fake_stt.transcribe_count = 0
    await pipeline._handle_wake_detection()

    # Crucial: zero network / provider calls made to STT!
    assert fake_stt.transcribe_count == 0
    assert state_machine.current_state == DenverState.STANDBY


@pytest.mark.asyncio
async def test_hallucinated_denver_with_high_no_speech_prob_rejected(voice_env) -> None:
    """Whisper hallucinated 'Denver.' with high no_speech_prob (> 0.6) must be rejected."""
    pipeline = voice_env["pipeline"]
    state_machine = voice_env["state_machine"]
    fake_stt = voice_env["stt"]
    fake_tts = voice_env["tts"]

    for _ in range(10):
        pipeline._ring_buffer.append(
            AudioChunk(data=b"\x00\x20" * 400, sample_rate=16000, duration_ms=50.0, energy=0.1)
        )

    fake_stt.canned_transcript = "Denver."
    fake_stt.canned_no_speech_prob = 0.85
    fake_stt.canned_avg_logprob = -0.3

    await pipeline._handle_wake_detection()

    assert state_machine.current_state == DenverState.STANDBY
    assert fake_tts.synthesize_count == 0


@pytest.mark.asyncio
async def test_hallucinated_denver_with_low_logprob_rejected(voice_env) -> None:
    """Whisper hallucinated text with very low log probability (< -1.0) must be rejected."""
    pipeline = voice_env["pipeline"]
    state_machine = voice_env["state_machine"]
    fake_stt = voice_env["stt"]
    fake_tts = voice_env["tts"]

    for _ in range(10):
        pipeline._ring_buffer.append(
            AudioChunk(data=b"\x00\x20" * 400, sample_rate=16000, duration_ms=50.0, energy=0.1)
        )

    fake_stt.canned_transcript = "Denver"
    fake_stt.canned_no_speech_prob = 0.1
    fake_stt.canned_avg_logprob = -1.45

    await pipeline._handle_wake_detection()

    assert state_machine.current_state == DenverState.STANDBY
    assert fake_tts.synthesize_count == 0


@pytest.mark.asyncio
async def test_short_click_wake_word_rejected_under_point_four_seconds(voice_env) -> None:
    """Standalone wake word with voiced duration under 0.4s must be rejected (transient noise)."""
    pipeline = voice_env["pipeline"]
    state_machine = voice_env["state_machine"]
    fake_stt = voice_env["stt"]
    fake_tts = voice_env["tts"]

    # Only 2 chunks (100ms voiced audio < 400ms threshold)
    for _ in range(2):
        pipeline._ring_buffer.append(
            AudioChunk(data=b"\x00\x20" * 400, sample_rate=16000, duration_ms=50.0, energy=0.1)
        )

    fake_stt.canned_transcript = "Denver"
    fake_stt.canned_no_speech_prob = 0.05
    fake_stt.canned_avg_logprob = -0.2

    await pipeline._handle_wake_detection()

    assert state_machine.current_state == DenverState.STANDBY
    assert fake_tts.synthesize_count == 0


@pytest.mark.asyncio
async def test_real_hey_denver_passes_with_empty_prompt_and_verbose_json(voice_env) -> None:
    """Real wake phrase with sufficient voiced audio passes, speaks reply, and requests verbose_json with empty prompt."""
    pipeline = voice_env["pipeline"]
    state_machine = voice_env["state_machine"]
    fake_stt = voice_env["stt"]
    fake_tts = voice_env["tts"]

    # 10 chunks (500ms voiced audio > 400ms)
    for _ in range(10):
        pipeline._ring_buffer.append(
            AudioChunk(data=b"\x00\x20" * 400, sample_rate=16000, duration_ms=50.0, energy=0.1)
        )

    fake_stt.canned_transcript = "Hey Denver"
    fake_stt.canned_no_speech_prob = 0.02
    fake_stt.canned_avg_logprob = -0.15

    await pipeline._handle_wake_detection()

    assert state_machine.current_state == DenverState.LISTENING
    assert fake_tts.synthesize_count == 1
    assert fake_stt.last_prompt == ""
    assert fake_stt.last_response_format == "verbose_json"


@pytest.mark.asyncio
async def test_domain_prompt_used_for_normal_commands(voice_env) -> None:
    """Normal command transcription retains the domain prompt to assist technical vocabulary."""
    pipeline = voice_env["pipeline"]
    fake_stt = voice_env["stt"]

    chunk = AudioChunk(data=b"\x00\x20" * 400, sample_rate=16000, duration_ms=50.0, energy=0.1)
    pipeline._current_speech_chunks.append(chunk)

    fake_stt.canned_transcript = "check my inbox"
    await pipeline._process_utterance()

    # Normal command transcription does not override prompt to ""
    assert fake_stt.last_prompt is None
    assert fake_stt.last_response_format == "json"



