# Denver AI Assistant — Dependency & Platform Compatibility Specification

**Product Name:** Denver AI Assistant  
**Namespace:** `denver`  
**Target Platform:** Windows 11 / Windows 10 (x64)  
**Interpreter:** Python 3.14.7 (CPython 64-bit)  
**Release Status:** Release Candidate (Phase 6.5)  

---

## 1. Core Runtime Dependencies

| Package | Minimum Version | Purpose | Python 3.14 Status |
|---|---|---|---|
| `PySide6` | `>=6.6.0` (6.11.2) | Native Desktop GUI (Qt 6), Signals/Slots, QPainter HUD canvas | Compatible (Stable ABI `cp310-abi3-win_amd64`) |
| `psutil` | `>=5.9.0` (6.1.1) | Real-time CPU, RAM, Battery, and hardware telemetry | Fully Compatible (Native C extension) |
| `python-dotenv` | `>=1.0.0` | Environment configuration loading (`.env`) | Fully Compatible (Pure Python) |
| `pycaw` | `>=20240210` | Windows Core Audio API volume control | Fully Compatible (Windows COM API) |
| `mss` | `>=9.0.0` | High-speed multi-monitor screen capture sandbox | Fully Compatible (ctypes / Win32 GDI) |
| `Pillow` | `>=10.0.0` | Image processing and screenshot verification | Fully Compatible |
| `pyinstaller` | `>=6.0.0` (6.22.3) | Standalone Windows executable compilation (`Denver.exe`) | Fully Compatible |

---

## 2. Windows Native & Standard Library Subsystems

Denver leverages Windows-native APIs directly via Python standard libraries:

- **Windows DPAPI (Data Protection API)**: `ctypes.windll.crypt32.CryptProtectData` for zero-plaintext credential encryption (`DenverVault`).
- **SQLite Database**: `sqlite3` 3.50.4 with Write-Ahead Logging (`WAL`), foreign keys, and 5000ms busy timeout.
- **Windows Shell & Automation**: `ctypes.windll.user32` for window management, minimizing, maximizing, focusing, and virtual key execution.
- **Async Runtime**: `asyncio` for asynchronous EventBus event dispatching and non-blocking command execution.

---

## 3. Audio & Voice Subsystem (Phase 4 Specification)

| Component | Active Implementation | Fallback / Compatibility Notes |
|---|---|---|
| **Audio Capture** | `sounddevice` / PortAudio | Captures 16kHz mono audio from default Windows microphone. |
| **VAD (Voice Activity Detection)** | `EnergyVAD` | Energy-based acoustic framing (zero C++ compilation requirements). |
| **Wake Word Engine** | `FallbackAcousticDetector` | Real-time acoustic energy and phonetic pattern matching. |
| **Speech-to-Text (STT)** | `whisper` / offline pipeline | High-accuracy transcription. |
| **Text-to-Speech (TTS)** | `edge_tts` / SAPI5 Windows Native | High-fidelity neural voice synthesis (`en-GB-RyanNeural`). |

> [!NOTE]
> As documented in Phase 4, native `openWakeWord` / `faster-whisper` C++ wheels remain optional pending upstream Python 3.14 wheel releases. The existing fallback acoustic engine ensures 100% operational uptime without downgrading Python.

---

## 4. Packaging Strategy

- **Build Tool:** PyInstaller 6.22.3
- **Packaging Mode:** **One-Folder Mode** (`dist/Denver/`)
  - Ensures instant sub-second startup without extracting dozens of megabytes of Qt 6 binaries to `%TEMP%` on every launch.
  - Guarantees Qt plugin discovery (`qwindows.dll`, `styles/`, `imageformats/`).
  - Preserves user data and database isolation in `%LOCALAPPDATA%/Denver` or current workspace.
