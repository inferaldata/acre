"""Main Textual application for acre."""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header

from acre.core.session import get_session_file_path, load_session, save_session
from acre.core.watcher import SessionWatcher
from acre.models.diff import DiffSet
from acre.models.review import ReviewSession
from acre.screens.help import HelpScreen
from acre.screens.main import MainScreen


class AcreApp(App):
    """Agentic Code Review TUI application."""

    TITLE = "acre"
    SUB_TITLE = "Agentic Code Review"

    CSS = """
    Screen {
        background: $surface;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("?", "help", "Help", show=True),
    ]

    def __init__(
        self,
        diff_set: DiffSet,
        session: ReviewSession,
        semantic_mode: bool = False,
    ):
        super().__init__()
        self.diff_set = diff_set
        self.session = session
        self.semantic_mode = semantic_mode
        self._watcher: SessionWatcher | None = None
        self._diff_context = self._generate_diff_context()

    def _generate_diff_context(self) -> str:
        """Generate the diff context for the YAML file."""
        from acre.models.diff import LineType

        lines = []
        for file in self.diff_set.files:
            lines.append(f"# {file.path} ({file.status})")
            for hunk in file.hunks:
                lines.append(f"@@ {hunk.header} @@")
                for line in hunk.lines:
                    prefix = {
                        LineType.ADDITION: "+",
                        LineType.DELETION: "-",
                        LineType.CONTEXT: " ",
                        LineType.HEADER: "",
                    }.get(line.line_type, " ")
                    lines.append(f"{prefix}{line.content}")
            lines.append("")
        return "\n".join(lines)

    def on_mount(self) -> None:
        """Called when app is mounted."""
        # Start file watcher
        session_path = get_session_file_path(self.session)
        self._watcher = SessionWatcher(
            session_path=session_path,
            on_change=self._on_session_file_changed,
        )
        self._watcher.start()

        # Push main screen
        self.push_screen(
            MainScreen(
                diff_set=self.diff_set,
                session=self.session,
                semantic_mode=self.semantic_mode,
            )
        )

    def _on_session_file_changed(self) -> None:
        """Handle external session file changes."""
        # Schedule the reload - use call_later since we're in an async task, not a thread
        self.call_later(self._reload_session)

    def _reload_session(self) -> None:
        """Reload the session from disk and refresh the UI."""
        session_path = get_session_file_path(self.session)
        if not session_path.exists():
            return

        try:
            new_session = load_session(session_path)

            # Merge changes: take new comments and review states from disk
            # but keep the session ID and other metadata
            for file_path, new_state in new_session.files.items():
                if file_path in self.session.files:
                    old_state = self.session.files[file_path]
                    # Update reviewed status if changed
                    old_state.reviewed = new_state.reviewed

                    # Merge comments: keep existing, add new ones
                    existing_ids = {c.id for c in old_state.comments}
                    for comment in new_state.comments:
                        if comment.id not in existing_ids:
                            old_state.comments.append(comment)
                        else:
                            # Update existing comment if it was modified
                            for i, existing in enumerate(old_state.comments):
                                if existing.id == comment.id:
                                    # Check if modified externally (e.g., llm_response added)
                                    if (
                                        comment.llm_response != existing.llm_response
                                        or comment.content != existing.content
                                    ):
                                        old_state.comments[i] = comment
                                    break
                else:
                    # New file state
                    self.session.files[file_path] = new_state

            # Refresh the main screen
            main_screen = self.screen
            if isinstance(main_screen, MainScreen):
                main_screen.diff_view.refresh_current_file()
                main_screen.file_list._build_tree()
                main_screen.file_list.root.expand()
                if main_screen._show_comment_panel:
                    main_screen.comment_panel.refresh_comments()

            self.notify("Session reloaded from external changes")

        except Exception as e:
            self.notify(f"Failed to reload session: {e}", severity="error")

    def save_session_with_context(self) -> None:
        """Save the session with diff context for LLM."""
        save_session(self.session, diff_context=self._diff_context)
        # Mark our save AFTER writing so mtime comparison works
        if self._watcher:
            self._watcher.mark_our_save()

    def action_help(self) -> None:
        """Show help screen."""
        self.push_screen(HelpScreen())

    def on_unmount(self) -> None:
        """Called when app is unmounted."""
        if self._watcher:
            self._watcher.stop()
