"""Unit tests for Voice Activity Detection (VAD)."""

import pytest
from denver.audio.fake import FakeVAD
from denver.audio.models import AudioChunk, VoiceActivityState
from denver.audio.vad import EnergyVAD, SileroVAD


def test_energy_vad_silence_detection() -> None:
    vad = EnergyVAD(energy_threshold=0.05, min_speech_ms=60.0, min_silence_ms=100.0)

    silent_chunk = AudioChunk(data=b"\x00\x00" * 480, sample_rate=16000)
    res = vad.process_chunk(silent_chunk)

    assert not res.is_speech
    assert res.state == VoiceActivityState.SILENCE
    assert res.energy == 0.0


def test_energy_vad_speech_state_transitions() -> None:
    vad = EnergyVAD(energy_threshold=0.01, min_speech_ms=50.0, min_silence_ms=50.0)

    # Low frequency square-like wave (zero crossings far apart, high energy)
    loud_pcm = (b"\x00\x40" * 200) + (b"\x00\xc0" * 200)
    loud_chunk = AudioChunk(data=loud_pcm, sample_rate=16000, duration_ms=50.0, energy=0.15)
    silent_chunk = AudioChunk(data=b"\x00\x00" * 800, sample_rate=16000, duration_ms=50.0, energy=0.0)

    r1 = vad.process_chunk(loud_chunk)
    r2 = vad.process_chunk(loud_chunk)
    assert r2.is_speech is True
    assert r2.state in {VoiceActivityState.SPEECH_START, VoiceActivityState.SPEECH_ACTIVE}

    r3 = vad.process_chunk(loud_chunk)
    assert r3.is_speech is True
    assert r3.state == VoiceActivityState.SPEECH_ACTIVE

    r_end = vad.process_chunk(silent_chunk)
    assert r_end.state == VoiceActivityState.SPEECH_END
    assert r_end.is_speech is False

    r_silence = vad.process_chunk(silent_chunk)
    assert r_silence.state == VoiceActivityState.SILENCE


def test_energy_vad_reset() -> None:
    vad = EnergyVAD()
    vad.reset()
    assert vad.name == "energy_vad"


def test_silero_vad_graceful_degradation() -> None:
    silero = SileroVAD()
    assert isinstance(silero.is_available, bool)

    chunk = AudioChunk(data=b"\x00\x00" * 480, sample_rate=16000)
    res = silero.process_chunk(chunk)
    assert res.state == VoiceActivityState.SILENCE


def test_fake_vad_state_sequence() -> None:
    fake_vad = FakeVAD()
    fake_vad.set_sequence([
        VoiceActivityState.SPEECH_START,
        VoiceActivityState.SPEECH_ACTIVE,
        VoiceActivityState.SPEECH_END,
        VoiceActivityState.SILENCE,
    ])
    chunk = AudioChunk(data=b"\x00\x00" * 480, sample_rate=16000)

    s1 = fake_vad.process_chunk(chunk)
    assert s1.state == VoiceActivityState.SPEECH_START
    assert s1.is_speech is True

    s2 = fake_vad.process_chunk(chunk)
    assert s2.state == VoiceActivityState.SPEECH_ACTIVE

    s3 = fake_vad.process_chunk(chunk)
    assert s3.state == VoiceActivityState.SPEECH_END

    s4 = fake_vad.process_chunk(chunk)
    assert s4.state == VoiceActivityState.SILENCE
    assert s4.is_speech is False
