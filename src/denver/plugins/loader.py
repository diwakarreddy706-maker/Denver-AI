"""Plugin Discovery, Manifest Loading, State Management, and Lifecycle Manager for Denver AI Assistant."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

from denver.logging.logger import get_logger
from denver.plugins.base import BasePlugin, PluginContext
from denver.plugins.manifest import PluginManifest, PluginRiskLevel

logger = get_logger("plugins.loader")


class PluginRegistry:
    """Maintains active loaded plugins, state management, and routes extension commands."""

    def __init__(
        self,
        plugins_dir: str | Path = "plugins",
        data_dir: str | Path = "data/plugins",
        state_file: str | Path = "data/plugin_state.json",
    ) -> None:
        self.plugins_dir = Path(plugins_dir)
        self.data_dir = Path(data_dir)
        self.state_file = Path(state_file)
        self._plugins: dict[str, BasePlugin] = {}
        self._manifests: dict[str, PluginManifest] = {}
        self._states: dict[str, bool] = self._load_states()

    @property
    def loaded_plugins(self) -> dict[str, BasePlugin]:
        return self._plugins

    @property
    def manifests(self) -> dict[str, PluginManifest]:
        return self._manifests

    def _load_states(self) -> dict[str, bool]:
        """Load persistent enabled/disabled states from JSON file."""
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return {str(k).lower(): bool(v) for k, v in data.items()}
            except Exception as exc:
                logger.warning("Could not read plugin state file: %s", exc)
        return {}

    def _save_states(self) -> None:
        """Save persistent enabled/disabled states atomically."""
        try:
            from denver.utils.atomic_write import atomic_write_json
            atomic_write_json(self.state_file, self._states)
        except Exception as exc:
            logger.error("Failed to save plugin states: %s", exc)

    def is_enabled(self, plugin_id: str) -> bool:
        """Check if a plugin is currently enabled."""
        p_id = plugin_id.lower().strip()
        if p_id in self._states:
            return self._states[p_id]
        if p_id in self._manifests:
            return self._manifests[p_id].enabled
        return True

    def enable_plugin(self, plugin_id: str) -> bool:
        """Enable a plugin and invoke its on_enable hook."""
        p_id = plugin_id.lower().strip()
        self._states[p_id] = True
        self._save_states()

        if p_id in self._plugins:
            try:
                self._plugins[p_id].on_enable()
            except Exception as exc:
                logger.error("Error in on_enable for plugin '%s': %s", p_id, exc)
            logger.info("Plugin '%s' enabled.", p_id)
            return True

        # If not yet loaded, discover and load it
        plugin_folder = self.plugins_dir / p_id
        if plugin_folder.exists():
            return self.load_plugin(plugin_folder)
        return False

    def disable_plugin(self, plugin_id: str) -> bool:
        """Disable a plugin and invoke its on_disable hook."""
        p_id = plugin_id.lower().strip()
        self._states[p_id] = False
        self._save_states()

        if p_id in self._plugins:
            try:
                self._plugins[p_id].on_disable()
            except Exception as exc:
                logger.error("Error in on_disable for plugin '%s': %s", p_id, exc)
            logger.info("Plugin '%s' disabled.", p_id)
            return True
        return True

    def discover_and_load_all(self) -> int:
        """Scan plugins directory, validate manifests, and instantiate active plugins."""
        if not self.plugins_dir.exists():
            self.plugins_dir.mkdir(parents=True, exist_ok=True)
            return 0

        loaded_count = 0
        for entry in self.plugins_dir.iterdir():
            if entry.is_dir() and (entry / "manifest.json").exists():
                try:
                    if self.load_plugin(entry):
                        loaded_count += 1
                except Exception as exc:
                    logger.error("Failed to load plugin from directory '%s': %s", entry.name, exc)

        logger.info("Plugin discovery completed: %d plugins successfully active.", loaded_count)
        return loaded_count

    def load_plugin(self, plugin_dir: Path) -> bool:
        """Load a single plugin from a directory containing manifest.json and Python code."""
        manifest_file = plugin_dir / "manifest.json"
        if not manifest_file.exists():
            logger.warning("No manifest.json found in '%s'", plugin_dir)
            return False

        try:
            raw_manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            manifest = PluginManifest.from_dict(raw_manifest)
        except Exception as exc:
            logger.error("Invalid manifest in '%s': %s", plugin_dir, exc)
            return False

        self._manifests[manifest.id] = manifest

        # Check enabled state from persistent state store
        if not self.is_enabled(manifest.id):
            logger.info("Plugin '%s' is disabled by policy/user; not activating.", manifest.id)
            return False

        plugin_data_dir = self.data_dir / manifest.id
        plugin_data_dir.mkdir(parents=True, exist_ok=True)

        context = PluginContext(
            manifest=manifest,
            plugin_dir=plugin_dir,
            data_dir=plugin_data_dir,
            logger=get_logger(f"plugin.{manifest.id}"),
        )

        entry_parts = manifest.entrypoint.split(":")
        module_file_name = entry_parts[0]
        class_name = entry_parts[1] if len(entry_parts) > 1 else "Plugin"

        if not module_file_name.endswith(".py"):
            module_file_name = f"{module_file_name}.py"

        module_path = plugin_dir / module_file_name
        if not module_path.exists():
            logger.error("Plugin entrypoint file '%s' not found for '%s'", module_path, manifest.id)
            return False

        try:
            spec = importlib.util.spec_from_file_location(f"denver_plugin_{manifest.id}", module_path)
            if not spec or not spec.loader:
                logger.error("Could not create import spec for '%s'", module_path)
                return False

            mod = importlib.util.module_from_spec(spec)
            sys.modules[f"denver_plugin_{manifest.id}"] = mod
            spec.loader.exec_module(mod)

            plugin_cls = getattr(mod, class_name, None)
            if not plugin_cls or not issubclass(plugin_cls, BasePlugin):
                logger.error("Plugin class '%s' in '%s' does not inherit from BasePlugin", class_name, module_path)
                return False

            instance = plugin_cls(context=context)
            if not instance.on_load():
                logger.warning("Plugin '%s' on_load returned False; not registering.", manifest.id)
                return False

            self._plugins[manifest.id] = instance
            logger.info("Successfully loaded plugin: %s v%s (%s)", manifest.name, manifest.version, manifest.id)
            return True

        except Exception as exc:
            logger.error("Exception loading plugin '%s': %s", manifest.id, exc)
            return False

    def list_plugins(self) -> list[dict[str, Any]]:
        """Return a structured summary of all discovered plugins and active states."""
        # Ensure discovery has scanned plugins dir
        if self.plugins_dir.exists():
            for entry in self.plugins_dir.iterdir():
                if entry.is_dir() and (entry / "manifest.json").exists() and entry.name.lower() not in self._manifests:
                    try:
                        raw = json.loads((entry / "manifest.json").read_text(encoding="utf-8"))
                        m = PluginManifest.from_dict(raw)
                        self._manifests[m.id] = m
                    except Exception:
                        pass

        summary: list[dict[str, Any]] = []
        for p_id, m in self._manifests.items():
            is_active = p_id in self._plugins and self.is_enabled(p_id)
            summary.append({
                "id": m.id,
                "name": m.name,
                "version": m.version,
                "author": m.author,
                "description": m.description,
                "permissions": [p.value for p in m.permissions],
                "max_risk": m.max_risk_level().value,
                "enabled": self.is_enabled(p_id),
                "loaded": is_active,
            })
        return summary

    def dispatch_command(self, text: str) -> str | None:
        """Route user utterance through all active and enabled plugins."""
        import re
        norm_text = text.strip()
        for plugin_id, plugin in self._plugins.items():
            if not self.is_enabled(plugin_id):
                continue
            
            # 1. Check registered command patterns
            if hasattr(plugin, "context") and hasattr(plugin.context, "_registered_commands"):
                for pattern, handler in plugin.context._registered_commands.items():
                    matched = False
                    if pattern.lower() in norm_text.lower():
                        matched = True
                    else:
                        try:
                            if re.search(pattern, norm_text, re.IGNORECASE):
                                matched = True
                        except Exception:
                            pass
                    if matched:
                        try:
                            res = handler(norm_text)
                            if res and isinstance(res, str) and res.strip():
                                logger.info("Plugin '%s' handled pattern '%s' for utterance: '%s'", plugin_id, pattern, norm_text)
                                return res.strip()
                        except Exception as exc:
                            logger.error("Error in handler for pattern '%s' in plugin '%s': %s", pattern, plugin_id, exc)

            # 2. General on_command fallback
            try:
                res = plugin.on_command(norm_text)
                if res and isinstance(res, str) and res.strip():
                    logger.info("Plugin '%s' handled command utterance: '%s'", plugin_id, norm_text)
                    return res.strip()
            except Exception as exc:
                logger.error("Error executing on_command in plugin '%s': %s", plugin_id, exc)
        return None

    def reload_all(self) -> int:
        """Unload and reload all plugins."""
        self.unload_all()
        return self.discover_and_load_all()

    def unload_all(self) -> None:
        """Unload and clean up all loaded plugins."""
        for plugin_id, plugin in list(self._plugins.items()):
            try:
                plugin.on_unload()
            except Exception as exc:
                logger.error("Error in on_unload for plugin '%s': %s", plugin_id, exc)
        self._plugins.clear()
        self._manifests.clear()
