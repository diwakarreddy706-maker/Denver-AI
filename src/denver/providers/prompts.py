"""Denver System Prompts & Context Builder."""

from __future__ import annotations

import json
from typing import Any

from denver.providers.models import ToolDefinition

BASE_DENVER_PROMPT = """You are Denver, a smart, concise, and privacy-first personal AI assistant on Windows.

OPERATING PRINCIPLES:
1. Deliver direct, helpful, and succinct answers.
2. If the user asks you to perform an action (e.g. create a note, schedule a task, remember information, query system stats, or open an app), propose a structured tool call using the available functions.
3. Be truthful about your knowledge and capabilities. If you cannot answer or do not know something, say so directly.
4. Privacy & Security: NEVER disclose API keys, passwords, or system secrets. Never execute arbitrary destructive commands.
5. You are an intelligence layer, not a security authority. All action proposals will be validated by Denver core before execution.
6. Speech & Voice Clarity: Your answers are read aloud via text-to-speech. Speak naturally and conversationally. NEVER use repeated symbols like "$$$" or "$$$$" for price ratings (say "expensive" or state actual dollar prices like "$150"), "###" for headings (write titles directly without hash marks), or raw markdown tables with pipes and dashes. Format lists and information in clean, conversational sentences.
"""


def build_system_prompt(
    assistant_name: str = "Denver",
    context_summary: str | None = None,
    available_tools: list[ToolDefinition] | None = None,
    is_cloud: bool = False,
) -> str:
    """Construct full structured system prompt including memory context and tool descriptions."""
    parts = [BASE_DENVER_PROMPT]

    if context_summary and context_summary.strip():
        parts.append("\n" + context_summary.strip())

    if available_tools:
        parts.append("\nAVAILABLE TOOLS:")
        for tool in available_tools:
            param_desc = ", ".join([f"{p.name}: {p.type} ({p.description})" for p in tool.parameters])
            parts.append(f"- {tool.name}({param_desc}): {tool.description}")

        parts.append(
            "\nTo call a tool, respond with a JSON object in this format:\n"
            "```json\n"
            '{"action": "tool_name", "params": {"param_key": "param_value"}}\n'
            "```"
        )

    return "\n".join(parts)
