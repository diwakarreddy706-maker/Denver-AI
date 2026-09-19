"""Denver Configuration Manager and Settings Schema."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from dotenv import load_dotenv

# Load .env if present
load_dotenv()


def _parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    val_str = str(value).strip().lower()
    return val_str in {"1", "true", "yes", "on", "enabled"}


def _parse_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_tuple(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    if isinstance(value, (list, tuple)):
        return tuple(str(x).strip().lower() for x in value if str(x).strip())
    parts = str(value).split(",")
    parsed = tuple(p.strip().lower() for p in parts if p.strip())
    return parsed if parsed else default


@dataclass(frozen=True)
class DenverSettings:
    """Central configuration for Denver AI Assistant."""

    # Product Identity
    assistant_name: str = "Denver"
    product_name: str = "Denver AI Assistant"
    short_name: str = "Denver"

    # Environment & Logging
    environment: str = "development"
    log_level: str = "INFO"
    log_file_path: Path = field(default_factory=lambda: Path("logs/denver.log"))

    # Storage & Persistence
    database_path: Path = field(default_factory=lambda: Path("denver_memory.sqlite3"))
    privacy_mode: bool = False
    memory_enabled: bool = True
    semantic_memory_enabled: bool = True
    memory_top_k: int = 8
    memory_max_results: int = 20
    context_max_turns: int = 10
    context_max_chars: int = 12000
    memory_default_importance: float = 0.5
    memory_default_confidence: float = 1.0
    memory_ttl_hours: float = 0.0
    allow_private_cloud_context: bool = False
    allow_sensitive_cloud_context: bool = False
    embedding_provider: str = "lexical"  # lexical, ollama, custom
    embedding_model: str = "nomic-embed-text"


    # AI & Providers
    ai_mode: str = "auto"  # auto, free_cloud, offline, rules
    ai_enabled: bool = True
    ai_local_first: bool = True
    ai_timeout_seconds: float = 10.0
    provider_priority: tuple[str, ...] = ("ollama", "lmstudio", "groq", "gemini")

    # Local Providers
    ollama_enabled: bool = True
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    lm_studio_enabled: bool = True
    lm_studio_base_url: str = "http://localhost:1234/v1"
    lm_studio_model: str = "local-model"

    # Cloud Fallback Providers
    groq_enabled: bool = True
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"

    gemini_enabled: bool = True
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-latest"

    # Spotify Integration
    spotify_enabled: bool = False
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_redirect_uri: str = "http://localhost:8888/callback"
    cloud_fallback_enabled: bool = False
    air_gapped_mode: bool = False
    active_llm_provider: str = "groq"

    # Weather (Open-Meteo & WebAgent Fallback)
    weather_provider: str = "open-meteo"
    weather_geocode_url: str = "https://geocoding-api.open-meteo.com/v1/search"
    weather_forecast_url: str = "https://api.open-meteo.com/v1/forecast"
    weather_timeout_seconds: float = 8.0
    weather_fallback_to_web_agent: bool = True

    # Routing & Navigation (OSRM, Google Maps, Browser)
    routing_provider: str = "osrm"
    osrm_base_url: str = ""
    osrm_timeout_seconds: float = 8.0
    google_maps_enabled: bool = False
    google_maps_api_key: str = ""
    route_open_in_browser: bool = True


    # Voice & Audio
    voice_enabled: bool = True
    audio_enabled: bool = True
    audio_input_device: str | None = None
    audio_output_device: str | None = None
    vad_enabled: bool = True
    vad_threshold: float = 0.5
    vad_min_speech_ms: int = 250
    vad_min_silence_ms: int = 500
    vad_max_utterance_seconds: float = 15.0
    wake_word: str = "Denver"
    wake_word_enabled: bool = True
    wake_word_cooldown_seconds: float = 1.0
    wake_word_threshold: float = 0.5
    push_to_talk_enabled: bool = True
    push_to_talk_hotkey: str = "ctrl+space"
    stt_enabled: bool = True
    stt_provider: str = "whisper"  # whisper, groq_whisper, fake
    stt_model: str = "base"
    stt_language: str = "en"
    tts_enabled: bool = True
    tts_provider: str = "edge"  # edge, piper, windows, fake
    tts_voice: str = "en-GB-RyanNeural"
    tts_rate: str = "+0%"
    tts_volume: str = "+0%"
    tts_pitch: str = "+0Hz"
    voice_brevity: str = "concise"  # concise, detailed, normal
    language: str = "en-US"

    # Automation & Safety
    ui_enabled: bool = True
    automation_enabled: bool = True
    automation_confirmation_timeout: float = 30.0
    allow_high_risk_actions: bool = False
    default_browser: str = "default"
    screenshot_directory: Path = Path("data/screenshots")
    allow_destructive_actions: bool = False
    action_sequence_delay: float = 0.1
    app_launch_delay: float = 0.2

    # Phase 8: Proactive Intelligence & Scheduled Routines
    scheduler_enabled: bool = True
    scheduler_max_concurrency: int = 2
    scheduler_default_timeout_seconds: float = 60.0
    scheduler_min_interval_seconds: float = 300.0
    scheduler_global_pause: bool = False
    scheduler_notification_rate_limit_seconds: float = 10.0

    # Phase 9: Intelligent Task & Workflow Orchestration
    tasks_enabled: bool = True
    task_max_concurrency: int = 2
    task_default_timeout_seconds: float = 600.0
    task_step_timeout_seconds: float = 60.0
    task_max_steps: int = 20
    task_max_depth: int = 10
    task_max_retries: int = 1
    task_global_pause: bool = False

    # Phase 10: Weather & Navigation
    weather_provider: str = "open-meteo"
    weather_geocode_url: str = "https://geocoding-api.open-meteo.com/v1/search"
    weather_forecast_url: str = "https://api.open-meteo.com/v1/forecast"
    weather_timeout_seconds: float = 8.0
    weather_fallback_to_web_agent: bool = True
    routing_provider: str = "osrm"
    osrm_base_url: str = "https://router.project-osrm.org"
    osrm_timeout_seconds: float = 8.0
    google_maps_enabled: bool = False
    google_maps_api_key: str = ""
    route_open_in_browser: bool = True

    # Phase 11: Live Current Location
    location_provider_primary: str = "ipapi.co"
    location_provider_fallback: str = "ip-api.com"
    location_cache_ttl_seconds: int = 600
    location_timeout_seconds: float = 5.0

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> DenverSettings:
        """Construct settings from environment dictionary or os.environ."""
        source = os.environ if env is None else env

        # Resolve paths
        db_raw = source.get("DENVER_DATABASE_PATH", "denver_memory.sqlite3")
        log_raw = source.get("DENVER_LOG_FILE_PATH", "logs/denver.log")

        return cls(
            assistant_name=source.get("DENVER_ASSISTANT_NAME", "Denver"),
            product_name=source.get("DENVER_PRODUCT_NAME", "Denver AI Assistant"),
            short_name=source.get("DENVER_SHORT_NAME", "Denver"),
            environment=source.get("DENVER_ENVIRONMENT", "development").lower(),
            log_level=source.get("DENVER_LOG_LEVEL", "INFO").upper(),
            log_file_path=Path(log_raw),
            database_path=Path(db_raw),
            privacy_mode=_parse_bool(source.get("DENVER_PRIVACY_MODE"), False),
            memory_enabled=_parse_bool(source.get("DENVER_MEMORY_ENABLED"), True),
            semantic_memory_enabled=_parse_bool(source.get("DENVER_SEMANTIC_MEMORY_ENABLED"), True),
            memory_top_k=_parse_int(source.get("DENVER_MEMORY_TOP_K"), 8),
            memory_max_results=_parse_int(source.get("DENVER_MEMORY_MAX_RESULTS"), 20),
            context_max_turns=_parse_int(source.get("DENVER_CONTEXT_MAX_TURNS"), 10),
            context_max_chars=_parse_int(source.get("DENVER_CONTEXT_MAX_CHARS"), 12000),
            memory_default_importance=_parse_float(source.get("DENVER_MEMORY_DEFAULT_IMPORTANCE"), 0.5),
            memory_default_confidence=_parse_float(source.get("DENVER_MEMORY_DEFAULT_CONFIDENCE"), 1.0),
            memory_ttl_hours=_parse_float(source.get("DENVER_MEMORY_TTL_HOURS"), 0.0),
            allow_private_cloud_context=_parse_bool(source.get("DENVER_ALLOW_PRIVATE_CLOUD_CONTEXT"), False),
            allow_sensitive_cloud_context=_parse_bool(source.get("DENVER_ALLOW_SENSITIVE_CLOUD_CONTEXT"), False),
            embedding_provider=source.get("DENVER_EMBEDDING_PROVIDER", "lexical").lower(),
            embedding_model=source.get("DENVER_EMBEDDING_MODEL", "nomic-embed-text"),
            ai_mode=source.get("DENVER_AI_MODE", "auto").lower(),

            ai_enabled=_parse_bool(source.get("DENVER_AI_ENABLED"), True),
            ai_local_first=_parse_bool(source.get("DENVER_AI_LOCAL_FIRST"), True),
            ai_timeout_seconds=_parse_float(source.get("DENVER_AI_TIMEOUT_SECONDS"), 10.0),
            provider_priority=_parse_tuple(source.get("DENVER_PROVIDER_PRIORITY"), ("ollama", "lmstudio", "groq", "gemini")),
            ollama_enabled=_parse_bool(source.get("DENVER_OLLAMA_ENABLED"), True),
            ollama_base_url=source.get("DENVER_OLLAMA_BASE_URL", source.get("DENVER_OLLAMA_URL", "http://localhost:11434")),
            ollama_model=source.get("DENVER_OLLAMA_MODEL", "llama3.2"),
            lm_studio_enabled=_parse_bool(source.get("DENVER_LMSTUDIO_ENABLED", source.get("DENVER_LM_STUDIO_ENABLED")), True),
            lm_studio_base_url=source.get("DENVER_LMSTUDIO_BASE_URL", source.get("DENVER_LM_STUDIO_URL", "http://localhost:1234/v1")),
            lm_studio_model=source.get("DENVER_LMSTUDIO_MODEL", "local-model"),
            groq_enabled=_parse_bool(source.get("DENVER_GROQ_ENABLED"), True),
            groq_base_url=source.get("DENVER_GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
            groq_api_key=source.get("DENVER_GROQ_API_KEY", source.get("GROQ_API_KEY", "")),
            groq_model=source.get("DENVER_GROQ_MODEL", "llama-3.1-8b-instant"),
            gemini_enabled=_parse_bool(source.get("DENVER_GEMINI_ENABLED"), True),
            gemini_base_url=source.get("DENVER_GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"),
            gemini_api_key=source.get("DENVER_GEMINI_API_KEY", source.get("GEMINI_API_KEY", "")),
            gemini_model=source.get("DENVER_GEMINI_MODEL", "gemini-flash-latest"),
            spotify_enabled=_parse_bool(source.get("DENVER_SPOTIFY_ENABLED", source.get("JARVIS_ENABLE_SPOTIFY")), False),
            spotify_client_id=source.get("SPOTIFY_CLIENT_ID", source.get("DENVER_SPOTIFY_CLIENT_ID", "")),
            spotify_client_secret=source.get("SPOTIFY_CLIENT_SECRET", source.get("DENVER_SPOTIFY_CLIENT_SECRET", "")),
            spotify_redirect_uri=source.get("SPOTIFY_REDIRECT_URI", source.get("DENVER_SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback")),
            cloud_fallback_enabled=_parse_bool(source.get("DENVER_CLOUD_FALLBACK_ENABLED"), False),
            air_gapped_mode=_parse_bool(source.get("DENVER_AIR_GAPPED_MODE"), False),
            active_llm_provider=source.get("DENVER_ACTIVE_LLM_PROVIDER", "groq").strip().lower(),
            voice_enabled=_parse_bool(source.get("DENVER_VOICE_ENABLED", source.get("DENVER_AUDIO_ENABLED")), True),
            audio_enabled=_parse_bool(source.get("DENVER_AUDIO_ENABLED", source.get("DENVER_VOICE_ENABLED")), True),
            audio_input_device=source.get("DENVER_AUDIO_INPUT_DEVICE"),
            audio_output_device=source.get("DENVER_AUDIO_OUTPUT_DEVICE"),
            vad_enabled=_parse_bool(source.get("DENVER_VAD_ENABLED"), True),
            vad_threshold=_parse_float(source.get("DENVER_VAD_THRESHOLD"), 0.5),
            vad_min_speech_ms=int(source.get("DENVER_VAD_MIN_SPEECH_MS", 250)),
            vad_min_silence_ms=int(source.get("DENVER_VAD_MIN_SILENCE_MS", 500)),
            vad_max_utterance_seconds=_parse_float(source.get("DENVER_VAD_MAX_UTTERANCE_SECONDS"), 15.0),
            wake_word=source.get("DENVER_WAKE_WORD", "Denver"),
            wake_word_enabled=_parse_bool(source.get("DENVER_WAKE_WORD_ENABLED"), True),
            wake_word_cooldown_seconds=_parse_float(source.get("DENVER_WAKE_WORD_COOLDOWN_SECONDS"), 1.0),
            wake_word_threshold=_parse_float(source.get("DENVER_WAKE_WORD_THRESHOLD"), 0.5),
            push_to_talk_enabled=_parse_bool(source.get("DENVER_PUSH_TO_TALK_ENABLED"), True),
            push_to_talk_hotkey=source.get("DENVER_PUSH_TO_TALK_HOTKEY", "ctrl+space"),
            stt_enabled=_parse_bool(source.get("DENVER_STT_ENABLED"), True),
            stt_provider=source.get("DENVER_STT_PROVIDER", "whisper").lower(),
            stt_model=source.get("DENVER_STT_MODEL", "base"),
            stt_language=source.get("DENVER_STT_LANGUAGE", "en"),
            tts_enabled=_parse_bool(source.get("DENVER_TTS_ENABLED"), True),
            tts_provider=source.get("DENVER_TTS_PROVIDER", "edge").lower(),
            tts_voice=source.get("DENVER_TTS_VOICE", "en-GB-RyanNeural"),
            tts_rate=source.get("DENVER_TTS_RATE", "+0%"),
            tts_volume=source.get("DENVER_TTS_VOLUME", "+0%"),
            tts_pitch=source.get("DENVER_TTS_PITCH", "+0Hz"),
            voice_brevity=source.get("DENVER_VOICE_BREVITY", "concise").lower(),
            language=source.get("DENVER_LANGUAGE", "en-US"),
            ui_enabled=_parse_bool(source.get("DENVER_UI_ENABLED"), True),
            automation_enabled=_parse_bool(source.get("DENVER_AUTOMATION_ENABLED"), True),
            automation_confirmation_timeout=_parse_float(source.get("DENVER_AUTOMATION_CONFIRMATION_TIMEOUT"), 30.0),
            allow_high_risk_actions=_parse_bool(source.get("DENVER_ALLOW_HIGH_RISK_ACTIONS"), False),
            default_browser=source.get("DENVER_DEFAULT_BROWSER", "default"),
            screenshot_directory=Path(source.get("DENVER_SCREENSHOT_DIRECTORY", "data/screenshots")),
            allow_destructive_actions=_parse_bool(source.get("DENVER_ALLOW_DESTRUCTIVE_ACTIONS"), False),
            action_sequence_delay=_parse_float(source.get("DENVER_ACTION_SEQUENCE_DELAY"), 0.1),
            app_launch_delay=_parse_float(source.get("DENVER_APP_LAUNCH_DELAY"), 0.2),
            scheduler_enabled=_parse_bool(source.get("DENVER_SCHEDULER_ENABLED"), True),
            scheduler_max_concurrency=int(source.get("DENVER_SCHEDULER_MAX_CONCURRENCY", 2)),
            scheduler_default_timeout_seconds=_parse_float(source.get("DENVER_SCHEDULER_DEFAULT_TIMEOUT_SECONDS"), 60.0),
            scheduler_min_interval_seconds=_parse_float(source.get("DENVER_SCHEDULER_MIN_INTERVAL_SECONDS"), 300.0),
            scheduler_global_pause=_parse_bool(source.get("DENVER_SCHEDULER_GLOBAL_PAUSE"), False),
            scheduler_notification_rate_limit_seconds=_parse_float(source.get("DENVER_SCHEDULER_NOTIFICATION_RATE_LIMIT_SECONDS"), 10.0),
            tasks_enabled=_parse_bool(source.get("DENVER_TASKS_ENABLED"), True),
            task_max_concurrency=int(source.get("DENVER_TASK_MAX_CONCURRENCY", 2)),
            task_default_timeout_seconds=_parse_float(source.get("DENVER_TASK_DEFAULT_TIMEOUT_SECONDS"), 600.0),
            task_step_timeout_seconds=_parse_float(source.get("DENVER_TASK_STEP_TIMEOUT_SECONDS"), 60.0),
            task_max_steps=int(source.get("DENVER_TASK_MAX_STEPS", 20)),
            task_max_depth=int(source.get("DENVER_TASK_MAX_DEPTH", 10)),
            task_max_retries=int(source.get("DENVER_TASK_MAX_RETRIES", 1)),
            task_global_pause=_parse_bool(source.get("DENVER_TASK_GLOBAL_PAUSE"), False),
            weather_provider=source.get("DENVER_WEATHER_PROVIDER", "open-meteo"),
            weather_geocode_url=source.get("DENVER_WEATHER_GEOCODE_URL", "https://geocoding-api.open-meteo.com/v1/search"),
            weather_forecast_url=source.get("DENVER_WEATHER_FORECAST_URL", "https://api.open-meteo.com/v1/forecast"),
            weather_timeout_seconds=_parse_float(source.get("DENVER_WEATHER_TIMEOUT_SECONDS"), 8.0),
            weather_fallback_to_web_agent=_parse_bool(source.get("DENVER_WEATHER_FALLBACK_TO_WEB_AGENT"), True),
            routing_provider=source.get("DENVER_ROUTING_PROVIDER", "osrm"),
            osrm_base_url=source.get("DENVER_OSRM_BASE_URL", ""),
            osrm_timeout_seconds=_parse_float(source.get("DENVER_OSRM_TIMEOUT_SECONDS"), 8.0),
            google_maps_enabled=_parse_bool(source.get("DENVER_GOOGLE_MAPS_ENABLED"), False),
            google_maps_api_key=source.get("DENVER_GOOGLE_MAPS_API_KEY", ""),
            route_open_in_browser=_parse_bool(source.get("DENVER_ROUTE_OPEN_IN_BROWSER"), True),
            location_provider_primary=source.get("DENVER_LOCATION_PROVIDER_PRIMARY", "ipapi.co"),
            location_provider_fallback=source.get("DENVER_LOCATION_PROVIDER_FALLBACK", "ip-api.com"),
            location_cache_ttl_seconds=_parse_int(source.get("DENVER_LOCATION_CACHE_TTL_SECONDS"), 600),
            location_timeout_seconds=_parse_float(source.get("DENVER_LOCATION_TIMEOUT_SECONDS"), 5.0),
        )

    def to_safe_dict(self) -> dict[str, Any]:
        """Export settings with sensitive credentials masked."""
        data = {}
        sensitive_keys = {"groq_api_key", "gemini_api_key", "google_maps_api_key", "spotify_client_secret"}
        for k, v in self.__dict__.items():
            if k in sensitive_keys:
                data[k] = "***" if v else ""
            elif isinstance(v, Path):
                data[k] = str(v)
            elif isinstance(v, tuple):
                data[k] = list(v)
            else:
                data[k] = v
        return data


# Global singleton cache for settings
_settings_instance: DenverSettings | None = None


def get_settings(reload: bool = False) -> DenverSettings:
    """Get or initialize Denver global settings."""
    global _settings_instance
    if _settings_instance is None or reload:
        _settings_instance = DenverSettings.from_env()
    return _settings_instance
