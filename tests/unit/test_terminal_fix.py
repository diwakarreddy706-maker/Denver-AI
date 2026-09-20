"""Unit tests for Component 4: Autonomous Terminal Fix Execution Engine."""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from denver.automation.executor import AutomationExecutor
from denver.automation.models import AutomationRequest, AutomationRisk
from denver.automation.terminal_fix import TerminalFixController
from denver.commands.models import CommandCategory, CommandIntent
from denver.commands.router import IntentRouter
from denver.commands.service import CommandEngineService
from denver.memory.database import DenverDatabase
from denver.memory.memory_service import MemoryService
from denver.runtime.event_bus import DenverEventBus
from denver.runtime.events import AutomationConfirmationRequired


def test_terminal_fix_extraction():
    """Verify extraction of fix commands from multimodal vision analysis text."""
    ctrl = TerminalFixController()

    # Case 1: Markdown backticks with 'proposed fix'
    text1 = (
        "I analyzed your terminal. There is a ModuleNotFoundError: No module named 'requests'.\n"
        "Proposed fix: `pip install requests`"
    )
    res1 = ctrl.extract_fix_proposal(text1)
    assert res1 is not None
    assert res1["command"] == "pip install requests"

    # Case 2: Code block with npm
    text2 = (
        "Active window is VS Code terminal showing error: Cannot find module 'axios'\n"
        "Solution:\n```bash\nnpm install axios\n```"
    )
    res2 = ctrl.extract_fix_proposal(text2)
    assert res2 is not None
    assert res2["command"] == "npm install axios"

    # Case 3: Direct inline pattern
    text3 = "You should run `poetry add fastapi` to fix the missing library."
    res3 = ctrl.extract_fix_proposal(text3)
    assert res3 is not None
    assert res3["command"] == "poetry add fastapi"

    # Case 4: No fix in general screen
    text4 = "Active screen shows browser with Wikipedia article."
    res4 = ctrl.extract_fix_proposal(text4)
    assert res4 is None


def test_terminal_fix_destructive_command_blocking():
    """Verify that dangerous and destructive commands are strictly rejected."""
    ctrl = TerminalFixController()

    dangerous_commands = [
        "rmdir /s /q c:\\",
        "del /f /q *.*",
        "rm -rf /",
        "rm -rf ./node_modules",
        "format d:",
        "diskpart",
        "mkfs.ext4 /dev/sda1",
        "sudo rm -rf /etc",
        "reg delete HKLM\\Software",
        "chmod -R 777 /",
    ]

    for cmd in dangerous_commands:
        is_safe, err, args = ctrl.validate_fix_command(cmd)
        assert is_safe is False, f"Expected '{cmd}' to be blocked!"
        assert err is not None
        assert args is None


def test_terminal_fix_shell_injection_blocking():
    """Verify that shell operator chaining and command injection are strictly blocked."""
    ctrl = TerminalFixController()

    injection_commands = [
        "pip install requests && calc.exe",
        "npm install; rm -rf /",
        "git status | bash",
        "python script.py || echo fail",
        "pip install $(whoami)",
        "echo `whoami`",
        "pip install foo > out.txt",
    ]

    for cmd in injection_commands:
        is_safe, err, args = ctrl.validate_fix_command(cmd)
        assert is_safe is False, f"Expected injection '{cmd}' to be blocked!"
        assert "chaining or redirection operator" in err or "safety violation" in err
        assert args is None


def test_terminal_fix_shell_false_execution():
    """Verify that valid fix commands execute with shell=False strictly enforced."""
    ctrl = TerminalFixController()

    with patch("subprocess.run") as mock_run:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "Successfully installed rich-13.7.0"
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        result = ctrl.execute_fix("pip install rich")

        assert result.success is True
        assert result.action == "execute_terminal_fix"
        assert result.data["returncode"] == 0
        assert "Successfully installed" in result.data["stdout"]

        # Verify subprocess.run call arguments: shell MUST be False
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["shell"] is False
        assert call_kwargs["capture_output"] is True

        # Verify tokenized argument array
        call_args = mock_run.call_args[0][0]
        assert call_args == ["pip", "install", "rich"]


