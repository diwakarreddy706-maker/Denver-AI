"""Plugin Manifest & Permission Validation for Denver AI Assistant."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PermissionDeniedError(Exception):
    """Raised when a plugin attempts to access an unauthorized capability."""


class PluginRiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PluginPermission(str, Enum):
    COMMANDS_REGISTER = "commands.register"
    COMMANDS_EXECUTE = "commands.execute"
    UI_NOTIFY = "ui.notify"
    MEMORY_READ = "memory.read"
    MEMORY_WRITE = "memory.write"
    AUDIO_PLAY = "audio.play"
    NETWORK_REQUEST = "network.request"
    FILESYSTEM_READ = "filesystem.read"
    FILESYSTEM_WRITE = "filesystem.write"
    DESKTOP_AUTOMATION = "desktop.automation"
    PROCESS_SPAWN = "process.spawn"
    
    # Aliases
    AUTOMATION = "automation"
    FILESYSTEM = "filesystem"
    NETWORK = "network"
    AUDIO = "audio"
    UI = "ui"


PERMISSION_RISK_MAP: dict[PluginPermission, PluginRiskLevel] = {
    PluginPermission.COMMANDS_REGISTER: PluginRiskLevel.LOW,
    PluginPermission.UI_NOTIFY: PluginRiskLevel.LOW,
    PluginPermission.UI: PluginRiskLevel.LOW,
    PluginPermission.AUDIO_PLAY: PluginRiskLevel.MEDIUM,
    PluginPermission.AUDIO: PluginRiskLevel.MEDIUM,
    PluginPermission.MEMORY_READ: PluginRiskLevel.MEDIUM,
    PluginPermission.MEMORY_WRITE: PluginRiskLevel.MEDIUM,
    PluginPermission.COMMANDS_EXECUTE: PluginRiskLevel.HIGH,
    PluginPermission.NETWORK_REQUEST: PluginRiskLevel.HIGH,
    PluginPermission.NETWORK: PluginRiskLevel.HIGH,
    PluginPermission.FILESYSTEM_READ: PluginRiskLevel.HIGH,
    PluginPermission.FILESYSTEM: PluginRiskLevel.HIGH,
    PluginPermission.FILESYSTEM_WRITE: PluginRiskLevel.CRITICAL,
    PluginPermission.DESKTOP_AUTOMATION: PluginRiskLevel.CRITICAL,
    PluginPermission.AUTOMATION: PluginRiskLevel.CRITICAL,
    PluginPermission.PROCESS_SPAWN: PluginRiskLevel.CRITICAL,
}


@dataclass
class PluginManifest:
    """Declared metadata and security permissions for an external Denver plugin."""
    id: str
    name: str
    version: str
    author: str = "Community"
    description: str = ""
    entrypoint: str = "main:Plugin"
    permissions: list[PluginPermission] = field(default_factory=list)
    min_denver_version: str = "0.1.0"
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PluginManifest:
        if not data.get("id") or not str(data["id"]).strip():
            raise ValueError("Plugin manifest missing required field: 'id'")
        if not data.get("name") or not str(data["name"]).strip():
            raise ValueError("Plugin manifest missing required field: 'name'")
        if not data.get("version") or not str(data["version"]).strip():
            raise ValueError("Plugin manifest missing required field: 'version'")

        raw_perms = data.get("permissions", [])
        parsed_perms: list[PluginPermission] = []
        for p in raw_perms:
            p_str = str(p).lower().strip()
            # Try matching enum value or alias
            matched = False
            for perm in PluginPermission:
                if perm.value == p_str or perm.name.lower() == p_str:
                    parsed_perms.append(perm)
                    matched = True
                    break
            if not matched:
                try:
                    parsed_perms.append(PluginPermission(p_str))
                except ValueError:
                    pass  # Ignore unknown permission

        return cls(
            id=str(data["id"]).strip().lower(),
            name=str(data["name"]).strip(),
            version=str(data["version"]).strip(),
            author=str(data.get("author", "Community")).strip(),
            description=str(data.get("description", "")).strip(),
            entrypoint=str(data.get("entrypoint", "main:Plugin")).strip(),
            permissions=parsed_perms,
            min_denver_version=str(data.get("min_denver_version", "0.1.0")).strip(),
            enabled=bool(data.get("enabled", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "entrypoint": self.entrypoint,
            "permissions": [p.value for p in self.permissions],
            "min_denver_version": self.min_denver_version,
            "enabled": self.enabled,
        }

    def max_risk_level(self) -> PluginRiskLevel:
        """Evaluate highest risk level among requested permissions."""
        highest = PluginRiskLevel.LOW
        order = [PluginRiskLevel.LOW, PluginRiskLevel.MEDIUM, PluginRiskLevel.HIGH, PluginRiskLevel.CRITICAL]
        for p in self.permissions:
            risk = PERMISSION_RISK_MAP.get(p, PluginRiskLevel.MEDIUM)
            if order.index(risk) > order.index(highest):
                highest = risk
        return highest
