"""Status bar widget."""

from textual.widgets import Static

from acre.models.review import ReviewSession


class StatusBar(Static):
    """Status bar showing review progress."""

    DEFAULT_CSS = """
    StatusBar {
        background: $primary;
        color: $text;
        padding: 0 1;
    }
    """

    def __init__(self, session: ReviewSession, **kwargs):
        super().__init__(**kwargs)
        self.session = session

    def on_mount(self) -> None:
        """Update status on mount."""
        self.refresh_status()

    def refresh_status(self) -> None:
        """Refresh the status display."""
        reviewed = self.session.reviewed_count
        total = self.session.total_files
        comments = self.session.total_comments

        # Progress bar style
        progress = reviewed / total if total > 0 else 0
        bar_width = 20
        filled = int(progress * bar_width)
        bar = "\u2588" * filled + "\u2591" * (bar_width - filled)

        # Use plain text for status to avoid markup issues
        status = (
            f"Files: {reviewed}/{total} [{bar}] "
            f"Comments: {comments} "
            f"| j/k:scroll {{/}}:file n/N:comment e:edit x:del c:add q:quit"
        )
        self.update(status)
