"""Git Dev Workflow Service for Denver Desktop Automation."""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

from denver.automation.git.models import (
    GitBranchInfo,
    GitCommitInfo,
    GitDiffSummary,
    GitStatusResult,
)
from denver.logging.logger import get_logger

logger = get_logger("automation.git")


class GitDevService:
    """Manages local Git workflow operations via secure, direct CLI executions."""

    def __init__(self, default_repo_path: str | Path | None = None) -> None:
        self._default_repo_path = (
            Path(default_repo_path).resolve()
            if default_repo_path
            else Path.cwd().resolve()
        )

    def is_git_available(self) -> bool:
        """Check if git binary is present in system environment."""
        return shutil.which("git") is not None

    def resolve_repo_path(self, repo_path: str | Path | None = None) -> Path:
        """Resolve target directory or fallback to current repository root."""
        if repo_path:
            p = Path(repo_path).resolve()
            if p.exists() and p.is_dir():
                return p
        return self._default_repo_path

    def _run_git(
        self,
        args: list[str],
        repo_path: Path,
    ) -> tuple[int, str, str]:
        """Execute a git command securely without shell interpretation."""
        if not self.is_git_available():
            return 127, "", "Git executable was not found on system PATH."

        try:
            proc = subprocess.run(
                ["git"] + args,
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                check=False,
                encoding="utf-8",
                errors="replace",
            )
            return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
        except Exception as exc:
            logger.error("Failed running git %s in %s: %s", args, repo_path, exc)
            return 1, "", str(exc)

    def is_git_repository(self, repo_path: str | Path | None = None) -> bool:
        """Verify whether directory is part of a valid git working tree."""
        target = self.resolve_repo_path(repo_path)
        code, stdout, _ = self._run_git(["rev-parse", "--is-inside-work-tree"], target)
        return code == 0 and stdout.strip().lower() == "true"

    def get_status(self, repo_path: str | Path | None = None) -> tuple[bool, GitStatusResult | None, str]:
        """Retrieve repository working tree status."""
        target = self.resolve_repo_path(repo_path)
        if not self.is_git_repository(target):
            return False, None, f"Directory '{target.name}' is not a valid Git repository."

        code, stdout, stderr = self._run_git(["status", "--porcelain=v1", "-b"], target)
        if code != 0:
            return False, None, f"Failed getting git status: {stderr or 'Unknown error'}"

        lines = stdout.splitlines()
        branch_name = "unknown"
        tracking_branch = None
        ahead = 0
        behind = 0
        staged: list[str] = []
        modified: list[str] = []
        untracked: list[str] = []

        if lines:
            header = lines[0]
            # e.g., "## main...origin/main [ahead 1, behind 2]" or "## main" or "## HEAD (no branch)"
            if header.startswith("## "):
                branch_part = header[3:]
                # Check for sync info [ahead X, behind Y]
                sync_match = re.search(r"\[(.*?)\]", branch_part)
                if sync_match:
                    sync_info = sync_match.group(1)
                    ahead_m = re.search(r"ahead (\d+)", sync_info)
                    if ahead_m:
                        ahead = int(ahead_m.group(1))
                    behind_m = re.search(r"behind (\d+)", sync_info)
                    if behind_m:
                        behind = int(behind_m.group(1))
                    branch_part = branch_part[:sync_match.start()].strip()

                # Extract branch and tracking
                if "..." in branch_part:
                    parts = branch_part.split("...", 1)
                    branch_name = parts[0].strip()
                    tracking_branch = parts[1].strip()
                else:
                    branch_name = branch_part.strip()

            # Process file entries
            for line in lines[1:]:
                if len(line) < 3:
                    continue
                code_x = line[0]
                code_y = line[1]
                filepath = line[3:].strip()

                if line.startswith("??"):
                    untracked.append(filepath)
                else:
                    if code_x not in {" ", "?"}:
                        staged.append(filepath)
                    if code_y not in {" ", "?"}:
                        modified.append(filepath)

        is_clean = not (staged or modified or untracked)
        res = GitStatusResult(
            branch=branch_name,
            tracking_branch=tracking_branch,
            ahead=ahead,
            behind=behind,
            staged_files=staged,
            modified_files=modified,
            untracked_files=untracked,
            is_clean=is_clean,
            repo_path=str(target),
        )
        return True, res, res.format_display()

    def get_branches(self, repo_path: str | Path | None = None) -> tuple[bool, list[GitBranchInfo], str]:
        """List local branches and identify active branch."""
        target = self.resolve_repo_path(repo_path)
        if not self.is_git_repository(target):
            return False, [], f"Directory '{target.name}' is not a valid Git repository."

        code, stdout, stderr = self._run_git(["branch", "-v", "--no-color"], target)
        if code != 0:
            return False, [], f"Failed listing branches: {stderr or 'Unknown error'}"

        branches: list[GitBranchInfo] = []
        for line in stdout.splitlines():
            line_str = line.strip()
            if not line_str:
                continue
            is_current = line.startswith("*")
            # Parse branch line: "* main 1a2b3c4 Commit subject"
            clean_line = line[2:].strip()
            parts = clean_line.split(maxsplit=2)
            name = parts[0] if parts else clean_line
            commit_hash = parts[1] if len(parts) > 1 else ""

            branches.append(
                GitBranchInfo(
                    name=name,
                    is_current=is_current,
                    commit_hash=commit_hash,
                )
            )

        lines = [f"🌿 Git Branches ({len(branches)}):"]
        for b in branches:
            current_tag = " (active)" if b.is_current else ""
            lines.append(f"  • {b.name} [{b.commit_hash[:7]}]{current_tag}")

        return True, branches, "\n".join(lines)

    def get_log(
        self,
        limit: int = 5,
        repo_path: str | Path | None = None,
    ) -> tuple[bool, list[GitCommitInfo], str]:
        """Retrieve recent commit history formatted for display."""
        target = self.resolve_repo_path(repo_path)
        if not self.is_git_repository(target):
            return False, [], f"Directory '{target.name}' is not a valid Git repository."

        # Use %x09 (tab) separator to prevent delimiter conflicts with commit messages
        code, stdout, stderr = self._run_git(
            ["log", f"-n{limit}", "--pretty=format:%h%x09%H%x09%an%x09%ad%x09%s", "--date=short"],
            target,
        )
        if code != 0:
            return False, [], f"Failed retrieving git log: {stderr or 'Unknown error'}"

        commits: list[GitCommitInfo] = []
        if stdout:
            for line in stdout.splitlines():
                parts = line.split("\t")
                if len(parts) >= 5:
                    commits.append(
                        GitCommitInfo(
                            commit_hash=parts[0],
                            full_hash=parts[1],
                            author=parts[2],
                            date=parts[3],
                            message=parts[4],
                        )
                    )

        if not commits:
            return True, [], "No commit history found in repository."

        lines = [f"📜 Recent Git Commits ({len(commits)}):"]
        for c in commits:
            lines.append(f"  • {c.format_display()}")

        return True, commits, "\n".join(lines)

    def get_diff_summary(
        self,
        staged: bool = False,
        repo_path: str | Path | None = None,
    ) -> tuple[bool, GitDiffSummary | None, str]:
        """Get summary of working tree differences or staged changes."""
        target = self.resolve_repo_path(repo_path)
        if not self.is_git_repository(target):
            return False, None, f"Directory '{target.name}' is not a valid Git repository."

        args = ["diff", "--stat"]
        if staged:
            args.append("--cached")

        code, stdout, stderr = self._run_git(args, target)
        if code != 0:
            return False, None, f"Failed getting git diff: {stderr or 'Unknown error'}"

        if not stdout.strip():
            target_str = "staged changes" if staged else "working tree changes"
            return True, GitDiffSummary(), f"No {target_str} detected."

        # Parse summary line: " 3 files changed, 24 insertions(+), 5 deletions(-)"
        lines = stdout.splitlines()
        last_line = lines[-1] if lines else ""
        files_changed = 0
        insertions = 0
        deletions = 0

        m_files = re.search(r"(\d+)\s+file", last_line)
        if m_files:
            files_changed = int(m_files.group(1))

        m_ins = re.search(r"(\d+)\s+insertion", last_line)
        if m_ins:
            insertions = int(m_ins.group(1))

        m_del = re.search(r"(\d+)\s+deletion", last_line)
        if m_del:
            deletions = int(m_del.group(1))

        diff_summary = GitDiffSummary(
            files_changed=files_changed,
            insertions=insertions,
            deletions=deletions,
            diff_stat=stdout,
        )
        return True, diff_summary, diff_summary.format_display()

    def create_branch(
        self,
        branch_name: str,
        checkout: bool = True,
        repo_path: str | Path | None = None,
    ) -> tuple[bool, str]:
        """Create a new Git branch and optionally switch to it."""
        target = self.resolve_repo_path(repo_path)
        if not self.is_git_repository(target):
            return False, f"Directory '{target.name}' is not a valid Git repository."

        clean_name = branch_name.strip()
        if not clean_name or re.search(r"[\s~^:?*\[\\;]", clean_name):
            return False, f"Invalid branch name '{branch_name}'. Branch names cannot contain spaces or special characters."

        args = ["checkout", "-b", clean_name] if checkout else ["branch", clean_name]
        code, stdout, stderr = self._run_git(args, target)
        if code != 0:
            return False, f"Failed creating branch: {stderr or stdout or 'Unknown error'}"

        msg = f"Created and switched to new branch '{clean_name}'." if checkout else f"Created branch '{clean_name}'."
        return True, msg

    def switch_branch(
        self,
        branch_name: str,
        repo_path: str | Path | None = None,
    ) -> tuple[bool, str]:
        """Switch/checkout an existing Git branch."""
        target = self.resolve_repo_path(repo_path)
        if not self.is_git_repository(target):
            return False, f"Directory '{target.name}' is not a valid Git repository."

        clean_name = branch_name.strip()
        if not clean_name:
            return False, "Branch name cannot be empty."

        code, stdout, stderr = self._run_git(["checkout", clean_name], target)
        if code != 0:
            return False, f"Failed switching branch: {stderr or stdout or 'Unknown error'}"

        return True, f"Switched to branch '{clean_name}'."

    def commit(
        self,
        message: str,
        stage_all: bool = False,
        repo_path: str | Path | None = None,
    ) -> tuple[bool, str]:
        """Create a commit with the specified message, optionally auto-staging tracked/all changes."""
        target = self.resolve_repo_path(repo_path)
        if not self.is_git_repository(target):
            return False, f"Directory '{target.name}' is not a valid Git repository."

        clean_msg = message.strip()
        if not clean_msg:
            return False, "Commit message cannot be empty."

        if stage_all:
            code_add, _, err_add = self._run_git(["add", "-A"], target)
            if code_add != 0:
                return False, f"Failed staging files before commit: {err_add}"

        code, stdout, stderr = self._run_git(["commit", "-m", clean_msg], target)
        if code != 0:
            if "nothing to commit" in (stdout + stderr).lower():
                return False, "Nothing to commit — working tree clean."
            return False, f"Git commit failed: {stderr or stdout or 'Unknown error'}"

        return True, f"Successfully committed: '{clean_msg}'\n{stdout}"


_git_dev_service: GitDevService | None = None


def get_git_service(default_repo_path: str | Path | None = None) -> GitDevService:
    """Obtain or initialize singleton instance of GitDevService."""
    global _git_dev_service
    if _git_dev_service is None or default_repo_path is not None:
        _git_dev_service = GitDevService(default_repo_path=default_repo_path)
    return _git_dev_service
