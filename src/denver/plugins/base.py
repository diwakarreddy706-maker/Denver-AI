"""Base Plugin interfaces and restricted execution context for Denver extensions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from denver.logging.logger import get_logger
from denver.plugins.manifest import PermissionDeniedError, PluginManifest, PluginPermission


@dataclass
class PluginContext:
    """Restricted execution context exposed to third-party plugins with permission gating."""
    manifest: PluginManifest
    plugin_dir: Path
    data_dir: Path
    logger: Any
    _registered_commands: dict[str, Callable[[str], str | None]] = field(default_factory=dict)
    notifications: list[dict[str, str]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)

    def has_permission(self, permission: PluginPermission | str) -> bool:
        """Check if this plugin was granted a specific permission."""
        if isinstance(permission, str):
            for p in self.manifest.permissions:
                if p.value == permission or p.name.lower() == permission.lower():
                    return True
            return False
        return permission in self.manifest.permissions

    def require_permission(self, permission: PluginPermission | str) -> None:
        """Raise PermissionDeniedError if the plugin lacks the requested permission."""
        if not self.has_permission(permission):
            perm_name = permission.value if isinstance(permission, PluginPermission) else str(permission)
            raise PermissionDeniedError(
                f"Plugin '{self.manifest.id}' attempted to access capability requiring permission '{perm_name}' which is not declared in manifest.json"
            )

    def register_command_pattern(self, pattern: str, handler: Callable[[str], str | None]) -> None:
        """Register a regex or trigger phrase pattern for custom plugin voice handling."""
        self.require_permission(PluginPermission.COMMANDS_REGISTER)
        self._registered_commands[pattern] = handler
        self.logger.info("Plugin '%s' registered command pattern: '%s'", self.manifest.id, pattern)

    def notify(self, message: str, level: str = "info") -> dict[str, str]:
        """Post a notification or status update to Denver event bus / UI."""
        self.require_permission(PluginPermission.UI_NOTIFY)
        notif = {"plugin_id": self.manifest.id, "level": level, "message": str(message)}
        self.notifications.append(notif)
        self.logger.info("[Plugin Notification][%s] %s: %s", level.upper(), self.manifest.name, message)
        return notif

    def emit_event(self, event_type: str, detail: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Record a safe plugin diagnostic or telemetry event."""
        event = {
            "plugin_id": self.manifest.id,
            "event_type": str(event_type),
            "detail": str(detail),
            "context": context or {},
        }
        self.events.append(event)
        return event

    def read_data_file(self, filename: str) -> str:
        """Read a file safely from the plugin's isolated data directory."""
        self.require_permission(PluginPermission.FILESYSTEM_READ)
        target = (self.data_dir / filename).resolve()
        if not str(target).startswith(str(self.data_dir.resolve())):
            raise PermissionDeniedError("Path traversal escape outside plugin data directory is prohibited.")
        if not target.exists():
            return ""
        return target.read_text(encoding="utf-8")

    def write_data_file(self, filename: str, content: str) -> None:
        """Write a file safely into the plugin's isolated data directory."""
        self.require_permission(PluginPermission.FILESYSTEM_WRITE)
        target = (self.data_dir / filename).resolve()
        if not str(target).startswith(str(self.data_dir.resolve())):
            raise PermissionDeniedError("Path traversal escape outside plugin data directory is prohibited.")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def request_memory_read(self, scope: str = "default") -> dict[str, Any]:
        """Safely query memory scope with permission validation."""
        self.require_permission(PluginPermission.MEMORY_READ)
        return {"status": "ok", "scope": scope, "data": {}}

    def request_memory_write(self, scope: str, value: Any) -> dict[str, Any]:
        """Safely write to memory scope with permission validation."""
        self.require_permission(PluginPermission.MEMORY_WRITE)
        return {"status": "ok", "scope": scope, "saved": True}

    def request_network(self, url: str, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Network request facade with permission validation."""
        self.require_permission(PluginPermission.NETWORK_REQUEST)
        return {"status": "ok", "url": url, "method": method}

    def request_audio_play(self, sound_name: str) -> dict[str, Any]:
        """Request audio playback with permission validation."""
        self.require_permission(PluginPermission.AUDIO_PLAY)
        return {"status": "ok", "sound": sound_name}


class BasePlugin(ABC):
    """Abstract Base Class that all Denver plugins must inherit from."""

    def __init__(self, context: PluginContext) -> None:
        self.context = context
        self.logger = context.logger

    def on_load(self) -> bool:
        """Invoked when the plugin is loaded during application startup."""
        return True

    def on_enable(self) -> None:
        """Invoked when the plugin is enabled dynamically."""
        pass

    def on_disable(self) -> None:
        """Invoked when the plugin is disabled dynamically."""
        pass

    def on_command(self, command_text: str) -> str | None:
        """Invoked when a user utterance is processed. Return a response string or None if unhandled."""
        return None

    def on_unload(self) -> None:
        """Invoked during application shutdown to release resources."""
        pass
