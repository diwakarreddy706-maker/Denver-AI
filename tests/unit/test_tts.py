"""Unit tests for Text-to-Speech (TTS) providers."""

import pytest
from denver.audio.fake import FakeTTSProvider
from denver.audio.models import TTSRequest, TTSResult
from denver.audio.tts import EdgeTTSProvider, PiperTTSProvider, WindowsTTSProvider


@pytest.mark.asyncio
async def test_fake_tts_provider() -> None:
    fake_tts = FakeTTSProvider()
    assert fake_tts.name == "fake_tts"
    assert fake_tts.is_available is True

    req = TTSRequest(text="Denver is fully operational.")
    res = await fake_tts.synthesize(req)

    assert res.success is True
    assert res.provider == "fake_tts"
    assert len(res.audio_data) > 0


@pytest.mark.asyncio
async def test_edge_tts_provider_availability() -> None:
    tts = EdgeTTSProvider(default_voice="en-GB-RyanNeural")
    assert tts.name == "edge_tts"
    assert isinstance(tts.is_available, bool)

    health = tts.get_health_status()
    assert "status" in health
    assert health["provider"] == "edge_tts"


@pytest.mark.asyncio
async def test_windows_tts_provider() -> None:
    win_tts = WindowsTTSProvider()
    assert win_tts.name == "windows_sapi"
    assert isinstance(win_tts.is_available, bool)


@pytest.mark.asyncio
async def test_piper_tts_provider() -> None:
    piper_tts = PiperTTSProvider()
    assert piper_tts.name == "piper_tts"
    assert isinstance(piper_tts.is_available, bool)
