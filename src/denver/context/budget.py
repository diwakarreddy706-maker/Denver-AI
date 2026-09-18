"""Context Window Budgeting and Truncation Enforcement."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from denver.context.models import ShortTermTurn
from denver.memory.models import MemorySearchResult


@dataclass(frozen=True)
class ContextBudgetConfig:
    """Limits and policies for AI prompt context construction."""

    max_turns: int = 10
    max_chars: int = 12000
    max_memories: int = 8
    allow_private_cloud: bool = False
    allow_sensitive_cloud: bool = False


def fit_context_budget(
    turns: Sequence[ShortTermTurn],
    memories: Sequence[MemorySearchResult],
    config: ContextBudgetConfig,
) -> tuple[list[ShortTermTurn], list[MemorySearchResult], bool]:
    """Prune conversation turns and memory items to fit strictly within configured limits.

    Returns (pruned_turns, pruned_memories, was_budget_applied).
    """
    orig_turn_count = len(turns)
    orig_mem_count = len(memories)

    # 1. Limit turns by max_turns (keep most recent)
    pruned_turns = list(turns[-config.max_turns :])

    # 2. Limit memories by max_memories (keep highest scored)
    pruned_memories = list(memories[: config.max_memories])

    # 3. Check character budget and trim older turns if necessary
    def _calc_total_chars() -> int:
        turn_chars = sum(len(t.content) for t in pruned_turns)
        mem_chars = sum(len(m.memory.content) for m in pruned_memories)
        return turn_chars + mem_chars

    while _calc_total_chars() > config.max_chars and len(pruned_turns) > 1:
        pruned_turns.pop(0)  # Drop oldest conversational turn

    while _calc_total_chars() > config.max_chars and len(pruned_memories) > 1:
        pruned_memories.pop()  # Drop lowest-ranked memory item

    budget_applied = (
        len(pruned_turns) < orig_turn_count
        or len(pruned_memories) < orig_mem_count
    )

    return pruned_turns, pruned_memories, budget_applied
