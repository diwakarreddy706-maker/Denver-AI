"""Unit tests for Denver Plugin System, Security Sandboxing, and State Management."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from denver.commands.router import IntentRouter
from denver.plugins.base import BasePlugin, PluginContext
from denver.plugins.loader import PluginRegistry
from denver.plugins.manifest import (
    PERMISSION_RISK_MAP,
    PermissionDeniedError,
    PluginManifest,
    PluginPermission,
    PluginRiskLevel,
)


def test_plugin_manifest_parsing_and_risks() -> None:
    data = {
        "id": "sample_tool",
        "name": "Sample Productivity Tool",
        "version": "1.0.0",
        "author": "Denver Community",
        "description": "A demo extension",
        "entrypoint": "plugin:SamplePlugin",
        "permissions": ["commands.register", "desktop.automation"],
        "enabled": True,
    }

    manifest = PluginManifest.from_dict(data)
    assert manifest.id == "sample_tool"
    assert manifest.name == "Sample Productivity Tool"
    assert manifest.version == "1.0.0"
    assert PluginPermission.COMMANDS_REGISTER in manifest.permissions
    assert PluginPermission.DESKTOP_AUTOMATION in manifest.permissions
    assert manifest.max_risk_level() == PluginRiskLevel.CRITICAL


def test_plugin_context_permission_gating(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    plugin_dir = tmp_path / "plugin"
    data_dir.mkdir()
    plugin_dir.mkdir()

    manifest = PluginManifest(
        id="safe_plugin",
        name="Safe Plugin",
        version="1.0.0",
        permissions=[PluginPermission.COMMANDS_REGISTER, PluginPermission.FILESYSTEM_READ],
    )

    ctx = PluginContext(
        manifest=manifest,
        plugin_dir=plugin_dir,
        data_dir=data_dir,
        logger=MagicMock(),
    )

    assert ctx.has_permission(PluginPermission.COMMANDS_REGISTER)
    assert ctx.has_permission(PluginPermission.FILESYSTEM_READ)
    assert not ctx.has_permission(PluginPermission.FILESYSTEM_WRITE)

    # Allowed require_permission
    ctx.require_permission(PluginPermission.COMMANDS_REGISTER)

    # Denied require_permission
    with pytest.raises(PermissionDeniedError, match="not declared in manifest.json"):
        ctx.require_permission(PluginPermission.FILESYSTEM_WRITE)


def test_plugin_safe_filesystem_and_traversal_rejection(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    plugin_dir = tmp_path / "plugin"
    data_dir.mkdir()
    plugin_dir.mkdir()

    manifest = PluginManifest(
        id="fs_plugin",
        name="FS Plugin",
        version="1.0.0",
        permissions=[PluginPermission.FILESYSTEM_READ, PluginPermission.FILESYSTEM_WRITE],
    )

    ctx = PluginContext(
        manifest=manifest,
        plugin_dir=plugin_dir,
        data_dir=data_dir,
        logger=MagicMock(),
    )

    # Write & read valid file
    ctx.write_data_file("config.json", '{"key": "value"}')
    content = ctx.read_data_file("config.json")
    assert content == '{"key": "value"}'

    # Reject path traversal
    with pytest.raises(PermissionDeniedError, match="Path traversal escape"):
        ctx.write_data_file("../../../evil.txt", "attack")


def test_plugin_enable_disable_state_persistence(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    data_dir = tmp_path / "data" / "plugins"
    state_file = tmp_path / "data" / "plugin_state.json"
    plugins_dir.mkdir(parents=True)

    my_plugin_dir = plugins_dir / "math_bot"
    my_plugin_dir.mkdir()

    manifest_data = {
        "id": "math_bot",
        "name": "Math Helper",
        "version": "1.0.0",
        "entrypoint": "plugin:MathPlugin",
        "permissions": ["commands.register"],
        "enabled": True,
    }
    (my_plugin_dir / "manifest.json").write_text(json.dumps(manifest_data), encoding="utf-8")

    code = """
from denver.plugins.base import BasePlugin

class MathPlugin(BasePlugin):
    def on_load(self) -> bool:
        return True

    def on_command(self, command_text: str) -> str | None:
        if command_text.startswith("calc "):
            return f"Calculated: {command_text[5:]}"
        return None
