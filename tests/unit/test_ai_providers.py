"""Unit tests for Denver AI Providers and Cloud Privacy Sanitization."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from denver.providers.fake import FakeAIProvider
from denver.providers.gemini import GeminiProvider
from denver.providers.groq import GroqProvider
from denver.providers.lmstudio import LMStudioProvider
from denver.providers.models import (
    ProviderHealth,
    ProviderRequest,
    ProviderResponse,
    ProviderStatus,
    ProviderType,
    ToolCall,
)
from denver.providers.ollama import OllamaProvider
from denver.providers.privacy import sanitize_messages_for_cloud, sanitize_text_for_cloud
from denver.security.vault import DenverVault


class TestPrivacySanitizer(unittest.TestCase):
    """Test suite for cloud privacy filtering and secret protection."""

    def test_sanitize_api_keys_and_tokens(self) -> None:
        """Verify API keys and bearer tokens are redacted prior to cloud transmission."""
        raw_text = "Here is my secret gsk_1234567890abcdef1234567890abcdef and AIzaSyD1234567890abcdef1234567890"
        sanitized = sanitize_text_for_cloud(raw_text)
        self.assertNotIn("gsk_1234567890", sanitized)
        self.assertNotIn("AIzaSyD1234567890", sanitized)
        self.assertIn("***", sanitized)

    def test_sanitize_bearer_auth(self) -> None:
        """Verify Authorization headers and Bearer tokens are redacted."""
        raw = "Bearer sk-proj-1234567890abcdef1234567890abcdef"
        sanitized = sanitize_text_for_cloud(raw)
        self.assertNotIn("sk-proj-12345", sanitized)
        self.assertIn("***", sanitized)

    def test_sanitize_messages(self) -> None:
        """Verify multi-turn message arrays are recursively sanitized."""
        messages = [
            {"role": "system", "content": "Assistant prompt with key: gsk_abcdef1234567890abcdef12345678"},
            {"role": "user", "content": "My password is password=SuperSecret123!"},
        ]
        sanitized_msgs = sanitize_messages_for_cloud(messages)
        self.assertEqual(len(sanitized_msgs), 2)
        self.assertNotIn("gsk_abcdef", sanitized_msgs[0]["content"])
        self.assertNotIn("SuperSecret123!", sanitized_msgs[1]["content"])


class TestFakeAIProvider(unittest.IsolatedAsyncioTestCase):
    """Test suite for the deterministic FakeAIProvider."""

    async def test_fake_generation(self) -> None:
        """Verify default and preset text generation."""
        provider = FakeAIProvider(name="test_fake", default_text="Hello from Denver AI!")
        req = ProviderRequest(messages=[{"role": "user", "content": "Hi"}])
        res = await provider.generate(req)
        self.assertTrue(res.success)
        self.assertEqual(res.text, "Hello from Denver AI!")
        self.assertEqual(res.provider_name, "test_fake")

    async def test_fake_tool_calling(self) -> None:
        """Verify fake provider can simulate tool calls."""
        fake_tool = ToolCall(action_name="get_time", parameters={})
        provider = FakeAIProvider(simulated_tool_calls=[fake_tool])
        req = ProviderRequest(messages=[{"role": "user", "content": "What time is it?"}])
        res = await provider.generate(req)
        self.assertTrue(res.success)
        self.assertEqual(len(res.tool_calls), 1)
        self.assertEqual(res.tool_calls[0].action_name, "get_time")

    async def test_fake_simulated_error(self) -> None:
        """Verify fake provider handles simulated failure cleanly."""
        provider = FakeAIProvider(should_fail=True, failure_error="Simulated network error")
        req = ProviderRequest(messages=[{"role": "user", "content": "Hi"}])
        with self.assertRaises(RuntimeError):
            await provider.generate(req)


class TestOllamaProvider(unittest.IsolatedAsyncioTestCase):
    """Test suite for local Ollama provider."""

    def setUp(self) -> None:
        self.provider = OllamaProvider(
            base_url="http://127.0.0.1:19999",  # Non-existent local port
            default_model="llama3.2",
            timeout_seconds=0.5,
        )

    async def test_ollama_offline_health(self) -> None:
        """Verify Ollama returns UNAVAILABLE when daemon is offline without crashing."""
        health = await self.provider.check_health()
        self.assertEqual(health.provider_name, "ollama")
        self.assertEqual(health.status, ProviderStatus.UNAVAILABLE)
        self.assertEqual(health.provider_type, ProviderType.LOCAL)

    async def test_ollama_offline_generate(self) -> None:
        """Verify Ollama raises typed RuntimeError when daemon is offline."""
        req = ProviderRequest(messages=[{"role": "user", "content": "Explain quantum physics"}])
        with self.assertRaises(RuntimeError):
            await self.provider.generate(req)


class TestLMStudioProvider(unittest.IsolatedAsyncioTestCase):
    """Test suite for local LM Studio provider."""

    def setUp(self) -> None:
        self.provider = LMStudioProvider(
            base_url="http://127.0.0.1:19998/v1",
            default_model="local-model",
            timeout_seconds=0.5,
        )

    async def test_lmstudio_offline_health(self) -> None:
        """Verify LM Studio returns UNAVAILABLE when server is offline."""
        health = await self.provider.check_health()
        self.assertEqual(health.provider_name, "lmstudio")
        self.assertEqual(health.status, ProviderStatus.UNAVAILABLE)

    async def test_lmstudio_offline_generate(self) -> None:
        """Verify LM Studio raises typed RuntimeError when server is offline."""
        req = ProviderRequest(messages=[{"role": "user", "content": "Hello"}])
        with self.assertRaises(RuntimeError):
            await self.provider.generate(req)


class TestCloudProvidersWithVault(unittest.IsolatedAsyncioTestCase):
    """Test suite for Groq and Gemini providers with Denver Vault integration."""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.vault_path = Path(self.tmp_dir.name) / "test_vault.dat"
        self.vault = DenverVault(vault_path=self.vault_path)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    async def test_groq_not_configured_when_no_key(self) -> None:
        """Verify Groq reports NOT_CONFIGURED when GROQ_API_KEY is missing from Vault."""
        provider = GroqProvider(vault=self.vault)
        health = await provider.check_health()
        self.assertEqual(health.status, ProviderStatus.NOT_CONFIGURED)
        self.assertIn("GROQ_API_KEY", health.error or "")

        with self.assertRaises(RuntimeError):
            await provider.generate(ProviderRequest(messages=[{"role": "user", "content": "Hi"}]))

    async def test_gemini_not_configured_when_no_key(self) -> None:
        """Verify Gemini reports NOT_CONFIGURED when GEMINI_API_KEY is missing from Vault."""
        provider = GeminiProvider(vault=self.vault)
        health = await provider.check_health()
        self.assertEqual(health.status, ProviderStatus.NOT_CONFIGURED)
        self.assertIn("GEMINI_API_KEY", health.error or "")

        with self.assertRaises(RuntimeError):
            await provider.generate(ProviderRequest(messages=[{"role": "user", "content": "Hi"}]))

    async def test_groq_with_mock_vault_key(self) -> None:
        """Verify Groq attempts call when key is present in Vault without exposing secret."""
        self.vault.set_secret("GROQ_API_KEY", "gsk_testdummykey1234567890abcdef1234567890")
        provider = GroqProvider(
            vault=self.vault,
            base_url="http://127.0.0.1:19997/v1",
            timeout_seconds=0.5,
        )
        req = ProviderRequest(messages=[{"role": "user", "content": "Test"}])
        with self.assertRaises(RuntimeError) as ctx:
            await provider.generate(req)
        # Secret must never be in error message
        self.assertNotIn("gsk_testdummykey", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
