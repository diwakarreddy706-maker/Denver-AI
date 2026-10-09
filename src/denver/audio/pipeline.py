"""Voice Pipeline Orchestrator for Denver AI Assistant."""

from __future__ import annotations

import asyncio
import collections
import time
from typing import Any

from denver.audio.capture import AudioCapture
from denver.audio.device import AudioDeviceManager
from denver.audio.models import (
    AudioChunk,
    AudioFormat,
    AudioPipelineStatus,
    Transcript,
    TTSRequest,
    TTSResult,
    VoiceActivityState,
)
from denver.audio.playback import AudioPlayback
from denver.audio.push_to_talk import PushToTalkListener
from denver.audio.sentence_splitter import stream_sentences
from denver.audio.stt import GroqWhisperSTTProvider, SpeechToTextProvider, WhisperSTTProvider
from denver.audio.tts import EdgeTTSProvider, TextToSpeechProvider, WindowsTTSProvider, clean_text_for_speech
from denver.audio.tts_queue import DenverTTSQueue, TTSPriority
from denver.audio.vad import EnergyVAD, VADEngine
from denver.audio.wakeword import FallbackWakeWordDetector, WakeWordDetector
from denver.commands.models import CommandRequest
from denver.commands.service import CommandEngineService
from denver.config.settings import DenverSettings, get_settings
from denver.logging.logger import get_logger
from denver.runtime.event_bus import DenverEventBus, get_event_bus
from denver.security.vault import get_vault
from denver.runtime.events import (
    AudioDeviceDetected,
    AudioError,
    AudioPlaybackCompleted,
    AudioPlaybackStarted,
    AudioPlaybackStopped,
    BargeInDetected,
    SpeechStarted,
    SpeechStopped,
    StateChanged,
    TranscriptProduced,
    TTSCompleted,
    TTSStarted,
    WakeWordDetected,
)
from denver.runtime.state_machine import DenverStateMachine
from denver.runtime.states import DenverState

logger = get_logger("audio.pipeline")


