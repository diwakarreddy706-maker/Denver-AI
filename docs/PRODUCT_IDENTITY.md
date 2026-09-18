# Denver AI Assistant — Product Identity & Brand Specification

> **Official Product Specification**: This document establishes the brand, nomenclature, terminology, and product identity for **Denver AI Assistant** (`Denver`), distinguishing it from any external reference architectures.

---

## 1. Core Identity & Nomenclature

| Attribute | Official Specification |
|---|---|
| **Product Full Name** | **Denver AI Assistant** |
| **Assistant Name** | **Denver** |
| **Short / Brand Name** | **Denver** |
| **Package Namespace** | `denver` (`src/denver/`) |
| **Configuration Prefix** | `DENVER_` (e.g. `DENVER_WAKE_WORD`, `DENVER_AI_MODE`) |
| **Default Storage File** | `denver_memory.sqlite3` |
| **Default Executable** | `Denver.exe` |

---

## 2. Voice & Conversational Persona

### Self-Identification
When queried about its identity or role:
- **User**: *"Who are you?"*
- **Denver**: *"I'm Denver, your personal AI assistant."*
- **User**: *"Introduce yourself."*
- **Denver**: *"Denver at your service, sir. All core systems are operational."*

### Voice Profile & Tone
- **Demeanor**: Calm, articulate, highly capable, professional, with subtle dry wit.
- **Formality**: British-style formal address (*"sir"* / *"ma'am"* configurable), concise and action-oriented.
- **Voice Synthesis Engine**:
  - *Online Primary*: Edge Neural TTS (`en-GB-RyanNeural`, Rate `-8%`, Pitch `-12Hz`).
  - *Offline Fallback*: Piper Neural TTS (`en_GB-alan-medium` or `en_US-lessac-medium`).

---

## 3. Wake Word Specification

- **Official Wake Word**: `Denver`
- **Secondary / Follow-up Phrases**: `Hey Denver`, `Denver assistant`
- **Implementation Status**:
  - **Current Phase**: Architectural specification and configuration baseline.
  - **Planned Implementation**: Streaming acoustic neural model via `openWakeWord` (ONNX) in Phase 1 (Voice Pipeline).
  - *Note*: Wake-word detection is documented as a planned feature for the audio phase and is not falsely claimed as currently operational.

---

## 4. Brand Terminology

| Component | Official Name | Description |
|---|---|---|
| **Core Runtime** | **Denver Core** | The asynchronous event loop, state machine, and orchestrator. |
| **Desktop GUI** | **Denver Cockpit** | The dark-mode cyber HUD desktop interface and telemetry dashboard. |
| **Quick Launcher** | **Denver Spotlight** | The floating global shortcut overlay (`Ctrl+Shift+J`). |
| **Storage Engine** | **Denver Memory Engine** | SQLite WAL relational database + vector semantic index. |
| **Security Layer** | **Denver Vault** | Windows DPAPI encrypted credential manager and safe execution sandbox. |
| **Extension System** | **Denver Hub / Plugin Engine**| Sandboxed community plugin subsystem with Ed25519 signatures. |

---

## 5. Central Product Identity Configuration

Denver uses a centralized configuration schema rather than hardcoded strings across the codebase:

```ini
# Central Denver Product Identity
ASSISTANT_NAME=Denver
PRODUCT_NAME=Denver AI Assistant
WAKE_WORD=Denver
WAKE_WORD_ENABLED=true
WAKE_WORD_COOLDOWN_SECONDS=1.0
LANGUAGE=en-US

# Runtime Defaults
DENVER_AI_MODE=auto
DENVER_VOICE_ENABLED=true
DENVER_TTS_PROVIDER=edge
DENVER_PRIVACY_MODE=false
DENVER_ALLOW_DESTRUCTIVE_ACTIONS=false
```

---

## 6. Package & Module Structure

The Python project namespace is strictly `denver`:

```
src/
└── denver/
    ├── __init__.py
    ├── app/                     # CLI entrypoint & bootstrap
    │   ├── __init__.py
    │   └── main.py
    ├── audio/                   # Audio I/O, VAD, STT, TTS, Wake detection
    │   ├── __init__.py
    │   ├── capture.py
    │   ├── vad.py
    │   ├── stt.py
    │   ├── tts.py
    │   └── wake.py
    ├── automation/              # Windows UIA, App launcher, Web & Power
    │   ├── __init__.py
    │   ├── apps.py
    │   ├── browser.py
    │   ├── desktop.py
    │   └── uia.py
    ├── commands/                # Normalization, intent routing, action dispatcher
    │   ├── __init__.py
    │   ├── dispatcher.py
    │   ├── router.py
    │   └── schema.py
    ├── config/                  # Configuration manager, schema, vault
    │   ├── __init__.py
    │   ├── manager.py
    │   └── schema.py
    ├── health/                  # Diagnostics, observability, self-repair
    │   ├── __init__.py
    │   ├── diagnostics.py
    │   └── observability.py
    ├── memory/                  # SQLite storage, vector embeddings, context
    │   ├── __init__.py
    │   ├── db.py
    │   ├── vector.py
    │   └── context.py
    ├── plugins/                 # Manifest validation, sandbox, signatures
    │   ├── __init__.py
    │   ├── loader.py
    │   ├── sandbox.py
    │   └── registry.py
    ├── providers/               # LLM adapters (Ollama, Groq, Gemini)
    │   ├── __init__.py
    │   ├── base.py
    │   ├── local_llm.py
    │   └── cloud_llm.py
    ├── security/                # DPAPI vault, path safety, process safety
    │   ├── __init__.py
    │   ├── vault.py
    │   ├── command_safety.py
    │   └── path_safety.py
    └── ui/                      # Desktop cockpit, HUD visualizers, quickbar
        ├── __init__.py
        ├── app.py
        ├── reactor.py
        ├── visualizers.py
        └── pages/
```

---

## 7. UI & Visual Identity

- **Main Window Title**: `DENVER Cyber Interface`
- **Center Stage Title**: `D E N V E R`
- **Default Subtitle**: `"I am Denver, your personal AI assistant. How may I help you, sir?"`
- **Standby Label**: `STANDBY - SAY DENVER`
- **Terminal Banner**: `[STARTUP] Denver Core systems initialized. Standby active.`
- **Visual Distinction**: Denver utilizes its own bespoke geometric HUD reactor layout, high-frequency audio visualizers, and glassmorphic telemetry cards without copying proprietary artwork or assets from reference repositories.

---

## 8. Reference Project Terminology Guidelines

To maintain historical and technical accuracy:
- **`Open.Jarvis`** is strictly referred to as the **external reference project** or **baseline architecture**.
- Legacy filenames, Turkish naming shims, and module paths specific to `Open.Jarvis` are documented as historical reference context only.
- All target code, new architectural components, new tests, and new configurations are strictly branded and namespaced under **Denver**.

---

## 9. Future Branding Guidelines

1. **Tone of Voice**: Always dignified, efficient, intelligent, and unpretentious. Avoid childish persona traits or generic robotic speech.
2. **Privacy Assurance**: Denver explicitly emphasizes user privacy: *"Your data remains local to your device, sir."*
3. **Open Standards**: Denver extensions, themes, and plugins adhere to open JSON specifications with asymmetric cryptographic trust.
