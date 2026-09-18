"""Unit tests for Audio Playback and barge-in interruption."""

import asyncio
import pytest
from denver.audio.fake import FakeAudioPlayback
from denver.audio.models import AudioFormat
from denver.audio.playback import AudioPlayback


@pytest.mark.asyncio
async def test_audio_playback_basics() -> None:
    playback = AudioPlayback()
    assert not playback.is_playing

    # Stop when nothing is playing should be a clean no-op
    await playback.stop()
    assert not playback.is_playing


@pytest.mark.asyncio
async def test_fake_audio_playback_play_and_stop() -> None:
    fake = FakeAudioPlayback()
    assert not fake.is_playing

    # Play bytes
    res = await fake.play_bytes(b"\x00" * 960, format="wav")
    assert res is True
    assert fake.play_count == 1
    assert len(fake.played_payloads) == 1

    await fake.stop()
    assert not fake.is_playing
