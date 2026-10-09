"""Unit tests for VoicePipeline streaming sentence-boundary TTS execution."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from denver.audio.models import Transcript, TTSRequest, TTSResult
from denver.audio.pipeline import VoicePipeline
from denver.commands.models import CommandResponse
from denver.config.settings import DenverSettings
from denver.runtime.events import TTSStarted, TTSCompleted, AudioPlaybackStarted, AudioPlaybackCompleted


@pytest.mark.asyncio
async def test_voice_pipeline_streaming_sentence_order_and_no_lost_text():
    settings = DenverSettings(tts_enabled=True, tts_streaming_enabled=True)
    
    mock_command_service = MagicMock()
    mock_command_service.is_ai_command.return_value = True

    async def mock_tokens(text):
        tokens = [
            "First sentence is complete. ",
            "Second sentence is fast! ",
            "And here is the final sentence.",
        ]
        for t in tokens:
            await asyncio.sleep(0.01)
            yield t

    mock_command_service.stream_ai_tokens = mock_tokens

    pipeline = VoicePipeline(
        command_service=mock_command_service,
        settings=settings,
    )

    synthesized_sentences = []

    async def mock_synthesize(req: TTSRequest):
        synthesized_sentences.append(req.text)
        return TTSResult(
            audio_data=b"\x00" * 200,
            duration_seconds=0.5,
            format="mp3",
            sample_rate=24000,
            success=True,
            latency_ms=10.0,
        )

    pipeline.tts.synthesize = AsyncMock(side_effect=mock_synthesize)
    played_chunks = []
    pipeline.playback.play_bytes = AsyncMock(side_effect=lambda data, format: played_chunks.append(data) or True)

    handled = await pipeline._handle_streaming_ai_voice_response("Explain relativity", t_request_start=100.0)

    assert handled is True
    assert len(synthesized_sentences) == 3
    assert synthesized_sentences[0] == "First sentence is complete."
    assert synthesized_sentences[1] == "Second sentence is fast!"
    assert synthesized_sentences[2] == "And here is the final sentence."
    assert len(played_chunks) == 3
    assert "first_sentence_detected" in pipeline.last_latency_metrics
    assert "ttfa_seconds" in pipeline.last_latency_metrics


@pytest.mark.asyncio
async def test_voice_pipeline_streaming_empty_falls_back():
    settings = DenverSettings(tts_enabled=True, tts_streaming_enabled=True)
    
    mock_command_service = MagicMock()
    mock_command_service.is_ai_command.return_value = True

    async def empty_tokens(text):
        if False:
            yield ""

    mock_command_service.stream_ai_tokens = empty_tokens

    pipeline = VoicePipeline(
        command_service=mock_command_service,
        settings=settings,
    )

    handled = await pipeline._handle_streaming_ai_voice_response("Unknown command", t_request_start=100.0)
    # Must return False so pipeline falls back to whole-utterance process_command
    assert handled is False
