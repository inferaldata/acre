"""Comment input widget for adding and editing review comments."""

from datetime import datetime

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Label, Select, Static, TextArea

from acre.core.session import get_git_user
from acre.models.comment import Comment, CommentCategory


class CommentSubmitted(Message):
    """Message sent when a comment is submitted."""

    def __init__(self, comment: Comment, is_edit: bool = False):
        super().__init__()
        self.comment = comment
        self.is_edit = is_edit


class CommentCancelled(Message):
    """Message sent when comment input is cancelled."""

    pass


class CommentDeleted(Message):
    """Message sent when a comment is deleted."""

    def __init__(self, comment: Comment):
        super().__init__()
        self.comment = comment


class CommentInput(Widget):
    """Multiline comment input panel - pinned to bottom."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("ctrl+enter", "submit", "Submit", show=False),
    ]

    DEFAULT_CSS = """
    CommentInput {
        dock: bottom;
        height: auto;
        min-height: 10;
        max-height: 20;
        background: $surface;
        border-top: solid $primary;
        padding: 1;
    }

    CommentInput #comment-header {
        height: 1;
        background: $primary-darken-2;
        padding: 0 1;
        margin-bottom: 1;
    }

    CommentInput #comment-location {
        color: $text-muted;
    }

    CommentInput #controls-row {
        height: 3;
        margin-bottom: 1;
    }

    CommentInput #category-select {
        width: 20;
        margin-right: 1;
    }

    CommentInput #button-row {
        height: 3;
        align: right middle;
    }

    CommentInput Button {
        margin-left: 1;
    }

    CommentInput #delete-btn {
        background: $error;
    }

    CommentInput #comment-textarea {
        height: 6;
        min-height: 4;
        max-height: 12;
    }

    CommentInput #action-hint {
        height: 1;
        color: $text-muted;
        margin-top: 1;
    }
    """

    def __init__(
        self,
        file_path: str,
        line_no: int | None = None,
        line_no_end: int | None = None,
        is_deleted_line: bool = False,
        edit_comment: Comment | None = None,
        context: str | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.file_path = file_path
        self.line_no = line_no
        self.line_no_end = line_no_end
        self.is_deleted_line = is_deleted_line
        self.edit_comment = edit_comment  # If set, we're editing an existing comment
        self.context = context  # Hunk content for LLM context

    def compose(self) -> ComposeResult:
        # Header with location
        if self.edit_comment:
            mode = "Edit comment"
            location = self.edit_comment.location
        elif self.line_no is None:
            mode = "New comment"
            location = f"`{self.file_path}`"
        elif self.line_no_end is not None and self.line_no_end != self.line_no:
            mode = "New comment"
            start, end = min(self.line_no, self.line_no_end), max(self.line_no, self.line_no_end)
            location = f"`{self.file_path}:{start}-{end}`"
        elif self.is_deleted_line:
            mode = "New comment"
            location = f"`{self.file_path}:~{self.line_no}`"
        else:
            mode = "New comment"
            location = f"`{self.file_path}:{self.line_no}`"

        yield Static(f"{mode} on {location}", id="comment-header")

        # Category selector row
        with Horizontal(id="controls-row"):
            initial_category = self.edit_comment.category.value if self.edit_comment else CommentCategory.NOTE.value
            yield Select(
                [
                    (cat.label, cat.value)
                    for cat in CommentCategory
                ],
                value=initial_category,
                id="category-select",
                allow_blank=False,
            )

        # Text area for multiline input
        initial_text = self.edit_comment.content if self.edit_comment else ""
        yield TextArea(
            initial_text,
            id="comment-textarea",
        )

        # Action buttons
        with Horizontal(id="button-row"):
            if self.edit_comment:
                yield Button("Delete", id="delete-btn", variant="error")
            yield Button("Cancel", id="cancel-btn", variant="default")
            yield Button("Save (Ctrl+Enter)", id="submit-btn", variant="primary")

        yield Static("Ctrl+Enter: save | Esc: cancel | Tab: navigate", id="action-hint")

    def on_mount(self) -> None:
        """Focus the textarea when mounted."""
        self.query_one("#comment-textarea", TextArea).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "submit-btn":
            self._submit_comment()
        elif event.button.id == "cancel-btn":
            self.action_cancel()
        elif event.button.id == "delete-btn":
            self._delete_comment()

    def action_cancel(self) -> None:
        """Cancel comment input."""
        self.post_message(CommentCancelled())

    def action_submit(self) -> None:
        """Submit the comment."""
        self._submit_comment()

    def _submit_comment(self) -> None:
        """Create and submit the comment."""
        textarea = self.query_one("#comment-textarea", TextArea)
        category_select = self.query_one("#category-select", Select)

        content = textarea.text.strip()
        if not content:
            self.notify("Comment cannot be empty", severity="warning")
            return

        category = CommentCategory(category_select.value)

        if self.edit_comment:
            # Update existing comment
            comment = self.edit_comment
            comment.category = category
            comment.content = content
            comment.updated_at = datetime.now()
            self.post_message(CommentSubmitted(comment, is_edit=True))
        else:
            # Create new comment
            # Normalize line range
            line_no = self.line_no
            line_no_end = self.line_no_end
            if line_no is not None and line_no_end is not None:
                line_no, line_no_end = min(line_no, line_no_end), max(line_no, line_no_end)
                if line_no == line_no_end:
                    line_no_end = None  # Single line, no range

            comment = Comment(
                content=content,
                file_path=self.file_path,
                category=category,
                author=get_git_user(),
                line_no=line_no,
                line_no_end=line_no_end,
                is_deleted_line=self.is_deleted_line,
                context=self.context,
            )
            self.post_message(CommentSubmitted(comment, is_edit=False))

    def _delete_comment(self) -> None:
        """Delete the comment being edited."""
        if self.edit_comment:
            self.post_message(CommentDeleted(self.edit_comment))
