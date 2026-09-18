"""Unit tests for WASAPI System Audio Loopback & Live Meeting Intelligence Subsystem."""

import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any
import pytest

from denver.audio.loopback import WasapiLoopbackCapture
from denver.audio.meeting import (
    MeetingIntelligenceEngine,
    MeetingSession,
    MeetingTranscriptSegment,
)
from denver.audio.models import AudioFormat, Transcript
from denver.audio.stt import SpeechToTextProvider
from denver.commands.router import IntentRouter
from denver.commands.service import CommandEngineService
from denver.memory.database import DenverDatabase
from denver.memory.memory_service import MemoryService


class MockSTTProvider(SpeechToTextProvider):
    """Mock STT provider for deterministic meeting audio tests."""

    def __init__(self, transcript_text: str = "We need to fix the deployment pipeline by tomorrow.") -> None:
        self.transcript_text = transcript_text
        self.transcribe_called = False

    @property
    def name(self) -> str:
        return "mock_stt"

    @property
    def is_available(self) -> bool:
        return True

    async def transcribe(self, audio_bytes: bytes, audio_format: AudioFormat | None = None) -> Transcript:
        self.transcribe_called = True
        return Transcript(
            text=self.transcript_text,
            is_final=True,
            confidence=0.99,
            provider=self.name,
        )


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def memory_service(temp_dir):
    db_path = temp_dir / "test_memory.sqlite3"
    db = DenverDatabase(db_path=str(db_path))
    return MemoryService(db=db, privacy_mode=False)


@pytest.mark.asyncio
async def test_wasapi_loopback_capture_lifecycle():
    """Test WASAPI loopback start, simulated chunk push, buffer retrieval, and stop."""
    loopback = WasapiLoopbackCapture(max_buffer_seconds=5.0)
    assert not loopback.is_capturing
    assert loopback.buffer_size == 0

    started = await loopback.start()
    assert started is True
    assert loopback.is_capturing

    # Push mock PCM chunks (simulating system audio from Zoom/Meet)
    mock_pcm = b"\x00\x01\x00\x02" * 100
    chunk = loopback.push_mock_chunk(mock_pcm, duration_ms=100.0)
    assert loopback.buffer_size == 1
    assert chunk.duration_ms == 100.0

    buffered = loopback.get_buffered_audio_bytes()
    assert buffered == mock_pcm

    read = await loopback.read_chunk(timeout=0.5)
    assert read is not None
    assert read.data == mock_pcm

    await loopback.stop()
    assert not loopback.is_capturing


@pytest.mark.asyncio
async def test_meeting_intelligence_session_lifecycle(temp_dir):
    """Test starting, ingesting segments, and stopping meeting session."""
    engine = MeetingIntelligenceEngine(output_dir=temp_dir, user_name="Diwakar")
    assert not engine.is_meeting_active

    session = await engine.start_meeting(title="Architecture Sync")
    assert engine.is_meeting_active
    assert session.title == "Architecture Sync"
    assert session.is_active

    # Ingest conversational segments
    engine.ingest_transcript_segment(
        text="Welcome everyone to the architecture review.",
        speaker="Alice",
    )
    engine.ingest_transcript_segment(
        text="Diwakar, please make sure to review the PR before end of day.",
        speaker="Bob",
    )
    engine.ingest_transcript_segment(
        text="Action item: deploy the staging environment at 4 PM.",
        speaker="Charlie",
    )
    engine.ingest_transcript_segment(
        text="We decided to use PostgreSQL for relational storage.",
        speaker="Alice",
    )

    # Verify extraction
    assert len(session.segments) == 4
    assert len(session.mentions) == 1
    assert "Bob: Diwakar, please make sure to review" in session.mentions[0]
    assert len(session.action_items) >= 1
    assert any("deploy the staging environment" in item.lower() for item in session.action_items)
    assert len(session.key_points) >= 1

    stopped_session = await engine.stop_meeting()
    assert stopped_session is not None
    assert not engine.is_meeting_active
    assert not stopped_session.is_active

    # Check that markdown notes file was created
    md_files = list(temp_dir.glob("*.md"))
    assert len(md_files) == 1
    content = md_files[0].read_text(encoding="utf-8")
    assert "# 📋 Meeting Notes: Architecture Sync" in content
    assert "## ✅ Action Items & Next Steps" in content
    assert "## 🔔 Direct Mentions (Diwakar)" in content
    assert "Alice" in content
    assert "Bob" in content


