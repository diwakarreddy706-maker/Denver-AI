# Denver Phase 4 — Denver Voice Engine Implementation

## Executive Summary

Phase 4 implements the complete voice and audio subsystem for **Denver AI Assistant**, integrating real-time microphone capture, continuous voice activity detection (VAD), acoustic and trained wake-word detection ("Denver"), speech-to-text (STT), text-to-speech (TTS), and responsive audio playback with instant barge-in support.

Following Denver's core architectural tenets:
1. **Audio has ZERO execution authority**: Audio produces transcripts only; all actions flow authoritatively through `CommandEngineService` $\to$ `ActionRegistry` $\to$ `SafetyValidator` $\to$ `ActionExecutor`.
2. **Deterministic safety & state integration**: Audio state transitions obey the state machine (`STANDBY` $\to$ `LISTENING` $\to$ `PROCESSING` $\to$ `SPEAKING` $\to$ `STANDBY`).
3. **Safe Barge-in**: User speech detected during `SPEAKING` immediately halts audio playback, transitions `SPEAKING` $\to$ `LISTENING`, and prevents previous speech continuation.
4. **Privacy-first design**: Raw audio buffers are strictly in-memory, bounded by ring buffers, never logged, and never persisted to SQLite.
5. **Python 3.14 & Offline-first compatibility**: Full offline test doubles (`Fake*`) and graceful degradation when optional ML libraries (ONNX, faster-whisper, openWakeWord) or audio hardware are absent.

---

## Complete Architecture & Pipeline

```
  [ MICROPHONE ]
        │ (16kHz, 16-bit Mono PCM)
        ▼
┌─────────────────────────────────────────────────────────┐
│                    AudioCapture                         │
│  - PortAudio / WASAPI stream (sounddevice)              │
│  - ctypes winmm fallback device enumeration             │
│  - Bounded memory ring buffer                           │
└──────────────────────────┬──────────────────────────────┘
                           │ AudioChunk (50ms)
                           ▼
┌─────────────────────────────────────────────────────────┐
│                     VoicePipeline                       │
│                                                         │
│   [ STANDBY State ]                                     │
│         │                                               │
│         ▼                                               │
│   WakeWordDetector ("Denver")                           │
│   ├── OpenWakeWordDetector (Trained ONNX model)         │
│   └── FallbackWakeWordDetector (Acoustic burst)         │
│         │                                               │
│         ▼ (WakeWordDetected Event)                      │
│   [ Transition: STANDBY -> LISTENING ]                  │
│         │                                               │
│   [ LISTENING State ]                                   │
│         │                                               │
│         ▼                                               │
│   VADEngine (Voice Activity Detection)                  │
│   ├── EnergyVAD (RMS Energy + ZCR + Hangover smoothing) │
│   └── SileroVAD (ONNX Silero model adapter)             │
│         │                                               │
│         ▼ (SpeechStopped Event / Utterance Buffer)      │
│   [ Transition: LISTENING -> PROCESSING ]               │
│         │                                               │
│         ▼                                               │
│   SpeechToTextProvider                                  │
│   ├── WhisperSTTProvider (Local faster-whisper)         │
│   └── GroqWhisperSTTProvider (Vault-authenticated Groq) │
│         │                                               │
│         ▼ Transcript                                    │
│   ┌─────────────────────────────────────────────────┐   │
│   │ CommandEngineService (Authoritative Execution)  │   │
│   │  CommandNormalizer -> DeterministicRouter       │   │
│   │  -> SafetyValidator -> ActionExecutor           │   │
│   │  -> ProviderRouter (LLM Fallback if needed)     │   │
│   └────────────────────────┬────────────────────────┘   │
│                            │                            │
│                            ▼ CommandResponse            │
│   [ Transition: PROCESSING -> SPEAKING ]                │
│         │                                               │
│         ▼                                               │
│   TextToSpeechProvider                                  │
│   ├── EdgeTTSProvider (Microsoft Edge Neural Voice)     │
│   ├── WindowsTTSProvider (SAPI5 local synthesizer)      │
│   └── PiperTTSProvider (Fast local ONNX TTS)            │
│         │                                               │
│         ▼ TTSResult (Audio bytes)                       │
│   AudioPlayback (Background Speaker Queue)              │
│   ├── Instant Cancellation on Barge-in                  │
│   └── [ Transition: SPEAKING -> STANDBY ]               │
│                                                         │
│   [ BARGE-IN INTERRUPTION ]                             │
│   When in SPEAKING state and VAD detects user speech:   │
│     1. AudioPlayback.stop() immediately executed        │
│     2. BargeInDetected event published                  │
│     3. [ Transition: SPEAKING -> LISTENING ]            │
└─────────────────────────────────────────────────────────┘
```

---

## Subsystem Details

