"""Unit tests for DenverSelfModel and Pillar 1 Capability Introspection."""

import pytest
from unittest.mock import MagicMock

from denver.commands.models import CommandCategory, CommandRiskLevel
from denver.commands.registry import ActionDefinition, ActionRegistry
from denver.commands.router import IntentRouter
from denver.commands.service import CommandEngineService
from denver.config.settings import DenverSettings
from denver.core.self_model import DenverSelfModel
from denver.memory.memory_service import MemoryService


def test_self_model_telemetry():
    settings = DenverSettings()
    model = DenverSelfModel(settings=settings)
    telem = model.get_system_telemetry()

    assert "os" in telem
    assert "cpu_percent" in telem
    assert "ram_percent" in telem
    assert "battery_percent" in telem


def test_self_model_capabilities_manifest():
    settings = DenverSettings(groq_model="openai/gpt-oss-20b", active_llm_provider="groq")
    registry = ActionRegistry()
    registry.register(
        ActionDefinition(
            name="test_action",
            description="A test action",
            category=CommandCategory.SYSTEM,
            risk_level=CommandRiskLevel.SAFE,
            handler=lambda p: None,
        )
    )

    self_model = DenverSelfModel(settings=settings, action_registry=registry)
    manifest = self_model.get_capabilities_manifest()

    assert manifest["assistant_name"] == "Denver"
    assert manifest["active_provider"] == "groq"
    assert manifest["active_model"] == "openai/gpt-oss-20b"
    assert manifest["total_registered_actions"] >= 1
    assert "system" in manifest["actions_by_category"]
    assert "test_action" in manifest["actions_by_category"]["system"]


def test_self_model_state_summary_block():
    settings = DenverSettings(groq_model="openai/gpt-oss-20b", active_llm_provider="groq")
    self_model = DenverSelfModel(settings=settings)
    summary = self_model.get_self_state_summary()

    assert "[DENVER RUNTIME SELF-STATE]" in summary
    assert "Active AI Provider: groq" in summary
    assert "Air-Gapped Mode:" in summary
    assert "System Health:" in summary


def test_self_model_capabilities_speech():
    settings = DenverSettings(groq_model="openai/gpt-oss-20b", active_llm_provider="groq")
    registry = ActionRegistry()
    registry.register(
        ActionDefinition(
            name="lock_workstation",
            description="Locks Windows",
            category=CommandCategory.SYSTEM,
            risk_level=CommandRiskLevel.HIGH,
            handler=lambda p: None,
        )
    )

    self_model = DenverSelfModel(settings=settings, action_registry=registry)
    speech_all = self_model.format_capabilities_speech()
    assert "registered actions" in speech_all
    assert "Groq" in speech_all

    speech_cat = self_model.format_capabilities_speech(category="system")
    assert "system category" in speech_cat
    assert "lock workstation" in speech_cat


def test_self_model_diagnose_failure():
    self_model = DenverSelfModel()

    msg1 = self_model.diagnose_failure("delete_root", "SafetyBlocked: Prohibited action")
    assert "blocked by my Safety Validator" in msg1

    msg2 = self_model.diagnose_failure("fly_drone", "ActionNotFound")
    assert "not recognized or registered" in msg2

    msg3 = self_model.diagnose_failure("ai_query", "HTTP Error 404: Not Found")
    assert "model or resource" in msg3 and "not found" in msg3

    msg4 = self_model.diagnose_failure("net_call", "ConnectionRefusedError: unreachable")
    assert "Unable to connect to the required service" in msg4

    msg5 = self_model.diagnose_failure("sys_mod", "PermissionError: access denied")
    assert "Permission was denied" in msg5


def test_intent_router_capabilities_queries():
    router = IntentRouter()

    queries = [
        "what can you do",
        "what are your capabilities",
        "what are your tools",
        "list your capabilities",
        "what model are you running",
        "what ai model are you using",
        "what provider are you using",
    ]

    for q in queries:
        intent = router.route(q)
        assert intent.action_name == "introspect_capabilities", f"Failed for query: {q}"
        assert intent.category == CommandCategory.SYSTEM
        assert intent.confidence == 1.0


@pytest.mark.asyncio
async def test_service_introspect_capabilities_execution():
    settings = DenverSettings()
    memory_mock = MagicMock(spec=MemoryService)
    service = CommandEngineService(memory_service=memory_mock, settings=settings)

    res = await service.process_command("what can you do")
    assert res.success is True
    assert res.action_name == "introspect_capabilities"
    assert "registered actions" in res.message
    assert "actions_by_category" in res.data
