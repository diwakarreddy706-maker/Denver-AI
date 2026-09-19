"""Typed Denver Event Definitions for the Asynchronous Event Bus."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from denver.runtime.states import DenverState


@dataclass(frozen=True)
class DenverEvent:
    """Base event contract for all Denver system events."""

    timestamp: float = field(default_factory=time.time)

    @property
    def event_name(self) -> str:
        return self.__class__.__name__


# ============================================================================
# Core Lifecycle & State Events
# ============================================================================

@dataclass(frozen=True)
class ApplicationStarted(DenverEvent):
    """Emitted when Denver has successfully initialized and reached STANDBY."""

    version: str = "0.1.0"
    environment: str = "development"


@dataclass(frozen=True)
class ApplicationStopping(DenverEvent):
    """Emitted when Denver initiates graceful shutdown."""

    reason: str = "normal_exit"


@dataclass(frozen=True)
class ApplicationStopped(DenverEvent):
    """Emitted when Denver has cleaned up all resources and entered STOPPED."""

    uptime_seconds: float = 0.0


@dataclass(frozen=True)
class StateChanged(DenverEvent):
    """Emitted on every valid state machine transition."""

    from_state: DenverState = DenverState.BOOTING
    to_state: DenverState = DenverState.STANDBY
    reason: str = ""


@dataclass(frozen=True)
class ErrorOccurred(DenverEvent):
    """Emitted when an unhandled or recoverable error is intercepted."""

    error_type: str = "generic"
    message: str = ""
    component: str = "core"
    recoverable: bool = True
    context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HealthChanged(DenverEvent):
    """Emitted when system health status updates."""

    status: str = "HEALTHY"
    details: Mapping[str, Any] = field(default_factory=dict)


# ============================================================================
# Memory Subsystem Events
# ============================================================================

@dataclass(frozen=True)
class MemoryCreated(DenverEvent):
    """Emitted when a new memory item or preference is created."""

    category: str = "general"
    key: str = ""
    privacy_level: str = "internal"


@dataclass(frozen=True)
class MemoryRetrieved(DenverEvent):
    """Emitted when memories or preferences are queried."""

    category: str = "general"
    key: str = ""
    privacy_level: str = "internal"


@dataclass(frozen=True)
class MemoryUpdated(DenverEvent):
    """Emitted when a memory item or preference is updated."""

    category: str = "general"
    key: str = ""
    privacy_level: str = "internal"


@dataclass(frozen=True)
class MemoryDeleted(DenverEvent):
    """Emitted when a memory item or preference is deleted."""

    category: str = "general"
    key: str = ""


@dataclass(frozen=True)
class MemoryCleared(DenverEvent):
    """Emitted when stored memories are wiped under privacy/maintenance."""

    category: str | None = None
    count: int = 0


@dataclass(frozen=True)
class MemoryExpired(DenverEvent):
    """Emitted when expired memories are purged by TTL."""

    purged_count: int = 0


@dataclass(frozen=True)
class MemoryDeduplicated(DenverEvent):
    """Emitted when a memory item was updated via deduplication/correction rather than duplicated."""

    category: str = "general"
    key: str = ""
    match_type: str = "exact"


@dataclass(frozen=True)
class MemoryExtractionCompleted(DenverEvent):
    """Emitted when structured memory extraction completes."""

    extracted_count: int = 0


@dataclass(frozen=True)
class ContextBuilt(DenverEvent):
    """Emitted when ContextEngine produces a ContextBundle."""

    memory_count: int = 0
    total_chars: int = 0
    has_profile: bool = False


@dataclass(frozen=True)
class ContextBudgetApplied(DenverEvent):
    """Emitted when context truncation / budgeting rules are applied."""

    original_turns: int = 0
    final_turns: int = 0
    original_chars: int = 0
    final_chars: int = 0


@dataclass(frozen=True)
class SensitiveMemoryExcluded(DenverEvent):
    """Emitted when sensitive memory is sanitized/excluded from cloud AI context."""

    excluded_count: int = 0
    reason: str = "cloud_privacy_policy"


@dataclass(frozen=True)
class EmbeddingStarted(DenverEvent):
    """Emitted when text embedding computation begins."""

    provider: str = "lexical"
    item_count: int = 1


@dataclass(frozen=True)
class EmbeddingCompleted(DenverEvent):
    """Emitted when embedding computation finishes."""

    provider: str = "lexical"
    dimension: int = 128
    latency_ms: float = 0.0


@dataclass(frozen=True)
class EmbeddingFailed(DenverEvent):
    """Emitted when an embedding provider encounters an error and triggers fallback."""

    provider: str = "ollama"
    error: str = ""



# ============================================================================
# Command Engine Lifecycle Events
# ============================================================================

@dataclass(frozen=True)
class CommandReceived(DenverEvent):
    """Emitted when a raw user command is received."""

    command_text: str = ""
    source: str = "text"  # voice, text, hotkey, cli


@dataclass(frozen=True)
class CommandNormalized(DenverEvent):
    """Emitted after input normalization."""

    raw_text: str = ""
    normalized_text: str = ""


@dataclass(frozen=True)
class CommandRouted(DenverEvent):
    """Emitted when an intent has been classified."""

    intent_name: str = ""
    action_name: str = ""
    category: str = "utility"
    confidence: float = 1.0
    risk_level: str = "SAFE"


@dataclass(frozen=True)
class CommandExecutionStarted(DenverEvent):
    """Emitted immediately before an action handler executes."""

    action_name: str = ""
    risk_level: str = "SAFE"


@dataclass(frozen=True)
class CommandExecutionCompleted(DenverEvent):
    """Emitted after an action handler successfully executes."""

    action_name: str = ""
    success: bool = True
    latency_ms: float = 0.0


@dataclass(frozen=True)
class CommandFailed(DenverEvent):
    """Emitted when command routing or execution fails."""

    action_name: str = ""
    reason: str = ""
    error: str = ""


# ============================================================================
# AI Provider Lifecycle Events
# ============================================================================

@dataclass(frozen=True)
class ProviderRequestStarted(DenverEvent):
    """Emitted when an AI provider inference request is initiated."""

    provider_name: str = ""
    model_name: str = ""
    is_cloud: bool = False


@dataclass(frozen=True)
class ProviderResponseReceived(DenverEvent):
    """Emitted when an AI provider returns a successful completion."""

    provider_name: str = ""
    model_name: str = ""
    latency_ms: float = 0.0
    has_tool_calls: bool = False


@dataclass(frozen=True)
class ProviderFailed(DenverEvent):
    """Emitted when an AI provider request encounters an error or times out."""

    provider_name: str = ""
    model_name: str = ""
    error: str = ""


@dataclass(frozen=True)
class ProviderFallback(DenverEvent):
    """Emitted when the router fails over from one provider to the next in priority order."""

    from_provider: str = ""
    to_provider: str = ""
    reason: str = ""


@dataclass(frozen=True)
class ProviderUnavailable(DenverEvent):
    """Emitted when a provider is skipped because it is offline/unconfigured."""

    provider_name: str = ""
    reason: str = ""


@dataclass(frozen=True)
class AirGappedModeChanged(DenverEvent):
    """Emitted when Air-Gapped / Local-Only mode is toggled."""

    enabled: bool = False
    enforced_providers: tuple[str, ...] = ("ollama", "lmstudio")


@dataclass(frozen=True)
class ProviderModeChanged(DenverEvent):
    """Emitted when active LLM provider or priority is switched."""

    active_provider: str = "groq"
    air_gapped: bool = False
    priority_order: tuple[str, ...] = ()


# ============================================================================
# Future Pipeline Event Interfaces (Audio & Automation)
# ============================================================================

@dataclass(frozen=True)
class WakeWordDetected(DenverEvent):
    wake_phrase: str = "Denver"
    confidence: float = 1.0


# ============================================================================
# Audio & Voice Subsystem Lifecycle Events
# ============================================================================

@dataclass(frozen=True)
class AudioDeviceDetected(DenverEvent):
    """Emitted when an audio input or output device is discovered."""

    device_name: str = ""
    device_type: str = "input"  # input, output
    channels: int = 1
    sample_rate: int = 16000


@dataclass(frozen=True)
class AudioDeviceLost(DenverEvent):
    """Emitted when an audio device is disconnected or unavailable."""

    device_name: str = ""
    device_type: str = "input"


@dataclass(frozen=True)
class SpeechStarted(DenverEvent):
    """Emitted by VAD when speech onset is detected."""

    source: str = "microphone"
    energy: float = 0.0


@dataclass(frozen=True)
class SpeechStopped(DenverEvent):
    """Emitted by VAD when speech terminates after silence hangover."""

    duration_seconds: float = 0.0
    speech_chunks: int = 0


@dataclass(frozen=True)
class SpeechEnded(DenverEvent):
    """Legacy alias for SpeechStopped."""

    duration_seconds: float = 0.0


@dataclass(frozen=True)
class WakeWordDetected(DenverEvent):
    """Emitted when the acoustic wake-word is detected."""

    wake_word: str = "Denver"
    confidence: float = 1.0
    detector_type: str = "acoustic"


@dataclass(frozen=True)
class TranscriptProduced(DenverEvent):
    """Emitted when STT converts an audio utterance into text."""

    text: str = ""
    is_final: bool = True
    confidence: float = 1.0
    provider: str = "whisper"
    latency_ms: float = 0.0


@dataclass(frozen=True)
class TranscriptReceived(DenverEvent):
    """Legacy alias for TranscriptProduced."""

    raw_text: str = ""
    is_final: bool = True
    engine: str = "local"


@dataclass(frozen=True)
class TTSStarted(DenverEvent):
    """Emitted when text-to-speech synthesis begins."""

    text: str = ""
    provider: str = "edge"
    voice: str = ""


@dataclass(frozen=True)
class TTSCompleted(DenverEvent):
    """Emitted when text-to-speech synthesis finishes."""

    text: str = ""
    duration_seconds: float = 0.0
    latency_ms: float = 0.0
    provider: str = ""


@dataclass(frozen=True)
class TTSEnded(DenverEvent):
    """Legacy alias for TTSCompleted."""

    text: str = ""
    duration_ms: float = 0.0


@dataclass(frozen=True)
class AudioPlaybackStarted(DenverEvent):
    """Emitted when audio playback begins on speaker."""

    duration_seconds: float = 0.0


@dataclass(frozen=True)
class AudioPlaybackCompleted(DenverEvent):
    """Emitted when audio playback finishes on speaker."""

    duration_seconds: float = 0.0


@dataclass(frozen=True)
class AudioPlaybackStopped(DenverEvent):
    """Emitted when audio playback is stopped early (e.g. barge-in)."""

    reason: str = "barge_in"


@dataclass(frozen=True)
class BargeInDetected(DenverEvent):
    """Emitted when user speaks over active Denver speech playback."""

    energy: float = 0.0
    duration_ms: float = 0.0


@dataclass(frozen=True)
class AudioError(DenverEvent):
    """Emitted when an error occurs in the audio subsystem."""

    subsystem: str = "capture"
    error: str = ""
    fatal: bool = False


# ============================================================================
# Generic Action Lifecycle Events
# ============================================================================

@dataclass(frozen=True)
class ActionStarted(DenverEvent):
    action_id: str = ""
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ActionCompleted(DenverEvent):
    action_id: str = ""
    result: Any = None
    duration_ms: float = 0.0


@dataclass(frozen=True)
class ActionFailed(DenverEvent):
    action_id: str = ""
    reason: str = ""
    error: str = ""


# ============================================================================
# Phase 5: Desktop Automation & System Control Events
# ============================================================================

@dataclass(frozen=True)
class AutomationRequested(DenverEvent):
    """Emitted when an automation action is requested."""

    action_name: str = ""
    target: str = ""
    risk_level: str = "LOW"
    requires_confirmation: bool = False


@dataclass(frozen=True)
class AutomationStarted(DenverEvent):
    """Emitted when an automation executor begins execution."""

    action_name: str = ""
    target: str = ""


@dataclass(frozen=True)
class AutomationCompleted(DenverEvent):
    """Emitted when an automation action completes successfully."""

    action_name: str = ""
    target: str = ""
    latency_ms: float = 0.0


@dataclass(frozen=True)
class AutomationFailed(DenverEvent):
    """Emitted when an automation action fails or is rejected."""

    action_name: str = ""
    target: str = ""
    error: str = ""
    reason: str = ""


@dataclass(frozen=True)
class AutomationConfirmationRequired(DenverEvent):
    """Emitted when a high-risk automation action requires explicit confirmation."""

    token: str = ""
    action_name: str = ""
    target: str = ""
    prompt_message: str = ""
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class AutomationConfirmationReceived(DenverEvent):
    """Emitted when a valid confirmation token is confirmed by the user."""

    token: str = ""
    action_name: str = ""


@dataclass(frozen=True)
class AutomationConfirmationExpired(DenverEvent):
    """Emitted when a pending confirmation token expires without being confirmed."""

    token: str = ""
    action_name: str = ""


@dataclass(frozen=True)
class ApplicationOpened(DenverEvent):
    """Emitted when an allowlisted desktop application is launched."""

    app_id: str = ""
    display_name: str = ""
    pid: int | None = None


@dataclass(frozen=True)
class ApplicationClosed(DenverEvent):
    """Emitted when an allowlisted application is closed/terminated."""

    app_id: str = ""
    display_name: str = ""
    terminated_processes: int = 0


@dataclass(frozen=True)
class WindowActionPerformed(DenverEvent):
    """Emitted when a window management action is performed."""

    operation: str = ""  # minimize, maximize, restore, focus, show_desktop
    window_title: str = ""
    matched_count: int = 0


@dataclass(frozen=True)
class VolumeChanged(DenverEvent):
    """Emitted when system volume is modified or muted."""

    operation: str = ""  # set, increase, decrease, mute, unmute
    new_volume: int | None = None
    is_muted: bool | None = None


@dataclass(frozen=True)
class ScreenshotCaptured(DenverEvent):
    """Emitted when a screenshot is successfully captured and saved."""

    file_path: str = ""
    file_size_bytes: int = 0
    width: int = 0
    height: int = 0


# ============================================================================
# Phase 8: Scheduler & Routine Events
# ============================================================================

@dataclass(frozen=True)
class SchedulerStarted(DenverEvent):
    """Emitted when the persistent scheduler service starts."""

    active_routines: int = 0


@dataclass(frozen=True)
class SchedulerStopped(DenverEvent):
    """Emitted when the persistent scheduler service cleanly stops."""

    reason: str = "normal"


@dataclass(frozen=True)
class SchedulerPaused(DenverEvent):
    """Emitted when the scheduler is globally paused."""

    reason: str = "user_command"


@dataclass(frozen=True)
class SchedulerResumed(DenverEvent):
    """Emitted when the scheduler is globally resumed."""

    reason: str = "user_command"


@dataclass(frozen=True)
class RoutineCreated(DenverEvent):
    """Emitted when a new routine is persisted."""

    routine_id: str = ""
    name: str = ""
    trigger_type: str = ""


@dataclass(frozen=True)
class RoutineUpdated(DenverEvent):
    """Emitted when an existing routine is modified."""

    routine_id: str = ""
    name: str = ""


@dataclass(frozen=True)
class RoutineEnabled(DenverEvent):
    """Emitted when a routine is enabled."""

    routine_id: str = ""


@dataclass(frozen=True)
class RoutineDisabled(DenverEvent):
    """Emitted when a routine is disabled."""

    routine_id: str = ""


@dataclass(frozen=True)
class RoutineDeleted(DenverEvent):
    """Emitted when a routine is deleted."""

    routine_id: str = ""


@dataclass(frozen=True)
class RoutineStarted(DenverEvent):
    """Emitted when a routine begins execution."""

    execution_id: str = ""
    routine_id: str = ""
    name: str = ""
    trigger_type: str = ""


@dataclass(frozen=True)
class RoutineCompleted(DenverEvent):
    """Emitted when a routine successfully completes execution."""

    execution_id: str = ""
    routine_id: str = ""
    name: str = ""
    action_count: int = 0
    duration_ms: float = 0.0


@dataclass(frozen=True)
class RoutineFailed(DenverEvent):
    """Emitted when a routine fails during execution."""

    execution_id: str = ""
    routine_id: str = ""
    name: str = ""
    error: str = ""
    failed_actions: int = 0


@dataclass(frozen=True)
class RoutineBlocked(DenverEvent):
    """Emitted when a routine is blocked by SafetyValidator policy."""

    routine_id: str = ""
    reason: str = ""


@dataclass(frozen=True)
class RoutineSkipped(DenverEvent):
    """Emitted when a routine run is skipped."""

    routine_id: str = ""
    reason: str = ""


@dataclass(frozen=True)
class RoutineMissed(DenverEvent):
    """Emitted when a routine was missed while offline."""

    routine_id: str = ""
    scheduled_for: str = ""


@dataclass(frozen=True)
class RoutineConfirmationRequested(DenverEvent):
    """Emitted when high-risk routine actions require user approval."""

    routine_id: str = ""
    token: str = ""
    action_summary: str = ""


@dataclass(frozen=True)
class RoutineConfirmationAccepted(DenverEvent):
    """Emitted when user confirms routine execution."""

    routine_id: str = ""
    token: str = ""


@dataclass(frozen=True)
class RoutineConfirmationRejected(DenverEvent):
    """Emitted when user rejects routine execution."""

    routine_id: str = ""
    token: str = ""


@dataclass(frozen=True)
class RoutineNotificationSent(DenverEvent):
    """Emitted when a routine desktop/UI notification is dispatched."""

    routine_id: str = ""
    title: str = ""
    message: str = ""
    status: str = "sent"


# ============================================================================
# Phase 9: Intelligent Task & Workflow Orchestration Lifecycle Events
# ============================================================================

@dataclass(frozen=True)
class TaskCreated(DenverEvent):
    """Emitted when a new multi-step task is created or saved."""

    task_id: str = ""
    title: str = ""
    origin: str = "user"
    step_count: int = 0


@dataclass(frozen=True)
class TaskProposed(DenverEvent):
    """Emitted when AI or planner produces a task proposal for user review."""

    task_id: str = ""
    title: str = ""
    proposal_id: str = ""
    step_count: int = 0
    estimated_duration_seconds: float = 0.0


@dataclass(frozen=True)
class TaskApprovalRequested(DenverEvent):
    """Emitted when a task plan or consequential step requires explicit user approval."""

    task_id: str = ""
    plan_id: str = ""
    token: str = ""
    summary: str = ""
    risk_level: str = "LOW"


@dataclass(frozen=True)
class TaskApprovalAccepted(DenverEvent):
    """Emitted when user explicitly approves a task plan or step."""

    task_id: str = ""
    plan_id: str = ""
    token: str = ""


@dataclass(frozen=True)
class TaskApprovalRejected(DenverEvent):
    """Emitted when user rejects a task plan or step."""

    task_id: str = ""
    plan_id: str = ""
    token: str = ""
    reason: str = ""


@dataclass(frozen=True)
class TaskStarted(DenverEvent):
    """Emitted when a workflow execution begins."""

    execution_id: str = ""
    task_id: str = ""
    plan_id: str = ""
    title: str = ""
    total_steps: int = 0


@dataclass(frozen=True)
class TaskPaused(DenverEvent):
    """Emitted when a running workflow is paused."""

    task_id: str = ""
    execution_id: str = ""
    current_step: str = ""


@dataclass(frozen=True)
class TaskResumed(DenverEvent):
    """Emitted when a paused workflow is resumed."""

    task_id: str = ""
    execution_id: str = ""


@dataclass(frozen=True)
class TaskCancelled(DenverEvent):
    """Emitted when a workflow is cancelled by user or safety trigger."""

    task_id: str = ""
    execution_id: str = ""
    reason: str = ""


@dataclass(frozen=True)
class TaskCompleted(DenverEvent):
    """Emitted when a task workflow successfully finishes all steps."""

    execution_id: str = ""
    task_id: str = ""
    title: str = ""
    completed_steps: int = 0
    total_steps: int = 0
    duration_ms: float = 0.0


@dataclass(frozen=True)
class TaskFailed(DenverEvent):
    """Emitted when a task workflow fails."""

    execution_id: str = ""
    task_id: str = ""
    title: str = ""
    failed_step: str = ""
    error: str = ""
    completed_steps: int = 0
    total_steps: int = 0


@dataclass(frozen=True)
class TaskBlocked(DenverEvent):
    """Emitted when a task is blocked by security validation or missing permissions."""

    task_id: str = ""
    reason: str = ""


@dataclass(frozen=True)
class TaskStepStarted(DenverEvent):
    """Emitted immediately before an individual step begins execution."""

    execution_id: str = ""
    task_id: str = ""
    step_id: str = ""
    action_name: str = ""
    step_index: int = 0


@dataclass(frozen=True)
class TaskStepCompleted(DenverEvent):
    """Emitted when an individual workflow step finishes successfully."""

    execution_id: str = ""
    task_id: str = ""
    step_id: str = ""
    action_name: str = ""
    latency_ms: float = 0.0


@dataclass(frozen=True)
class TaskStepFailed(DenverEvent):
    """Emitted when an individual workflow step fails."""

    execution_id: str = ""
    task_id: str = ""
    step_id: str = ""
    action_name: str = ""
    error: str = ""
    retry_count: int = 0


@dataclass(frozen=True)
class TaskStepBlocked(DenverEvent):
    """Emitted when an individual workflow step is blocked by SafetyValidator."""

    execution_id: str = ""
    task_id: str = ""
    step_id: str = ""
    action_name: str = ""
    reason: str = ""


@dataclass(frozen=True)
class TaskProgressUpdated(DenverEvent):
    """Emitted when task progress percentage or step index advances."""

    task_id: str = ""
    execution_id: str = ""
    completed_steps: int = 0
    total_steps: int = 0
    progress_percent: float = 0.0
    current_step_name: str = ""


@dataclass(frozen=True)
class WhatsAppMessageDispatched(DenverEvent):
    """Emitted when a WhatsApp message is dispatched."""

    contact: str = ""
    phone: str = ""
    message: str = ""
    success: bool = True


@dataclass(frozen=True)
class SpotifyPlaybackChanged(DenverEvent):
    """Emitted when Spotify / media playback action is triggered."""

    action: str = "play_pause"
    query: str = ""
    success: bool = True



