"""Denver Core Application Orchestrator."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from denver import __version__, assistant_name, product_name
from denver.audio.pipeline import VoicePipeline
from denver.automation.executor import AutomationExecutor
from denver.commands.models import CommandResponse
from denver.commands.service import CommandEngineService
from denver.config.settings import DenverSettings, get_settings
from denver.health.health_service import DenverHealthService
from denver.logging.logger import get_logger, setup_logging
from denver.memory.database import DenverDatabase
from denver.memory.memory_service import MemoryService
from denver.providers.gemini import GeminiProvider
from denver.providers.groq import GroqProvider
from denver.providers.lmstudio import LMStudioProvider
from denver.providers.ollama import OllamaProvider
from denver.providers.registry import ProviderRegistry
from denver.providers.router import ProviderRouter
from denver.runtime.event_bus import DenverEventBus
from denver.runtime.events import ApplicationStarted, ApplicationStopped, ApplicationStopping
from denver.runtime.state_machine import DenverStateMachine
from denver.runtime.states import DenverState
from denver.scheduler.execution_coordinator import RoutineExecutionCoordinator
from denver.scheduler.routine_registry import RoutineRegistry
from denver.scheduler.scheduler import DenverScheduler
from denver.scheduler.trigger_engine import TriggerEngine
from denver.security.vault import DenverVault

logger = get_logger("app")


class DenverApplication:
    """Central lifecycle orchestrator managing Denver foundation subsystems."""

    def __init__(self, settings: DenverSettings | None = None) -> None:
        self.settings: DenverSettings = settings or get_settings()
        self.start_time: float = time.time()

        # Initialize logging first
        setup_logging(
            level=self.settings.log_level,
            log_file=self.settings.log_file_path,
        )

        # Core subsystems
        self.event_bus = DenverEventBus()
        self.state_machine = DenverStateMachine(
            initial_state=DenverState.BOOTING,
            event_bus=self.event_bus,
        )
        self.database = DenverDatabase(db_path=self.settings.database_path)
        self.vault = DenverVault()

        # Seed vault from environment/settings if provided
        if getattr(self.settings, "groq_api_key", None):
            try:
                self.vault.set_secret("GROQ_API_KEY", self.settings.groq_api_key)
            except Exception:
                pass
        if getattr(self.settings, "gemini_api_key", None):
            try:
                self.vault.set_secret("GEMINI_API_KEY", self.settings.gemini_api_key)
            except Exception:
                pass

        # Phase 7 Embedding Provider Resolution
        emb_provider = None
        if self.settings.embedding_provider == "ollama":
            from denver.memory.embeddings import OllamaEmbeddingProvider
            emb_provider = OllamaEmbeddingProvider(
                base_url=self.settings.ollama_base_url,
                model=self.settings.embedding_model,
            )

        self.memory_service = MemoryService(
            db=self.database,
            event_bus=self.event_bus,
            privacy_mode=self.settings.privacy_mode,
            embedding_provider=emb_provider,
            semantic_enabled=self.settings.semantic_memory_enabled and self.settings.memory_enabled,
        )


        # AI Provider subsystem
        self.provider_registry = ProviderRegistry()
        self.provider_registry.register(
            OllamaProvider(
                base_url=self.settings.ollama_base_url,
                default_model=self.settings.ollama_model,
                enabled=self.settings.ollama_enabled,
                timeout_seconds=self.settings.ai_timeout_seconds,
            )
        )
        self.provider_registry.register(
            LMStudioProvider(
                base_url=self.settings.lm_studio_base_url,
                default_model=self.settings.lm_studio_model,
                enabled=self.settings.lm_studio_enabled,
                timeout_seconds=self.settings.ai_timeout_seconds,
            )
        )
        self.provider_registry.register(
            GroqProvider(
                vault=self.vault,
                base_url=self.settings.groq_base_url,
                default_model=self.settings.groq_model,
                enabled=self.settings.groq_enabled,
                timeout_seconds=self.settings.ai_timeout_seconds,
            )
        )
        self.provider_registry.register(
            GeminiProvider(
                vault=self.vault,
                base_url=self.settings.gemini_base_url,
                default_model=self.settings.gemini_model,
                enabled=self.settings.gemini_enabled,
                timeout_seconds=self.settings.ai_timeout_seconds,
            )
        )

        self.provider_router = ProviderRouter(
            registry=self.provider_registry,
            event_bus=self.event_bus,
            priority_order=self.settings.provider_priority,
            local_first=self.settings.ai_local_first,
            cloud_fallback_enabled=self.settings.groq_enabled or self.settings.gemini_enabled,
        )

        # Automation Subsystem
        self.automation_executor = AutomationExecutor(
            event_bus=self.event_bus,
            allow_high_risk_actions=self.settings.allow_high_risk_actions,
        )

        # Phase 8: Scheduler & Routine Subsystem
        self.trigger_engine = TriggerEngine(
            min_interval_seconds=float(self.settings.scheduler_min_interval_seconds)
        )
        self.routine_registry = RoutineRegistry(
            db=self.database,
            trigger_engine=self.trigger_engine,
            event_bus=self.event_bus,
        )

        self.command_service = CommandEngineService(
            memory_service=self.memory_service,
            state_machine=self.state_machine,
            event_bus=self.event_bus,
            settings=self.settings,
            provider_router=self.provider_router,
            automation_executor=self.automation_executor,
            routine_registry=self.routine_registry,
        )

        self.execution_coordinator = RoutineExecutionCoordinator(
            db=self.database,
            action_registry=self.command_service.registry,
            safety_validator=self.command_service.safety,
            automation_executor=self.automation_executor,
            trigger_engine=self.trigger_engine,
            event_bus=self.event_bus,
            max_concurrency=self.settings.scheduler_max_concurrency,
        )
        self.scheduler = DenverScheduler(
            settings=self.settings,
            registry=self.routine_registry,
            coordinator=self.execution_coordinator,
            event_bus=self.event_bus,
            trigger_engine=self.trigger_engine,
        )
        self.command_service.scheduler = self.scheduler

        self.voice_pipeline = VoicePipeline(
            command_service=self.command_service,
            state_machine=self.state_machine,
            event_bus=self.event_bus,
            settings=self.settings,
        )

        # Phase 9: Task & Workflow Orchestration Subsystem
        from denver.tasks.approval import TaskApprovalManager
        from denver.tasks.audit import TaskAuditLogger
        from denver.tasks.persistence import TaskPersistence
        from denver.tasks.plan_validator import PlanValidator
        from denver.tasks.planner import TaskPlanner
        from denver.tasks.task_registry import TaskRegistry
        from denver.tasks.workflow_engine import WorkflowEngine

        self.task_persistence = TaskPersistence(connection_factory=self.database.connect_sync)
        self.task_approval_manager = TaskApprovalManager()
        self.task_audit_logger = TaskAuditLogger(connection_factory=self.database.connect_sync)
        self.task_validator = PlanValidator(
            action_registry=self.command_service.registry,
            safety_validator=self.command_service.safety,
            max_steps=self.settings.task_max_steps,
            max_depth=self.settings.task_max_depth,
        )
        self.task_planner = TaskPlanner(validator=self.task_validator)
        self.workflow_engine = WorkflowEngine(
            action_registry=self.command_service.registry,
            safety_validator=self.command_service.safety,
            automation_executor=self.automation_executor,
            persistence=self.task_persistence,
            approval_manager=self.task_approval_manager,
            audit_logger=self.task_audit_logger,
            event_publisher=lambda evt: asyncio.create_task(self.event_bus.publish(evt)),
            max_concurrency=self.settings.task_max_concurrency,
        )
        self.task_registry = TaskRegistry(
            engine=self.workflow_engine,
            persistence=self.task_persistence,
            planner=self.task_planner,
            validator=self.task_validator,
            approval_manager=self.task_approval_manager,
            audit_logger=self.task_audit_logger,
            enabled=self.settings.tasks_enabled,
            max_concurrent_tasks=self.settings.task_max_concurrency,
        )
        self.command_service.task_registry = self.task_registry
        self.command_service.workflow_engine = self.workflow_engine

        self.health_service = DenverHealthService(
            state_machine=self.state_machine,
            event_bus=self.event_bus,
            database=self.database,
            provider_router=self.provider_router,
            voice_pipeline=self.voice_pipeline,
            automation_executor=self.automation_executor,
            memory_service=self.memory_service,
            scheduler=self.scheduler,
            task_registry=self.task_registry,
            start_time=self.start_time,
        )


        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """Execute Denver startup sequence, initialize database, and transition to STANDBY."""
        logger.info(
            "Starting %s v%s (Environment: %s, AI Mode: %s)...",
            product_name,
            __version__,
            self.settings.environment,
            self.settings.ai_mode,
        )

        # Initialize Database & Migrations
        try:
            await self.database.initialize()
            await self.routine_registry.seed_compound_routines()
        except Exception as exc:
            logger.error("Failed to initialize Denver database: %s", exc)
            await self.state_machine.transition_to(
                DenverState.ERROR,
                reason=f"Database initialization failed: {exc}",
            )
            raise

        # Start voice pipeline if audio enabled
        if self.settings.audio_enabled:
            try:
                await self.voice_pipeline.start()
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("Could not start voice pipeline on startup: %s", exc)

        # Start scheduler if enabled
        if self.settings.scheduler_enabled:
            try:
                await self.scheduler.start()
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("Could not start scheduler on startup: %s", exc)

        # Transition from BOOTING to STANDBY
        await self.state_machine.transition_to(
            DenverState.STANDBY,
            reason="Application startup sequence completed successfully",
        )

        # Publish ApplicationStarted event
        await self.event_bus.publish(
            ApplicationStarted(
                version=__version__,
                environment=self.settings.environment,
            )
        )

        logger.info("%s is online and ready in STANDBY mode.", assistant_name)

    async def process_command(self, command_text: str) -> CommandResponse:
        """Process a text command through the Denver command engine."""
        return await self.command_service.process_command(command_text)

    async def stop(self, reason: str = "normal_exit") -> None:
        """Execute graceful shutdown sequence, close database, and transition to STOPPED."""
        current = self.state_machine.current_state
        if current in {DenverState.SHUTTING_DOWN, DenverState.STOPPED}:
            logger.debug("Already in %s; stop is a no-op.", current)
            return

        logger.info("Initiating graceful shutdown for %s (Reason: '%s')...", product_name, reason)

        # Publish ApplicationStopping event
        await self.event_bus.publish(ApplicationStopping(reason=reason))

        # Transition to SHUTTING_DOWN
        try:
            await self.state_machine.transition_to(
                DenverState.SHUTTING_DOWN,
                reason=reason,
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Error transitioning to SHUTTING_DOWN: %s", exc)

        # Stop voice pipeline safely
        try:
            await self.voice_pipeline.stop()
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Error stopping voice pipeline: %s", exc)

        # Stop scheduler safely
        try:
            await self.scheduler.stop()
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Error stopping scheduler: %s", exc)

        # Stop / pause all active tasks
        if hasattr(self, "task_registry") and self.task_registry:
            try:
                self.task_registry.pause_all_tasks()
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("Error pausing active tasks on shutdown: %s", exc)

        # Close database safely
        try:
            await self.database.close()
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Error closing database: %s", exc)

        uptime = max(0.0, time.time() - self.start_time)

        # Transition to terminal STOPPED state
        try:
            await self.state_machine.transition_to(
                DenverState.STOPPED,
                reason="All subsystems cleanly shut down",
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Error transitioning to STOPPED: %s", exc)

        # Publish ApplicationStopped event
        await self.event_bus.publish(ApplicationStopped(uptime_seconds=uptime))

        # Clean up event bus
        await self.event_bus.shutdown()

        logger.info("%s has cleanly stopped (Total uptime: %.2fs).", product_name, uptime)
        self._shutdown_event.set()

    async def run_forever(self) -> None:
        """Keep the application event loop alive until shutdown is signaled."""
        await self.start()
        try:
            await self._shutdown_event.wait()
        except asyncio.CancelledError:
            logger.debug("Run loop cancelled; shutting down...")
            await self.stop(reason="asyncio_cancellation")
