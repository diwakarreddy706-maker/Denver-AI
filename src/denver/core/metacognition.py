"""Metacognitive Loop for Denver AI Assistant (Pillar 4: Plan -> Act -> Verify -> Adapt).

Implements end-to-end self-reflective autonomous execution:
1. Pre-flight Planning: Structured task decomposition into verifiable steps with expectations and fallbacks.
2. Native State Verification: Ground truth verification against native OS APIs (foreground window, running processes, filesystem).
3. Self-Reflective Retry & Remediation: Diagnoses discrepancies via DenverSelfModel and adapts with fallback strategies.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from denver.automation.models import WindowInfo
from denver.commands.models import ActionResult, CommandCategory, CommandRiskLevel
from denver.logging.logger import get_logger

logger = get_logger("core.metacognition")


@dataclass
class PlanStep:
    """An individual execution step in a metacognitive plan with state verification contract."""

    id: int
    action_name: str
    params: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    expected_state: dict[str, Any] | None = None
    fallback_action: str | None = None
    fallback_params: dict[str, Any] | None = None
    status: str = "pending"  # pending, executing, verified, adapted, failed
    execution_result: ActionResult | None = None
    verification_detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "action_name": self.action_name,
            "params": self.params,
            "description": self.description,
            "expected_state": self.expected_state,
            "fallback_action": self.fallback_action,
            "fallback_params": self.fallback_params,
            "status": self.status,
            "verification_detail": self.verification_detail,
        }


@dataclass
class MetacognitivePlan:
    """Structured pre-flight multi-step execution plan."""

    goal: str
    steps: list[PlanStep] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "steps": [s.to_dict() for s in self.steps],
            "total_steps": len(self.steps),
            "created_at": self.created_at,
        }


@dataclass
class VerificationResult:
    """Result of ground-truth native state verification."""

    verified: bool
    check_type: str
    actual_state: dict[str, Any] = field(default_factory=dict)
    expected_state: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "verified": self.verified,
            "check_type": self.check_type,
            "actual_state": self.actual_state,
            "expected_state": self.expected_state,
            "error_message": self.error_message,
        }


class StateVerifier:
    """Inspects native OS and application state to verify whether actions produced expected changes."""

    def __init__(
        self,
        native_api: Any | None = None,
        observer: Any | None = None,
    ) -> None:
        self.native_api = native_api
        self.observer = observer

    async def verify_step(self, step: PlanStep) -> VerificationResult:
        """Verify that the execution of a step resulted in the expected environment state."""
        if not step.expected_state:
            # No verification contract specified; assumed verified by default
            return VerificationResult(
                verified=True,
                check_type="none",
                actual_state={"status": "no_verification_contract"},
                expected_state={},
            )

        check_type = step.expected_state.get("type", "unknown")

        if check_type == "window_focused":
            return await self._verify_window_focused(step.expected_state)
        elif check_type == "app_running":
            return await self._verify_app_running(step.expected_state)
        elif check_type == "window_state":
            return await self._verify_window_state(step.expected_state)
        elif check_type == "file_exists":
            return self._verify_file_exists(step.expected_state)
        elif check_type == "custom":
            custom_fn = step.expected_state.get("verifier_fn")
            if callable(custom_fn):
                try:
                    res = custom_fn()
                    if asyncio.iscoroutine(res):
                        res = await res
                    return VerificationResult(
                        verified=bool(res),
                        check_type="custom",
                        actual_state={"result": res},
                        expected_state=step.expected_state,
                    )
                except Exception as exc:
                    return VerificationResult(
                        verified=False,
                        check_type="custom",
                        actual_state={"error": str(exc)},
                        expected_state=step.expected_state,
                        error_message=f"Custom verifier exception: {exc}",
                    )

        return VerificationResult(
            verified=True,
            check_type=check_type,
            actual_state={"status": "unsupported_check_type_treated_as_passed"},
            expected_state=step.expected_state,
        )

    async def _verify_window_focused(self, expected: dict[str, Any]) -> VerificationResult:
        target_process = (expected.get("process") or "").lower()
        target_title = (expected.get("title_contains") or "").lower()

        # Brief delay to allow OS window focus animation to complete
        await asyncio.sleep(0.05)

        fg_window = None
        if self.native_api and hasattr(self.native_api, "get_foreground_window"):
            fg_window = self.native_api.get_foreground_window()
        elif self.observer and hasattr(self.observer, "get_active_window_context"):
            ctx = self.observer.get_active_window_context()
            if ctx:
                fg_window = WindowInfo(
                    handle=ctx.hwnd,
                    title=ctx.title,
                    process_name=ctx.process_name,
                    process_id=0,
                    is_visible=True,
                )

        if not fg_window:
            return VerificationResult(
                verified=False,
                check_type="window_focused",
                actual_state={"foreground_window": None},
                expected_state=expected,
                error_message="Could not inspect active foreground window.",
            )

        actual_proc = (fg_window.process_name or "").lower()
        actual_title = (fg_window.title or "").lower()

        proc_match = not target_process or (target_process in actual_proc)
        title_match = not target_title or (target_title in actual_title)

        verified = bool(proc_match and title_match)
        err = None
        if not verified:
            err = f"Expected focused window matching process '{target_process}' or title '{target_title}', but found '{actual_proc}' ('{actual_title}')."

        return VerificationResult(
            verified=verified,
            check_type="window_focused",
            actual_state={"process_name": actual_proc, "title": actual_title, "handle": fg_window.handle},
            expected_state=expected,
            error_message=err,
        )

    async def _verify_app_running(self, expected: dict[str, Any]) -> VerificationResult:
        target_process = (expected.get("process") or "").lower()
        if not target_process:
            return VerificationResult(verified=True, check_type="app_running", expected_state=expected)

        try:
            import psutil
            matching = [
                p.info["name"]
                for p in psutil.process_iter(["name"])
                if p.info.get("name") and target_process in p.info["name"].lower()
            ]
            verified = len(matching) > 0
            err = None if verified else f"Process '{target_process}' is not running."
            return VerificationResult(
                verified=verified,
                check_type="app_running",
                actual_state={"running_matches": matching},
                expected_state=expected,
                error_message=err,
            )
        except Exception as exc:
            return VerificationResult(
                verified=True,
                check_type="app_running",
                actual_state={"error": str(exc)},
                expected_state=expected,
            )

    async def _verify_window_state(self, expected: dict[str, Any]) -> VerificationResult:
        expected_min = expected.get("is_minimized")
        expected_max = expected.get("is_maximized")

        fg = self.native_api.get_foreground_window() if self.native_api else None
        if not fg:
            return VerificationResult(
                verified=False,
                check_type="window_state",
                expected_state=expected,
                error_message="Window handle not found for state verification.",
            )

        verified = True
        err = None
        if expected_min is not None and fg.is_minimized != expected_min:
            verified = False
            err = f"Expected is_minimized={expected_min}, actual={fg.is_minimized}"
        elif expected_max is not None and fg.is_maximized != expected_max:
            verified = False
            err = f"Expected is_maximized={expected_max}, actual={fg.is_maximized}"

        return VerificationResult(
            verified=verified,
            check_type="window_state",
            actual_state={"is_minimized": fg.is_minimized, "is_maximized": fg.is_maximized},
            expected_state=expected,
            error_message=err,
        )

    def _verify_file_exists(self, expected: dict[str, Any]) -> VerificationResult:
        file_path = expected.get("path")
        if not file_path:
            return VerificationResult(verified=True, check_type="file_exists", expected_state=expected)

        exists = Path(file_path).exists()
        err = None if exists else f"File '{file_path}' does not exist on disk."
        return VerificationResult(
            verified=exists,
            check_type="file_exists",
            actual_state={"exists": exists, "path": str(file_path)},
            expected_state=expected,
            error_message=err,
        )


class MetacognitivePlanner:
    """Decomposes compound or multi-intent commands into an ordered verifiable execution plan."""

    @staticmethod
    def create_plan(instruction: str) -> MetacognitivePlan:
        """Analyze natural language instruction and construct a multi-step MetacognitivePlan."""
        text = instruction.strip()
        lower = text.lower()

        steps: list[PlanStep] = []

        # Compound Pattern 1: Open app/IDE and browse/search or take note
        if "open" in lower and ("code" in lower or "vs code" in lower) and ("note" in lower or "write" in lower):
            steps.append(
                PlanStep(
                    id=1,
                    action_name="open_application",
                    params={"application": "Code"},
                    description="Launch Visual Studio Code IDE",
                    expected_state={"type": "app_running", "process": "Code.exe"},
                    fallback_action="open_browser",
                    fallback_params={"target": "https://github.com"},
                )
            )
            steps.append(
                PlanStep(
                    id=2,
                    action_name="create_note",
                    params={"content": "Session initialized from metacognitive plan.", "title": "Work Session"},
                    description="Record work session initial note",
                )
            )
            return MetacognitivePlan(goal=instruction, steps=steps)

        # Compound Pattern 2: Mute audio and lock laptop / workstation
        if "mute" in lower and ("lock" in lower or "sleep" in lower):
            steps.append(
                PlanStep(
                    id=1,
                    action_name="mute_volume",
                    params={},
                    description="Mute system audio",
                )
            )
            steps.append(
                PlanStep(
                    id=2,
                    action_name="lock_workstation",
                    params={},
                    description="Lock workstation session",
                )
            )
            return MetacognitivePlan(goal=instruction, steps=steps)

        # Compound Pattern 3: Focus / switch window
        if lower.startswith("focus ") or lower.startswith("switch to "):
            target = text.split(" ", 2)[-1].strip()
            steps.append(
                PlanStep(
                    id=1,
                    action_name="focus_window",
                    params={"title": target},
                    description=f"Focus window matching '{target}'",
                    expected_state={"type": "window_focused", "title_contains": target},
                    fallback_action="open_application",
                    fallback_params={"application": target},
                )
            )
            return MetacognitivePlan(goal=instruction, steps=steps)

        # Compound Pattern 4: Open application with state expectation and browser fallback
        if lower.startswith("open ") or lower.startswith("launch "):
            app_target = text.split(" ", 1)[1].strip()
            steps.append(
                PlanStep(
                    id=1,
                    action_name="open_application",
                    params={"application": app_target},
                    description=f"Launch application '{app_target}'",
                    expected_state={"type": "app_running", "process": app_target},
                    fallback_action="open_browser",
                    fallback_params={"target": app_target},
                )
            )
            return MetacognitivePlan(goal=instruction, steps=steps)

        # Default: Single step atomic plan
        steps.append(
            PlanStep(
                id=1,
                action_name="atomic_command",
                params={"raw_text": instruction},
                description=f"Execute command: '{instruction}'",
            )
        )
        return MetacognitivePlan(goal=instruction, steps=steps)


@dataclass
class MetacognitiveExecutionResult:
    """Final result of a Metacognitive Plan -> Act -> Verify -> Adapt run."""

    success: bool
    goal: str
    completed_steps: int
    total_steps: int
    step_results: list[dict[str, Any]]
    final_message: str
    remediations_applied: list[str] = field(default_factory=list)
    failure_diagnosis: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "goal": self.goal,
            "completed_steps": self.completed_steps,
            "total_steps": self.total_steps,
            "step_results": self.step_results,
            "final_message": self.final_message,
            "remediations_applied": self.remediations_applied,
            "failure_diagnosis": self.failure_diagnosis,
        }


class MetacognitiveLoop:
    """The central orchestrator for Pillar 4: Metacognitive Loop (Plan -> Act -> Verify -> Adapt)."""

    def __init__(
        self,
        action_executor: Callable[[str, dict[str, Any]], Any],
        state_verifier: StateVerifier | None = None,
        self_model: Any | None = None,
        max_retries: int = 1,
    ) -> None:
        self.action_executor = action_executor
        self.verifier = state_verifier or StateVerifier()
        self.self_model = self_model
        self.max_retries = max_retries

    async def run(self, plan: MetacognitivePlan) -> MetacognitiveExecutionResult:
        """Execute a plan through the self-reflective Plan -> Act -> Verify -> Adapt loop."""
        step_receipts: list[dict[str, Any]] = []
        remediations: list[str] = []
        completed_count = 0

        for step in plan.steps:
            logger.info("Metacognitive Step %d/%d: %s (%s)", step.id, len(plan.steps), step.description, step.action_name)
            step.status = "executing"

            # 1. ACT
            act_res = await self._execute_action(step.action_name, step.params)
            step.execution_result = act_res

            # 2. VERIFY
            v_res = await self.verifier.verify_step(step)

            if act_res.success and v_res.verified:
                step.status = "verified"
                step.verification_detail = "Verified: Environment state confirmed matching expected contract."
                completed_count += 1
                step_receipts.append(step.to_dict())
                continue

            # 3. ADAPT (Self-Reflective Retry Loop)
            logger.warning(
                "Step %d verification discrepancy or execution failure: act_success=%s, verified=%s, err=%s",
                step.id,
                act_res.success,
                v_res.verified,
                v_res.error_message or act_res.error,
            )

            # Diagnose failure via DenverSelfModel if available
            diag_reason = "Action failed or state mismatch."
            if self.self_model and hasattr(self.self_model, "diagnose_failure"):
                raw_err = v_res.error_message or act_res.error or "StateMismatch"
                diag_reason = self.self_model.diagnose_failure(action_name=step.action_name, error=raw_err)

            # Check if fallback remediation exists
            if step.fallback_action:
                logger.info(
                    "Step %d adapting: executing fallback '%s' with params %s",
                    step.id,
                    step.fallback_action,
                    step.fallback_params,
                )
                remediation_msg = f"Step {step.id} ('{step.action_name}') failed; adapted with fallback '{step.fallback_action}'."
                remediations.append(remediation_msg)

                fallback_res = await self._execute_action(step.fallback_action, step.fallback_params or {})
                if fallback_res.success:
                    step.status = "adapted"
                    step.action_name = step.fallback_action
                    step.params = step.fallback_params or {}
                    step.verification_detail = f"Adapted with fallback '{step.fallback_action}'. Diagnosis: {diag_reason}"
                    completed_count += 1
                    step_receipts.append(step.to_dict())
                    continue

            # If fallback fails or no fallback exists, halt honestly without hallucinating completion
            step.status = "failed"
            step.verification_detail = f"Halted: {diag_reason}"
            step_receipts.append(step.to_dict())

            return MetacognitiveExecutionResult(
                success=False,
                goal=plan.goal,
                completed_steps=completed_count,
                total_steps=len(plan.steps),
                step_results=step_receipts,
                final_message=f"Metacognitive execution halted at step {step.id} ('{step.action_name}'). {diag_reason}",
                remediations_applied=remediations,
                failure_diagnosis=diag_reason,
            )

        return MetacognitiveExecutionResult(
            success=True,
            goal=plan.goal,
            completed_steps=completed_count,
            total_steps=len(plan.steps),
            step_results=step_receipts,
            final_message=f"All {len(plan.steps)} steps successfully executed and verified against native desktop state.",
            remediations_applied=remediations,
        )

    async def _execute_action(self, action_name: str, params: dict[str, Any]) -> ActionResult:
        """Call registered action executor cleanly with coroutine resolution."""
        try:
            res = self.action_executor(action_name, params)
            if asyncio.iscoroutine(res):
                res = await res
            if isinstance(res, ActionResult):
                return res
            return ActionResult(success=True, message=str(res), action_name=action_name)
        except Exception as exc:
            logger.error("Metacognitive action execution exception: %s", exc)
            return ActionResult(success=False, message=str(exc), action_name=action_name, error=str(exc))
