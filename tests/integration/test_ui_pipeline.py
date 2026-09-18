"""Integration tests for Denver Cockpit UI pipeline and backend orchestration."""

import asyncio
import os
import tempfile
import pytest
from PySide6.QtWidgets import QApplication

from denver.app.application import DenverApplication
from denver.config.settings import DenverSettings
from denver.runtime.states import DenverState
from denver.ui.controller import UIController
from denver.ui.window import MainWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["-platform", "offscreen"])
    return app


@pytest.fixture
def temp_db_path():
    fd, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    yield path
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


@pytest.mark.asyncio
async def test_ui_pipeline_end_to_end(qapp, temp_db_path):
    settings = DenverSettings(
        database_path=temp_db_path,
        audio_enabled=False,
        ai_enabled=False,
        privacy_mode=False,
        allow_high_risk_actions=False,
    )
    app = DenverApplication(settings=settings)
    await app.start()

    loop = asyncio.get_running_loop()
    controller = UIController(app_instance=app, event_loop=loop)
    window = MainWindow(controller=controller)

    # Submit a safe command: "what time is it"
    item = await controller.submit_command_async("Denver, what time is it?")
    assert item.success is True
    assert item.action_name == "get_time"
    assert "The current time is" in item.response_text
    assert len(controller.state.activity_history) == 1

    # Submit high-risk command: "lock my computer"
    lock_item = await controller.submit_command_async("Denver, lock my computer")
    assert lock_item.action_name == "lock_workstation"
    assert controller.state.pending_confirmation is not None
    assert controller.state.pending_confirmation.token.startswith("cnf_")
    assert len(controller.state.activity_history) == 2

    # Confirm action
    token = controller.state.pending_confirmation.token
    confirm_item = await controller.submit_command_async(f"Denver, confirm {token}")
    assert confirm_item.action_name == "confirm_action"
    assert confirm_item.success is True
    assert len(controller.state.activity_history) == 3

    # Test Graceful Shutdown
    await app.stop()
    assert app.state_machine.current_state == DenverState.STOPPED
