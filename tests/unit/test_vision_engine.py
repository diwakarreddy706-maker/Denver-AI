"""Unit tests for VisionEngine and Multimodal Screen Intelligence in Denver."""

import base64
import pytest
import pytest_asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from denver.automation.vision import VisionAnalysisResult, VisionEngine
from denver.commands.models import CommandCategory, CommandRequest, CommandRiskLevel
from denver.commands.router import IntentRouter
from denver.commands.service import CommandEngineService
from denver.memory.database import DenverDatabase
from denver.memory.memory_service import MemoryService
from denver.providers.gemini import GeminiProvider
from denver.providers.groq import GroqProvider
from denver.providers.models import ProviderRequest, ProviderResponse
from denver.providers.ollama import OllamaProvider
from denver.providers.router import ProviderRouter
from denver.security.vault import DenverVault


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_vision.sqlite3"
    db = DenverDatabase(db_path=str(db_file))
    return db


@pytest_asyncio.fixture
async def initialized_db(temp_db):
    await temp_db.initialize()
    return temp_db


def test_vision_engine_screen_capture(tmp_path):
    engine = VisionEngine(output_dir=tmp_path)
    target_path, b64_str, width, height = engine.capture_screen_base64(max_dimension=800)
    
    assert target_path is not None
    assert target_path.exists()
    assert len(b64_str) > 100
    assert width > 0
    assert height > 0

    # Ensure base64 string decodes to valid image bytes
    raw_bytes = base64.b64decode(b64_str)
    assert len(raw_bytes) > 0


@pytest.mark.asyncio
async def test_vision_engine_analyze_screen(tmp_path):
    engine = VisionEngine(output_dir=tmp_path)
    
    mock_router = MagicMock(spec=ProviderRouter)
    mock_router.generate = AsyncMock(
        return_value=ProviderResponse(
            text="The active window is Visual Studio Code showing a Python file with no errors.",
            provider_name="gemini",
            model_name="gemini-2.0-flash",
            success=True,
        )
    )

    result = await engine.analyze_screen(
        prompt="What is on my screen?",
        provider_router=mock_router,
    )

    assert result.success is True
    assert "Visual Studio Code" in result.text
    assert result.provider_used == "gemini"
    mock_router.generate.assert_awaited_once()

    # Verify ProviderRequest contained the image
    req: ProviderRequest = mock_router.generate.call_args[0][0]
    assert len(req.images) == 1
    assert len(req.images[0]) > 50


def test_intent_router_screen_vision_triggers():
    router = IntentRouter()

    # 1. Direct look at screen
    intent1 = router.route("look at my screen and tell me what is wrong")
    assert intent1.action_name == "analyze_screen"
    assert intent1.category == CommandCategory.SYSTEM
    assert "what is wrong" in intent1.params.get("prompt", "")

    # 2. What's on my screen
    intent2 = router.route("what is on my screen")
    assert intent2.action_name == "analyze_screen"

    # 3. Analyze my screen
    intent3 = router.route("analyze screen")
    assert intent3.action_name == "analyze_screen"

    # 4. Fix error on screen
    intent4 = router.route("fix this error on my screen")
    assert intent4.action_name == "analyze_screen"

    # 5. Summarize screen
    intent5 = router.route("summarize my screen")
    assert intent5.action_name == "analyze_screen"


@pytest.mark.asyncio
async def test_gemini_multimodal_payload_formatting():
    vault = MagicMock(spec=DenverVault)
    vault.get_secret.return_value = "fake_gemini_key"
    provider = GeminiProvider(vault=vault, default_model="gemini-2.0-flash")

    dummy_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    req = ProviderRequest(
        messages=[{"role": "user", "content": "Explain this screenshot"}],
        images=[dummy_b64],
    )

    with patch("denver.providers.gemini._http_request") as mock_http:
        mock_http.return_value = {
            "candidates": [{
                "content": {"parts": [{"text": "I see a 1x1 test pixel."}]}
            }]
        }
        res = await provider.generate(req)
        assert res.success is True
        assert res.text == "I see a 1x1 test pixel."

        # Verify inline_data was populated in payload
        call_payload = mock_http.call_args[0][1]
        user_content = call_payload["contents"][0]
        parts = user_content["parts"]
        assert len(parts) == 2
        assert parts[0]["text"] == "Explain this screenshot"
        assert parts[1]["inline_data"]["data"] == dummy_b64


@pytest.mark.asyncio
async def test_groq_multimodal_payload_formatting():
    vault = MagicMock(spec=DenverVault)
    vault.get_secret.return_value = "fake_groq_key"
    provider = GroqProvider(vault=vault, default_model="llama-3.3-70b-versatile")

    dummy_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    req = ProviderRequest(
        messages=[{"role": "user", "content": "Explain this screenshot"}],
        images=[dummy_b64],
    )

    with patch("denver.providers.groq._http_request") as mock_http:
        mock_http.return_value = {
            "choices": [{
                "message": {"content": "I see a pixel in Groq Vision."}
            }]
        }
        res = await provider.generate(req)
        assert res.success is True
        assert res.text == "I see a pixel in Groq Vision."

        # Verify image_url was added to multimodal message
        call_payload = mock_http.call_args[0][1]
        assert call_payload["model"] == "llama-3.2-11b-vision-preview"
        user_msg = call_payload["messages"][1]
        assert isinstance(user_msg["content"], list)
        assert user_msg["content"][0]["text"] == "Explain this screenshot"
        assert dummy_b64 in user_msg["content"][1]["image_url"]["url"]


@pytest.mark.asyncio
async def test_command_service_analyze_screen(initialized_db):
    memory = MemoryService(db=initialized_db, privacy_mode=False)
    mock_router = MagicMock(spec=ProviderRouter)
    mock_router.generate = AsyncMock(
        return_value=ProviderResponse(
            text="Screen contains a browser with Python documentation.",
            provider_name="gemini",
            model_name="gemini-2.0-flash",
            success=True,
        )
    )

    service = CommandEngineService(
        memory_service=memory,
        provider_router=mock_router,
    )

    res = await service.process_command("look at my screen and summarize")
    assert res.success is True
    assert "Python documentation" in res.message
    assert res.action_name == "analyze_screen"
