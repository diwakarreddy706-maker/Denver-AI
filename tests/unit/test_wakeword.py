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


def test_strict_wake_phrase_valid_mishears() -> None:
    from denver.audio.wakeword import check_strict_wake_phrase

    valid_inputs = [
        ("Denver", "denver", ""),
        ("Hey Denver", "hey denver", ""),
        ("hey denver.", "hey denver", ""),
        ("Hay Denver", "hay denver", ""),
        ("Danver", "danver", ""),
        ("Denvar", "denvar", ""),
        ("Denber", "denber", ""),
        ("Oh hey denver", "hey denver", ""),
        ("Um Denver", "denver", ""),
    ]
    for text, expected_phrase, expected_trailing in valid_inputs:
        is_valid, matched, trailing = check_strict_wake_phrase(text)
        assert is_valid is True, f"Failed for valid input: {text}"
        assert matched == expected_phrase
        assert trailing == expected_trailing


def test_strict_wake_phrase_one_sentence_command() -> None:
    from denver.audio.wakeword import check_strict_wake_phrase

    is_valid, matched, trailing = check_strict_wake_phrase("Hey Denver, open Chrome")
    assert is_valid is True
    assert matched == "hey denver"
    assert trailing == "open Chrome"

    is_valid, matched, trailing = check_strict_wake_phrase("Denver, what time is it?")
    assert is_valid is True
    assert matched == "denver"
    assert trailing == "what time is it?"

    is_valid, matched, trailing = check_strict_wake_phrase("Danver launch notepad")
    assert is_valid is True
    assert matched == "danver"
    assert trailing == "launch notepad"


def test_strict_wake_phrase_rejected() -> None:
    from denver.audio.wakeword import check_strict_wake_phrase

    rejected_inputs = [
        "hello everyone",
        "good morning",
        "play synthwave",
        "turn on the lights",
        "just random background noise",
        "",
        "   ",
        "...",
    ]
    for text in rejected_inputs:
        is_valid, matched, trailing = check_strict_wake_phrase(text)
        assert is_valid is False, f"Should have rejected: {text}"
        assert matched == ""
        assert trailing == ""


def test_strict_wake_phrase_custom_config_list() -> None:
    from denver.audio.wakeword import check_strict_wake_phrase

    custom_phrases = ("computer", "hey computer")
    is_valid, matched, trailing = check_strict_wake_phrase("Hey Computer, status report", accepted_phrases=custom_phrases)
    assert is_valid is True
    assert matched == "hey computer"
    assert trailing == "status report"

    # Denver should now be rejected with custom list
    is_valid, _, _ = check_strict_wake_phrase("Denver", accepted_phrases=custom_phrases)
    assert is_valid is False
