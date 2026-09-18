"""Central Context Engine Orchestrating Memory, Profile, Budget, and Privacy for AI Prompts."""

from __future__ import annotations

import time
from typing import Any

from denver.context.budget import ContextBudgetConfig, fit_context_budget
from denver.context.models import ContextBundle, ShortTermTurn, UserProfileContext
from denver.context.privacy import CloudPrivacyFilter
from denver.logging.logger import get_logger
from denver.memory.memory_service import MemoryService
from denver.runtime.event_bus import DenverEventBus, get_event_bus
from denver.runtime.events import (
    ContextBudgetApplied,
    ContextBuilt,
    SensitiveMemoryExcluded,
)

logger = get_logger("context.engine")


class ContextEngine:
    """Orchestrates short-term conversation context, long-term memory retrieval, user profile, and privacy controls."""

    def __init__(
        self,
        memory_service: MemoryService,
        event_bus: DenverEventBus | None = None,
        budget_config: ContextBudgetConfig | None = None,
    ) -> None:
        self.memory = memory_service
        self.event_bus = event_bus or get_event_bus()
        self.budget_config = budget_config or ContextBudgetConfig()
        self.privacy_filter = CloudPrivacyFilter(
            allow_private_cloud=self.budget_config.allow_private_cloud,
            allow_sensitive_cloud=self.budget_config.allow_sensitive_cloud,
        )

    async def build_context(
        self,
        query: str,
        is_cloud: bool = False,
        category: str | None = None,
        max_memories: int | None = None,
    ) -> ContextBundle:
        """Assemble a bounded, privacy-filtered context bundle for AI generation."""
        # 1. Gather short-term conversation turns
        raw_recents = self.memory.get_recent_conversation(limit=self.budget_config.max_turns * 2)
        turns = [
            ShortTermTurn(
                role=t.get("role", "user"),
                content=t.get("content", ""),
                timestamp=t.get("timestamp", ""),
            )
            for t in raw_recents
        ]

        # 2. Retrieve relevant long-term memories via hybrid search
        top_k = max_memories or self.budget_config.max_memories
        retrieved_memories = await self.memory.hybrid_search(
            query=query,
            category=category,
            top_k=top_k * 2,
            min_score=0.18,
        )

        # 3. Apply Cloud Privacy Policy
        eligible_memories, excluded_sensitive = self.privacy_filter.filter_memories(
            retrieved_memories,
            is_cloud=is_cloud,
        )
        if excluded_sensitive > 0:
            await self.event_bus.publish(
                SensitiveMemoryExcluded(excluded_count=excluded_sensitive, reason="cloud_privacy_policy")
            )

        # 4. Enforce Budget Constraints (turns + memories)
        pruned_turns, final_memories, budget_applied = fit_context_budget(
            turns=turns,
            memories=eligible_memories,
            config=self.budget_config,
        )
        if budget_applied:
            await self.event_bus.publish(
                ContextBudgetApplied(
                    original_turns=len(turns),
                    final_turns=len(pruned_turns),
                    original_chars=sum(len(t.content) for t in turns),
                    final_chars=sum(len(t.content) for t in pruned_turns),
                )
            )

        # 5. Gather Preferences & User Profile Context
        prefs = await self.memory.list_preferences()
        pref_dict = {p.key: p.value for p in prefs}

        user_profile = UserProfileContext(
            name=pref_dict.get("user_name", pref_dict.get("name", "User")),
            language=pref_dict.get("language", "en"),
            preferred_editor=pref_dict.get("editor", pref_dict.get("preferred_editor")),
            custom_attributes=pref_dict,
        )

        # 6. Format Prompt Context String
        context_parts = ["[SYSTEM CONTEXT: USER PROFILE & MEMORY]"]
        if pref_dict:
            context_parts.append(f"- Known User Preferences: {pref_dict}")

        if final_memories:
            mem_block = self.privacy_filter.wrap_memories_as_data(final_memories)
            context_parts.append(mem_block)

        if pruned_turns:
            context_parts.append("- Recent Conversation History:")
            for t in pruned_turns:
                context_parts.append(f"  {t.role.capitalize()}: \"{t.content}\"")

        context_str = "\n\n".join(context_parts)
        reasons = [m.retrieval_reason for m in final_memories]

        bundle = ContextBundle(
            short_term_context=pruned_turns,
            relevant_memories=final_memories,
            user_profile=user_profile,
            preferences=pref_dict,
            context_string=context_str,
            total_characters=len(context_str),
            retrieval_reasons=reasons,
            privacy_decisions={
                "is_cloud": is_cloud,
                "excluded_sensitive_count": excluded_sensitive,
                "allowed_private_cloud": self.budget_config.allow_private_cloud,
            },
            memories_used_count=len(final_memories),
        )

        await self.event_bus.publish(
            ContextBuilt(
                memory_count=len(final_memories),
                total_chars=bundle.total_characters,
                has_profile=bool(pref_dict),
            )
        )

        return bundle
