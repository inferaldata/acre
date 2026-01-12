"""Review session data models."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from acre.models.comment import Comment


@dataclass
class FileReviewState:
    """Review state for a single file."""

    file_path: str
    reviewed: bool = False
    comments: list[Comment] = field(default_factory=list)

    @property
    def comment_count(self) -> int:
        """Number of comments on this file."""
        return len(self.comments)

    def add_comment(self, comment: Comment) -> None:
        """Add a comment to this file."""
        self.comments.append(comment)

    def remove_comment(self, comment_id: str) -> bool:
        """Remove a comment by ID. Returns True if found and removed."""
        for i, c in enumerate(self.comments):
            if c.id == comment_id:
                self.comments.pop(i)
                return True
        return False


@dataclass
class ReviewSession:
    """A complete review session with persistence."""

    repo_path: Path
    diff_source_type: Literal["uncommitted", "staged", "branch", "commit", "pr"]
    diff_source_ref: str | None = None  # branch name, commit sha, PR number
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    notes: str = ""  # Session-level notes/summary

    # State
    files: dict[str, FileReviewState] = field(default_factory=dict)
    current_file_index: int = 0
    scroll_position: int = 0

    @property
    def reviewed_count(self) -> int:
        """Number of files marked as reviewed."""
        return sum(1 for f in self.files.values() if f.reviewed)

    @property
    def total_files(self) -> int:
        """Total number of files in the review."""
        return len(self.files)

    @property
    def all_comments(self) -> list[Comment]:
        """Get all comments across all files, sorted for export."""
        comments = []
        for file_state in self.files.values():
            comments.extend(file_state.comments)
        # Sort by file path, then by line number (file-level comments first)
        return sorted(
            comments, key=lambda c: (c.file_path, c.line_no if c.line_no else 0)
        )

    @property
    def total_comments(self) -> int:
        """Total number of comments."""
        return sum(f.comment_count for f in self.files.values())

    def get_file_state(self, file_path: str) -> FileReviewState:
        """Get or create file review state."""
        if file_path not in self.files:
            self.files[file_path] = FileReviewState(file_path=file_path)
        return self.files[file_path]

    def toggle_reviewed(self, file_path: str) -> bool:
        """Toggle reviewed status for a file. Returns new status."""
        state = self.get_file_state(file_path)
        state.reviewed = not state.reviewed
        self.touch()
        return state.reviewed

    def add_comment(self, comment: Comment) -> None:
        """Add a comment to the appropriate file."""
        state = self.get_file_state(comment.file_path)
        state.add_comment(comment)
        self.touch()

    def remove_comment(self, comment_or_path: Comment | str, comment_id: str | None = None) -> bool:
        """Remove a comment. Returns True if found and removed.

        Can be called as:
            remove_comment(comment)  # Pass Comment object
            remove_comment(file_path, comment_id)  # Pass path and ID
        """
        if isinstance(comment_or_path, Comment):
            file_path = comment_or_path.file_path
            comment_id = comment_or_path.id
        else:
            file_path = comment_or_path
            if comment_id is None:
                return False

        if file_path in self.files:
            if self.files[file_path].remove_comment(comment_id):
                self.touch()
                return True
        return False

    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now()

    def init_files(self, file_paths: list[str]) -> None:
        """Initialize file states for a list of paths."""
        for path in file_paths:
            if path not in self.files:
                self.files[path] = FileReviewState(file_path=path)
