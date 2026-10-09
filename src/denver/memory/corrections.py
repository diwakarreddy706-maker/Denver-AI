"""User Correction Store & Behavioral Override Engine for Denver Memory (Pillar 3)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from denver.logging.logger import get_logger
from denver.memory.database import DenverDatabase
from denver.memory.models import UserCorrection
from denver.memory.repositories import UserCorrectionsRepository

logger = get_logger("corrections")


# Precompiled detection patterns for explicit user corrections
CORRECTION_PATTERNS = [
    # "No, use Brave instead of Chrome" / "No, open Firefox instead of Edge"
    re.compile(
        r"^(?:no[,\s]+)?(?:use|open|prefer)\s+(?P<new_val>.+?)\s+instead\s+of\s+(?P<old_val>.+?)(?:\.|$)",
        re.IGNORECASE,
    ),
    # "Don't play music when I ask to code"
    re.compile(
        r"^don'?t\s+(?P<avoid_action>.+?)\s+when\s+I\s+(?P<condition>.+?)(?:\.|$)",
        re.IGNORECASE,
    ),
    # "Remember that I use poetry, not pip" / "I use poetry, not pip"
    re.compile(
        r"^(?:remember\s+that\s+)?I\s+use\s+(?P<new_val>.+?)[,\s]+not\s+(?P<old_val>.+?)(?:\.|$)",
        re.IGNORECASE,
    ),
    # "Correction: always use dark theme" / "Correction: use Brave for browsing"
    re.compile(
        r"^correction[:\s]+(?P<correction_text>.+?)(?:\.|$)",
        re.IGNORECASE,
    ),
    # "Actually, use X rather than Y"
    re.compile(
        r"^actually[,\s]+(?:use|prefer)\s+(?P<new_val>.+?)\s+rather\s+than\s+(?P<old_val>.+?)(?:\.|$)",
        re.IGNORECASE,
    ),
    # "Stop doing X, do Y" / "Stop X, instead do Y"
    re.compile(
        r"^stop\s+(?:doing\s+)?(?P<old_action>.+?)[,\s]+(?:instead\s+)?(?:do|use)\s+(?P<new_action>.+?)(?:\.|$)",
        re.IGNORECASE,
    ),
    # "Never X, always Y"
    re.compile(
        r"^never\s+(?P<avoid_action>.+?)[,\s]+always\s+(?P<prefer_action>.+?)(?:\.|$)",
        re.IGNORECASE,
    ),
]


class UserCorrectionStore:
    """Manages persistent user corrections and provides prompt-grounded behavioral overrides."""

    def __init__(self, db: DenverDatabase, repo: UserCorrectionsRepository | None = None) -> None:
        self.db = db
        self._repo = repo

    def _get_repo(self, conn: Any) -> UserCorrectionsRepository:
        return UserCorrectionsRepository(conn)

    async def add_correction(
        self,
        pattern: str,
        correction: str,
        target_domain: str = "general",
        priority: int = 10,
    ) -> UserCorrection:
        """Persist a new user correction rule."""
        def _add(conn: Any) -> UserCorrection:
            repo = self._get_repo(conn)
            return repo.add_correction(
                pattern=pattern,
                correction=correction,
                target_domain=target_domain,
                priority=priority,
            )

        correction_obj = await self.db.run_async(_add)
        logger.info(
            "Saved user correction #%s: '%s' -> '%s' (domain: %s)",
            correction_obj.id,
            pattern,
            correction,
            target_domain,
        )
        return correction_obj

    async def get_active_corrections(self, target_domain: str | None = None) -> list[UserCorrection]:
        """Retrieve all active corrections for context prompt injection."""
        def _get(conn: Any) -> list[UserCorrection]:
            repo = self._get_repo(conn)
            return repo.get_active_corrections(target_domain=target_domain)

        return await self.db.run_async(_get)

    async def list_corrections(self, include_inactive: bool = False, limit: int = 50) -> list[UserCorrection]:
        """List corrections."""
        def _list(conn: Any) -> list[UserCorrection]:
            repo = self._get_repo(conn)
            return repo.list_corrections(include_inactive=include_inactive, limit=limit)

        return await self.db.run_async(_list)

    async def delete_correction(self, correction_id: int) -> bool:
        """Permanently delete a correction by ID."""
        def _del(conn: Any) -> bool:
            repo = self._get_repo(conn)
            return repo.delete_correction(correction_id)

        result = await self.db.run_async(_del)
        if result:
            logger.info("Deleted user correction #%s", correction_id)
        return result

    async def clear_all_corrections(self) -> int:
        """Clear all corrections."""
        def _clear(conn: Any) -> int:
            repo = self._get_repo(conn)
            return repo.clear_corrections()

        return await self.db.run_async(_clear)

    @staticmethod
    def detect_correction(text: str) -> dict[str, Any] | None:
        """Detect if an utterance contains an explicit user correction to Denver's behavior."""
        clean_text = text.strip()

        # Match against predefined correction grammar
        for pattern_re in CORRECTION_PATTERNS:
            match = pattern_re.search(clean_text)
            if match:
                groups = match.groupdict()
                if "new_val" in groups and "old_val" in groups:
                    new_val = groups["new_val"].strip()
                    old_val = groups["old_val"].strip()
                    domain = "application" if any(b in clean_text.lower() for b in ["chrome", "brave", "edge", "firefox", "browser", "code", "ide"]) else "general"
                    return {
                        "pattern": f"use {old_val}",
                        "correction": f"Use {new_val} instead of {old_val}",
                        "target_domain": domain,
                        "priority": 15,
                    }
                elif "avoid_action" in groups and "condition" in groups:
                    avoid = groups["avoid_action"].strip()
                    cond = groups["condition"].strip()
                    return {
                        "pattern": f"{cond}",
                        "correction": f"Do not {avoid} when {cond}",
                        "target_domain": "workflow",
                        "priority": 15,
                    }
                elif "avoid_action" in groups and "prefer_action" in groups:
                    avoid = groups["avoid_action"].strip()
                    prefer = groups["prefer_action"].strip()
                    return {
                        "pattern": f"{avoid}",
                        "correction": f"Never {avoid}, always {prefer}",
                        "target_domain": "general",
                        "priority": 15,
                    }
                elif "old_action" in groups and "new_action" in groups:
                    old_act = groups["old_action"].strip()
                    new_act = groups["new_action"].strip()
                    return {
                        "pattern": f"{old_act}",
                        "correction": f"Stop {old_act}, do {new_act}",
                        "target_domain": "general",
                        "priority": 15,
                    }
                elif "correction_text" in groups:
                    corr = groups["correction_text"].strip()
                    return {
                        "pattern": "general",
                        "correction": corr,
                        "target_domain": "general",
                        "priority": 12,
                    }

        return None

    async def format_prompt_overrides(self, target_domain: str | None = None) -> str:
        """Format an authoritative markdown block of active overrides to inject into ContextEngine."""
        corrections = await self.get_active_corrections(target_domain=target_domain)
        if not corrections:
            return ""

        lines = ["[ACTIVE CORRECTIONS & OVERRIDES]"]
        lines.append("CRITICAL: The user has explicitly corrected previous actions. Always honor these overrides above default behavior:")
        for c in corrections:
            lines.append(f"- [{c.target_domain.upper()}] {c.correction} (Rule #{c.id}, Priority: {c.priority})")

        return "\n".join(lines)
