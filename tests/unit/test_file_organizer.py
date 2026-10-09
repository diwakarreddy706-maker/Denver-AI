"""Unit tests for Denver File System Assistant & Downloads Organizer (Step 5)."""

import os
from pathlib import Path
import tempfile
from unittest.mock import AsyncMock, MagicMock
import pytest

from denver.automation.executor import AutomationExecutor
from denver.automation.files.models import (
    DuplicateGroup,
    FileInfo,
    OrganizationAction,
    OrganizationSummary,
)
from denver.automation.files.organizer import FileOrganizerService, EXTENSION_MAP
from denver.commands.router import IntentRouter
from denver.commands.service import CommandEngineService, CommandRequest


def test_file_models():
    """Verify FileInfo and OrganizationSummary serialization and formatting."""
    info = FileInfo(
        path="C:/Downloads/report.pdf",
        name="report.pdf",
        extension=".pdf",
        category="Documents",
        size_bytes=1048576,  # 1 MB
        modified_at="2026-10-02T10:00:00",
    )
    assert info.category == "Documents"
    assert "1.0 MB" in info.format_size()
    d = info.to_dict()
    assert d["name"] == "report.pdf"
    assert d["category"] == "Documents"

    action = OrganizationAction(
        source_path="C:/Downloads/report.pdf",
        destination_path="C:/Downloads/Documents/report.pdf",
        category="Documents",
    )
    assert action.to_dict()["category"] == "Documents"

    summary = OrganizationSummary(
        target_directory="C:/Downloads",
        total_files_scanned=5,
        files_moved=3,
        bytes_moved=1024,
        by_category={"Documents": 3},
        actions=[action],
        dry_run=False,
    )
    assert summary.total_scanned == 5
    assert summary.total_moved == 3
    display = summary.format_display()
    assert "Files Organized: 3 of 5" in display
    assert "Documents: 3 file(s)" in display


def test_categorization_and_extension_map():
    """Verify extension to category mapping logic."""
    service = FileOrganizerService()
    assert service.get_category("paper.pdf") == "Documents"
    assert service.get_category("sheet.xlsx") == "Documents"
    assert service.get_category("photo.png") == "Images"
    assert service.get_category("clip.mp4") == "Videos"
    assert service.get_category("song.mp3") == "Audio"
    assert service.get_category("archive.zip") == "Archives"
    assert service.get_category("setup.exe") == "Installers"
    assert service.get_category("script.py") == "Code"
    assert service.get_category("unknown.xyz123") == "Others"


def test_organize_directory_dry_run_and_real():
    """Verify scanning, dry run, real file moves, collision resolution, and undo."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        service = FileOrganizerService(default_downloads_path=tmp_path)

        # Create sample files
        doc_file = tmp_path / "notes.txt"
        doc_file.write_text("Meeting notes")

        img_file = tmp_path / "avatar.jpg"
        img_file.write_bytes(b"fake image data")

        code_file = tmp_path / "main.py"
        code_file.write_text("print('hello')")

        # 1. Dry run
        dry_summary = service.organize_directory(target_dir=tmp_path, dry_run=True)
        assert dry_summary.dry_run is True
        assert dry_summary.total_scanned == 3
        assert dry_summary.total_moved == 3
        # Assert files were NOT moved
        assert doc_file.exists()
        assert img_file.exists()
        assert code_file.exists()
        assert not (tmp_path / "Documents").exists()

        # 2. Real organization
        real_summary = service.organize_directory(target_dir=tmp_path, dry_run=False)
        assert real_summary.dry_run is False
        assert real_summary.total_moved == 3

        # Assert files were moved to category folders
        assert not doc_file.exists()
        assert (tmp_path / "Documents" / "notes.txt").exists()
        assert (tmp_path / "Images" / "avatar.jpg").exists()
        assert (tmp_path / "Code" / "main.py").exists()

        # 3. Collision handling: create another file with same name and organize
        new_doc = tmp_path / "notes.txt"
        new_doc.write_text("New notes")
        collision_summary = service.organize_directory(target_dir=tmp_path, dry_run=False)
        assert collision_summary.total_moved == 1
        # Should be renamed with (1) collision counter
        assert (tmp_path / "Documents" / "notes (1).txt").exists()

        # 4. Undo last organization
        ok, reverted_count, msg = service.undo_last_organization()
        assert ok is True
        assert reverted_count == 1
        assert new_doc.exists()


def test_find_large_files():
    """Verify large file scanner finds files above the size threshold."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        service = FileOrganizerService(default_downloads_path=tmp_path)

        # 1 MB file
        f1 = tmp_path / "small.dat"
        f1.write_bytes(b"0" * (1024 * 1024))

        # 3 MB file
        f2 = tmp_path / "medium.dat"
        f2.write_bytes(b"0" * (3 * 1024 * 1024))

        # Threshold 2 MB -> should only find f2
        results = service.find_large_files(target_dir=tmp_path, min_size_mb=2.0)
        assert len(results) == 1
        assert results[0].name == "medium.dat"

        # Threshold 0.5 MB -> should find both, sorted descending
        results_all = service.find_large_files(target_dir=tmp_path, min_size_mb=0.5)
        assert len(results_all) == 2
        assert results_all[0].name == "medium.dat"
        assert results_all[1].name == "small.dat"


