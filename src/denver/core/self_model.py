"""Denver Self-Model: Introspection, Runtime State Modeling, and Failure Diagnostics."""

from __future__ import annotations

import platform
from typing import Any

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False

from denver.commands.models import CommandCategory
from denver.commands.registry import ActionRegistry
from denver.config.settings import DenverSettings, get_settings
from denver.logging.logger import get_logger
from denver.plugins.loader import PluginRegistry
from denver.providers.router import ProviderRouter
from denver.runtime.state_machine import DenverStateMachine

logger = get_logger("core.self_model")


class DenverSelfModel:
    """Maintains an authoritative runtime self-model of Denver's active state, capabilities, and health."""

    def __init__(
        self,
        settings: DenverSettings | None = None,
        action_registry: ActionRegistry | None = None,
        provider_router: ProviderRouter | None = None,
        plugin_registry: PluginRegistry | None = None,
        state_machine: DenverStateMachine | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.action_registry = action_registry
        self.provider_router = provider_router
        self.plugin_registry = plugin_registry
        self.state_machine = state_machine

    def get_system_telemetry(self) -> dict[str, Any]:
        """Collect instantaneous hardware resource utilization."""
        telemetry: dict[str, Any] = {
            "os": f"{platform.system()} {platform.release()}",
            "cpu_percent": None,
            "ram_percent": None,
            "battery_percent": None,
            "power_plugged": None,
        }
        if _PSUTIL_AVAILABLE:
            try:
                telemetry["cpu_percent"] = psutil.cpu_percent(interval=None)
                mem = psutil.virtual_memory()
                telemetry["ram_percent"] = round(mem.percent, 1)
                battery = psutil.sensors_battery()
                if battery:
                    telemetry["battery_percent"] = round(battery.percent, 1)
                    telemetry["power_plugged"] = battery.power_plugged
            except Exception as exc:
                logger.debug("Telemetry collection warning: %s", exc)
        return telemetry

    def get_capabilities_manifest(self) -> dict[str, Any]:
        """Aggregate structured catalog of all registered actions, plugins, and provider settings."""
        actions_by_cat: dict[str, list[str]] = {}
        total_actions = 0

        if self.action_registry:
            for cat in CommandCategory:
                matching = [a.name for a in self.action_registry.list_actions(category=cat) if a.enabled]
                if matching:
                    actions_by_cat[cat.value] = matching
                    total_actions += len(matching)

        active_plugins: list[str] = []
        if self.plugin_registry:
            active_plugins = [
                name for name, p in self.plugin_registry.loaded_plugins.items()
                if getattr(p, "is_enabled", True)
            ]

        active_provider_name = "unknown"
        active_model_name = "unknown"
        air_gapped = getattr(self.settings, "air_gapped_mode", False)

        if self.provider_router:
            active_provider_name = getattr(self.provider_router, "active_provider", self.settings.active_llm_provider)
            air_gapped = getattr(self.provider_router, "air_gapped_mode", air_gapped)
            prov = self.provider_router.registry.get_provider(active_provider_name)
            if prov:
                active_model_name = getattr(prov, "default_model", "unknown")
        else:
            active_provider_name = self.settings.active_llm_provider
            if active_provider_name == "groq":
                active_model_name = self.settings.groq_model
            elif active_provider_name == "gemini":
                active_model_name = self.settings.gemini_model
            elif active_provider_name == "ollama":
                active_model_name = self.settings.ollama_model

        current_state = "STANDBY"
        if self.state_machine and hasattr(self.state_machine, "current_state"):
            current_state = getattr(self.state_machine.current_state, "value", str(self.state_machine.current_state))

        return {
            "assistant_name": self.settings.assistant_name,
            "version": "1.0.0",
            "runtime_state": current_state,
            "active_provider": active_provider_name,
            "active_model": active_model_name,
            "air_gapped_mode": air_gapped,
            "cloud_fallback_enabled": getattr(self.settings, "cloud_fallback_enabled", False),
            "total_registered_actions": total_actions,
            "actions_by_category": actions_by_cat,
            "active_plugins": active_plugins,
            "safety_policies": {
                "allow_destructive_actions": getattr(self.settings, "allow_destructive_actions", False),
                "allow_high_risk_actions": getattr(self.settings, "allow_high_risk_actions", False),
                "screen_cloud_disclosure_acknowledged": getattr(self.settings, "screen_cloud_disclosure_acknowledged", False),
            },
            "telemetry": self.get_system_telemetry(),
        }

    def get_self_state_summary(self) -> str:
        """Construct a compact, token-efficient system context block for LLM prompt injection."""
        manifest = self.get_capabilities_manifest()
        telem = manifest["telemetry"]

        hw_parts = []
        if telem["cpu_percent"] is not None:
            hw_parts.append(f"CPU {telem['cpu_percent']}%")
        if telem["ram_percent"] is not None:
            hw_parts.append(f"RAM {telem['ram_percent']}%")
        if telem["battery_percent"] is not None:
            power_str = "AC" if telem["power_plugged"] else "Batt"
            hw_parts.append(f"Battery {telem['battery_percent']}% ({power_str})")
        hw_str = ", ".join(hw_parts) if hw_parts else "Nominal"

        air_gapped_str = "ON (Local Models Only)" if manifest["air_gapped_mode"] else "OFF"
        plugins_str = ", ".join(manifest["active_plugins"]) if manifest["active_plugins"] else "None"

        return (
            "[DENVER RUNTIME SELF-STATE]\n"
            f"- Identity: {manifest['assistant_name']} on {telem['os']}\n"
            f"- Active AI Provider: {manifest['active_provider']} (Model: {manifest['active_model']})\n"
            f"- Air-Gapped Mode: {air_gapped_str}\n"
            f"- Capabilities: {manifest['total_registered_actions']} registered actions across {len(manifest['actions_by_category'])} categories\n"
            f"- Active Plugins: {plugins_str}\n"
            f"- System Health: {hw_str}\n"
            "- Core Rule: When user asks what you can do, what model you use, or your status, answer accurately using these facts."
        )

    def format_capabilities_speech(self, category: str | None = None) -> str:
        """Produce a clean, conversational speech string describing Denver's active capabilities."""
        manifest = self.get_capabilities_manifest()
        cat_key = category.strip().lower() if category else None

        if cat_key and cat_key in manifest["actions_by_category"]:
            actions = manifest["actions_by_category"][cat_key]
            actions_list = ", ".join([a.replace("_", " ") for a in actions[:6]])
            return f"In the {cat_key} category, I can perform {len(actions)} actions including {actions_list}."

        total = manifest["total_registered_actions"]
        active_prov = str(manifest["active_provider"]).capitalize()
        model = manifest["active_model"]

        return (
            f"I have {total} registered actions available across system control, applications, "
            f"notes and memory, and desktop automation. I am currently running on {active_prov} "
            f"using the {model} model."
        )

    def diagnose_failure(self, action_name: str, error: str, category: str = "") -> str:
        """Provide a structured, human-understandable failure diagnostic and remediation advice."""
        err_lower = (error or "").lower()

        if "actionnotfound" in err_lower or "not recognized" in err_lower or "unknown" in err_lower:
            return (
                f"Action '{action_name}' is not recognized or registered in my system. "
                "You can ask 'what can you do' to see all supported actions."
            )

        if "safetyblocked" in err_lower or "destructive" in err_lower or "blocked" in err_lower:
            return (
                f"Action '{action_name}' was blocked by my Safety Validator. "
                "This action involves potentially destructive system modifications and is prohibited by current policy."
            )

        if "404" in err_lower or "not found" in err_lower:
            return (
                f"The AI model or resource required for '{action_name}' was not found. "
                "Please verify that the active provider model is currently supported."
            )

        if any(term in err_lower for term in ["connection", "unreachable", "refused", "timeout", "timed out"]):
            return (
                f"Unable to connect to the required service for '{action_name}'. "
                "Please check your network connection or ensure the local AI provider service is active."
            )

        if any(term in err_lower for term in ["permission", "access denied", "unauthorized"]):
            return (
                f"Permission was denied while executing '{action_name}'. "
                "Denver requires elevated Windows user permissions for this operation."
            )

        return f"Action '{action_name}' encountered an error: {error}. I have safely halted execution."