"""
    (my_plugin_dir / "plugin.py").write_text(code, encoding="utf-8")

    registry = PluginRegistry(plugins_dir=plugins_dir, data_dir=data_dir, state_file=state_file)
    registry.discover_and_load_all()

    assert registry.is_enabled("math_bot")
    assert registry.dispatch_command("calc 5 + 5") == "Calculated: 5 + 5"

    # Disable plugin
    registry.disable_plugin("math_bot")
    assert not registry.is_enabled("math_bot")
    assert registry.dispatch_command("calc 5 + 5") is None

    # Re-enable plugin
    registry.enable_plugin("math_bot")
    assert registry.is_enabled("math_bot")
    assert registry.dispatch_command("calc 5 + 5") == "Calculated: 5 + 5"


def test_intent_router_plugin_voice_intents() -> None:
    router = IntentRouter()

    # list plugins
    res1 = router.route("list plugins")
    assert res1.intent_name == "list_plugins"

    res2 = router.route("show installed plugins")
    assert res2.intent_name == "list_plugins"

    # enable plugin
    res3 = router.route("enable plugin weather_pro")
    assert res3.intent_name == "enable_plugin"
    assert res3.params.get("plugin_id") == "weather_pro"

    # disable plugin
    res4 = router.route("disable plugin echo_bot")
    assert res4.intent_name == "disable_plugin"
    assert res4.params.get("plugin_id") == "echo_bot"

    # reload plugins
    res5 = router.route("reload plugins")
    assert res5.intent_name == "reload_plugins"


def test_plugin_context_advanced_methods_and_events(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    plugin_dir = tmp_path / "plugin"
    data_dir.mkdir()
    plugin_dir.mkdir()

    manifest = PluginManifest(
        id="full_plugin",
        name="Full Feature Plugin",
        version="1.0.0",
        permissions=[
            PluginPermission.UI_NOTIFY,
            PluginPermission.MEMORY_READ,
            PluginPermission.MEMORY_WRITE,
            PluginPermission.NETWORK_REQUEST,
            PluginPermission.AUDIO_PLAY,
        ],
    )

    ctx = PluginContext(
        manifest=manifest,
        plugin_dir=plugin_dir,
        data_dir=data_dir,
        logger=MagicMock(),
    )

    # Notifications & Events
    notif = ctx.notify("Hello from plugin!", level="info")
    assert notif["message"] == "Hello from plugin!"
    assert len(ctx.notifications) == 1

    event = ctx.emit_event("sync_completed", "Synced 10 items", {"count": 10})
    assert event["event_type"] == "sync_completed"
    assert len(ctx.events) == 1

    # Permitted facade calls
    mem_read = ctx.request_memory_read("user_preferences")
    assert mem_read["status"] == "ok"

    mem_write = ctx.request_memory_write("user_preferences", {"theme": "dark"})
    assert mem_write["status"] == "ok"

    net_req = ctx.request_network("https://api.example.com", method="GET")
    assert net_req["status"] == "ok"

    audio_res = ctx.request_audio_play("chime.wav")
    assert audio_res["status"] == "ok"

    # Blocked call
    with pytest.raises(PermissionDeniedError):
        ctx.write_data_file("secret.txt", "data")


def test_plugin_pattern_registration_and_dispatch(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    data_dir = tmp_path / "data" / "plugins"
    state_file = tmp_path / "data" / "plugin_state.json"
    plugins_dir.mkdir(parents=True)

    bot_dir = plugins_dir / "pattern_bot"
    bot_dir.mkdir()

    manifest_data = {
        "id": "pattern_bot",
        "name": "Pattern Matcher Bot",
        "version": "1.0.0",
        "entrypoint": "plugin:PatternPlugin",
        "permissions": ["commands.register"],
        "enabled": True,
    }
    (bot_dir / "manifest.json").write_text(json.dumps(manifest_data), encoding="utf-8")

    code = """
from denver.plugins.base import BasePlugin

class PatternPlugin(BasePlugin):
    def on_load(self) -> bool:
        self.context.register_command_pattern(r"crypto price of (\\w+)", self.handle_crypto)
        self.context.register_command_pattern("joke time", lambda text: "Why did the AI cross the road? To optimize the path!")
        return True

    def handle_crypto(self, text: str) -> str:
        return "Bitcoin is currently trading at 90,000 USD."
"""
    (bot_dir / "plugin.py").write_text(code, encoding="utf-8")

    registry = PluginRegistry(plugins_dir=plugins_dir, data_dir=data_dir, state_file=state_file)
    registry.discover_and_load_all()

    assert registry.dispatch_command("what is the crypto price of BTC?") == "Bitcoin is currently trading at 90,000 USD."
    assert registry.dispatch_command("hey tell me joke time please") == "Why did the AI cross the road? To optimize the path!"
    assert registry.dispatch_command("completely unrelated query") is None


def test_plugin_error_isolation(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    data_dir = tmp_path / "data" / "plugins"
    state_file = tmp_path / "data" / "plugin_state.json"
    plugins_dir.mkdir(parents=True)

    buggy_dir = plugins_dir / "buggy_bot"
    buggy_dir.mkdir()

    manifest_data = {
        "id": "buggy_bot",
        "name": "Buggy Bot",
        "version": "1.0.0",
        "entrypoint": "plugin:BuggyPlugin",
        "permissions": [],
        "enabled": True,
    }
    (buggy_dir / "manifest.json").write_text(json.dumps(manifest_data), encoding="utf-8")

    code = """
from denver.plugins.base import BasePlugin

class BuggyPlugin(BasePlugin):
    def on_command(self, text: str) -> str | None:
        if "crash" in text:
            raise RuntimeError("Intentional plugin crash")
        return None
"""
    (buggy_dir / "plugin.py").write_text(code, encoding="utf-8")

    registry = PluginRegistry(plugins_dir=plugins_dir, data_dir=data_dir, state_file=state_file)
    registry.discover_and_load_all()

    # Broken plugin exception is safely caught and returns None without crashing
    res = registry.dispatch_command("please crash now")
    assert res is None
