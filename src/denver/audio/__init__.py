"""Denver Voice & Audio Subsystem.

This package provides audio capture, voice activity detection (VAD),
wake-word detection, speech-to-text (STT), text-to-speech (TTS),
audio playback with barge-in support, and the orchestrated VoicePipeline.
"""

from denver.audio.capture import AudioCapture
from denver.audio.device import AudioDeviceManager
from denver.audio.fake import (
    FakeAudioCapture,
    FakeAudioPlayback,
    FakeSTTProvider,
    FakeTTSProvider,
    FakeVAD,
    FakeWakeWordDetector,
)
from denver.audio.models import (
    AudioChunk,
    AudioDevice,
    AudioFormat,
    AudioPipelineStatus,
    SpeechResult,
    Transcript,
    TTSRequest,
    TTSResult,
    VoiceActivity,
    WakeWordResult,
)
from denver.audio.playback import AudioPlayback
from denver.audio.pipeline import VoicePipeline
from denver.audio.stt import (
    GroqWhisperSTTProvider,
    SpeechToTextProvider,
    WhisperSTTProvider,
)
from denver.audio.tts import (
    EdgeTTSProvider,
    PiperTTSProvider,
    TextToSpeechProvider,
    WindowsTTSProvider,
)
from denver.audio.vad import EnergyVAD, SileroVAD, VADEngine
from denver.audio.wakeword import (
    FallbackWakeWordDetector,
    OpenWakeWordDetector,
    WakeWordDetector,
)

from denver.audio.loopback import WasapiLoopbackCapture
from denver.audio.meeting import (
    MeetingIntelligenceEngine,
    MeetingSession,
    MeetingTranscriptSegment,
)
from denver.audio.push_to_talk import PushToTalkListener
from denver.audio.tts_cache import CachedTTSProvider, TTSPhraseCache
from denver.audio.tts_queue import DenverTTSQueue, TTSPriority

__all__ = [
    "AudioCapture",
    "AudioChunk",
    "AudioDevice",
    "AudioDeviceManager",
    "AudioFormat",
    "AudioPipelineStatus",
    "AudioPlayback",
    "CachedTTSProvider",
    "DenverTTSQueue",
    "EdgeTTSProvider",
    "EnergyVAD",
    "FakeAudioCapture",
    "FakeAudioPlayback",
    "FakeSTTProvider",
    "FakeTTSProvider",
    "FakeVAD",
    "FakeWakeWordDetector",
    "FallbackWakeWordDetector",
    "GroqWhisperSTTProvider",
    "MeetingIntelligenceEngine",
    "MeetingSession",
    "MeetingTranscriptSegment",
    "OpenWakeWordDetector",
    "PiperTTSProvider",
    "PushToTalkListener",
    "SileroVAD",
    "SpeechResult",
    "SpeechToTextProvider",
    "TTSPriority",
    "TTSPhraseCache",
    "TTSRequest",
    "TTSResult",
    "TextToSpeechProvider",
    "VADEngine",
    "VoiceActivity",
    "VoicePipeline",
    "WakeWordDetector",
    "WakeWordResult",
    "WasapiLoopbackCapture",
    "WhisperSTTProvider",
    "WindowsTTSProvider",
]
