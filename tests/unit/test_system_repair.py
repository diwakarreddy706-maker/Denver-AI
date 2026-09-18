"""Unit tests for Denver Self-Healing Diagnostics & Automated Repair Engine."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from denver.commands.router import IntentRouter
from denver.config.settings import DenverSettings
from denver.health.repair import RepairAction, RepairReport, SystemRepairManager


def test_system_repair_dry_run(tmp_path: Path) -> None:
    db_path = tmp_path / "test_denver.sqlite3"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE test_table (id INTEGER PRIMARY KEY, text TEXT);")
    conn.commit()
    conn.close()

    log_path = tmp_path / "test.log"
    log_path.write_text("sample log line\n" * 100)

    settings = DenverSettings(
        database_path=db_path,
        log_file_path=log_path,
    )

    manager = SystemRepairManager(settings=settings)
    report = manager.run_repair(dry_run=True)

    assert isinstance(report, RepairReport)
    assert report.issues_detected >= 0
    assert report.issues_fixed == 0  # Dry run doesn't apply fixes


def test_system_repair_apply(tmp_path: Path) -> None:
    db_path = tmp_path / "test_denver.sqlite3"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE test_table (id INTEGER PRIMARY KEY, text TEXT);")
    conn.commit()
    conn.close()

    log_path = tmp_path / "test.log"
    log_path.write_text("sample log line\n" * 100)

    settings = DenverSettings(
        database_path=db_path,
        log_file_path=log_path,
    )

    manager = SystemRepairManager(settings=settings)
    report = manager.run_repair(dry_run=False)

    assert isinstance(report, RepairReport)
    spoken = report.format_spoken_summary()
    assert isinstance(spoken, str)
    assert "System" in spoken or "repair" in spoken or "optimal" in spoken


def test_intent_router_system_repair_intents() -> None:
    router = IntentRouter()

    intents = [
        "repair system",
        "repair system issues",
        "fix system health",
        "auto repair system",
        "run auto repair",
        "system repair",
        "diagnose and repair",
        "repair denver",
    ]

    for phrase in intents:
        res = router.route(phrase)
        assert res.intent_name == "system_repair", f"Failed for phrase: '{phrase}'"
