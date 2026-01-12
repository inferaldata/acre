"""Export format models."""

from dataclasses import dataclass
from enum import Enum

from acre.models.comment import CommentCategory
from acre.models.review import ReviewSession


class ExportFormat(Enum):
    """Supported export formats."""

    MARKDOWN = "markdown"
    JSON = "json"


@dataclass
class ReviewExport:
    """Handles exporting review session to various formats."""

    session: ReviewSession

    def to_markdown(self) -> str:
        """Export to Markdown format optimized for LLM consumption.

        Format matches tuicr:
        1. Opening statement
        2. Commit range (if applicable)
        3. Comment type legend
        4. Session summary (if notes exist)
        5. Numbered comment list
        """
        lines = []

        # Opening statement
        lines.append(
            "I reviewed your code and have the following comments. Please address them."
        )
        lines.append("")

        # Commit range info
        if self.session.diff_source_type == "commit":
            if self.session.diff_source_ref:
                lines.append(f"Reviewing commit: {self.session.diff_source_ref[:7]}")
                lines.append("")
        elif self.session.diff_source_type == "branch":
            if self.session.diff_source_ref:
                lines.append(f"Reviewing changes: {self.session.diff_source_ref}")
                lines.append("")
        elif self.session.diff_source_type == "pr":
            if self.session.diff_source_ref:
                lines.append(f"Reviewing PR #{self.session.diff_source_ref}")
                lines.append("")

        # Comment type legend
        legend_parts = [
            f"{cat.label} ({cat.description})" for cat in CommentCategory
        ]
        lines.append(f"Comment types: {', '.join(legend_parts)}")
        lines.append("")

        # Session summary
        if self.session.notes:
            lines.append(f"Summary: {self.session.notes}")
            lines.append("")

        # Numbered comment list
        comments = self.session.all_comments
        if not comments:
            lines.append("No comments.")
        else:
            for i, comment in enumerate(comments, 1):
                lines.append(comment.to_export_line(i))

        return "\n".join(lines)

    def to_json(self) -> dict:
        """Export to JSON format."""
        return {
            "session_id": self.session.id,
            "repo_path": str(self.session.repo_path),
            "diff_source": {
                "type": self.session.diff_source_type,
                "ref": self.session.diff_source_ref,
            },
            "notes": self.session.notes,
            "files_reviewed": self.session.reviewed_count,
            "files_total": self.session.total_files,
            "comments": [
                {
                    "id": c.id,
                    "category": c.category.value,
                    "file_path": c.file_path,
                    "line_no": c.line_no,
                    "is_deleted_line": c.is_deleted_line,
                    "content": c.content,
                    "created_at": c.created_at.isoformat(),
                }
                for c in self.session.all_comments
            ],
        }
