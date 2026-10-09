"""Data models for Denver Local Git & Dev Workflow Actions."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class GitStatusResult:
    """Snapshot representation of git repository working tree status."""
    branch: str
    tracking_branch: str | None = None
    ahead: int = 0
    behind: int = 0
    staged_files: list[str] = field(default_factory=list)
    modified_files: list[str] = field(default_factory=list)
    untracked_files: list[str] = field(default_factory=list)
    is_clean: bool = True
    repo_path: str = ""

    def format_display(self) -> str:
        lines = [f"🌿 Git Status: {Path(self.repo_path).name or self.repo_path}"]
        tracking_info = f" -> {self.tracking_branch}" if self.tracking_branch else ""
        ahead_behind = []
        if self.ahead > 0:
            ahead_behind.append(f"ahead {self.ahead}")
        if self.behind > 0:
            ahead_behind.append(f"behind {self.behind}")
        sync_str = f" ({', '.join(ahead_behind)})" if ahead_behind else ""

        lines.append(f"On branch: {self.branch}{tracking_info}{sync_str}")

        if self.is_clean:
            lines.append("Working tree clean — nothing to commit.")
            return "\n".join(lines)

        if self.staged_files:
            lines.append(f"\nChanges staged for commit ({len(self.staged_files)}):")
            for f in self.staged_files:
                lines.append(f"  + {f}")

        if self.modified_files:
            lines.append(f"\nChanges not staged for commit ({len(self.modified_files)}):")
            for f in self.modified_files:
                lines.append(f"  • {f}")

        if self.untracked_files:
            lines.append(f"\nUntracked files ({len(self.untracked_files)}):")
            for f in self.untracked_files:
                lines.append(f"  ? {f}")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch": self.branch,
            "tracking_branch": self.tracking_branch,
            "ahead": self.ahead,
            "behind": self.behind,
            "staged_files": self.staged_files,
            "modified_files": self.modified_files,
            "untracked_files": self.untracked_files,
            "is_clean": self.is_clean,
            "repo_path": self.repo_path,
        }


@dataclass
class GitCommitInfo:
    """Metadata regarding a single Git commit."""
    commit_hash: str
    full_hash: str
    author: str
    date: str
    message: str

    def format_display(self) -> str:
        return f"`{self.commit_hash}` {self.message} ({self.author}, {self.date})"

    def to_dict(self) -> dict[str, Any]:
        return {
            "commit_hash": self.commit_hash,
            "full_hash": self.full_hash,
            "author": self.author,
            "date": self.date,
            "message": self.message,
        }


@dataclass
class GitBranchInfo:
    """Information regarding a local or remote Git branch."""
    name: str
    is_current: bool = False
    commit_hash: str = ""

    def format_display(self) -> str:
        prefix = "* " if self.is_current else "  "
        return f"{prefix}{self.name}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "is_current": self.is_current,
            "commit_hash": self.commit_hash,
        }


@dataclass
class GitDiffSummary:
    """Aggregate statistics for git diff."""
    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0
    diff_stat: str = ""

    def format_display(self) -> str:
        if self.files_changed == 0 and not self.diff_stat.strip():
            return "No changes detected."
        return (
            f"{self.files_changed} file(s) changed, "
            f"+{self.insertions} insertions(+), -{self.deletions} deletions(-)\n\n"
            f"{self.diff_stat}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "files_changed": self.files_changed,
            "insertions": self.insertions,
            "deletions": self.deletions,
            "diff_stat": self.diff_stat,
        }
