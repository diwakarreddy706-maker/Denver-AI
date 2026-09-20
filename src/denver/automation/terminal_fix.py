"""Autonomous Terminal Fix Execution Engine for Denver AI Assistant.

Provides structured error diagnosis extraction, strict security command validation,
destructive pattern blocking, tokenized shell=False subprocess execution, and
post-fix visual verification.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

from denver.automation.models import AutomationResult, AutomationRisk
from denver.commands.safety import SafetyValidator
from denver.logging.logger import get_logger

logger = get_logger("automation.terminal_fix")

# Whitelist of recognized development, build, and package management binaries strictly permitted for fixes
ALLOWED_FIX_BINARIES = {
    "pip", "pip3", "python", "python3", "py",
    "npm", "npx", "pnpm", "yarn",
    "cargo", "rustc", "rustup",
    "git", "dotnet", "go",
    "composer", "poetry", "uv",
    "pytest", "ruff", "flake8", "black", "mypy",
    "node", "deno", "bun", "tsc",
    "gem", "bundle", "make", "cmake", "ctest",
    "winget", "choco", "scoop",
}

# Regex patterns identifying prohibited destructive or dangerous shell actions
DESTRUCTIVE_COMMAND_PATTERNS = [
    re.compile(r"\b(rmdir\s+/[sq]|del\s+/[fqs]|rm\s+-rf|rm\s+-r)\b", re.IGNORECASE),
    re.compile(r"\b(format(?:\s+[a-z]:|\s+[a-z]))\b", re.IGNORECASE),
    re.compile(r"\b(diskpart|vssadmin|bcdedit|mkfs|dd\s+if=)\b", re.IGNORECASE),
    re.compile(r"\b(reg(?:\.exe)?\s+delete)\b", re.IGNORECASE),
    re.compile(r"\b(takeown|icacls\s+.*grant)\b", re.IGNORECASE),
    re.compile(r"\b(chmod\s+-R\s+777|sudo\s+rm)\b", re.IGNORECASE),
    re.compile(r"\b(curl|wget)\s+.*\|\s*(?:bash|sh|cmd|powershell)\b", re.IGNORECASE),
    re.compile(r">\s*(?:/dev/sd[a-z]|\\\\.\\[a-zA-Z]:)", re.IGNORECASE),
    # PowerShell destructive cmdlets and administrative manipulation
    re.compile(
        r"\b(remove-item|clear-content|set-content|invoke-expression|invoke-command|start-process|"
        r"stop-process|stop-computer|restart-computer|set-executionpolicy|new-object|add-type|"
        r"disable-windowsoptionalfeature|ri|iex|icm|saps|kill|clc)\b",
        re.IGNORECASE,
    ),
    # Obfuscated or base64 encoded PowerShell flags
    re.compile(r"-(?:e|enc|encodedcommand)\b", re.IGNORECASE),
]

# Prohibited command chaining, redirection, obfuscation, or subshell characters
SHELL_INJECTION_CHARS = [
    "\n", "\r", ";", "&&", "||", "|", "&", ">", "<", "`", "$(", "${", "^"
]

# Environment variable indirection patterns (%COMSPEC%, $env:COMSPEC, $VAR)
ENV_INDIRECTION_PATTERN = re.compile(r"(%[a-zA-Z0-9_]+%|\$env:[a-zA-Z0-9_]+|\$[a-zA-Z0-9_]+)", re.IGNORECASE)

# Mandatory indicators of a genuine terminal or compiler error
GENUINE_ERROR_INDICATORS = [
    "modulenotfounderror",
    "importerror",
    "command not found",
    "not recognized as an internal or external command",
    "cannot find module",
    "fatal error:",
    "compilation error",
    "syntaxerror",
    "failed to compile",
    "package not found",
    "could not find a version that satisfies the requirement",
    "no matching distribution found",
    "error: failed to run custom build command",
    "error: could not compile",
    "npm err!",
    "traceback (most recent call last)",
]


class TerminalFixController:
    """Safely extracts, validates, and executes terminal fix commands with zero shell injection risk."""

    def __init__(self, safety_validator: SafetyValidator | None = None) -> None:
        self.safety = safety_validator or SafetyValidator(allow_destructive_actions=False)

    def extract_fix_proposal(
        self,
        analysis_text: str,
        context_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Extract root cause and proposed fix command from multimodal vision analysis text.
        
        Requires genuine error verification to mitigate prompt injection from arbitrary webpages.
        """
        if not analysis_text or not analysis_text.strip():
            return None

        # Threat Model Mitigation: Block extraction if context metadata flags untrusted source
        if context_metadata:
            if context_metadata.get("is_untrusted", False):
                logger.warning("Fix proposal extraction rejected: context is marked untrusted.")
                return None
            source_app = str(context_metadata.get("source_app", "")).lower()
            if any(browser in source_app for browser in ["chrome", "msedge", "firefox", "brave", "opera", "safari"]):
                logger.warning("Fix proposal extraction rejected: active window is an untrusted browser context.")
                return None

        # Verify genuine error indicators in analysis text
        lower_analysis = analysis_text.lower()
        has_genuine_error = any(ind in lower_analysis for ind in GENUINE_ERROR_INDICATORS)
        if not has_genuine_error:
            logger.info("Fix proposal extraction bypassed: text does not contain genuine terminal/compiler error signatures.")
            return None

        # 1. Search for explicit fix command code blocks: ```fix_command ... ``` or ```bash ... ``` or `command`
        patterns = [
            r"(?:proposed\s+fix|fix\s+command|run\s+command|recommended\s+fix|solution|command\s+to\s+run|fix\s*:)\s*[:\s]*`([^`]+)`",
            r"(?:proposed\s+fix|fix\s+command|run\s+command|recommended\s+fix|solution|fix\s*:)\s*[:\s]*```(?:bash|sh|powershell|cmd|shell)?\s*\n?([^\n`]+)\n?```",
            r"(?:run|execute)\s+`([^`]+)`\s+to\s+fix",
            r"`(pip\s+install\s+[a-zA-Z0-9_\-]+)`",
            r"`(npm\s+install\s+[a-zA-Z0-9_\-@/]+)`",
            r"`(pnpm\s+add\s+[a-zA-Z0-9_\-@/]+)`",
            r"`(yarn\s+add\s+[a-zA-Z0-9_\-@/]+)`",
            r"`(cargo\s+add\s+[a-zA-Z0-9_\-]+)`",
            r"`(poetry\s+add\s+[a-zA-Z0-9_\-]+)`",
            r"`(uv\s+add\s+[a-zA-Z0-9_\-]+)`",
            r"`(git\s+[a-zA-Z0-9_\-\s]+)`",
        ]

        extracted_cmd: str | None = None
        for pat in patterns:
            match = re.search(pat, analysis_text, flags=re.IGNORECASE)
            if match:
                candidate = match.group(1).strip()
                if candidate and len(candidate) > 2:
                    extracted_cmd = candidate
                    break

        if not extracted_cmd:
            return None

        # Clean trailing punctuation
        extracted_cmd = extracted_cmd.rstrip(".;")

        return {
            "command": extracted_cmd,
            "raw_analysis": analysis_text,
            "extracted_at": time.time(),
        }

    def validate_fix_command(self, command: str) -> tuple[bool, str | None, list[str] | None]:
        """Strictly validate command against destructive patterns, shell chaining, and verify tokenization.
        
        Returns:
            (is_safe, error_message, tokenized_args)
        """
        if not command or not command.strip():
            return False, "Command string is empty.", None

        cmd_clean = command.strip()

        # 1. Reject command chaining / pipeline / redirection / obfuscation operators
        for char in SHELL_INJECTION_CHARS:
            if char in cmd_clean:
                display_char = "\\n" if char == "\n" else ("\\r" if char == "\r" else char)
                return (
                    False,
                    f"Prohibited shell chaining, redirection, or obfuscation character '{display_char}' detected. Compound commands are not allowed.",
                    None,
                )

        # 2. Reject environment variable indirection (%VAR%, $env:VAR, $VAR)
        if ENV_INDIRECTION_PATTERN.search(cmd_clean):
            return (
                False,
                "Command blocked: Environment variable indirection is prohibited in terminal fix commands.",
                None,
            )

        # 3. Check for destructive command patterns & dangerous PowerShell cmdlets
        for pattern in DESTRUCTIVE_COMMAND_PATTERNS:
            if pattern.search(cmd_clean):
                return (
                    False,
                    f"Command blocked: Destructive or prohibited command pattern '{pattern.pattern}' detected.",
                    None,
                )

        # 4. Check Denver SafetyValidator baseline
        safety_violation = self.safety.check_for_dangerous_patterns(cmd_clean)
        if safety_violation:
            return False, f"Command safety violation: {safety_violation}", None

        # 5. Safe Tokenization (shell=False enforcement)
        try:
            # Use posix=False on Windows to preserve Windows quoting rules
            use_posix = os.name != "nt"
            args = shlex.split(cmd_clean, posix=use_posix)
        except Exception as exc:
            return False, f"Failed to tokenize command into arguments: {exc}", None

        if not args:
            return False, "Tokenized arguments array is empty.", None

        raw_bin = args[0].strip("\"'")
        base_bin = Path(raw_bin).name.lower()
        if base_bin.endswith(".exe"):
            base_bin = base_bin[:-4]

        # 6. Verify base binary against strictly allowed developer package/build tools
        if base_bin in {"cmd", "powershell", "pwsh", "bash", "sh", "zsh", "wscript", "cscript"}:
            return False, f"Direct invocation of raw shell binary '{base_bin}' is prohibited.", None

        if base_bin not in ALLOWED_FIX_BINARIES:
            return (
                False,
                f"Binary '{base_bin}' is not permitted for autonomous terminal fix execution. Only approved development and package manager binaries ({', '.join(sorted(ALLOWED_FIX_BINARIES))}) are allowed.",
                None,
            )

        return True, None, args

    def execute_fix(
        self,
        command: str,
        timeout_seconds: float = 60.0,
        cwd: str | Path | None = None,
    ) -> AutomationResult:
        """Safely execute the validated fix using subprocess with shell=False strictly enforced."""
        is_safe, err, tokenized_args = self.validate_fix_command(command)
        if not is_safe or not tokenized_args:
            logger.warning("Fix execution rejected by security validator: %s", err)
            return AutomationResult(
                success=False,
                action="execute_terminal_fix",
                target=command,
                message=f"Command validation failed: {err}",
                risk_level=AutomationRisk.HIGH,
                error=err,
            )

        start_time = time.perf_counter()
        logger.info("Executing validated terminal fix with shell=False: %s", tokenized_args)

        try:
            proc = subprocess.run(
                tokenized_args,
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                cwd=str(cwd) if cwd else None,
                check=False,
            )
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            stdout = (proc.stdout or "").strip()
            stderr = (proc.stderr or "").strip()

            success = (proc.returncode == 0)
            summary_msg = (
                f"Terminal fix `{command}` executed successfully (exit code 0)."
                if success
                else f"Terminal fix `{command}` failed with exit code {proc.returncode}."
            )

            return AutomationResult(
                success=success,
                action="execute_terminal_fix",
                target=command,
                message=summary_msg,
                data={
                    "command": command,
                    "args": tokenized_args,
                    "returncode": proc.returncode,
                    "stdout": stdout,
                    "stderr": stderr,
                    "latency_ms": elapsed_ms,
                },
                risk_level=AutomationRisk.HIGH,
                error=stderr if not success else None,
            )
        except subprocess.TimeoutExpired as exc:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error("Terminal fix timed out after %.1fs: %s", timeout_seconds, exc)
            return AutomationResult(
                success=False,
                action="execute_terminal_fix",
                target=command,
                message=f"Terminal fix `{command}` timed out after {timeout_seconds} seconds.",
                risk_level=AutomationRisk.HIGH,
                error="TimeoutExpired",
                data={"latency_ms": elapsed_ms},
            )
        except FileNotFoundError as exc:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error("Executable not found for terminal fix: %s", exc)
            return AutomationResult(
                success=False,
                action="execute_terminal_fix",
                target=command,
                message=f"Executable '{tokenized_args[0]}' was not found on system PATH.",
                risk_level=AutomationRisk.HIGH,
                error="FileNotFoundError",
                data={"latency_ms": elapsed_ms},
            )
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error("Terminal fix execution failed: %s", exc)
            return AutomationResult(
                success=False,
                action="execute_terminal_fix",
                target=command,
                message=f"Failed to execute terminal fix: {exc}",
                risk_level=AutomationRisk.HIGH,
                error=str(exc),
                data={"latency_ms": elapsed_ms},
            )
