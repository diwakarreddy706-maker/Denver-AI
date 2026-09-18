"""Unit tests for Denver audio data models and contracts."""

import pytest
from denver.audio.models import (
    AudioChunk,
    AudioDevice,
    AudioDeviceType,
    AudioFormat,
    AudioPipelineStatus,
    SpeechResult,
    TTSRequest,
    TTSResult,
    Transcript,
    VoiceActivity,
    VoiceActivityState,
    WakeWordResult,
)


def test_audio_device_properties() -> None:
    dev = AudioDevice(
        index=0,
        name="Realtek High Definition Audio",
        channels=2,
        default_samplerate=16000,
        is_input=True,
        is_output=False,
        is_default=True,
        host_api="WASAPI",
    )
    assert dev.is_input is True
    assert dev.is_output is False
    assert dev.name == "Realtek High Definition Audio"
    assert dev.channels == 2
    assert dev.to_dict()["index"] == 0
    assert dev.to_dict()["is_input"] is True


def test_audio_format_properties() -> None:
    fmt = AudioFormat(sample_rate=16000, channels=1, sample_width=2, chunk_size=800)
    assert fmt.bytes_per_sample == 2
    assert fmt.chunk_bytes == 1600  # 800 * 2
    assert fmt.frame_duration_ms == 50.0  # 800 / 16000 * 1000


def test_audio_chunk_properties() -> None:
    silent_pcm = b"\x00\x00" * 800
    chunk_silent = AudioChunk(
        data=silent_pcm,
        sample_rate=16000,
        channels=1,
        sample_width=2,
        duration_ms=50.0,
        energy=0.0,
    )

    assert chunk_silent.sample_count == 800
    assert chunk_silent.energy == 0.0
    assert chunk_silent.duration_ms == 50.0

    loud_pcm = b"\x00\x40\x00\xc0" * 400
    chunk_loud = AudioChunk(
        data=loud_pcm,
        sample_rate=16000,
        channels=1,
        sample_width=2,
        duration_ms=50.0,
        energy=0.15,
    )
    assert chunk_loud.sample_count == 800
    assert chunk_loud.energy == 0.15


def test_voice_activity_model() -> None:
    va = VoiceActivity(
        state=VoiceActivityState.SPEECH_ACTIVE,
        confidence=0.95,
        energy=0.25,
        is_speech=True,
    )
    assert va.is_speech is True
    assert va.state == VoiceActivityState.SPEECH_ACTIVE
    assert va.confidence == 0.95


def test_wake_word_result_model() -> None:
    res = WakeWordResult(
        detected=True,
        wake_word="Denver",
        confidence=0.88,
        detector_type="acoustic",
    )
    assert res.detected is True
    assert res.wake_word == "Denver"
    assert res.confidence == 0.88


def test_transcript_model() -> None:
    tr = Transcript(
        text="Denver, what time is it?",
        is_final=True,
        confidence=0.98,
        provider="whisper",
        latency_ms=45.2,
    )
    assert tr.text == "Denver, what time is it?"
    assert tr.is_final is True
    assert tr.provider == "whisper"
    assert tr.latency_ms == 45.2
    assert tr.to_dict()["text"] == "Denver, what time is it?"


def test_speech_result_model() -> None:
    sr = SpeechResult(
        success=True,
        transcript="Denver, status report",
        duration_seconds=1.5,
        confidence=0.99,
    )
    assert sr.success is True
    assert sr.transcript == "Denver, status report"


def test_tts_request_and_result() -> None:
    req = TTSRequest(text="Hello, sir. Denver is ready.", voice="en-GB-RyanNeural", rate="+0%")
    assert req.text == "Hello, sir. Denver is ready."

    res = TTSResult(
        audio_data=b"\x00\x00" * 100,
        format="wav",
        duration_seconds=1.2,
        latency_ms=120.0,
        provider="edge_tts",
        success=True,
    )
    assert res.success is True
    assert res.duration_seconds == 1.2
    assert res.provider == "edge_tts"


def test_audio_pipeline_status() -> None:
    status = AudioPipelineStatus(
        status="READY",
        capture_active=True,
        vad_active=True,
        wakeword_active=True,
        stt_active=True,
        tts_active=True,
        playback_active=False,
        devices={"input": "Microphone", "output": "Speakers"},
        components={"vad": "EnergyVAD", "wakeword": "Fallback"},
    )
    assert status.status == "READY"
    assert status.capture_active is True
    assert status.devices["input"] == "Microphone"
    assert status.to_dict()["status"] == "READY"
