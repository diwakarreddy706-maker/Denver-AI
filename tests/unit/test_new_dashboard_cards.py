"""Unit tests for the three new Home Dashboard cards:
- AudioBriefingCard
- GitDevCard
- DownloadsCleanerCard
"""

from unittest.mock import MagicMock
import pytest
from PySide6.QtWidgets import QApplication

from denver.ui.controller import UIController
from denver.ui.widgets.home_dashboard import (
    AudioBriefingCard,
    DenverHomeTabWidget,
    DownloadsCleanerCard,
    GitDevCard,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["-platform", "offscreen"])
    return app


def test_audio_briefing_card_toggle_and_actions(qapp):
    mock_controller = MagicMock(spec=UIController)
    card = AudioBriefingCard(controller=mock_controller)

    # Defaults to morning mode
    assert card._briefing_mode == "morning"
    assert "Morning" in card.play_btn.text()

    # Trigger Play Morning Briefing
    card.play_btn.click()
    mock_controller.submit_command.assert_called_with("play morning briefing")

    # Toggle to Night mode
    card.btn_night.click()
    assert card._briefing_mode == "night"
    assert "Evening" in card.play_btn.text()

    # Trigger Play Evening Briefing
    card.play_btn.click()
    mock_controller.submit_command.assert_called_with("evening briefing")

    # Refresh counts
    card.refresh_counts(events_count=3, unread_emails=5)
    assert "3 events today" in card.counts_lbl.text()
    assert "5 unread emails" in card.counts_lbl.text()


def test_git_dev_card_actions(qapp):
    mock_controller = MagicMock(spec=UIController)
    card = GitDevCard(controller=mock_controller)

    # Check branch dropdown
    assert card.branch_combo.count() >= 1
    assert "main" in [card.branch_combo.itemText(i) for i in range(card.branch_combo.count())]

    # Switch branch
    card.branch_combo.setCurrentText("dev")
    card.switch_btn.click()
    mock_controller.submit_command.assert_called_with("git switch branch dev")

    # Commit action
    card.commit_btn.click()
    mock_controller.submit_command.assert_called_with("git commit staged changes")

    # Status action
    card.status_btn.click()
    mock_controller.submit_command.assert_called_with("git status")


def test_downloads_cleaner_card_actions(qapp):
    mock_controller = MagicMock(spec=UIController)
    card = DownloadsCleanerCard(controller=mock_controller)

    # Dry run is primary / default action
    assert "Dry Run" in card.dry_run_btn.text()
    card.dry_run_btn.click()
    mock_controller.submit_command.assert_called_with("organize downloads dry run")

    # Organize Now
    card.organize_btn.click()
    mock_controller.submit_command.assert_called_with("organize downloads")


def test_home_tab_contains_all_three_cards(qapp):
    mock_controller = MagicMock(spec=UIController)
    home_tab = DenverHomeTabWidget(controller=mock_controller)

    assert hasattr(home_tab, "briefing_card")
    assert isinstance(home_tab.briefing_card, AudioBriefingCard)

    assert hasattr(home_tab, "git_card")
    assert isinstance(home_tab.git_card, GitDevCard)

    assert hasattr(home_tab, "cleaner_card")
    assert isinstance(home_tab.cleaner_card, DownloadsCleanerCard)
