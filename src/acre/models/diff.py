"""Diff data models - wrappers around unidiff types."""

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from unidiff import PatchSet, PatchedFile, Hunk


class LineType(Enum):
    """Type of a diff line."""

    CONTEXT = "context"
    ADDITION = "addition"
    DELETION = "deletion"
    HEADER = "header"


@dataclass
class DiffLine:
    """A single line in a diff."""

    line_type: LineType
    content: str
    old_line_no: int | None = None
    new_line_no: int | None = None

    @property
    def line_no(self) -> int | None:
        """Get the relevant line number for this line."""
        if self.line_type == LineType.DELETION:
            return self.old_line_no
        return self.new_line_no

    @property
    def is_deleted(self) -> bool:
        """Check if this is a deleted line."""
        return self.line_type == LineType.DELETION


@dataclass
class DiffHunk:
    """A contiguous block of changes."""

    old_start: int
    old_count: int
    new_start: int
    new_count: int
    header: str
    lines: list[DiffLine] = field(default_factory=list)

    def get_id(self, file_path: str) -> str:
        """Generate a stable identifier for this hunk.

        Uses position info plus first few lines of content for uniqueness.
        """
        content = f"{self.old_start}:{self.old_count}:{self.new_start}:{self.new_count}"
        for line in self.lines[:3]:
            content += line.content
        hash_part = hashlib.md5(content.encode()).hexdigest()[:12]
        return f"{file_path}::{hash_part}"

    @classmethod
    def from_unidiff(cls, hunk: Hunk) -> "DiffHunk":
        """Create DiffHunk from unidiff Hunk."""
        lines = []
        for line in hunk:
            if line.is_added:
                line_type = LineType.ADDITION
            elif line.is_removed:
                line_type = LineType.DELETION
            else:
                line_type = LineType.CONTEXT

            lines.append(
                DiffLine(
                    line_type=line_type,
                    content=line.value.rstrip("\n"),
                    old_line_no=line.source_line_no,
                    new_line_no=line.target_line_no,
                )
            )

        return cls(
            old_start=hunk.source_start,
            old_count=hunk.source_length,
            new_start=hunk.target_start,
            new_count=hunk.target_length,
            header=hunk.section_header or "",
            lines=lines,
        )


@dataclass
class DiffFile:
    """A single file's diff."""

    path: str
    old_path: str | None
    new_path: str | None
    status: Literal["modified", "added", "deleted", "renamed", "untracked"]
    hunks: list[DiffHunk] = field(default_factory=list)
    is_binary: bool = False

    @property
    def added_lines(self) -> int:
        """Count of added lines."""
        return sum(
            1
            for hunk in self.hunks
            for line in hunk.lines
            if line.line_type == LineType.ADDITION
        )

    @property
    def removed_lines(self) -> int:
        """Count of removed lines."""
        return sum(
            1
            for hunk in self.hunks
            for line in hunk.lines
            if line.line_type == LineType.DELETION
        )

    @classmethod
    def from_unidiff(cls, patched_file: PatchedFile) -> "DiffFile":
        """Create DiffFile from unidiff PatchedFile."""
        # Determine status
        if patched_file.is_added_file:
            status = "added"
        elif patched_file.is_removed_file:
            status = "deleted"
        elif patched_file.is_rename:
            status = "renamed"
        else:
            status = "modified"

        # Get paths
        old_path = patched_file.source_file
        new_path = patched_file.target_file

        # Strip a/ and b/ prefixes if present
        if old_path and old_path.startswith("a/"):
            old_path = old_path[2:]
        if new_path and new_path.startswith("b/"):
            new_path = new_path[2:]

        # Determine canonical path
        path = new_path or old_path or "unknown"

        hunks = [DiffHunk.from_unidiff(h) for h in patched_file]

        return cls(
            path=path,
            old_path=old_path if status != "added" else None,
            new_path=new_path if status != "deleted" else None,
            status=status,
            hunks=hunks,
            is_binary=patched_file.is_binary_file,
        )


@dataclass
class DiffSet:
    """Complete set of diffs for a review."""

    files: list[DiffFile]
    source_description: str
    base_ref: str | None = None
    head_ref: str | None = None

    @property
    def total_added(self) -> int:
        """Total lines added across all files."""
        return sum(f.added_lines for f in self.files)

    @property
    def total_removed(self) -> int:
        """Total lines removed across all files."""
        return sum(f.removed_lines for f in self.files)

    @classmethod
    def from_unidiff(
        cls,
        patch_set: PatchSet,
        description: str,
        base_ref: str | None = None,
        head_ref: str | None = None,
    ) -> "DiffSet":
        """Create DiffSet from unidiff PatchSet."""
        files = [DiffFile.from_unidiff(pf) for pf in patch_set]
        return cls(
            files=files,
            source_description=description,
            base_ref=base_ref,
            head_ref=head_ref,
        )
