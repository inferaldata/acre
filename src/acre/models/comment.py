"""Comment data models."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from functools import lru_cache
from uuid import uuid4


# AI author identifier prefix - agents should use format: "Agent (Model/Version)"
# Example: "Agent (Claude/Opus-4.5)"
AI_AUTHOR_PREFIX = "Agent ("


class CommentCategory(Enum):
    """Category of a review comment."""

    NOTE = "note"
    SUGGESTION = "suggestion"
    ISSUE = "issue"
    PRAISE = "praise"
    AI_ANALYSIS = "ai_analysis"

    @property
    def label(self) -> str:
        """Get display label for the category."""
        return self.value.upper()

    @property
    def description(self) -> str:
        """Get description of what this category means."""
        descriptions = {
            CommentCategory.NOTE: "observations",
            CommentCategory.SUGGESTION: "improvements",
            CommentCategory.ISSUE: "problems to fix",
            CommentCategory.PRAISE: "positive feedback",
            CommentCategory.AI_ANALYSIS: "AI-generated analysis",
        }
        return descriptions[self]


@dataclass
class Comment:
    """A review comment."""

    content: str
    file_path: str
    category: CommentCategory = CommentCategory.NOTE
    author: str = "human"  # "human" or "claude"
    line_no: int | None = None  # None = file-level comment
    line_no_end: int | None = None  # End of range (None = single line)
    is_deleted_line: bool = False  # True if commenting on a deleted line
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # Diff context - the hunk content being commented on (for LLM awareness)
    context: str | None = None

    # For tracking LLM interaction
    llm_response: str | None = None
    llm_session_id: str | None = None

    @property
    def is_ai(self) -> bool:
        """Check if this comment was authored by an AI.

        AI authors use format: 'Agent (Model/Version)'
        Example: 'Agent (Claude/Opus-4.5)'
        """
        return self.author.startswith(AI_AUTHOR_PREFIX)

    @property
    def is_range(self) -> bool:
        """Check if this comment covers a line range."""
        return self.line_no is not None and self.line_no_end is not None and self.line_no != self.line_no_end

    @property
    def line_range(self) -> tuple[int, int] | None:
        """Get the line range as (start, end) tuple, or None for file-level."""
        if self.line_no is None:
            return None
        end = self.line_no_end if self.line_no_end is not None else self.line_no
        return (min(self.line_no, end), max(self.line_no, end))

    def covers_line(self, line_no: int) -> bool:
        """Check if this comment covers the given line number."""
        if self.line_no is None:
            return False
        if self.line_no_end is None:
            return self.line_no == line_no
        start, end = self.line_range
        return start <= line_no <= end

    @property
    def location(self) -> str:
        """Get formatted location string for export.

        Format:
        - Deleted lines: `path:~linenum`
        - Line range: `path:start-end`
        - Single line: `path:linenum`
        - File comments: `path`
        """
        if self.line_no is None:
            return f"`{self.file_path}`"
        elif self.is_range:
            start, end = self.line_range
            return f"`{self.file_path}:{start}-{end}`"
        elif self.is_deleted_line:
            return f"`{self.file_path}:~{self.line_no}`"
        else:
            return f"`{self.file_path}:{self.line_no}`"

    @property
    def location_short(self) -> str:
        """Get short location string for inline display."""
        if self.line_no is None:
            return "file"
        elif self.is_range:
            start, end = self.line_range
            return f"L{start}-{end}"
        else:
            return f"L{self.line_no}"

    def to_export_line(self, number: int) -> str:
        """Format comment for export.

        Format: N. **[TYPE]** `location` - content
        """
        return f"{number}. **[{self.category.label}]** {self.location} - {self.content}"
