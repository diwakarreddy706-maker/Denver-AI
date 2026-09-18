"""Unit tests for Speech-to-Text (STT) providers."""

import pytest
from denver.audio.fake import FakeSTTProvider
from denver.audio.models import AudioFormat, Transcript
from denver.audio.stt import GroqWhisperSTTProvider, WhisperSTTProvider
from denver.security.vault import DenverVault


@pytest.mark.asyncio
async def test_fake_stt_provider() -> None:
    fake_stt = FakeSTTProvider(canned_transcript="Denver, status report")

    assert fake_stt.name == "fake_stt"
    assert fake_stt.is_available is True

    t1 = await fake_stt.transcribe(b"\x00" * 960, AudioFormat())
    assert t1.text == "Denver, status report"
    assert fake_stt.transcribe_count == 1


@pytest.mark.asyncio
async def test_whisper_stt_provider_graceful_fallback() -> None:
    stt = WhisperSTTProvider(model_size="base")
    assert stt.name == "whisper"
    assert isinstance(stt.is_available, bool)

    tr = await stt.transcribe(b"\x00" * 960, AudioFormat())
    assert isinstance(tr, Transcript)


@pytest.mark.asyncio
async def test_groq_whisper_stt_provider_availability() -> None:
    vault = DenverVault()
    groq_stt = GroqWhisperSTTProvider(vault=vault)
    assert groq_stt.name == "groq_whisper"
    assert isinstance(groq_stt.is_available, bool)

    health = groq_stt.get_health_status()
    assert "status" in health
    assert health["provider"] == "groq_whisper"
