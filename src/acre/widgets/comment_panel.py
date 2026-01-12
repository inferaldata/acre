"""Comment panel widget for viewing all review comments."""

from rich.markup import escape as rich_escape
from rich.text import Text
from textual.containers import VerticalScroll
from textual.message import Message
from textual.widgets import Static

from acre.models.comment import Comment
from acre.models.review import ReviewSession


class CommentSelected(Message):
    """Message sent when a comment is selected in the panel."""

    def __init__(self, comment: Comment):
        super().__init__()
        self.comment = comment


class CommentPanel(VerticalScroll):
    """Panel showing all comments in the review session."""

    DEFAULT_CSS = """
    CommentPanel {
        background: $surface;
        border-left: solid $primary;
        min-width: 30;
        max-width: 60;
    }

    CommentPanel .comment-header {
        background: $primary-darken-2;
        color: $text;
        padding: 0 1;
        text-style: bold;
    }

    CommentPanel .comment-item {
        padding: 0 1;
        margin-bottom: 1;
    }

    CommentPanel .comment-location {
        color: $text-muted;
    }

    CommentPanel .comment-content {
        padding-left: 2;
    }

    CommentPanel .no-comments {
        color: $text-muted;
        padding: 1;
        text-align: center;
    }

    CommentPanel .comment-item:hover {
        background: $surface-lighten-1;
    }

    CommentPanel .comment-selected {
        background: $primary-darken-1;
    }
    """

    def __init__(self, session: ReviewSession, **kwargs):
        super().__init__(**kwargs)
        self.session = session
        self._comments_by_id: dict[str, Comment] = {}
        self._selected_comment_id: str | None = None
        self._widget_counter = 0  # For unique widget IDs

    def compose(self):
        """Render the comment list."""
        yield Static("Comments", classes="comment-header")
        yield from self._render_comments()

    def _render_comments(self):
        """Render all comments."""
        self._comments_by_id.clear()
        comments = self.session.all_comments
        if not comments:
            yield Static(
                "No comments yet.\nPress 'c' to add a line comment\nor 'C' for a file comment.",
                classes="no-comments",
            )
            return

        for i, comment in enumerate(comments, 1):
            # Store for lookup
            self._comments_by_id[comment.id] = comment

            # Build comment display
            category_colors = {
                "note": "blue",
                "suggestion": "cyan",
                "issue": "red",
                "praise": "green",
                "ai_analysis": "magenta",
            }
            color = category_colors.get(comment.category.value, "white")

            # AI comments get a cyan tint
            if comment.is_ai:
                color = "cyan"

            # Author badge
            author_badge = "[cyan](AI)[/cyan]" if comment.is_ai else ""

            # Location line
            if comment.line_no is None:
                location = f"{rich_escape(comment.file_path)}"
            elif comment.is_deleted_line:
                location = f"{rich_escape(comment.file_path)}:~{comment.line_no}"
            else:
                location = f"{rich_escape(comment.file_path)}:{comment.line_no}"

            # Format the comment
            content = rich_escape(comment.content)
            markup = (
                f"[{color}]{i}. [{comment.category.label}][/{color}] {author_badge}\n"
                f"[dim]{location}[/dim]\n"
                f"{content}"
            )

            # Add LLM response if present
            if comment.llm_response:
                response = rich_escape(comment.llm_response)
                markup += f"\n[dim cyan]└─ AI: {response}[/dim cyan]"

            # Check if selected
            classes = "comment-item"
            if self._selected_comment_id == comment.id:
                classes += " comment-selected"

            # Use counter for unique widget ID
            self._widget_counter += 1
            widget = Static(
                Text.from_markup(markup),
                classes=classes,
                id=f"comment-widget-{self._widget_counter}",
            )
            # Store comment id as data attribute for click handling
            widget._comment_id = comment.id
            yield widget

    def on_click(self, event) -> None:
        """Handle clicks on comment items."""
        # Find clicked comment item
        widget = event.widget
        while widget and widget is not self:
            if hasattr(widget, "_comment_id"):
                comment_id = widget._comment_id
                if comment_id in self._comments_by_id:
                    self.select_comment(comment_id)
                    self.post_message(CommentSelected(self._comments_by_id[comment_id]))
                break
            widget = widget.parent

    def select_comment(self, comment_id: str | None) -> None:
        """Select a comment by ID."""
        if self._selected_comment_id == comment_id:
            return
        self._selected_comment_id = comment_id
        self.refresh_comments()
        # Scroll selected comment into view - find widget with matching _comment_id
        if comment_id:
            for widget in self.query(".comment-item"):
                if hasattr(widget, "_comment_id") and widget._comment_id == comment_id:
                    widget.scroll_visible()
                    break

    def refresh_comments(self) -> None:
        """Refresh the comment display."""
        # Remove existing comment items - collect first, then remove
        widgets_to_remove = list(self.query(".comment-item, .no-comments"))
        for widget in widgets_to_remove:
            widget.remove()

        # Add new comment widgets
        for widget in self._render_comments():
            self.mount(widget)
