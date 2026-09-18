"""Unit tests for Denver AudioCapture and bounded ring buffer."""

import asyncio
import pytest
from denver.audio.capture import AudioCapture
from denver.audio.fake import FakeAudioCapture
from denver.audio.models import AudioChunk, AudioFormat


@pytest.mark.asyncio
async def test_audio_capture_lifecycle() -> None:
    fmt = AudioFormat(sample_rate=16000, chunk_size=800)
    capture = AudioCapture(audio_format=fmt, max_buffer_seconds=1.0)

    assert not capture.is_capturing
    assert capture.buffer_size == 0

    started = await capture.start()
    assert isinstance(started, bool)

    chunk = await capture.read_chunk(timeout=0.05)
    if chunk is not None:
        assert isinstance(chunk, AudioChunk)
        assert chunk.sample_rate == 16000

    await capture.stop()
    assert not capture.is_capturing


@pytest.mark.asyncio
async def test_audio_capture_bounded_buffer_overflow() -> None:
    fmt = AudioFormat(sample_rate=16000, chunk_size=800)
    # Max buffer of 0.1s -> ~2-3 chunks max
    capture = AudioCapture(audio_format=fmt, max_buffer_seconds=0.1)

    chunk_bytes = fmt.chunk_bytes
    for _ in range(10):
        c = AudioChunk(data=b"\x00" * chunk_bytes, sample_rate=16000)
        capture._enqueue_chunk(c)

    # Bounded buffer should prevent memory leak and maintain max bound
    assert capture.buffer_size <= 4

    capture.clear()
    assert capture.buffer_size == 0


@pytest.mark.asyncio
async def test_fake_audio_capture() -> None:
    fake_capture = FakeAudioCapture()
    assert not fake_capture.is_capturing

    await fake_capture.start()
    assert fake_capture.is_capturing

    # Feed a custom chunk
    chunk = AudioChunk(data=b"\x00\x01" * 400, sample_rate=16000)
    fake_capture.inject_chunk(chunk)

    read = await fake_capture.read_chunk(timeout=0.1)
    assert read is not None
    assert read.data == chunk.data

    # Synthetic speech injection
    speech_chunks = fake_capture.inject_synthetic_speech(duration_ms=200.0)
    assert len(speech_chunks) > 0

    await fake_capture.stop()
    assert not fake_capture.is_capturing