@pytest.mark.asyncio
async def test_terminal_fix_confirmation_gate_in_executor():
    """Verify that execute_terminal_fix requires user confirmation before running."""
    event_bus = DenverEventBus()
    executor = AutomationExecutor(event_bus=event_bus)

    # 1. Attempt execution without confirmation token
    req = AutomationRequest(
        action_name="execute_terminal_fix",
        target="pip install fastapi",
        params={"command": "pip install fastapi"},
    )

    published = []

    def on_conf(evt):
        published.append(evt)

    event_bus.subscribe(AutomationConfirmationRequired, on_conf)

    res = await executor.execute(req)
    await asyncio.sleep(0.05)

    assert res.requires_confirmation is True
    assert res.confirmation_token is not None
    assert len(published) == 1
    assert published[0].token == res.confirmation_token
    assert published[0].action_name == "execute_terminal_fix"

    # 2. Supply valid token to execute
    with patch.object(executor.terminal_fix, "execute_fix") as mock_exec:
        mock_exec.return_value = MagicMock(
            success=True,
            action="execute_terminal_fix",
            target="pip install fastapi",
            message="Fix executed successfully.",
            data={"returncode": 0},
            error=None,
        )

        confirm_req = AutomationRequest(
            action_name="execute_terminal_fix",
            target="pip install fastapi",
            params={"command": "pip install fastapi"},
            confirmation_token=res.confirmation_token,
        )
        confirm_res = await executor.execute(confirm_req)

        assert confirm_res.success is True
        mock_exec.assert_called_once_with(command="pip install fastapi", timeout_seconds=60.0, cwd=None)


@pytest.mark.asyncio
async def test_service_analyze_screen_proposes_fix_and_stages_confirmation(tmp_path):
    """Verify that screen error diagnosis automatically extracts fix and stages confirmation."""
    db_file = tmp_path / "test_term_fix.sqlite3"
    db = DenverDatabase(db_path=str(db_file))
    await db.initialize()
    memory = MemoryService(db=db, privacy_mode=False)

    service = CommandEngineService(memory_service=memory)

    # Mock VisionEngine analyze_screen to return diagnosis with fix
    from denver.automation.vision import VisionAnalysisResult
    mock_diag = VisionAnalysisResult(
        success=True,
        text="Found error in terminal: ModuleNotFoundError: No module named 'pytest'. Proposed fix: `pip install pytest`",
        provider_used="gemini",
        model_used="gemini-flash-latest",
    )
    service.vision_engine.analyze_screen = AsyncMock(return_value=mock_diag)

    published = []

    def listener(evt):
        published.append(evt)

    service.event_bus.subscribe(AutomationConfirmationRequired, listener)

    res = await service.process_command("Denver, look at my screen and diagnose errors")
    await asyncio.sleep(0.05)

    assert res.success is True
    assert "Proposed Terminal Fix: `pip install pytest`" in res.message
    assert len(published) == 1
    assert published[0].action_name == "execute_terminal_fix"
    assert published[0].target == "pip install pytest"

    # Verify voice confirmation "Yes, do it" consumes token and executes
    with patch.object(service.automation.terminal_fix, "execute_fix") as mock_exec:
        mock_exec.return_value = MagicMock(
            success=True,
            action="execute_terminal_fix",
            target="pip install pytest",
            message="Successfully installed pytest.",
            data={"returncode": 0},
            error=None,
        )

        confirm_res = await service.process_command("Yes, do it")
        assert confirm_res.success is True
        assert "Successfully installed pytest" in confirm_res.message
        mock_exec.assert_called_once()


def test_intent_router_terminal_fix_and_confirmation():
    """Verify IntentRouter routes terminal fix commands and confirmation utterances."""
    router = IntentRouter()

    # 1. Terminal fix intent
    intent1 = router.route("Denver, execute terminal fix: pip install rich")
    assert intent1.action_name == "execute_terminal_fix"
    assert intent1.params.get("command") == "pip install rich"

    intent2 = router.route("Denver, apply fix")
    assert intent2.action_name == "execute_terminal_fix"

    intent3 = router.route("Denver, fix terminal error")
    assert intent3.action_name == "execute_terminal_fix"

    # 2. Confirmation intents
    intent_yes = router.route("yes")
    assert intent_yes.action_name == "confirm_action"

    intent_do_it = router.route("do it")
    assert intent_do_it.action_name == "confirm_action"

    intent_confirm = router.route("confirm")
    assert intent_confirm.action_name == "confirm_action"

    # 3. Cancellation intents
    intent_cancel = router.route("cancel")
    assert intent_cancel.action_name == "cancel_action"

    intent_no = router.route("no")
    assert intent_no.action_name == "cancel_action"
