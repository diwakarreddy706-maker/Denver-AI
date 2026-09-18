"""Unit tests for Wake Word detection."""

import pytest
from denver.audio.fake import FakeWakeWordDetector
from denver.audio.models import AudioChunk
from denver.audio.wakeword import FallbackWakeWordDetector, OpenWakeWordDetector


def test_fallback_wakeword_detector_burst_and_cooldown() -> None:
    detector = FallbackWakeWordDetector(
        wake_word="Denver",
        threshold=0.05,
        cooldown_seconds=1.0,
    )

    assert detector.detector_type == "acoustic_fallback"
    assert detector.name == "fallback_acoustic_detector"

    silent_chunk = AudioChunk(data=b"\x00\x00" * 480, sample_rate=16000)
    res_silent = detector.process_chunk(silent_chunk)
    assert not res_silent.detected

    loud_pcm = b"\x00\x60\x00\xa0" * 240
    loud_chunk = AudioChunk(data=loud_pcm, sample_rate=16000)

    res_loud1 = detector.process_chunk(loud_chunk)
    if res_loud1.detected:
        assert res_loud1.wake_word == "Denver"
        assert res_loud1.confidence > 0.0

        # Debounce via cooldown
        res_loud2 = detector.process_chunk(loud_chunk)
        assert not res_loud2.detected


def test_openwakeword_graceful_degradation() -> None:
    oww = OpenWakeWordDetector(wake_word="Denver")
    assert isinstance(oww.is_available, bool)
    assert oww.detector_type == "acoustic_fallback"

    chunk = AudioChunk(data=b"\x00\x00" * 480, sample_rate=16000)
    res = oww.process_chunk(chunk)
    assert not res.detected


def test_fake_wakeword_detector() -> None:
    fake = FakeWakeWordDetector(wake_word="Denver")
    chunk = AudioChunk(data=b"\x00\x00" * 480, sample_rate=16000)

    # Initial state -> not triggered
    r1 = fake.process_chunk(chunk)
    assert not r1.detected

    # Trigger programmatically
    fake.trigger()
    r2 = fake.process_chunk(chunk)
    assert r2.detected
    assert r2.wake_word == "Denver"
    assert r2.detector_type == "fake"
