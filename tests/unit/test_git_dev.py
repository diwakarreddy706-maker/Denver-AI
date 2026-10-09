"""Unit tests for Denver Local Git & Dev Workflow Actions (Step 6)."""

import os
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import AsyncMock, MagicMock
import pytest

from denver.automation.executor import AutomationExecutor
from denver.automation.git.models import (
    GitBranchInfo,
    GitCommitInfo,
    GitDiffSummary,
    GitStatusResult,
)
from denver.automation.git.service import GitDevService, get_git_service
from denver.commands.router import IntentRouter
from denver.commands.service import CommandEngineService, CommandRequest


def init_test_git_repo(repo_dir: Path) -> None:
    """Helper to initialize a clean git repository for testing."""
    subprocess.run(["git", "init"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Denver Tester"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "tester@denver.ai"], cwd=str(repo_dir), check=True, capture_output=True)


def test_git_models():
    """Verify GitStatusResult, GitCommitInfo, GitBranchInfo, and GitDiffSummary serialization and display."""
    status = GitStatusResult(
        branch="feature/ai-agent",
        tracking_branch="origin/feature/ai-agent",
        ahead=1,
        behind=0,
        staged_files=["src/main.py"],
        modified_files=["README.md"],
        untracked_files=["temp.log"],
        is_clean=False,
        repo_path="C:/Projects/Denver",
    )
    d = status.to_dict()
    assert d["branch"] == "feature/ai-agent"
    assert d["ahead"] == 1
    assert "src/main.py" in d["staged_files"]
    disp = status.format_display()
    assert "On branch: feature/ai-agent" in disp
    assert "ahead 1" in disp
    assert "+ src/main.py" in disp

    commit = GitCommitInfo(
        commit_hash="7a1b2c3",
        full_hash="7a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b",
        author="Denver",
        date="2026-10-02",
        message="feat: add git automation",
    )
    assert "`7a1b2c3` feat: add git automation" in commit.format_display()
    assert commit.to_dict()["commit_hash"] == "7a1b2c3"

    branch = GitBranchInfo(name="main", is_current=True, commit_hash="1234567")
    assert "* main" in branch.format_display()
    assert branch.to_dict()["is_current"] is True

    diff = GitDiffSummary(files_changed=2, insertions=15, deletions=3, diff_stat="2 files changed")
    assert "+15 insertions(+), -3 deletions(-)" in diff.format_display()


def test_git_service_non_git_repo():
    """Verify GitDevService gracefully handles non-git directory."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        service = GitDevService(default_repo_path=tmp_dir)
        assert service.is_git_available() is True
        assert service.is_git_repository(tmp_dir) is False

        ok, status_res, msg = service.get_status(tmp_dir)
        assert ok is False
        assert "not a valid Git repository" in msg


def test_git_service_lifecycle_in_repo():
    """Verify git status, commit, log, branch, switch, and diff on a live repo."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_path = Path(tmp_dir)
        init_test_git_repo(repo_path)

        service = GitDevService(default_repo_path=repo_path)
        assert service.is_git_repository(repo_path) is True

        # 1. Create initial file & commit
        readme = repo_path / "README.md"
        readme.write_text("# Test Repo")

        ok_commit, msg_commit = service.commit(message="Initial commit", stage_all=True, repo_path=repo_path)
        assert ok_commit is True
        assert "Successfully committed" in msg_commit

        # 2. Check git status (should be clean)
        ok_stat, stat_res, msg_stat = service.get_status(repo_path=repo_path)
        assert ok_stat is True
        assert stat_res.is_clean is True

        # 3. Check git log
        ok_log, commits, msg_log = service.get_log(limit=5, repo_path=repo_path)
        assert ok_log is True
        assert len(commits) == 1
        assert commits[0].message == "Initial commit"

        # 4. Check git branches
        ok_br, branches, msg_br = service.get_branches(repo_path=repo_path)
        assert ok_br is True
        assert len(branches) >= 1
        active_branch = [b for b in branches if b.is_current][0]

        # 5. Create new branch
        ok_new_br, msg_new_br = service.create_branch("feature/test-branch", checkout=True, repo_path=repo_path)
        assert ok_new_br is True
        assert "Created and switched" in msg_new_br

        # 6. Switch back to original branch
        ok_switch, msg_switch = service.switch_branch(active_branch.name, repo_path=repo_path)
        assert ok_switch is True
        assert f"Switched to branch '{active_branch.name}'" in msg_switch

        # 7. Modify file and check diff
        readme.write_text("# Test Repo\nUpdated line.")
        ok_diff, diff_res, msg_diff = service.get_diff_summary(staged=False, repo_path=repo_path)
        assert ok_diff is True
        assert diff_res.files_changed >= 1


@pytest.mark.asyncio
async def test_automation_executor_git():
    """Verify AutomationExecutor handles git_status and git_log."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_path = Path(tmp_dir)
        init_test_git_repo(repo_path)
        (repo_path / "file.txt").write_text("Hello")

        from denver.automation.models import AutomationRequest
        executor = AutomationExecutor()

        # 1. Commit file
        req_commit = AutomationRequest(
            action_name="git_commit",
            params={"repo_path": str(repo_path), "message": "Initial commit", "stage_all": True},
        )
        res_commit = await executor.execute(req_commit)
        assert res_commit.success is True

        # 2. Query git_status
        req_status = AutomationRequest(
            action_name="git_status",
            params={"repo_path": str(repo_path)},
        )
        res_status = await executor.execute(req_status)
        assert res_status.success is True
        assert res_status.data["is_clean"] is True

        # 3. Query git_log
        req_log = AutomationRequest(
            action_name="git_log",
            params={"repo_path": str(repo_path), "limit": 3},
        )
        res_log = await executor.execute(req_log)
        assert res_log.success is True
        assert res_log.data["count"] == 1


@pytest.mark.asyncio
async def test_command_service_git():
    """Verify CommandEngineService executes registered git actions."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_path = Path(tmp_dir)
        init_test_git_repo(repo_path)
        (repo_path / "app.py").write_text("print('test')")

        executor = AutomationExecutor()
        memory_mock = MagicMock()
        memory_mock.record_habit = AsyncMock()
        memory_mock.log_audit = AsyncMock()
        service = CommandEngineService(memory_service=memory_mock, automation_executor=executor)

        # 1. Process git status command
        res_stat = await service.process_command(CommandRequest(raw_text=f"git status in {repo_path}"))
        assert res_stat.success is True
        assert res_stat.action_name == "git_status"

        # 2. Process git branches command
        res_br = await service.process_command(CommandRequest(raw_text=f"git branches in {repo_path}"))
        assert res_br.success is True
        assert res_br.action_name == "git_branches"


def test_intent_router_git():
    """Verify natural language commands route to git intents."""
    router = IntentRouter()

    # 1. Status
    i1 = router.route("git status")
    assert i1.action_name == "git_status"

    i2 = router.route("what is my git status")
    assert i2.action_name == "git_status"

    i3 = router.route("what changed in git")
    assert i3.action_name == "git_status"

    # 2. Branches
    i4 = router.route("git branches")
    assert i4.action_name == "git_branches"

    i5 = router.route("what branch am i on")
    assert i5.action_name == "git_branches"

    # 3. Log
    i6 = router.route("git log")
    assert i6.action_name == "git_log"

    i7 = router.route("what were the last 3 commits")
    assert i7.action_name == "git_log"
    assert i7.params["limit"] == 3

    # 4. Diff
    i8 = router.route("git diff")
    assert i8.action_name == "git_diff"
    assert i8.params["staged"] is False

    i9 = router.route("git staged diff")
    assert i9.action_name == "git_diff"
    assert i9.params["staged"] is True

    # 5. Create & Switch Branch
    i10 = router.route("create branch feature/login")
    assert i10.action_name == "git_create_branch"
    assert i10.params["branch"] == "feature/login"

    i11 = router.route("checkout branch main")
    assert i11.action_name == "git_switch_branch"
    assert i11.params["branch"] == "main"

    # 6. Commit
    i12 = router.route("git commit 'fix: resolve race condition'")
    assert i12.action_name == "git_commit"
    assert "race condition" in i12.params["message"]

    i13 = router.route("commit all changes with message 'chore: update deps'")
    assert i13.action_name == "git_commit"
    assert i13.params["stage_all"] is True
    assert "update deps" in i13.params["message"]
