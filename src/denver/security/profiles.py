"""Security Profiles and Dynamic Policy Enforcement for Denver AI Assistant."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any

from denver.logging.logger import get_logger

logger = get_logger("security.profiles")


class SecurityProfile(str, Enum):
    """Denver operational security profiles defining system-wide trust boundaries."""
    SAFE = "safe"
    NORMAL = "normal"
    HIGH_SECURITY = "high_security"
    DEVELOPER = "developer"


@dataclass(frozen=True)
class PolicyRuleSet:
    """Security permissions and operational constraints for a given security profile."""
    profile: SecurityProfile
    allow_destructive_actions: bool
    destructive_requires_confirmation: bool
    allow_clipboard_read: bool
    mask_clipboard_secrets: bool
    allow_unsigned_plugins: bool
    allow_cloud_llm: bool
    allow_shell_execution: bool
    strict_path_confinement: bool
    max_confirmation_timeout_sec: float


PROFILE_RULES: dict[SecurityProfile, PolicyRuleSet] = {
    SecurityProfile.SAFE: PolicyRuleSet(
        profile=SecurityProfile.SAFE,
        allow_destructive_actions=False,
        destructive_requires_confirmation=True,
        allow_clipboard_read=True,
        mask_clipboard_secrets=True,
        allow_unsigned_plugins=False,
        allow_cloud_llm=False,
        allow_shell_execution=False,
        strict_path_confinement=True,
        max_confirmation_timeout_sec=10.0,
    ),
    SecurityProfile.HIGH_SECURITY: PolicyRuleSet(
        profile=SecurityProfile.HIGH_SECURITY,
        allow_destructive_actions=False,  # Blocked completely even if confirmed
        destructive_requires_confirmation=True,
        allow_clipboard_read=True,
        mask_clipboard_secrets=True,
        allow_unsigned_plugins=False,
        allow_cloud_llm=False,  # Zero cloud egress
        allow_shell_execution=False,
        strict_path_confinement=True,
        max_confirmation_timeout_sec=10.0,
    ),
    SecurityProfile.NORMAL: PolicyRuleSet(
        profile=SecurityProfile.NORMAL,
        allow_destructive_actions=True,  # Allowed only when confirmed
        destructive_requires_confirmation=True,
        allow_clipboard_read=True,
        mask_clipboard_secrets=True,
        allow_unsigned_plugins=True,  # With warning
        allow_cloud_llm=True,
        allow_shell_execution=True,  # Guarded subprocess execution
        strict_path_confinement=True,
        max_confirmation_timeout_sec=30.0,
    ),
    SecurityProfile.DEVELOPER: PolicyRuleSet(
        profile=SecurityProfile.DEVELOPER,
        allow_destructive_actions=True,
        destructive_requires_confirmation=False,  # Permissive for developer testing
        allow_clipboard_read=True,
        mask_clipboard_secrets=False,
        allow_unsigned_plugins=True,
        allow_cloud_llm=True,
        allow_shell_execution=True,
        strict_path_confinement=False,
        max_confirmation_timeout_sec=60.0,
    ),
}


class SecurityPolicyManager:
    """Evaluates and enforces security policy rules across all Denver subsystems."""

    def __init__(self, profile: SecurityProfile | str = SecurityProfile.NORMAL) -> None:
        self.set_profile(profile)

    def set_profile(self, profile: SecurityProfile | str) -> None:
        """Switch active security profile dynamically."""
        if isinstance(profile, str):
            clean = profile.strip().lower()
            if clean in {"high", "high_security", "paranoid", "strict"}:
                self._profile = SecurityProfile.HIGH_SECURITY
            elif clean in {"safe", "safemode"}:
                self._profile = SecurityProfile.SAFE
            elif clean in {"dev", "developer"}:
                self._profile = SecurityProfile.DEVELOPER
            else:
                self._profile = SecurityProfile.NORMAL
        else:
            self._profile = profile

        self._rules = PROFILE_RULES[self._profile]
        logger.info("Denver Security Profile active: %s", self._profile.value.upper())

    @property
    def current_profile(self) -> SecurityProfile:
        return self._profile

    @property
    def rules(self) -> PolicyRuleSet:
        return self._rules

    def can_execute_destructive(self, is_confirmed: bool = False) -> tuple[bool, str | None]:
        """Check if a destructive action is permitted under current profile."""
        if self._profile in {SecurityProfile.SAFE, SecurityProfile.HIGH_SECURITY}:
            return False, f"Destructive actions are prohibited in {self._profile.value.upper()} profile."

        if self._rules.destructive_requires_confirmation and not is_confirmed:
            return False, "Destructive action requires explicit user confirmation."

        return True, None

    def can_load_plugin(self, is_signed: bool = False) -> tuple[bool, str | None]:
        """Check if plugin loading is permitted."""
        if not self._rules.allow_unsigned_plugins and not is_signed:
            return False, f"Unsigned plugin rejected in {self._profile.value.upper()} profile."
        return True, None

    def can_access_cloud(self) -> tuple[bool, str | None]:
        """Check if cloud network queries / cloud LLMs are permitted."""
        if not self._rules.allow_cloud_llm:
            return False, f"Cloud queries blocked in {self._profile.value.upper()} profile (Air-Gapped / Local-Only)."
        return True, None

    def can_execute_shell(self) -> tuple[bool, str | None]:
        """Check if terminal/shell subprocess execution is permitted."""
        if not self._rules.allow_shell_execution:
            return False, f"Shell subprocess execution is blocked in {self._profile.value.upper()} profile."
        return True, None


_default_security_manager: SecurityPolicyManager | None = None


def get_security_manager(profile: SecurityProfile | str | None = None) -> SecurityPolicyManager:
    """Get or initialize global security policy manager."""
    global _default_security_manager
    if _default_security_manager is None:
        env_profile = os.environ.get("DENVER_SECURITY_PROFILE", "normal")
        _default_security_manager = SecurityPolicyManager(profile or env_profile)
    elif profile is not None:
        _default_security_manager.set_profile(profile)
    return _default_security_manager