class VoicePipeline:
    """End-to-end Voice Processing Pipeline managing Capture, VAD, Wake-Word, STT, TTS, and Playback."""

    def __init__(
        self,
        command_service: CommandEngineService,
        state_machine: DenverStateMachine | None = None,
        event_bus: DenverEventBus | None = None,
        settings: DenverSettings | None = None,
        capture: AudioCapture | None = None,
        vad: VADEngine | None = None,
        wakeword: WakeWordDetector | None = None,
        stt: SpeechToTextProvider | None = None,
        tts: TextToSpeechProvider | None = None,
        playback: AudioPlayback | None = None,
        device_manager: AudioDeviceManager | None = None,
        fallback_tts: TextToSpeechProvider | None = None,
    ) -> None:
        self.command_service = command_service
        self.state_machine = state_machine
        self.event_bus = event_bus or get_event_bus()
        self.settings = settings or get_settings()

        self.device_manager = device_manager or AudioDeviceManager()
        self.format = AudioFormat()

        self.capture = capture or AudioCapture(
            audio_format=self.format,
            device_manager=self.device_manager,
        )
        self.vad = vad or EnergyVAD(
            energy_threshold=max(0.015, float(self.settings.vad_threshold) * 0.04),
            min_speech_ms=float(self.settings.vad_min_speech_ms),
            min_silence_ms=float(self.settings.vad_min_silence_ms),
            max_utterance_seconds=self.settings.vad_max_utterance_seconds,
        )
        self.wakeword = wakeword or FallbackWakeWordDetector(
            wake_word=self.settings.wake_word,
            threshold=max(0.035, float(self.settings.wake_word_threshold) * 0.08),
            cooldown_seconds=self.settings.wake_word_cooldown_seconds,
        )

        if stt is not None:
            self.stt = stt
        elif self.settings.stt_provider == "groq_whisper":
            self.stt = GroqWhisperSTTProvider()
        else:
            local_whisper = WhisperSTTProvider(
                model_size=self.settings.stt_model,
                language=self.settings.stt_language,
            )
            # Try to load local model; if unavailable and GROQ_API_KEY is configured, use Groq Whisper Cloud
            if not local_whisper.load_model() and get_vault().get_secret("GROQ_API_KEY"):
                logger.info("Local Whisper not available; activating Groq Cloud Whisper STT.")
                self.stt = GroqWhisperSTTProvider()
            else:
                self.stt = local_whisper

        self.tts = tts or EdgeTTSProvider(
            default_voice=self.settings.tts_voice,
            default_rate=self.settings.tts_rate,
            default_volume=self.settings.tts_volume,
            default_pitch=self.settings.tts_pitch,
        )
        self.fallback_tts = fallback_tts or WindowsTTSProvider(
            voice_name=getattr(self.settings, "tts_fallback_voice", "")
        )
        self.playback = playback or AudioPlayback(device_manager=self.device_manager)
        self.tts_queue = DenverTTSQueue(enabled=self.settings.tts_enabled)

        if self.settings.push_to_talk_enabled:
            self.ptt: PushToTalkListener | None = PushToTalkListener(
                hotkey=self.settings.push_to_talk_hotkey,
                on_trigger=self.trigger_listening,
            )
        else:
            self.ptt = None

        self._is_running = False
        self._loop_task: asyncio.Task[Any] | None = None
        self._current_speech_chunks: list[AudioChunk] = []
        self._preroll_chunks: collections.deque[AudioChunk] = collections.deque(maxlen=6)
        self.last_latency_metrics: dict[str, float] = {}

    @property
    def is_running(self) -> bool:
        return self._is_running

    def get_status(self) -> AudioPipelineStatus:
        """Produce diagnostic summary of all audio pipeline components."""
        in_dev = self.device_manager.get_default_input_device()
        out_dev = self.device_manager.get_default_output_device()

        components = {
            "vad": self.vad.name,
            "wakeword": f"{self.wakeword.name} ({self.wakeword.detector_type})",
            "stt": self.stt.name,
            "tts": self.tts.name,
        }
        devices = {
            "input": in_dev.name if in_dev else "NO_INPUT_DEVICE",
            "output": out_dev.name if out_dev else "NO_OUTPUT_DEVICE",
        }

        status_code = "READY"
        if not in_dev or not out_dev:
            status_code = "DEGRADED"

        return AudioPipelineStatus(
            status=status_code,
            capture_active=self.capture.is_capturing,
            vad_active=True,
            wakeword_active=self.settings.wake_word_enabled,
            stt_active=self.stt.is_available,
            tts_active=self.tts.is_available,
            playback_active=self.playback.is_playing,
            devices=devices,
            components=components,
        )

    @property
    def is_muted(self) -> bool:
        return getattr(self.capture, "is_muted", False)

    def mute(self) -> None:
        """Mute microphone audio capture."""
        if hasattr(self.capture, "mute"):
            self.capture.mute()

    def unmute(self) -> None:
        """Unmute microphone audio capture."""
        if hasattr(self.capture, "unmute"):
            self.capture.unmute()

    def toggle_mute(self) -> bool:
        """Toggle microphone audio capture mute state."""
        if hasattr(self.capture, "toggle_mute"):
            return self.capture.toggle_mute()
        return False

    def _notify_overlay(self, state: str) -> None:
        """Lazily notify wake HUD overlay without top-level PySide6 import."""
        try:
            from denver.ui.widgets.wake_overlay import notify_wake_overlay
            notify_wake_overlay(state)
        except Exception:
            pass

    def _notify_overlay_subtitle(self, text: str) -> None:
        try:
            from denver.ui.widgets.wake_overlay import notify_wake_overlay_subtitle
            notify_wake_overlay_subtitle(text)
        except Exception:
            pass

    def _notify_overlay_audio(self, level: float) -> None:
        try:
            from denver.ui.widgets.wake_overlay import notify_wake_overlay_audio
            notify_wake_overlay_audio(level)
        except Exception:
            pass

    def _notify_overlay_receipt(self, icon: str, title: str, detail: str = "") -> None:
        try:
            from denver.ui.widgets.wake_overlay import notify_wake_overlay_receipt
            notify_wake_overlay_receipt(icon, title, detail)
        except Exception:
            pass

    async def trigger_listening(self) -> None:
        """Manually trigger LISTENING state (push-to-talk / mic button click)."""
        if not self._is_running:
            await self.start()
        if hasattr(self.wakeword, "trigger_wake"):
            self.wakeword.trigger_wake()
        self._current_speech_chunks.clear()
        self.vad.reset()
        self._listening_start_time = time.time()
        self._notify_overlay("LISTENING")
        if self.state_machine and self.state_machine.can_transition_to(DenverState.LISTENING):
            await self.state_machine.transition_to(
                DenverState.LISTENING,
                reason="Push-to-talk manual voice activation",
            )
        await self.event_bus.publish(SpeechStarted(energy=0.5))

    async def _synthesize_with_fallback(self, request: TTSRequest) -> tuple[TTSResult, str]:
        """Synthesize speech using primary TTS, falling back to offline WindowsTTSProvider on failure."""
        primary_name = self.tts.name
        try:
            res = await self.tts.synthesize(request)
            if res.success and res.audio_data:
                return res, primary_name
            logger.warning(
                "Primary TTS provider '%s' failed (%s); falling back to offline '%s'.",
                primary_name,
                getattr(res, "error", "") or "empty audio",
                self.fallback_tts.name,
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning(
                "Primary TTS provider '%s' raised exception: %s; falling back to offline '%s'.",
                primary_name,
                exc,
                self.fallback_tts.name,
            )

        fallback_res = await self.fallback_tts.synthesize(request)
        return fallback_res, self.fallback_tts.name

    async def start(self) -> bool:
        """Start background microphone capture and continuous processing loop."""
        if self._is_running:
            return True

        if not self.settings.audio_enabled:
            logger.info("Audio engine disabled in configuration.")
            return False

        started = await self.capture.start()
        if not started:
            logger.warning("Could not start audio capture.")
            return False

        # Calibrate ambient noise baseline to prevent false acoustic triggers in noisy environments
        try:
            noise_floor = await self.capture.calibrate_noise_floor(duration_seconds=0.3)
            if hasattr(self.vad, "energy_threshold"):
                self.vad.energy_threshold = max(float(self.vad.energy_threshold), noise_floor + 0.015)
            if hasattr(self.wakeword, "threshold"):
                self.wakeword.threshold = max(float(self.wakeword.threshold), noise_floor + 0.025)
            logger.info(
                "Acoustic calibration complete: noise floor=%.4f, VAD threshold=%.4f, Wake threshold=%.4f",
                noise_floor,
                getattr(self.vad, "energy_threshold", 0.0),
                getattr(self.wakeword, "threshold", 0.0),
            )
        except Exception as exc:
            logger.debug("Noise floor calibration skipped: %s", exc)

        self._is_running = True
        self._loop_task = asyncio.create_task(self._pipeline_loop(), name="denver_voice_pipeline")

        if self.ptt and not self.ptt.is_running:
            try:
                self.ptt.loop = asyncio.get_running_loop()
                self.ptt.start()
            except Exception as exc:
                logger.debug("PTT listener startup note: %s", exc)

        # Synchronize HUD overlay with all state machine transitions
        async def _on_state_changed(event: StateChanged) -> None:
            self._notify_overlay(event.to_state.name)

        try:
            self.event_bus.subscribe(StateChanged, _on_state_changed)
        except Exception:
            pass

        logger.info("Voice processing pipeline active.")
        return True

    async def stop(self) -> None:
        """Halt the voice pipeline and release audio capture/playback."""
        if not self._is_running:
            return

        self._is_running = False
        if self.ptt:
            self.ptt.stop()

        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None

        await self.capture.stop()
        await self.playback.stop()
        self.tts_queue.interrupt()
        self.capture.clear()
        self._current_speech_chunks.clear()
        self._preroll_chunks.clear()
        logger.info("Voice pipeline cleanly shut down.")

    async def _handle_barge_in(self, chunk: AudioChunk) -> None:
        """Interrupt active TTS speech playback when user starts speaking."""
        if self.playback.is_playing or self.tts_queue.is_speaking:
            logger.info("Barge-in detected: interrupting Denver speech.")
            self.tts_queue.interrupt()
            await self.playback.stop()
            await self.event_bus.publish(
                BargeInDetected(energy=chunk.energy, duration_ms=chunk.duration_ms)
            )
            await self.event_bus.publish(
                AudioPlaybackStopped(reason="barge_in")
            )
            if self.state_machine and self.state_machine.can_transition_to(DenverState.LISTENING):
                await self.state_machine.transition_to(
                    DenverState.LISTENING,
                    reason="User barge-in interrupted speech playback",
                )

    async def _pipeline_loop(self) -> None:
        """Continuous temporal processing loop analyzing streaming chunks."""
        try:
            while self._is_running:
                chunk = await self.capture.read_chunk(timeout=0.2)
                if not chunk:
                    await asyncio.sleep(0.01)
                    continue

                curr_state = self.state_machine.current_state if self.state_machine else DenverState.STANDBY

                # 1. Check for barge-in if currently speaking
                if curr_state == DenverState.SPEAKING:
                    vad_res = self.vad.process_chunk(chunk)
                    if vad_res.is_speech and vad_res.energy >= (self.settings.vad_threshold * 0.05):
                        await self._handle_barge_in(chunk)
                    continue

                # 2. If in STANDBY mode, monitor for wake-word activation
                if curr_state == DenverState.STANDBY:
                    if self.settings.wake_word_enabled:
                        wake_res = self.wakeword.process_chunk(chunk)
                        if wake_res.detected:
                            logger.info("Acoustic wake word '%s' detected (Confidence: %.2f)", wake_res.wake_word, wake_res.confidence)
                            self._notify_overlay("LISTENING")
                            await self.event_bus.publish(
                                WakeWordDetected(
                                    wake_word=wake_res.wake_word,
                                    confidence=wake_res.confidence,
                                    detector_type=wake_res.detector_type,
                                )
                            )
                            if self.state_machine and self.state_machine.can_transition_to(DenverState.LISTENING):
                                try:
                                    asyncio.create_task(self.playback.play_listening_chime())
                                except Exception:
                                    pass
                                await self.state_machine.transition_to(
                                    DenverState.LISTENING,
                                    reason=f"Wake word '{wake_res.wake_word}' detected",
                                )
                                self._current_speech_chunks.clear()
                                self.vad.reset()
                                self._listening_start_time = time.time()
                            else:
                                self._current_speech_chunks.clear()
                                self.vad.reset()
                                self._listening_start_time = time.time()
                    continue

                # 3. If in LISTENING mode, accumulate speech frames until silence hangover
                if curr_state == DenverState.LISTENING:
                    vad_res = self.vad.process_chunk(chunk)
                    self._notify_overlay_audio(min(1.0, vad_res.energy * 2.8))
                    if vad_res.state == VoiceActivityState.SPEECH_START:
                        await self.event_bus.publish(SpeechStarted(energy=vad_res.energy))
                        # Prepend preroll buffer so the first syllable/word is never clipped
                        self._current_speech_chunks.extend(self._preroll_chunks)
                        self._preroll_chunks.clear()
                        self._current_speech_chunks.append(chunk)

                    elif vad_res.is_speech or vad_res.state == VoiceActivityState.SPEECH_ACTIVE:
                        self._current_speech_chunks.append(chunk)

                    elif vad_res.state == VoiceActivityState.SPEECH_END:
                        if self._current_speech_chunks:
                            self._current_speech_chunks.append(chunk)
                        duration_sec = sum(c.duration_ms for c in self._current_speech_chunks) / 1000.0
                        await self.event_bus.publish(
                            SpeechStopped(
                                duration_seconds=duration_sec,
                                speech_chunks=len(self._current_speech_chunks),
                            )
                        )
                        # Dispatch complete utterance
                        if self._current_speech_chunks:
                            await self._process_utterance(list(self._current_speech_chunks))
                            self._current_speech_chunks.clear()
                            self._preroll_chunks.clear()
                        else:
                            self._notify_overlay("STANDBY")
                            if self.state_machine and self.state_machine.can_transition_to(DenverState.STANDBY):
                                await self.state_machine.transition_to(DenverState.STANDBY, reason="Empty speech buffer")
                    elif not self._current_speech_chunks:
                        self._preroll_chunks.append(chunk)
                        if time.time() - getattr(self, "_listening_start_time", 0.0) > 8.0:
                            # Listening timeout without speech
                            self._notify_overlay("STANDBY")
                            if self.state_machine and self.state_machine.can_transition_to(DenverState.STANDBY):
                                await self.state_machine.transition_to(DenverState.STANDBY, reason="Listening timeout (no speech)")

        except asyncio.CancelledError:
            pass
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Voice pipeline exception: %s", exc)
            await self.event_bus.publish(AudioError(subsystem="pipeline", error=str(exc), fatal=False))

    async def _process_utterance(self, chunks: list[AudioChunk] | None = None) -> None:
        """Process finalized speech buffer through STT, Command Engine, and TTS."""
        active_chunks = list(chunks) if chunks is not None else list(self._current_speech_chunks)
        raw_pcm = b"".join(c.data for c in active_chunks)
        if not raw_pcm:
            self._notify_overlay("STANDBY")
            if self.state_machine and self.state_machine.can_transition_to(DenverState.STANDBY):
                await self.state_machine.transition_to(DenverState.STANDBY, reason="No audio captured")
            return

        # 1. State transition: LISTENING -> PROCESSING
        self._notify_overlay("PROCESSING")
        if self.state_machine and self.state_machine.can_transition_to(DenverState.PROCESSING):
            await self.state_machine.transition_to(
                DenverState.PROCESSING,
                reason="Transcribing audio utterance",
            )

        # 2. STT Recognition
        transcript: Transcript
        try:
            transcript = await self.stt.transcribe(raw_pcm, self.format)
            await self.event_bus.publish(
                TranscriptProduced(
                    text=transcript.text,
                    confidence=transcript.confidence,
                    provider=transcript.provider,
                    latency_ms=transcript.latency_ms,
                )
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("STT transcription error: %s", exc)
            transcript = Transcript(text="", is_final=True, confidence=0.0, provider=self.stt.name)

        clean_text = transcript.text.strip()
        logger.info("Recognized user speech: '%s' (Confidence: %.2f)", clean_text, transcript.confidence)
        if clean_text:
            self._notify_overlay_subtitle(f"> {clean_text}")
        if not clean_text:
            logger.info("Empty transcript produced; returning to STANDBY.")
            self._notify_overlay("STANDBY")
            if self.state_machine and self.state_machine.can_transition_to(DenverState.STANDBY):
                await self.state_machine.transition_to(DenverState.STANDBY, reason="Empty transcript")
            return

        t_request_start = time.perf_counter()
        stream_handled = False

        # 3. Streaming Sentence-Boundary TTS for conversational AI queries
        if (
            self.settings.tts_enabled
            and getattr(self.settings, "tts_streaming_enabled", True)
            and hasattr(self.command_service, "is_ai_command")
            and self.command_service.is_ai_command(clean_text)
        ):
            stream_handled = await self._handle_streaming_ai_voice_response(clean_text, t_request_start)

        cmd_response = None
        if not stream_handled:
            # Command Engine Processing (Authoritative Execution & Safety)
            cmd_response = await self.command_service.process_command(
                CommandRequest(raw_text=clean_text, source="voice")
            )

            if cmd_response and cmd_response.action_name:
                act = cmd_response.action_name
                icon = "🚀"
                if "weather" in act:
                    icon = "🌤"
                elif "email" in act:
                    icon = "📧"
                elif "git" in act:
                    icon = "🌱"
                elif "lock" in act:
                    icon = "🔒"
                elif "note" in act or "file" in act:
                    icon = "📝"
                elif "calendar" in act:
                    icon = "📅"
                self._notify_overlay_receipt(icon, act.replace("_", " ").title(), cmd_response.message[:40] if cmd_response.message else "")

            # 4. Text-to-Speech (TTS) Synthesis (Whole-Utterance Fallback)
            if cmd_response.message and self.settings.tts_enabled:
                clean_speech = clean_text_for_speech(cmd_response.message)
                if not clean_speech:
                    clean_speech = "Task completed."

                self._notify_overlay_subtitle(f"Denver: {clean_speech[:60]}")

                # Transition: EXECUTING/PROCESSING -> SPEAKING
                self._notify_overlay("SPEAKING")
                if self.state_machine and self.state_machine.can_transition_to(DenverState.SPEAKING):
                    await self.state_machine.transition_to(
                        DenverState.SPEAKING,
                        reason="Speaking response",
                    )

                t_tts_start = time.perf_counter()
                tts_res, provider_used = await self._synthesize_with_fallback(TTSRequest(text=clean_speech))
                t_tts_ready = time.perf_counter()

                if tts_res.success and tts_res.audio_data:
                    await self.event_bus.publish(TTSStarted(text=clean_speech, provider=provider_used))
                    await self.event_bus.publish(
                        TTSCompleted(
                            text=clean_speech,
                            duration_seconds=tts_res.duration_seconds,
                            latency_ms=tts_res.latency_ms,
                            provider=provider_used,
                        )
                    )

                    t_audio_play = time.perf_counter()
                    self.last_latency_metrics = {
                        "request_start": t_request_start,
                        "first_sentence_detected": t_tts_start,
                        "first_audio_ready": t_tts_ready,
                        "first_audio_playing": t_audio_play,
                        "ttfs_seconds": round(t_tts_start - t_request_start, 4),
                        "ttfa_seconds": round(t_tts_ready - t_request_start, 4),
                        "total_latency_seconds": round(t_audio_play - t_request_start, 4),
                    }
                    logger.info(
                        "Whole-utterance TTS Latency: TTFA=%.3fs, Total=%.3fs",
                        self.last_latency_metrics["ttfa_seconds"],
                        self.last_latency_metrics["total_latency_seconds"],
                    )

                    await self.event_bus.publish(AudioPlaybackStarted(duration_seconds=tts_res.duration_seconds))
                    played = await self.playback.play_bytes(tts_res.audio_data, format=tts_res.format)
                    if played:
                        await self.event_bus.publish(AudioPlaybackCompleted(duration_seconds=tts_res.duration_seconds))
                    # Allow room acoustics / speaker reverberation to dissipate
                    await asyncio.sleep(0.25)

        # 5. Clear residual speaker audio & debounce wake word
        self.capture.clear()
        self.vad.reset()
        self.wakeword.reset()
        if hasattr(self.wakeword, "_last_trigger_time"):
            self.wakeword._last_trigger_time = time.time() + 0.6  # 600ms grace period against speaker echo

        # 6. If user invoked assistant greeting/call, immediately transition back to LISTENING
        if cmd_response and cmd_response.action_name == "assistant_call":
            if self.state_machine and self.state_machine.can_transition_to(DenverState.LISTENING):
                self._current_speech_chunks.clear()
                self._preroll_chunks.clear()
                self._listening_start_time = time.time()
                await self.state_machine.transition_to(
                    DenverState.LISTENING,
                    reason="Prompted user, continuing to listen for command",
                )
                self._notify_overlay("LISTENING")
                return

        # 7. Return to STANDBY
        self._notify_overlay("STANDBY")
        if self.state_machine and self.state_machine.can_transition_to(DenverState.STANDBY):
            await self.state_machine.transition_to(
                DenverState.STANDBY,
                reason="Voice turn complete",
            )

    async def _handle_streaming_ai_voice_response(
        self,
        clean_text: str,
        t_request_start: float,
    ) -> bool:
        """Stream tokens incrementally, detect sentence boundaries, synthesize concurrently, and play sequentially."""
        token_stream = self.command_service.stream_ai_tokens(clean_text)
        sentence_stream = stream_sentences(token_stream)

        audio_queue: asyncio.Queue[tuple[str, asyncio.Task[Any]] | None] = asyncio.Queue()
        first_sentence_detected_time: float | None = None
        first_audio_ready_time: float | None = None
        first_audio_playing_time: float | None = None
        sentence_count = 0

        async def producer():
            nonlocal first_sentence_detected_time, sentence_count
            try:
                async for raw_sentence in sentence_stream:
                    cleaned_sentence = clean_text_for_speech(raw_sentence)
                    if not cleaned_sentence:
                        continue
                    if first_sentence_detected_time is None:
                        first_sentence_detected_time = time.perf_counter()
                    sentence_count += 1
                    tts_task = asyncio.create_task(self._synthesize_with_fallback(TTSRequest(text=cleaned_sentence)))
                    await audio_queue.put((cleaned_sentence, tts_task))
            finally:
                await audio_queue.put(None)

        producer_task = asyncio.create_task(producer())

        try:
            while True:
                item = await audio_queue.get()
                if item is None:
                    break
                sentence_text, tts_task = item
                tts_res, provider_used = await tts_task

                if tts_res.success and tts_res.audio_data:
                    now = time.perf_counter()
                    if first_audio_ready_time is None:
                        first_audio_ready_time = now

                    self._notify_overlay("SPEAKING")
                    if self.state_machine and self.state_machine.can_transition_to(DenverState.SPEAKING):
                        await self.state_machine.transition_to(
                            DenverState.SPEAKING,
                            reason="Streaming sentence TTS",
                        )

                    await self.event_bus.publish(TTSStarted(text=sentence_text, provider=provider_used))
                    await self.event_bus.publish(
                        TTSCompleted(
                            text=sentence_text,
                            duration_seconds=tts_res.duration_seconds,
                            latency_ms=tts_res.latency_ms,
                            provider=provider_used,
                        )
                    )

                    if first_audio_playing_time is None:
                        first_audio_playing_time = time.perf_counter()
                        self.last_latency_metrics = {
                            "request_start": t_request_start,
                            "first_sentence_detected": first_sentence_detected_time or now,
                            "first_audio_ready": first_audio_ready_time,
                            "first_audio_playing": first_audio_playing_time,
                            "ttfs_seconds": round((first_sentence_detected_time or now) - t_request_start, 4),
                            "ttfa_seconds": round(first_audio_ready_time - t_request_start, 4),
                            "total_latency_seconds": round(first_audio_playing_time - t_request_start, 4),
                        }
                        logger.info(
                            "Streaming TTS Real Latency: TTFS=%.3fs, TTFA=%.3fs, Total=%.3fs",
                            self.last_latency_metrics["ttfs_seconds"],
                            self.last_latency_metrics["ttfa_seconds"],
                            self.last_latency_metrics["total_latency_seconds"],
                        )

                    await self.event_bus.publish(AudioPlaybackStarted(duration_seconds=tts_res.duration_seconds))
                    played = await self.playback.play_bytes(tts_res.audio_data, format=tts_res.format)
                    if played:
                        await self.event_bus.publish(AudioPlaybackCompleted(duration_seconds=tts_res.duration_seconds))

            await producer_task
            if sentence_count > 0:
                await asyncio.sleep(0.25)
                return True
            return False
        except Exception as exc:
            logger.warning("Streaming TTS playback failed: %s", exc)
            return False
