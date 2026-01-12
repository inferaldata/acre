"""Diff source implementations."""

from abc import ABC, abstractmethod
from pathlib import Path
import subprocess

from acre.core.diff_loader import load_diff_from_text
from acre.models.diff import DiffSet


class DiffSource(ABC):
    """Abstract base class for diff sources."""

    @abstractmethod
    def get_diff(self) -> DiffSet:
        """Fetch and return the diff."""

    @abstractmethod
    def get_description(self) -> str:
        """Human-readable description of the diff source."""

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Type identifier for this source."""


class UncommittedDiffSource(DiffSource):
    """Diff of uncommitted changes (staged + unstaged + untracked)."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path

    def get_diff(self) -> DiffSet:
        """Get diff of all uncommitted changes vs HEAD, including untracked files."""
        from acre.models.diff import DiffFile, DiffHunk, DiffLine, LineType

        # Get diff of tracked files (staged + unstaged)
        result = subprocess.run(
            ["git", "-C", str(self.repo_path), "diff", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )

        # Parse tracked files diff
        diff_set = load_diff_from_text(result.stdout, self.get_description())

        # Get list of untracked files
        untracked = subprocess.run(
            ["git", "-C", str(self.repo_path), "ls-files", "--others", "--exclude-standard"],
            capture_output=True,
            text=True,
            check=True,
        )
        untracked_files = [f for f in untracked.stdout.strip().split("\n") if f]

        # Create DiffFile objects for untracked files with status="untracked"
        for filepath in untracked_files:
            full_path = self.repo_path / filepath
            if full_path.is_file():
                try:
                    content = full_path.read_text()
                    file_lines = content.split("\n")
                    # Remove trailing empty line if file ends with newline
                    if file_lines and file_lines[-1] == "":
                        file_lines = file_lines[:-1]

                    # Create diff lines (all additions)
                    diff_lines = [
                        DiffLine(
                            line_type=LineType.ADDITION,
                            content=line,
                            old_line_no=None,
                            new_line_no=i + 1,
                        )
                        for i, line in enumerate(file_lines)
                    ]

                    # Create hunk
                    hunk = DiffHunk(
                        old_start=0,
                        old_count=0,
                        new_start=1,
                        new_count=len(file_lines),
                        header="",
                        lines=diff_lines,
                    )

                    # Create DiffFile with untracked status
                    diff_file = DiffFile(
                        path=filepath,
                        old_path=None,
                        new_path=filepath,
                        status="untracked",
                        hunks=[hunk],
                    )
                    diff_set.files.append(diff_file)

                except (UnicodeDecodeError, OSError):
                    # Skip binary or unreadable files
                    pass

        return diff_set

    def get_description(self) -> str:
        return "uncommitted changes"

    @property
    def source_type(self) -> str:
        return "uncommitted"


class StagedDiffSource(DiffSource):
    """Diff of staged changes only."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path

    def get_diff(self) -> DiffSet:
        """Get diff of staged changes."""
        result = subprocess.run(
            ["git", "-C", str(self.repo_path), "diff", "--staged"],
            capture_output=True,
            text=True,
            check=True,
        )
        return load_diff_from_text(result.stdout, self.get_description())

    def get_description(self) -> str:
        return "staged changes"

    @property
    def source_type(self) -> str:
        return "staged"


class BranchDiffSource(DiffSource):
    """Diff between current HEAD and a base branch."""

    def __init__(self, repo_path: Path, base: str, head: str = "HEAD"):
        self.repo_path = repo_path
        self.base = base
        self.head = head

    def get_diff(self) -> DiffSet:
        """Get diff between base and head."""
        result = subprocess.run(
            [
                "git",
                "-C",
                str(self.repo_path),
                "diff",
                f"{self.base}...{self.head}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return load_diff_from_text(
            result.stdout,
            self.get_description(),
            base_ref=self.base,
            head_ref=self.head,
        )

    def get_description(self) -> str:
        return f"{self.base}...{self.head}"

    @property
    def source_type(self) -> str:
        return "branch"


class CommitDiffSource(DiffSource):
    """Diff of a specific commit."""

    def __init__(self, repo_path: Path, commit: str):
        self.repo_path = repo_path
        self.commit = commit

    def get_diff(self) -> DiffSet:
        """Get diff of the specified commit."""
        result = subprocess.run(
            [
                "git",
                "-C",
                str(self.repo_path),
                "show",
                self.commit,
                "--format=",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return load_diff_from_text(
            result.stdout,
            self.get_description(),
            head_ref=self.commit,
        )

    def get_description(self) -> str:
        return f"commit {self.commit[:7]}"

    @property
    def source_type(self) -> str:
        return "commit"


class PRDiffSource(DiffSource):
    """Diff from a GitHub PR using gh CLI."""

    def __init__(self, repo_path: Path, pr_number: int):
        self.repo_path = repo_path
        self.pr_number = pr_number

    def get_diff(self) -> DiffSet:
        """Get diff of the PR using gh CLI."""
        result = subprocess.run(
            ["gh", "pr", "diff", str(self.pr_number)],
            capture_output=True,
            text=True,
            cwd=str(self.repo_path),
            check=True,
        )
        return load_diff_from_text(
            result.stdout,
            self.get_description(),
        )

    def get_description(self) -> str:
        return f"PR #{self.pr_number}"

    @property
    def source_type(self) -> str:
        return "pr"


def get_diff_source(
    repo_path: Path,
    staged: bool = False,
    branch: str | None = None,
    commit: str | None = None,
    pr: int | None = None,
) -> DiffSource:
    """Factory function to create the appropriate diff source.

    Priority:
    1. PR (if specified)
    2. Commit (if specified)
    3. Branch (if specified)
    4. Staged (if flag set)
    5. Uncommitted (default)
    """
    if pr is not None:
        return PRDiffSource(repo_path, pr)
    elif commit is not None:
        return CommitDiffSource(repo_path, commit)
    elif branch is not None:
        return BranchDiffSource(repo_path, branch)
    elif staged:
        return StagedDiffSource(repo_path)
    else:
        return UncommittedDiffSource(repo_path)
