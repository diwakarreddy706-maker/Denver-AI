"""Unit tests for Cockpit Home Dashboard Tab integration in ActivityPanelWidget."""

from unittest.mock import MagicMock
import pytest
from PySide6.QtWidgets import QApplication

from denver.ui.controller import UIController
from denver.ui.widgets.activity_panel import ActivityPanelWidget
from denver.ui.widgets.home_dashboard import DenverHomeTabWidget


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["-platform", "offscreen"])
    return app


def test_activity_panel_tab_structure(qapp):
    """Assert ActivityPanelWidget has exactly 5 tabs and Home is leftmost & default."""
    panel = ActivityPanelWidget()
    assert panel.tabs.count() == 5, f"Expected 5 tabs, got {panel.tabs.count()}"

    # Tab 0: Home tab
    assert "HOME" in panel.tabs.tabText(0)
    assert isinstance(panel.tabs.widget(0), DenverHomeTabWidget)
    assert panel.tabs.currentIndex() == 0

    # Remaining tabs preserved in order
    assert "LIVE CHAT" in panel.tabs.tabText(1) or "STREAM" in panel.tabs.tabText(1)
    assert "TASK WORKFLOWS" in panel.tabs.tabText(2)
    assert "SCHEDULED ROUTINES" in panel.tabs.tabText(3)
    assert "PLUGINS" in panel.tabs.tabText(4)


def test_quick_action_buttons_route_to_shared_controller(qapp):
    """Assert clicking Quick Action buttons dispatches submit_command to shared UIController."""
    mock_controller = MagicMock(spec=UIController)
    panel = ActivityPanelWidget(controller=mock_controller)
    home_tab = panel.home_tab

    quick_actions = home_tab.quick_actions_card
    assert quick_actions.controller is mock_controller

    # 1. New Task
    quick_actions.task_btn.click()
    mock_controller.submit_command.assert_called_with("create task New Task")

    # 2. Reminder
    quick_actions.reminder_btn.click()
    mock_controller.submit_command.assert_called_with("create reminder in 10 minutes Check progress")

    # 3. Notes
    quick_actions.notes_btn.click()
    mock_controller.submit_command.assert_called_with("create note Quick Note: Added from dashboard")

    # 4. Calendar (TODO stub, emits action_triggered with calendar_todo)
    emitted = []
    quick_actions.action_triggered.connect(lambda act: emitted.append(act))
    quick_actions.calendar_btn.click()
    assert "calendar_todo" in emitted


def test_five_tabs_switching_and_stream_focus(qapp):
    """Assert switching between all 5 tabs and returning does not raise errors."""
    mock_controller = MagicMock(spec=UIController)
    panel = ActivityPanelWidget(controller=mock_controller)

    # Initial state
    assert panel.tabs.currentIndex() == 0

    # Switch across all 5 tabs
    for idx in range(5):
        panel.tabs.setCurrentIndex(idx)
        assert panel.tabs.currentIndex() == idx

    # Switch back to Home (tab 0)
    panel.tabs.setCurrentIndex(0)
    assert panel.tabs.currentIndex() == 0

    # Receiving a stream item switches view to stream tab (tab 1)
    from denver.ui.state import ActivityItem
    test_item = ActivityItem(command_text="diagnostics", response_text="running")
    panel.add_item(test_item)
    assert panel.tabs.currentIndex() == 1
    assert panel.tabs.currentWidget() == panel.stream_tab

    # Can return back to Home cleanly
    panel.tabs.setCurrentWidget(panel.home_tab)
    assert panel.tabs.currentIndex() == 0


def test_spotify_media_card_on_home_tab(qapp):
    """Assert Home tab contains SpotifyMediaCard (replacing SystemPerformanceCard) and controls work."""
    from denver.ui.widgets.home_dashboard import SpotifyMediaCard

    mock_controller = MagicMock(spec=UIController)
    panel = ActivityPanelWidget(controller=mock_controller)
    home_tab = panel.home_tab

    # Assert SpotifyMediaCard is mounted on Home tab
    assert hasattr(home_tab, "spotify_card")
    assert isinstance(home_tab.spotify_card, SpotifyMediaCard)
    assert not hasattr(home_tab, "perf_card")  # SystemPerformanceCard removed from Home tab

    # Test playback signals and controller routing
    spotify_card = home_tab.spotify_card
    emitted = []
    spotify_card.media_action_triggered.connect(lambda act: emitted.append(act))

    spotify_card.play_btn.click()
    assert "play_pause" in emitted

    spotify_card.next_btn.click()
    assert "next_track" in emitted

    spotify_card.prev_btn.click()
    assert "previous_track" in emitted

