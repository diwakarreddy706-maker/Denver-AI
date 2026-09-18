"""Denver Health Monitoring and Diagnostics Service."""

from __future__ import annotations

import os
import platform
import sys
import time
from pathlib import Path
from typing import Any, Mapping

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False

from denver import __version__, assistant_name, product_name
from denver.logging.logger import get_logger
from denver.memory.database import DenverDatabase
from denver.providers.router import ProviderRouter
from denver.runtime.event_bus import DenverEventBus
from denver.runtime.state_machine import DenverStateMachine
from denver.runtime.states import DenverState

logger = get_logger("health")


class DenverHealthService:
    """Provides system telemetry, runtime status, and subsystem health reports."""

    def __init__(
        self,
        state_machine: DenverStateMachine | None = None,
        event_bus: DenverEventBus | None = None,
        database: DenverDatabase | None = None,
        provider_router: ProviderRouter | None = None,
        voice_pipeline: Any | None = None,
        automation_executor: Any | None = None,
        memory_service: Any | None = None,
        scheduler: Any | None = None,
        task_registry: Any | None = None,
        start_time: float | None = None,
    ) -> None:
        self._state_machine = state_machine
        self._event_bus = event_bus
        self._database = database
        self._provider_router = provider_router
        self._voice_pipeline = voice_pipeline
        self._automation_executor = automation_executor
        self._memory_service = memory_service
        self._scheduler = scheduler
        self._task_registry = task_registry
        self._start_time = start_time or time.time()


    @property
    def uptime_seconds(self) -> float:
        """Elapsed uptime in seconds since instantiation."""
        return max(0.0, time.time() - self._start_time)

    def _get_cpu_telemetry(self) -> dict[str, Any]:
        if not _PSUTIL_AVAILABLE:
            return {"usage_percent": None, "cores": os.cpu_count() if hasattr(os, "cpu_count") else None}
        try:
            return {
                "usage_percent": psutil.cpu_percent(interval=None),
                "physical_cores": psutil.cpu_count(logical=False),
                "logical_cores": psutil.cpu_count(logical=True),
            }
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("Failed to read CPU telemetry: %s", exc)
            return {"usage_percent": None, "error": str(exc)}

    def _get_memory_telemetry(self) -> dict[str, Any]:
        if not _PSUTIL_AVAILABLE:
            return {"usage_percent": None}
        try:
            vm = psutil.virtual_memory()
            return {
                "usage_percent": vm.percent,
                "used_gb": round(vm.used / (1024**3), 2),
                "total_gb": round(vm.total / (1024**3), 2),
            }
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("Failed to read memory telemetry: %s", exc)
            return {"usage_percent": None, "error": str(exc)}

    def get_subsystems_status(self) -> dict[str, str]:
        """Expose status of all subsystems, strictly reflecting real database, provider, and automation status."""
        db_status = "NOT_CONFIGURED"
        if self._database is not None:
            db_health = self._database.get_health_status()
            db_status = db_health.get("status", "ERROR")

        ai_status = "NOT_CONFIGURED"
        if self._provider_router is not None:
            router_health = self._provider_router.get_health_status()
            ai_status = router_health.get("status", "NOT_CONFIGURED")

        audio_status = "NOT_CONFIGURED"
        if self._voice_pipeline is not None:
            audio_diag = self._voice_pipeline.get_status()
            audio_status = audio_diag.status

        automation_status = "NOT_CONFIGURED"
        if self._automation_executor is not None:
            auto_health = self._automation_executor.get_health_status()
            automation_status = auto_health.get("status", "READY")

        ui_status = "NOT_IMPLEMENTED"
        if getattr(self, "_ui", None) is not None:
            ui_status = "READY"

        memory_status = "NOT_CONFIGURED"
        if self._memory_service is not None:
            memory_status = "READY"

        scheduler_status = "NOT_CONFIGURED"
        if self._scheduler is not None:
            if not getattr(self._scheduler, "is_enabled", True):
                scheduler_status = "DISABLED"
            elif getattr(self._scheduler, "is_paused", False):
                scheduler_status = "PAUSED"
            elif getattr(self._scheduler, "is_running", False):
                scheduler_status = "READY"
            else:
                scheduler_status = "STOPPED"

        task_status = "NOT_CONFIGURED"
        if self._task_registry is not None:
            if not getattr(self._task_registry, "enabled", True):
                task_status = "DISABLED"
            elif getattr(self._task_registry, "is_global_paused", False):
                task_status = "PAUSED"
            else:
                task_status = "READY"

        return {
            "core_runtime": "READY" if (self._state_machine and self._state_machine.current_state != DenverState.ERROR) else "ERROR",
            "event_bus": "READY" if (self._event_bus and self._event_bus.is_running) else "STOPPED",
            "database": db_status,
            "memory": memory_status,
            "audio": audio_status,
            "ai_providers": ai_status,
            "automation": automation_status,
            "scheduler": scheduler_status,
            "task_orchestration": task_status,
            "plugins": "NOT_IMPLEMENTED",
            "ui": ui_status,
        }

    def get_health_report(self) -> dict[str, Any]:
        """Generate a complete structured health report for Denver AI Assistant."""
        current_state = self._state_machine.current_state if self._state_machine else DenverState.BOOTING

        overall_status = "HEALTHY"
        if current_state == DenverState.ERROR:
            overall_status = "DEGRADED"
        elif current_state == DenverState.STOPPED:
            overall_status = "STOPPED"

        uptime = self.uptime_seconds
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)
        seconds = int(uptime % 60)
        formatted_uptime = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        report: dict[str, Any] = {
            "product": product_name,
            "assistant": assistant_name,
            "version": __version__,
            "status": overall_status,
            "current_state": current_state.value,
            "uptime_seconds": round(uptime, 2),
            "uptime_formatted": formatted_uptime,
            "system_info": {
                "os": platform.system(),
                "os_release": platform.release(),
                "os_version": platform.version(),
                "platform": platform.platform(),
                "python_version": sys.version.split()[0],
                "python_executable": sys.executable,
            },
            "telemetry": {
                "cpu": self._get_cpu_telemetry(),
                "memory": self._get_memory_telemetry(),
            },
            "event_bus": {
                "is_running": self._event_bus.is_running if self._event_bus else False,
                "events_published": self._event_bus.published_count if self._event_bus else 0,
            },
            "subsystems": self.get_subsystems_status(),
        }

        if self._database is not None:
            report["database"] = self._database.get_health_status()

        if self._memory_service is not None:
            mem_count = 0
            notes_count = 0
            tasks_count = 0
            try:
                conn = getattr(self._memory_service.db, "_connection", None)
                if conn is not None:
                    c1 = conn.execute("SELECT count(*) FROM memory_items WHERE is_deleted = 0;").fetchone()
                    mem_count = c1[0] if c1 else 0
                    c2 = conn.execute("SELECT count(*) FROM notes WHERE is_deleted = 0;").fetchone()
                    notes_count = c2[0] if c2 else 0
                    c3 = conn.execute("SELECT count(*) FROM tasks WHERE is_deleted = 0;").fetchone()
                    tasks_count = c3[0] if c3 else 0
            except Exception:
                pass

            report["memory"] = {
                "status": "READY",
                "privacy_mode": self._memory_service.privacy_mode,
                "semantic_enabled": getattr(self._memory_service.embedding_manager, "enabled", False),
                "embedding_provider": getattr(self._memory_service.embedding_manager.fallback, "name", "lexical"),
                "memories_count": mem_count,
                "notes_count": notes_count,
                "tasks_count": tasks_count,
            }

        if self._provider_router is not None:
            report["ai_providers"] = self._provider_router.get_health_status()

        if self._voice_pipeline is not None:
            status_obj = self._voice_pipeline.get_status()
            report["audio"] = {
                "status": status_obj.status,
                "capture_active": status_obj.capture_active,
                "vad_active": status_obj.vad_active,
                "wakeword_active": status_obj.wakeword_active,
                "stt_active": status_obj.stt_active,
                "tts_active": status_obj.tts_active,
                "playback_active": status_obj.playback_active,
                "devices": status_obj.devices,
                "components": status_obj.components,
            }

        if self._automation_executor is not None:
            report["automation"] = self._automation_executor.get_health_status()

        if self._scheduler is not None:
            report["scheduler"] = {
                "enabled": getattr(self._scheduler, "is_enabled", False),
                "running": getattr(self._scheduler, "is_running", False),
                "paused": getattr(self._scheduler, "is_paused", False),
            }

        return report

    def export_safe_diagnostics(self, target_path: str | Path | None = None) -> dict[str, Any]:
        """Produce a comprehensive, zero-secret sanitized diagnostic bundle."""
        import json
        from denver.config.settings import get_settings
        from denver.security.vault import get_vault

        settings = get_settings()
        vault = get_vault()

        bundle: dict[str, Any] = {
            "product": product_name,
            "assistant": assistant_name,
            "version": __version__,
            "timestamp": time.time(),
            "uptime_seconds": round(self.uptime_seconds, 2),
            "system_telemetry": {
                "cpu": self._get_cpu_telemetry(),
                "memory": self._get_memory_telemetry(),
            },
            "subsystems": self.get_health_report(),
            "configuration": settings.to_safe_dict(),
            "secret_status": {
                "GROQ_API_KEY": "configured" if vault.get_secret("GROQ_API_KEY") or settings.groq_api_key else "missing",
                "GEMINI_API_KEY": "configured" if vault.get_secret("GEMINI_API_KEY") or settings.gemini_api_key else "missing",
                "SPOTIFY_CLIENT_SECRET": "configured" if vault.get_secret("SPOTIFY_CLIENT_SECRET") or settings.spotify_client_secret else "missing",
                "GOOGLE_MAPS_API_KEY": "configured" if vault.get_secret("GOOGLE_MAPS_API_KEY") or settings.google_maps_api_key else "missing",
            },
        }

        if target_path:
            p = Path(target_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
            logger.info("Exported safe diagnostic report to %s", p)

        return bundle