@pytest.mark.asyncio
async def test_meeting_intelligence_mention_callback(temp_dir):
    """Verify mention notification hooks are triggered in real-time."""
    engine = MeetingIntelligenceEngine(output_dir=temp_dir, user_name="Diwakar")
    mentions_caught = []

    def on_mention(user: str, segment: MeetingTranscriptSegment):
        mentions_caught.append((user, segment.speaker, segment.text))

    engine.register_mention_callback(on_mention)
    await engine.start_meeting("Team Standup")

    engine.ingest_transcript_segment("Hey Diwakar what do you think?", speaker="Sarah")
    engine.ingest_transcript_segment("Everything looks good.", speaker="Diwakar")

    assert len(mentions_caught) == 1
    assert mentions_caught[0][0] == "Diwakar"
    assert mentions_caught[0][1] == "Sarah"

    await engine.stop_meeting()


@pytest.mark.asyncio
async def test_meeting_intelligence_with_stt(temp_dir):
    """Test live audio chunk transcription through STT provider."""
    mock_stt = MockSTTProvider("Action item: update the documentation.")
    engine = MeetingIntelligenceEngine(stt_provider=mock_stt, output_dir=temp_dir)
    await engine.start_meeting("Docs Review")

    pcm_data = b"\x01\x00" * 8000
    text = await engine.transcribe_audio_chunk(pcm_data, speaker="Remote")
    assert text == "Action item: update the documentation."
    assert mock_stt.transcribe_called is True
    assert len(engine.current_session.segments) == 1
    assert any("update the documentation" in a for a in engine.current_session.action_items)

    await engine.stop_meeting()


def test_meeting_router_intents():
    """Verify IntentRouter correctly classifies meeting-related utterances."""
    router = IntentRouter()

    # Start meeting intents
    i1 = router.route("start meeting notes")
    assert i1.action_name == "start_meeting_notes"
    assert i1.params.get("title") == "Live Meeting"

    i2 = router.route("start meeting notes Sprint Planning")
    assert i2.action_name == "start_meeting_notes"
    assert i2.params.get("title") == "Sprint Planning"

    i3 = router.route("transcribe meeting")
    assert i3.action_name == "start_meeting_notes"

    # Stop meeting intents
    i4 = router.route("stop meeting notes")
    assert i4.action_name == "stop_meeting_notes"

    i5 = router.route("end meeting")
    assert i5.action_name == "stop_meeting_notes"

    # Summary intents
    i6 = router.route("get meeting summary")
    assert i6.action_name == "get_meeting_summary"

    i7 = router.route("show meeting notes")
    assert i7.action_name == "get_meeting_summary"


@pytest.mark.asyncio
async def test_meeting_command_service_end_to_end(memory_service, temp_dir):
    """End-to-end command execution for start, note capture, summary, and stop."""
    service = CommandEngineService(memory_service=memory_service)
    service.meeting_engine.output_dir = temp_dir

    # 1. Start meeting via natural command
    res1 = await service.process_command("start meeting notes Product Launch")
    assert res1.success is True
    assert "started meeting intelligence session 'product launch'" in res1.message.lower()
    assert service.meeting_engine.is_meeting_active

    # 2. Ingest some conversational meeting segments
    service.meeting_engine.ingest_transcript_segment(
        text="Action item: coordinate with the marketing team on Thursday.",
        speaker="Sarah",
    )
    service.meeting_engine.ingest_transcript_segment(
        text="Diwakar will handle the backend API deployment.",
        speaker="Dave",
    )

    # 3. Retrieve live summary
    res2 = await service.process_command("meeting summary")
    assert res2.success is True
    assert "product launch" in res2.message.lower()
    assert "coordinate with the marketing team" in res2.message

    # 4. Stop meeting
    res3 = await service.process_command("stop meeting notes")
    assert res3.success is True
    assert "ended" in res3.message
    assert not service.meeting_engine.is_meeting_active
