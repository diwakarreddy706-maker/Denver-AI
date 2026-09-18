"""Typed Domain Models and Contracts for Denver AI Providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ProviderStatus(str, Enum):
    """Health and readiness status of an individual AI provider."""

    READY = "READY"                    # Endpoint reachable, model ready
    NOT_CONFIGURED = "NOT_CONFIGURED"  # Missing credentials (e.g. no API key in Vault)
    UNAVAILABLE = "UNAVAILABLE"        # Connection refused / daemon not running locally
    DEGRADED = "DEGRADED"              # High latency or intermittent timeouts
    ERROR = "ERROR"                    # Fatal error returned by provider


class ProviderType(str, Enum):
    """Classification of provider infrastructure."""

    LOCAL = "local"
    CLOUD = "cloud"


@dataclass(frozen=True)
class ModelInfo:
    """Metadata describing a specific AI model."""

    model_id: str
    name: str
    family: str | None = None
    context_length: int = 4096


@dataclass(frozen=True)
class ToolParameter:
    """Parameter schema for structured function/tool definitions."""

    name: str
    type: str = "string"
    description: str = ""
    required: bool = True


@dataclass(frozen=True)
class ToolDefinition:
    """Definition of a callable action/tool exposed to AI models."""

    name: str
    description: str
    parameters: list[ToolParameter] = field(default_factory=list)

    def to_schema(self) -> dict[str, Any]:
        """Convert into standard OpenAI-compatible tool JSON schema."""
        properties = {}
        required_params = []
        for p in self.parameters:
            properties[p.name] = {
                "type": p.type,
                "description": p.description,
            }
            if p.required:
                required_params.append(p.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required_params,
                },
            },
        }


class ToolCall:
    """A tool/action execution proposed by an AI model."""

    def __init__(
        self,
        name: str = "",
        arguments: dict[str, Any] | None = None,
        action_name: str | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> None:
        self.name = action_name if action_name is not None else name
        self.arguments = parameters if parameters is not None else (arguments or {})

    @property
    def action_name(self) -> str:
        return self.name

    @property
    def parameters(self) -> dict[str, Any]:
        return self.arguments

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.name, "params": self.arguments}

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ToolCall):
            return False
        return self.name == other.name and self.arguments == other.arguments

    def __repr__(self) -> str:
        return f"ToolCall(name='{self.name}', arguments={self.arguments})"


@dataclass
class ToolResult:
    """Output generated after executing a model-proposed tool."""

    name: str
    output: Any
    tool_call_id: str | None = None


@dataclass
class ProviderRequest:
    """Standardized multi-turn request passed to an AI provider."""

    messages: list[dict[str, str]]
    tools: list[ToolDefinition] = field(default_factory=list)
    images: list[str] = field(default_factory=list)  # Base64 encoded images or image file paths
    temperature: float = 0.7
    max_tokens: int = 1024
    system_prompt: str | None = None
    context_summary: str | None = None


@dataclass
class ProviderResponse:
    """Standardized response produced by an AI provider."""

    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    model_name: str = ""
    provider_name: str = ""
    latency_ms: float = 0.0
    token_usage: dict[str, int] = field(default_factory=dict)
    raw_response: dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error: str | None = None

    @property
    def usage(self) -> dict[str, int]:
        return self.token_usage


@dataclass
class ProviderHealth:
    """Structured health assessment for a single provider."""

    provider_name: str
    status: ProviderStatus
    provider_type: ProviderType
    model_name: str
    latency_ms: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "type": self.provider_type.value,
            "model": self.model_name,
            "latency_ms": self.latency_ms,
            "error": self.error,
        }
