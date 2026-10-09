"""Unit tests for Pillar 2: Continuous Desktop & Window Awareness (Desktop Observer)."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from denver.automation.models import WindowInfo
from denver.commands.models import CommandCategory, CommandRiskLevel
from denver.commands.router import IntentRouter
from denver.commands.service import CommandEngineService
from denver.context.engine import ContextEngine
from denver.core.observer import (
    DesktopObserverEngine,
    DesktopWindowContext,
    WorkspaceCategory,
    _format_dwell,
)
from denver.memory.memory_service import MemoryService
from denver.runtime.event_bus import DenverEventBus
from denver.runtime.events import ActiveWindowChanged


class MockNativeAPI:
    """Mock Windows Native API returning controllable foreground window."""

    def __init__(self, window: WindowInfo | None = None) -> None:
        self.window = window
        self.is_available = True

    def get_foreground_window(self) -> WindowInfo | None:
        return self.window


def test_format_dwell():
    """Verify dwell duration formatting helper."""
    assert _format_dwell(15) == "15s"
    assert _format_dwell(95) == "1m 35s"
    assert _format_dwell(3665) == "1h 1m"


def test_classify_window_development():
    """Verify IDE / development window title classification."""
    observer = DesktopObserverEngine(native_api=MockNativeAPI())

    # VS Code with active file and project
    cat, file_name, proj = observer.classify_window(
        "terminal_fix.py - AI - Visual Studio Code", "Code.exe"
    )
    assert cat == WorkspaceCategory.DEVELOPMENT.value
    assert file_name == "terminal_fix.py"
    assert proj == "AI"

    # VS Code with unsaved dirty dot
    cat, file_name, proj = observer.classify_window(
        "● sentence_splitter.py - Denver - Visual Studio Code", "code.exe"
    )
    assert cat == WorkspaceCategory.DEVELOPMENT.value
    assert file_name == "sentence_splitter.py"
    assert proj == "Denver"

    # VS Code folder workspace only
    cat, file_name, proj = observer.classify_window(
        "Denver-AI - Visual Studio Code", "Code.exe"
    )
    assert cat == WorkspaceCategory.DEVELOPMENT.value
    assert file_name is None
    assert proj == "Denver-AI"

    # Cursor IDE
    cat, file_name, proj = observer.classify_window(
        "main.py - MyProject - Cursor", "cursor.exe"
    )
    assert cat == WorkspaceCategory.DEVELOPMENT.value
    assert file_name == "main.py"
    assert proj == "MyProject"


def test_classify_window_browser_and_terminal():
    """Verify browser tabs and terminal classifications."""
    observer = DesktopObserverEngine(native_api=MockNativeAPI())

    # Chrome
    cat, file_name, tab = observer.classify_window(
        "Pull Requests · diwakarreddy706/Denver - Google Chrome", "chrome.exe"
    )
    assert cat == WorkspaceCategory.BROWSER.value
    assert file_name is None
    assert tab == "Pull Requests · diwakarreddy706/Denver"

    # Edge
    cat, file_name, tab = observer.classify_window(
        "Documentation - Microsoft Edge", "msedge.exe"
    )
    assert cat == WorkspaceCategory.BROWSER.value
    assert tab == "Documentation"

    # Windows Terminal
    cat, file_name, proj = observer.classify_window(
        "Administrator: Windows PowerShell", "WindowsTerminal.exe"
    )
    assert cat == WorkspaceCategory.TERMINAL.value


def test_classify_window_communication_media_and_office():
    """Verify communication, media, and office application classifications."""
    observer = DesktopObserverEngine(native_api=MockNativeAPI())

    # Discord
    cat, _, _ = observer.classify_window("general | Denver - Discord", "Discord.exe")
    assert cat == WorkspaceCategory.COMMUNICATION.value

    # Spotify
    cat, _, _ = observer.classify_window("Spotify Free", "Spotify.exe")
    assert cat == WorkspaceCategory.MEDIA.value

    # Word
    cat, _, _ = observer.classify_window("Document1 - Word", "WINWORD.EXE")
    assert cat == WorkspaceCategory.DOCUMENT.value

    # Unknown general app
    cat, _, _ = observer.classify_window("Some Random Window", "random_tool.exe")
    assert cat == WorkspaceCategory.GENERAL.value


def test_get_active_window_dwell_and_event_publishing():
    """Verify dwell time tracking and focus switch event publication."""
    event_bus = DenverEventBus()
    received_events = []
    event_bus.subscribe(ActiveWindowChanged, lambda evt: received_events.append(evt))

    win1 = WindowInfo(handle=101, title="terminal_fix.py - AI - Visual Studio Code", process_name="Code.exe")
    mock_api = MockNativeAPI(window=win1)
    observer = DesktopObserverEngine(native_api=mock_api, event_bus=event_bus)

    # First call sets focus
    ctx1 = observer.get_active_window()
    assert ctx1 is not None
    assert ctx1.title == win1.title
    assert ctx1.category == WorkspaceCategory.DEVELOPMENT.value
    assert ctx1.active_file == "terminal_fix.py"
    assert ctx1.project_name == "AI"

    # Shift window focus to Chrome
    win2 = WindowInfo(handle=102, title="GitHub - Google Chrome", process_name="chrome.exe")
    mock_api.window = win2

    ctx2 = observer.get_active_window()
    assert ctx2 is not None
    assert ctx2.category == WorkspaceCategory.BROWSER.value
    assert ctx2.process_name == "chrome.exe"

    # Verify event was published
    assert len(received_events) == 1
    evt = received_events[0]
    assert evt.old_app == "Code.exe"
    assert evt.new_app == "chrome.exe"
    assert evt.category == WorkspaceCategory.BROWSER.value


def test_workspace_summary_and_speech_formatting():
    """Verify markdown context block and natural speech formatting."""
    win = WindowInfo(handle=201, title="test_core.py - Denver - Visual Studio Code", process_name="Code.exe")
    mock_api = MockNativeAPI(window=win)
    observer = DesktopObserverEngine(native_api=mock_api)

    summary = observer.get_active_workspace_summary()
    assert "[ACTIVE WORKSPACE CONTEXT]" in summary
    assert "Focused Application: Code (Code.exe)" in summary
    assert "Workspace Category: DEVELOPMENT (File: test_core.py, Project: Denver)" in summary

    speech = observer.format_active_window_speech()
    assert "Visual Studio Code" in speech
    assert "test_core.py" in speech
    assert "Denver" in speech

    # Fallback speech when no window is active
    empty_observer = DesktopObserverEngine(native_api=MockNativeAPI(window=None))
    assert "No application window is currently active" in empty_observer.format_active_window_speech()
    assert empty_observer.get_active_workspace_summary() == ""


@pytest.mark.asyncio
async def test_context_engine_injects_workspace_context():
    """Verify ContextEngine automatically includes active workspace context."""
    memory_mock = MagicMock(spec=MemoryService)
    memory_mock.get_recent_conversation.return_value = []
    memory_mock.hybrid_search = AsyncMock(return_value=[])
    memory_mock.list_preferences = AsyncMock(return_value=[])

    win = WindowInfo(handle=301, title="app.py - MyApp - Visual Studio Code", process_name="Code.exe")
    observer = DesktopObserverEngine(native_api=MockNativeAPI(window=win))

    engine = ContextEngine(
        memory_service=memory_mock,
        desktop_observer=observer,
    )

    bundle = await engine.build_context(query="What should I work on next?")
    assert "[ACTIVE WORKSPACE CONTEXT]" in bundle.context_string
    assert "File: app.py, Project: MyApp" in bundle.context_string


def test_intent_router_active_window_patterns():
    """Verify natural language window query routing."""
    router = IntentRouter()

    queries = [
        "what window is active",
        "what is the active window",
        "what's the current window",
        "what am i looking at",
        "what app is open",
        "what app is focused",
        "what app is active",
        "which window is active",
        "active window",
        "current window",
    ]

    for q in queries:
        intent = router.route(q)
        assert intent is not None, f"Failed to route: {q}"
        assert intent.action_name == "get_active_window", f"Wrong action for: {q} -> {intent.action_name}"
        assert intent.risk_level == CommandRiskLevel.SAFE
        assert intent.confidence == 1.0


@pytest.mark.asyncio
async def test_service_executes_get_active_window(tmp_path):
    """Verify CommandEngineService executes get_active_window action end-to-end."""
    memory_mock = MagicMock(spec=MemoryService)
    memory_mock.get_recent_conversation.return_value = []
    memory_mock.hybrid_search = AsyncMock(return_value=[])
    memory_mock.list_preferences = AsyncMock(return_value=[])

    service = CommandEngineService(
        memory_service=memory_mock,
    )

    # Provide active window on observer
    win = WindowInfo(handle=401, title="main.py - Engine - Visual Studio Code", process_name="Code.exe")
    service.desktop_observer.native_api = MockNativeAPI(window=win)

    result = await service.process_command("what window is active")
    assert result.success is True
    assert result.action_name == "get_active_window"
    assert "Visual Studio Code" in result.message
    assert "main.py" in result.message
    assert result.data["active_file"] == "main.py"
    assert result.data["category"] == "DEVELOPMENT"

