# 🛰️ Denver AI Assistant — Project Checkpoint & State Manifest

> **Last Updated:** September 19, 2026 (07:54 IST)  
> **Environment:** Windows 11 Pro, Python 3.14.7  
> **Repository:** `C:\Users\diwak\Desktop\AI`  
> **Test Suite Status:** ✅ **459 / 459 PASSING (100%)**

---

## 🚀 Enhancements Completed

### 0.1 🛠️ Self-Healing Diagnostics & 1-Click Auto-Repair (`src/denver/health/repair.py`)
- **System Diagnosis Engine**:
  - Automatically verifies and creates missing application directories (`data/screenshots`, `data/screenshots/web`, `data/meetings`, `data/cache`, `logs`).
  - Analyzes SQLite database integrity (`PRAGMA integrity_check`), WAL mode status, runs `VACUUM` and `ANALYZE` optimization.
  - Automatically detects and rotates oversized logs (>5MB) without interrupting background threads.
  - Cleans stale temporary cache files older than 48 hours.
- **Execution & Integration**:
  - `python main.py --repair`: Runs immediate diagnostics and outputs structured fix summary.
  - Voice Commands: *"Denver, repair system issues"*, *"Denver, run auto repair"*, *"Denver, fix system health"*, *"Denver, diagnose and repair"*.

### 0.2 🚫 Non-Blocking Priority TTS Audio Queue (`src/denver/audio/tts_queue.py`)
- **Multi-Level Priority Queuing**:
  - `HIGH`: Direct voice command responses (automatically clears lower priority backlogs).
  - `NORMAL`: Routine scheduled briefings and reminders.
  - `LOW`: Background system telemetry alerts.
- **Barge-In Interruption**:
  - Automatically interrupts ongoing playback and purges stale speech queues when user speaks or triggers barge-in.

### 0.3 🗣️ Dynamic Voice Brevity & Response Style Modes (`src/denver/config/settings.py`)
- **Brevity Modes**:
  - `concise` (default): 1-line crisp verbal answers tailored for fast desktop operation.
  - `detailed`: Comprehensive spoken explanations.
- **Voice Commands**:
  - *"Denver, be concise"* / *"Denver, concise mode"* / *"Denver, switch to concise mode"*.
  - *"Denver, be detailed"* / *"Denver, detailed mode"* / *"Denver, switch to detailed mode"*.
- **Config & Env**:
  - `DENVER_VOICE_BREVITY=concise`

### 0.4 📦 Sanitized Safe Diagnostic Bundle Exporter (`src/denver/health/health_service.py`)
- **Zero-Secret Export**:
  - `python main.py --export-diagnostics [output_path.json]`
  - Exports a comprehensive system health report, CPU/RAM telemetry, active providers, and audio status with 100% of API keys, tokens, and credentials masked as `***` or audited as `configured`/`missing`.