def test_find_duplicates():
    """Verify duplicate file detector finds files with identical hash contents."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        service = FileOrganizerService(default_downloads_path=tmp_path)

        content_a = b"Unique content A"
        content_b = b"Identical duplicate content"

        (tmp_path / "orig.txt").write_bytes(content_b)
        (tmp_path / "copy.txt").write_bytes(content_b)
        (tmp_path / "unique.txt").write_bytes(content_a)

        dups = service.find_duplicates(target_dir=tmp_path)
        assert len(dups) == 1
        assert dups[0].count == 2
        filenames = [Path(p).name for p in dups[0].files]
        assert "orig.txt" in filenames
        assert "copy.txt" in filenames


def test_clean_temp_files():
    """Verify cleaning of temporary and scratch files."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        service = FileOrganizerService(default_downloads_path=tmp_path)

        # Create temporary and normal files
        t1 = tmp_path / "scratch.tmp"
        t1.write_text("temp")
        t2 = tmp_path / "old.bak"
        t2.write_text("backup")
        normal = tmp_path / "keep_me.txt"
        normal.write_text("preserve")

        count, freed, msg = service.clean_temp_files(target_dir=tmp_path)
        assert count == 2
        assert not t1.exists()
        assert not t2.exists()
        assert normal.exists()


@pytest.mark.asyncio
async def test_automation_executor_file_organizer():
    """Verify AutomationExecutor integration for file organizer actions."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / "test.pdf").write_bytes(b"%PDF-1.4 demo")
        (tmp_path / "trash.tmp").write_bytes(b"temp")

        from denver.automation.models import AutomationRequest
        executor = AutomationExecutor()

        # 1. organize_downloads (dry_run)
        req = AutomationRequest(
            action_name="organize_downloads",
            params={"path": str(tmp_path), "dry_run": True},
        )
        res = await executor.execute(req)
        assert res.success is True
        assert res.data["dry_run"] is True

        # 2. find_large_files
        req2 = AutomationRequest(
            action_name="find_large_files",
            params={"path": str(tmp_path), "min_size_mb": 0.0},
        )
        res2 = await executor.execute(req2)
        assert res2.success is True
        assert res2.data["count"] >= 1

        # 3. clean_temp_files
        req3 = AutomationRequest(
            action_name="clean_temp_files",
            params={"path": str(tmp_path)},
        )
        res3 = await executor.execute(req3)
        assert res3.success is True
        assert res3.data["cleaned_count"] == 1


@pytest.mark.asyncio
async def test_command_service_file_organizer():
    """Verify CommandEngineService executes registered file organizer actions."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / "data.csv").write_text("a,b,c\n1,2,3")

        executor = AutomationExecutor()
        memory_mock = MagicMock()
        memory_mock.record_habit = AsyncMock()
        memory_mock.log_audit = AsyncMock()
        service = CommandEngineService(memory_service=memory_mock, automation_executor=executor)

        # Execute organize_downloads via process_command
        res = await service.process_command(CommandRequest(raw_text=f"organize folder {tmp_path} dry run"))
        assert res.success is True
        assert res.action_name == "organize_downloads"
        assert res.data.get("dry_run") is True


def test_intent_router_file_organizer():
    """Verify natural language commands route accurately to file organizer intents."""
    router = IntentRouter()

    # 1. Organize commands
    i1 = router.route("organize downloads")
    assert i1.action_name == "organize_downloads"
    assert not i1.params.get("dry_run", False)

    i2 = router.route("organize downloads dry run")
    assert i2.action_name == "organize_downloads"
    assert i2.params.get("dry_run") is True

    i3 = router.route("dry run organize downloads")
    assert i3.action_name == "organize_downloads"
    assert i3.params.get("dry_run") is True

    i4 = router.route(r"organize folder C:\Users\Denver\Downloads")
    assert i4.action_name == "organize_downloads"
    assert "Denver" in i4.params.get("path", "")

    # 2. Large files commands
    i5 = router.route("find large files")
    assert i5.action_name == "find_large_files"

    i6 = router.route("find files larger than 100 mb")
    assert i6.action_name == "find_large_files"
    assert i6.params.get("min_size_mb") == 100.0

    # 3. Duplicate files commands
    i7 = router.route("find duplicate files")
    assert i7.action_name == "find_duplicate_files"

    i8 = router.route("find duplicates")
    assert i8.action_name == "find_duplicate_files"

    # 4. Clean temp files commands
    i9 = router.route("clean temp files")
    assert i9.action_name == "clean_temp_files"

    i10 = router.route("clean temporary files")
    assert i10.action_name == "clean_temp_files"

    # 5. Undo organization
    i11 = router.route("undo file organization")
    assert i11.action_name == "undo_file_organization"

    i12 = router.route("undo downloads organization")
    assert i12.action_name == "undo_file_organization"