### 1. Audio Device Discovery (`src/denver/audio/device.py`)
- Hardware inspection utilizing `sounddevice` / PortAudio with automatic fallback to Windows Multimedia API (`winmm.dll` via `ctypes`).
- Inspects input channels, output channels, default devices, and host APIs.
- Emits health diagnostics with `READY`, `DEGRADED`, or `UNAVAILABLE`.

### 2. Audio Capture (`src/denver/audio/capture.py`)
- Real-time asynchronous PCM stream capture.
- Enforces maximum bounded memory ring buffer (`max_buffer_seconds`, default 10s).
- Noise floor auto-calibration baseline.
- `clear()` flushes all buffers to guarantee zero stale audio bleed.

### 3. Voice Activity Detection (`src/denver/audio/vad.py`)
- **`EnergyVAD`**: Pure Python time-domain RMS energy analysis combined with Zero-Crossing Rate (ZCR) filtering (`zcr < 0.45`) and hangover smoothing (e.g. 500ms silence tolerance).
- **`SileroVAD`**: Adapter for ONNX-based neural voice activity detection with graceful fallback to `EnergyVAD`.

### 4. Wake-Word Detection (`src/denver/audio/wakeword.py`)
- Truthfully distinguished detectors:
  - `OpenWakeWordDetector`: Trained model adapter (`detector_type="trained_openwakeword"`).
  - `FallbackWakeWordDetector`: Acoustic energy burst detector with temporal cooldown debouncing (`detector_type="acoustic_fallback"`).
  - `FakeWakeWordDetector`: Programmatic test double (`detector_type="fake"`).

### 5. Speech-to-Text (`src/denver/audio/stt.py`)
- **`WhisperSTTProvider`**: Offline faster-whisper provider with explicit loading (`load_model()`) to avoid automatic downloads.
- **`GroqWhisperSTTProvider`**: Cloud-accelerated Whisper-large-v3 using credentials securely fetched from `DenverVault`.

### 6. Text-to-Speech (`src/denver/audio/tts.py`)
- **`EdgeTTSProvider`**: Natural high-fidelity neural speech via `edge-tts` (default: `en-GB-RyanNeural`).
- **`WindowsTTSProvider`**: Built-in Windows SAPI5 synthesizer fallback.
- **`PiperTTSProvider`**: Local fast neural TTS engine.

### 7. Audio Playback & Barge-In (`src/denver/audio/playback.py`)
- Asynchronous playback using `sounddevice` / `winsound` fallback.
- Non-blocking async worker queue.
- Immediate interruption: Calling `playback.stop()` cancels the playing stream and flushes remaining playback queues instantaneously.

### 8. Voice Pipeline Orchestration (`src/denver/audio/pipeline.py`)
- Glues the end-to-end flow with state machine and event bus.
- Emits structured telemetry events: `SpeechStarted`, `SpeechStopped`, `WakeWordDetected`, `TranscriptProduced`, `TTSStarted`, `TTSCompleted`, `AudioPlaybackStarted`, `AudioPlaybackCompleted`, `AudioPlaybackStopped`, `BargeInDetected`.

### 9. Test Doubles (`src/denver/audio/fake.py`)
- `FakeAudioCapture`: Allows deterministic chunk and synthetic speech injection.
- `FakeVAD`: Programmable state sequence engine.
- `FakeWakeWordDetector`: Single-shot and multi-shot wake-word triggering.
- `FakeSTTProvider`: Returns deterministic canned transcripts.
- `FakeTTSProvider`: Generates synthetic audio buffers.
- `FakeAudioPlayback`: Tracks played payloads and supports barge-in simulation.

---

## Health & Telemetry Reporting

When querying `DenverHealthService.get_health_report()`, the audio subsystem is reported granularly:
```json
{
  "subsystems": {
    "core_runtime": "READY",
    "event_bus": "READY",
    "database": "READY",
    "audio": "READY",
    "ai_providers": "UNAVAILABLE"
  },
  "audio": {
    "status": "READY",
    "capture_active": false,
    "vad_active": true,
    "wakeword_active": true,
    "stt_active": false,
    "tts_active": true,
    "playback_active": false,
    "devices": {
      "input": "Microphone Array (Intel® Smart Sound)",
      "output": "Speaker (Realtek(R) Audio)"
    },
    "components": {
      "vad": "energy_vad",
      "wakeword": "fallback_acoustic_detector (acoustic_fallback)",
      "stt": "whisper",
      "tts": "edge_tts"
    }
  }
}
```

---

## Validation & Test Results

- Total Test Count: **141 passing tests** (100% Green, 0 Failures, 0 Regressions)
- Cumulative breakdown:
  - **Phase 0 Foundation**: 23 tests
  - **Phase 1 Memory & Vault**: 26 tests
  - **Phase 2 Command Engine**: 30 tests
  - **Phase 3 AI Providers**: 24 tests
  - **Phase 4 Voice Engine**: 38 new unit & integration tests
- Regression baseline: 141/141 passing across Windows 11 on Python 3.14.7.