### 0.5 🧩 Modular Plugin Sandboxing, State Management & Voice Routing (`src/denver/plugins/`)
- **Permission Risk Model & Gating**:
  - Granular permissions with risk levels (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
  - `PluginContext.require_permission(permission)` raises `PermissionDeniedError` on unauthorized access.
  - Permission-gated facade methods for `notify`, `emit_event`, `read_data_file`, `write_data_file`, `request_memory_read`, `request_memory_write`, `request_network`, `request_audio_play`.
  - Path traversal protections on plugin file I/O.
- **Plugin State Persistence & Management**:
  - Enables and disables plugins dynamically with state saved to `data/plugin_state.json`.
  - Dispatches `on_enable` and `on_disable` lifecycle hooks cleanly.
- **Voice & CLI Command Routing**:
  - *"Denver, list plugins"* / *"what plugins are installed?"*
  - *"Denver, enable plugin [id]"*
  - *"Denver, disable plugin [id]"*
  - *"Denver, reload plugins"*
  - Registered command pattern matching (regex and phrase matching via `context.register_command_pattern`) + `on_command` fallback.
  - Fault isolation ensuring unhandled errors or bugs in third-party plugins never crash Denver.

### 0.6 ⚡ Atomic File Persistence Helper (`src/denver/utils/atomic_write.py`)
- **Zero-Corruption State Protection**:
  - `atomic_write_json(path, data)` & `atomic_write_text(path, text)`: Writes to a temporary file on the same disk drive, flushes buffers, executes `os.fsync()`, and invokes `os.replace()` to atomically swap the target file.
  - Protects `data/plugin_state.json`, `data/contacts.json`, `data/apps.json`, and `data/memory_export.json` against partial writes, crashes, or abrupt power losses.

### 0.7 📦 Release Artifact & Portable Package Verifier (`src/denver/release/verifier.py`)
- **Automated Pre-Distribution Audits**:
  - `python main.py --verify-release [dir_or_zip]`: Recursively scans release folders or ZIP archives before distribution.
  - Detects and rejects real API keys (`gsk_`, `sk-`, `AIzaSy`, `Bearer`), private SQLite databases, live `.env` files, debug logs, audio recordings, and malicious ZIP path traversal (`../`).
  - Allows safe placeholders (`your_groq_api_key_here`, `***`) in `.env.example` without false positives.

### 0.8 ⚡ Fast TTS Phrase Caching (`src/denver/audio/tts_cache.py`)
- **Zero-Latency In-Memory & Disk Cache**:
  - SHA-256 hashed audio cache keyed by `text + voice + rate + pitch + format`.
  - Instant sub-millisecond playback for repeated phrases (*"Standing by"*, *"Command completed"*, *"All systems operational"*, *"I am listening"*, *"Diagnostic complete"*).
  - Decorator provider `CachedTTSProvider` wraps any backend TTS engine with automatic LRU memory and persistent disk caching.

### 0.9 ⏱️ Per-Stage Latency Telemetry (`src/denver/runtime/telemetry.py`)
- **Stage Timers & Breakdown**:
  - Tracks execution timing across STT Transcription $\rightarrow$ Intent Routing $\rightarrow$ Action Execution $\rightarrow$ TTS Synthesis.
  - Formats real-time latency logs: `[LATENCY] STT: 142ms | Route: 4ms | Exec: 32ms | TTS: 48ms | Total: 226ms`.
  - Publishes `pipeline.latency` telemetry events to `DenverEventBus`.

### 0.10 🗃️ Memory Data Controls & Safe JSON Exporter (`src/denver/memory/memory_service.py`)
- **Safe Export & Pruning**:
  - `python main.py --export-memory [output_path.json]`: Exports full snapshot of notes, preferences, habits, saved locations, and tasks with all sensitive keys/passwords automatically redacted.
  - Voice Commands:
    - *"Denver, export my memory data"* / *"export memories"*
    - *"Denver, clear all my notes"* / *"clear all memories"* (with confirmation gating)
    - *"Denver, list my saved memories"* / *"show memories"*

### 0.11 🎙️ Global Push-to-Talk (PTT) Hotkey (`src/denver/audio/push_to_talk.py`)
- **Native Windows Hotkey Registration**:
  - Implemented `PushToTalkListener` using native `user32.RegisterHotKey` in a dedicated background daemon thread.
  - Zero third-party dependencies, works system-wide across full-screen games, IDEs, and browser windows.
  - Hotkey string parser supporting `ctrl+space`, `alt+d`, `ctrl+shift+f1`, `win+space`, etc.
  - Non-Windows / test simulated trigger fallback for testing pipelines.
- **Voice Pipeline Integration**:
  - Integrated into `VoicePipeline` lifecycle (`start()` and `stop()`).
  - Thread-safe callback invokes `VoicePipeline.trigger_listening()`, switching Denver into active voice command state immediately without requiring the user to speak the wake word.
- **Settings & Environment Configuration**:
  - `DENVER_PUSH_TO_TALK_ENABLED=true`
  - `DENVER_PUSH_TO_TALK_HOTKEY="ctrl+space"` (default)

### 0. 📍 Live Current Location Detection & Dual-Layer Cache (`src/denver/automation/location.py`)
- **Ordered Provider Fallback Chain**:
  - **Primary**: `ipapi.co` (`https://ipapi.co/json/`) via secure HTTPS.
  - **Secondary**: `ip-api.com` (`http://ip-api.com/json/`) via plaintext HTTP fallback with 45 req/min rate limit protection.
  - Distinct HTTP 429 rate limit skipping to immediately try the next provider in the chain without stalling retries.
- **Dual-Layer Caching Architecture (In-Memory + SQLite Migration v6)**:
  - Single-row `location_cache` SQLite table (`id = 1` constraint) persists the detected location across single-shot CLI invocations (`main.py -c`).
  - In-memory `dict` cache serves sub-millisecond hot-path lookups within long-running processes (headless voice loop, Cockpit UI).
  - Explicit TTL evaluation (`DENVER_LOCATION_CACHE_TTL_SECONDS=1800`): fresh locations returned instantly; stale cache returned only as a named fallback with explicit disclosure (*"using your last known location from earlier today"*).
- **Confirmation-Gated Saved Locations**:
  - Voice/CLI command *"save my current location as home"* detects live coordinates, speaks back the formatted address, and creates a pending confirmation token.
  - Persists to `saved_locations` only upon explicit affirmative user confirmation (*"confirm"*, *"yes"*).
- **Context-Aware Auto-Resolution**:
  - Automatically resolves `"here"`, `"current location"`, or empty city queries in Weather (*"what is the weather here"*) and Navigation (*"how do I get to Central Station from here"*) seamlessly.
- **Natural Language Location Commands**:
  - *"Denver, where am I?"* / *"what is my current location?"*
  - *"Denver, save my current location as home / office"*
  - *"Denver, what is the weather here?"*
  - *"Denver, how do I get to [destination] from here?"*

### 1. 🌦️ Live Weather Subsystem (`src/denver/automation/weather.py`)
- **Zero-API-Key Open-Meteo Integration**:
  - Live weather retrieval using Open-Meteo REST API (current weather, hourly forecasts, temperatures, humidity, precipitation probability, wind speed).
  - Built-in WMO weather code mapping to human-friendly spoken descriptions (0="Clear sky", 61="Slight rain", 95="Thunderstorm", etc.).
  - Geocoding disambiguation with population ranking (`result.get("population") or 0` fallback) and multi-match disambiguation.
  - Fail-safe fallback to `WebAgent.search()` if Open-Meteo API is unreachable.
- **Natural Language Weather Commands**:
  - *"Denver, what is the weather in London?"*
  - *"Denver, will it rain today?"* / *"what is the forecast for Tokyo?"*
  - *"Denver, how cold is it outside?"*

### 2. 🗺️ Fastest-Route Navigation Subsystem (`src/denver/automation/navigation.py`)
- **Multi-Modal Routing Engine**:
  - OSRM (Open Source Routing Machine) routing with automatic step durations, distance calculations, and human-friendly formatting ("25 mins", "1 hr 15 mins", "14.2 km").
  - Google Maps Directions API fallback with configurable secret key in Denver Vault.
  - Automatic Google Maps browser visualizer launch (`https://www.google.com/maps/dir/...`) for hands-free interactive turn-by-turn routing.
  - Multi-travel mode support (`driving`, `walking`, `bicycling`, `transit`).
  - Contextual transit advice (explaining why real-time schedule apps are launched for public transit).
- **Natural Language Navigation Commands**:
  - *"Denver, how do I get to Central Park?"*
  - *"Denver, navigate from home to office"*
  - *"Denver, find the fastest route to Heathrow Airport"*
  - *"Denver, switch to walking directions"*

### 3. 📍 Persistent Saved Locations Memory (`src/denver/memory/`)
- **Schema Migration v5 (`saved_locations`)**:
  - Added dedicated `saved_locations` table tracking label, raw address, latitude, longitude, and timestamps.
  - Fast label resolution ("home", "work", "office", "gym", "parents house") for origin/destination auto-fill in weather & directions queries.
  - Geocoding at save-time for instant sub-millisecond route calculation.
- **Natural Language Location Commands**:
  - *"Denver, remember this address as home: 10 Downing Street, London"*
  - *"Denver, what is my saved work address?"*
  - *"Denver, forget my saved office location"*

### 1. 🌐 Playwright / CDP Deep Web Agent (`src/denver/automation/web_agent.py`)
- **Autonomous Web Research & Scraping**:
  - Implemented [`WebAgent`](file:///c:/Users/diwak/Desktop/AI/src/denver/automation/web_agent.py) with structured multi-engine web search (DuckDuckGo, Google) extracting titles, URLs, and summaries.
  - HTML content extractor with automatic script/style/nav tag stripping and Markdown-ready content truncation.
  - Automated website visual rendering and PNG screenshot snapshots saved to `data/screenshots/web/`.
  - Fail-safe fallback mode for non-browser and CI environments.
- **Natural Language Web Commands**:
  - *"Denver, search the web for [query]"*
  - *"Denver, read webpage [url]"* / *"summarize webpage [url]"*
  - *"Denver, take screenshot of website [url]"*

### 2. 🧠 Proactive Intelligence & Autonomous Observer (`src/denver/proactive/`)
- **Telemetry & Context Observer**:
  - Implemented [`ProactiveIntelligenceEngine`](file:///c:/Users/diwak/Desktop/AI/src/denver/proactive/engine.py) to periodically inspect system health, active foreground applications, continuous focus duration, and pending task queues.
- **Context-Aware Rule Evaluators**:
  - `BatteryHealthRule`: High/Critical alerts for low battery levels (<25% and <15%) when running on battery.
  - `FocusFatigueRule`: Ergonomics and hydration recommendations after prolonged continuous focus (>60 mins).
  - `RoutineOpportunityRule`: Proactively recommends launching `Coding Mode` macro when opening IDEs or `Wrap Up Work` at end of work days.
  - `PendingTaskReminderRule`: Proactively brings up urgent scheduled and pending action items.
  - `SystemResourceRule`: Alerts on memory saturation (>90% RAM utilization).
- **Anti-Annoyance Cooldowns & Controls**:
  - Category-based cooldown throttles prevent repetitive alert spam.
  - Full voice/text commands: *"Denver, any suggestions?"*, *"enable proactive mode"*, *"disable proactive mode"*, *"dismiss suggestions"*.

### 3. 🎧 WASAPI System Audio & Live Meeting Intelligence (`src/denver/audio/meeting.py`, `src/denver/audio/loopback.py`)
- **WASAPI Output Loopback Capture**:
  - Implemented [`WasapiLoopbackCapture`](file:///c:/Users/diwak/Desktop/AI/src/denver/audio/loopback.py) using Windows WASAPI loopback streams for high-fidelity capture of remote meeting participants (Zoom, Google Meet, Microsoft Teams, YouTube) with bounded ring buffering.
  - Fail-safe simulated software buffer mode for testing and non-interactive environments.
- **Meeting Intelligence Engine**:
  - Implemented [`MeetingIntelligenceEngine`](file:///c:/Users/diwak/Desktop/AI/src/denver/audio/meeting.py) with real-time sliding window audio transcription.
  - Automatic mention detection (triggers immediate alert hooks when user's name is called).
  - Pattern-based and heuristic action item extraction (*"need to"*, *"action item:"*, *"assigned to"*, *"will follow up on"*).
  - Key discussion point tracking and automated markdown meeting notes generation with full timeline timeline transcripts saved to `data/meetings/`.
- **Command Engine & Intent Integration**:
  - *"Denver, start meeting notes [title]"*
  - *"Denver, stop meeting notes"*
  - *"Denver, show meeting summary"*

### 4. 👁️ Screen Awareness & Multimodal Vision Engine (`src/denver/automation/vision.py`)
- **Real-Time Desktop Capture & Image Optimization**:
  - Implemented [`VisionEngine`](file:///c:/Users/diwak/Desktop/AI/src/denver/automation/vision.py) for desktop capture with automatic aspect-ratio-preserving downscaling and JPEG/PNG base64 encoding.
  - Fail-safe fallback canvas to ensure stability in non-desktop/CI environments.
- **Multimodal AI Provider Upgrades**:
  - **Gemini Vision**: Seamless `inline_data` attachment for Gemini 2.0 / 1.5 Flash Vision.
  - **Groq Vision**: Automatic translation to `image_url` data URIs targeting `llama-3.2-11b-vision-preview`.
  - **Ollama Vision**: Base64 payload mapping for local `llava` and `llama3.2-vision`.
- **Natural Language Vision Commands**:
  - *"Denver, look at my screen and tell me what is wrong"*
  - *"Denver, what is on my screen?"*
  - *"Denver, analyze my screen"*
  - *"Denver, fix this error on my screen"*
  - *"Denver, summarize what you see on my screen"*

### 2. ⚡ Compound Routines & Workflows Engine (`data/routines.json`)
- **Pre-configured Macro Routines**:
  - `rtn_coding_mode` (*"Coding Mode"*): Launches VS Code, opens GitHub dashboard, sets volume to 30%, logs session in memory.
  - `rtn_meeting_mode` (*"Meeting Mode"*): Opens Google Meet, balances volume to 45%, checks battery telemetry.
  - `rtn_morning_briefing` (*"Morning Briefing"*): Retrieves time, date, battery status, reads pending tasks.
  - `rtn_focus_mode` (*"Focus Mode"*): Minimizes distracting windows, sets volume to 20%, records deep work session.
  - `rtn_wrap_up_work` (*"Wrap Up Work"*): Saves daily wrap-up note, audits system resources, stores session completion memory.
- **Dynamic Seeding & Fast Tier-1 Routing**:
  - Implemented [`CompoundRoutineLoader`](file:///c:/Users/diwak/Desktop/AI/src/denver/scheduler/compound_routines.py) and auto-seeding in [`RoutineRegistry.seed_compound_routines()`](file:///c:/Users/diwak/Desktop/AI/src/denver/scheduler/routine_registry.py).
  - Configured instant deterministic routing in [`IntentRouter`](file:///c:/Users/diwak/Desktop/AI/src/denver/commands/router.py) for natural trigger phrases.
  - Seamless sequential & DAG action execution with full status summary and speech feedback.

### 3. 🧠 Contextual Memory & Conversational Recall
- **Smart Category Auto-Detection**:
  - Automatically classifies memories into `PROJECT`, `WORKFLOW`, `PREFERENCE`, or `PERSONAL` categories upon creation.
- **Preference Mirroring & Fallback Recall**:
  - Preferences are synchronized across SQLite tables and mirrored in memory items for fast search.
  - Natural recall queries (*"what was I working on"*, *"what did I do today"*, *"what do you know about <topic>"*) query both long-term memories and user preferences.
- **Dynamic AI Prompt Enrichment**:
  - [`ContextEngine`](file:///c:/Users/diwak/Desktop/AI/src/denver/context/engine.py) enriches LLM requests with structured user profiles, recent conversation history, and privacy-filtered memories.

### 4. 📇 Local Contacts & Direct WhatsApp Automation
- Contact Book Engine ([`contacts.py`](file:///c:/Users/diwak/Desktop/AI/src/denver/memory/contacts.py)) with 413 user contacts in `data/contacts.json`.
- Direct 1-on-1 WhatsApp protocol bypassing search dialogs in <350ms.

### 5. 💻 Applications & Shortcuts Dataset (`data/apps.json`)
- Windows Apps Scanner ([`apps_scanner.py`](file:///c:/Users/diwak/Desktop/AI/src/denver/automation/apps_scanner.py)) with 81 discovered applications and shortcuts.
- Win32 binary resolution for `.cmd`, `.bat`, and local AppData executables.

### 5. 🔒 Direct Workstation Locking & Sleep Mode Subsystem
- **Direct Workstation Locking**:
  - `DENVER_ALLOW_HIGH_RISK_ACTIONS=true` in [.env](file:///c:/Users/diwak/Desktop/AI/.env) for instant, friction-free execution in 4.49ms.
  - Matches phrases: *"Denver lock the laptop"*, *"lock the pc"*, *"lock computer"*, *"lock screen"*.
- **Background Sleep Mode & Wake-Up**:
  - *"Denver, go to sleep"* puts Denver into silent background monitoring mode while keeping laptop telemetry running.
  - *"Denver, wake up"* restores full active voice responsiveness.
- **Continuous Voice Interaction Flow**:
  - Two-stage wake flow: User says *"Denver"* $\rightarrow$ Denver responds *"Yes, Diwakar? I'm listening."* and immediately remains in `LISTENING` mode for the subsequent command.
  - One-breath command flow: User says *"Denver lock the laptop"* in one breath $\rightarrow$ pre-roll buffer captures full speech without syllable clipping.
### 6. 📋 Clipboard Intelligence Subsystem (`src/denver/automation/clipboard.py`)
- **Read Clipboard Content**:
  - Voice/CLI intent: *"Denver, read my clipboard"* / *"what did I copy?"*.
  - Speaks out the copied text with intelligent length bounding and character counts.
- **AI-Powered & Extractive Clipboard Summarization**:
  - Voice/CLI intent: *"Denver, summarize my clipboard"* / *"what is this clipboard about?"*.
  - Uses Groq/Gemini to distill long copied articles, code blocks, or emails into 1-2 crisp sentences with local extractive fallback.

### 7. ⌨️ Hands-Free Typing & Keyboard Automation (`src/denver/automation/keyboard.py`)
- **Direct Window Typing**:
  - Voice intent: *"Denver, type 'Meeting scheduled for 3 PM' "* $\rightarrow$ types text directly into the active focused window.
- **Key Press Automation**:
  - Voice intent: *"Denver, press enter"*, *"Denver, press space"*, *"Denver, press tab"*, *"Denver, press escape"*.
- **Mouse & Window Scrolling**:
  - Voice intent: *"Denver, scroll down"* / *"Denver, scroll up 10"*.

### 8. 🛡️ URL Sanitization & Web Guardrails (`src/denver/automation/url_safety.py`)
- Restricts web browsing and links to strictly permitted `http/https` protocols.
- Strips dangerous URI schemes (`javascript:`, `file:`, `data:`, `blob:`) and forbidden script injection characters.
- Sanitized Google search query builder with URL parameter encoding.

---

### 0.12 📦 Automated Windows Portable Release Builder (`src/denver/release/builder.py`, `scripts/build_windows_portable.py`)
- **Zero-Secret Distribution Packager**:
  - `python main.py --build-portable [--dry-run] [output_dir]`: Assembles clean distribution packages in `dist/`.
  - Automatically isolates runtime caches (`__pycache__`, `.pytest_cache`, `.vscode`, `logs/`, `meetings/`), live databases (`.sqlite3`), and `.env` secrets.
  - Automatically pipes generated ZIP archives into `ReleaseArtifactVerifier` for 1-click pre-release security validation.
  - Standalone script: `scripts/build_windows_portable.py`.

### 0.13 🖥️ Cyber Cockpit Plugin Center & Auto-Repair Controls (`src/denver/ui/widgets/plugins_widget.py`, `telemetry_panel.py`)
- **Plugin Management Tab**:
  - Dedicated **🧩 PLUGINS** tab in Cockpit UI displaying discovered plugins, risk level badges, permissions, and 1-click toggle switches.
  - 1-click "Reload Plugins" button dispatching dynamic discovery.
- **1-Click System Auto-Repair UI Integration**:
  - Interactive `🛠 AUTO REPAIR` trigger in `TelemetryPanelWidget` with live SQLite database integrity badge (`● SQLite: HEALTHY (WAL)`).
  - Background asynchronous execution dispatching `SystemRepairManager.run_repair()` without freezing the 60+ FPS UI.

### 0.14 👁️ Multimodal Screen Vision & Targeted Error Analysis (`src/denver/automation/vision.py`)
- **Focus-Mode Intelligence**:
  - `error_diagnosis` mode: specifically extracts stack traces, terminal compiler outputs, and exact code fixes.
  - `ocr_reading` mode: high-fidelity visual transcription of text and UI labels.
  - `summary` mode: 1-2 sentence executive overview of active workflow.
- **Natural Language Vision Commands**:
  - *"Denver, look at my screen and tell me what is wrong"*
  - *"Denver, fix this error on my screen"*
  - *"Denver, read text on my screen"*
  - *"Denver, summarize what's on my screen"*

### 0.15 🛡️ Package Structure Refactor & Repository Cleanliness Automation (`scripts/repo_hygiene.py`, `repo_hygiene.py`, `release_build.py`)
- **Repository Hygiene & Secret Scanner**:
  - `python repo_hygiene.py [--clean]`: Recursive scanner detecting unmasked API keys, cache artifacts (`__pycache__`, `.pytest_cache`), compiled bytecode (`.pyc`), and forbidden files.
  - `--clean` auto-purges temporary bytecode and caches before commits or packaging.
  - Root convenience shortcuts: `repo_hygiene.py` and `release_build.py` (with `sys.dont_write_bytecode = True`).
- **Open-Source Governance & Security Assets**:
  - [`.gitignore`](file:///c:/Users/diwak/Desktop/AI/.gitignore): Comprehensive zero-leak ignore rules for `.env`, `.sqlite3`, logs, and caches.
  - [`LICENSE`](file:///c:/Users/diwak/Desktop/AI/LICENSE): Standard MIT Open Source License.
  - [`SECURITY.md`](file:///c:/Users/diwak/Desktop/AI/SECURITY.md): Security policy, vulnerability reporting protocol, and zero-secret architecture specification.
  - [`CONTRIBUTING.md`](file:///c:/Users/diwak/Desktop/AI/CONTRIBUTING.md): Code standards, determinism rules, and test verification workflow.
  - [`CODE_OF_CONDUCT.md`](file:///c:/Users/diwak/Desktop/AI/CODE_OF_CONDUCT.md): Contributor Covenant pledge and enforcement guidelines.

### 0.16 💬 Advanced WhatsApp Voice Dispatch & ContactBook Integration (`src/denver/automation/whatsapp.py`)
- **Deterministic Contact Matching**:
  - Direct integration with `ContactBook` (413 curated contacts in `data/contacts.json`).
  - Fuzzy and relationship matching ("Mom", "Dad", "Alex", "Home") with phone normalization (E.164 standard).
  - Ambiguity resolution handling: prompts for clarification if multiple candidate contacts share similar names.
- **Protocol & Browser Automation**:
  - Native URI protocol dispatch (`whatsapp://send?phone=...&text=...`) with seamless fallback to WhatsApp Web (`https://web.whatsapp.com/send?phone=...&text=...`).
  - E.164 phone number sanitation and URL encoding.
- **Voice Intents**:
  - *"Denver, send WhatsApp to Alex saying I will join the meeting in 5 minutes"*
  - *"Denver, message Mom on WhatsApp saying I arrived safely"*

### 0.17 🎵 Spotify Voice Controller Subsystem (`src/denver/automation/spotify.py`)
- **Native Windows Media Key Triggers**:
  - Zero-latency media control via `user32.dll` virtual key codes (`VK_MEDIA_PLAY_PAUSE`, `VK_MEDIA_NEXT_TRACK`, `VK_MEDIA_PREV_TRACK`, `VK_MEDIA_STOP`).
  - Spotify desktop URI protocol search (`spotify:search:<query>`) and web player fallback (`https://open.spotify.com/search/<query>`).
- **Telemetry & Event Bus**:
  - Dispatches strongly typed `SpotifyPlaybackChanged` event with action type, query metadata, and timestamp.
- **Voice Intents**:
  - *"Denver, play music"* / *"Denver, play Spotify"* / *"Denver, pause music"* / *"Denver, resume"*
  - *"Denver, next song"* / *"Denver, skip track"* / *"Denver, previous track"*
  - *"Denver, play Starboy on Spotify"* / *"Denver, search Spotify for Interstellar"*

### 0.18 🛡️ Local-First Air-Gapped Mode & Dynamic AI Provider Toggles (`src/denver/providers/router.py`)
- **Strict Air-Gapped Privacy Enclosure**:
  - Dynamic runtime toggle `set_air_gap_mode(enabled: bool)`.
  - When enabled, strictly filters out and blocks all cloud AI providers (`groq`, `gemini`), enforcing 100% local processing (`ollama`, `lmstudio`) with zero network egress.
  - Prevents credential and memory leakage with built-in cloud context sanitizers.
- **Dynamic Active Provider Switching**:
  - `set_active_provider(provider_name: str)`: Dynamically reprioritizes the AI router fallback queue.
  - Telemetry event emission via `AirGappedModeChanged` and `ProviderModeChanged`.
- **Voice Intents**:
  - *"Denver, switch to local only mode"* / *"Denver, air-gapped mode"* / *"Denver, go offline"* / *"Denver, disconnect cloud"*
  - *"Denver, switch to cloud mode"* / *"Denver, go online"* / *"Denver, disable air-gapped mode"*
  - *"Denver, switch provider to Groq"* / *"Denver, switch to Gemini"* / *"Denver, use Ollama"* / *"Denver, set provider to LM Studio"*

---

## 🔮 Roadmap & Next Objectives

- [x] **Priority 1**: Advanced WhatsApp Automation & Voice Dispatch (Complete — 413 contacts integrated & tested).
- [x] **Priority 2**: Spotify Voice Controller Subsystem (Complete — Native media keys + Spotify search + 17 unit tests).
- [x] **Priority 3**: Local-First Air-Gapped Mode & AI Provider Toggles (Complete — Strict cloud enclosure + 9 unit tests).
- [ ] **Next Objective 1**: Continuous Ambient Audio & Multi-turn Conversation Mode.
- [ ] **Next Objective 2**: Deep Desktop Workflow Orchestration (Multi-App chaining with confirmation gates).

---

## 📌 How to Run Denver

| Mode | Command | Description |
|---|---|---|
| **Voice Assistant (Headless)** | `python main.py --headless` | Full hands-free voice loop (Wake word + Chime + STT + LLM + TTS + Routines + WhatsApp + Spotify). |
| **Cyber Cockpit GUI** | `python -m denver --gui` | PySide6 dark cockpit with animated HUD visualizer, DAG workflows, and live telemetry. |
| **Repo Hygiene Audit** | `python repo_hygiene.py --clean` | Pre-commit/pre-release cache cleanup & secret scan. |
| **Build Portable Package** | `python release_build.py --dry-run` | Stage & audit Windows portable distribution package. |
| **Lock Laptop** | `python main.py -c "lock the laptop"` | Instantly lock Windows session via CLI or voice. |
| **Spotify Control** | `python main.py -c "play Starboy on spotify"` | Search & play tracks on Spotify via CLI or voice. |
| **Air-Gapped Mode** | `python main.py -c "switch to local only mode"` | Lock AI inference strictly to offline local models. |
| **Sleep Mode** | `python main.py -c "go to sleep"` | Put Denver into background silent observation mode. |
| **Wake Up** | `python main.py -c "wake up"` | Restore active voice assistance from sleep mode. |
| **Run Compound Routine** | `python main.py -c "start coding mode"` | Execute multi-step compound routine via CLI. |
| **Recall Memory** | `python main.py -c "what do you know about <topic>"` | Query contextual memory and preferences. |
| **Single CLI Command** | `python main.py -c "<command>"` | Run a one-off text command (e.g. `python main.py -c "open vs code"`). |
| **System Auto-Repair** | `python main.py --repair` | Run self-healing diagnostics and automated repair. |
| **Re-scan Applications** | `python main.py --scan-apps` | Re-index all installed programs, folders, and shortcuts. |
| **Import Contacts** | `python main.py --import-contacts "contacts.csv"` | Bulk import contacts into `data/contacts.json`. |

---

## 📂 Key Files & Dataset Locations

- `data/routines.json` (Curated compound routines dataset)
- `data/contacts.json` (413 user contacts)
- `data/apps.json` (81 discovered applications and shortcuts)
- `src/denver/automation/spotify.py` (Spotify Voice Controller & Windows virtual media keys)
- `src/denver/automation/whatsapp.py` (WhatsApp voice messaging & ContactBook integration)
- `src/denver/providers/router.py` (AI Provider Router with Air-Gapped enclosure & dynamic toggles)
- `src/denver/scheduler/compound_routines.py` (Compound routine loader & matcher)
- `src/denver/scheduler/routine_registry.py` (Routine lifecycle & seeding)
- `src/denver/context/engine.py` (Context engine & prompt builder)
- `src/denver/commands/router.py` (Deterministic intent routing)
- `src/denver/commands/service.py` (Command orchestration & multi-step execution)
- `src/denver/audio/pipeline.py` (Real-time voice processing & state transitions)
- `src/denver/audio/stt.py` (Dual Groq Cloud Whisper & Faster-Whisper STT engines)
- `src/denver/release/builder.py` (Windows Portable release builder)
- `src/denver/release/verifier.py` (Release security artifact verifier)
- `src/denver/ui/widgets/plugins_widget.py` (Cockpit modular plugin manager)
- `src/denver/health/repair.py` (Self-healing auto-repair engine)
- `tests/unit/` & `tests/integration/` (459 automated unit & integration tests)


