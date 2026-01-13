"""Main Textual application for acre."""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header

from acre.core.diff_source import get_diff_source
from acre.core.watcher import DiffWatcher, SessionWatcher
from acre.models.diff import DiffSet
from acre.models.ocr_adapter import AcreSession, get_session_path


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
        session: AcreSession,
        semantic_mode: bool = False,
    ):
        super().__init__()
        self.diff_set = diff_set
        self.session = session
        self.semantic_mode = semantic_mode
        self._watcher: SessionWatcher | None = None
        self._diff_watcher: DiffWatcher | None = None

    def _get_session_path(self):
        """Get the session file path."""
        return get_session_path(
            self.session.repo_path,
            self.session.diff_source_type,
            self.session.diff_source_ref,
            self.session.format,
        )

    def on_mount(self) -> None:
        """Called when app is mounted."""
        # Start session file watcher
        session_path = self._get_session_path()
        self._watcher = SessionWatcher(
            session_path=session_path,
            on_change=self._on_session_file_changed,
        )
        self._watcher.start()

        # Start diff watcher for live diff sources (not commit or PR)
        if self.session.diff_source_type not in ("commit", "pr"):
            self._diff_watcher = DiffWatcher(
                repo_path=self.session.repo_path,
                on_change=self._on_diff_changed,
                session_file=session_path,
            )
            self._diff_watcher.start()

        # Push main screen
        from acre.screens.main import MainScreen
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

    def _on_diff_changed(self) -> None:
        """Handle repository file changes - reload the diff."""
        self.call_later(self._reload_diff_and_refresh)

    def _reload_session(self) -> None:
        """Reload the session from disk and refresh the UI.

        With OCR's append-only model, we simply reload the entire review
        since get_visible_activities() handles superseded/retracted items.
        """
        session_path = self._get_session_path()
        if not session_path.exists():
            return

        try:
            # Load the new session state
            new_session = AcreSession.load(session_path, format=self.session.format)

            # Replace the review with the newly loaded one
            self.session.review = new_session.review

            # Reload the diff to pick up any new changes
            self._reload_diff()

            # Refresh the main screen
            from acre.screens.main import MainScreen
            main_screen = self.screen
            if isinstance(main_screen, MainScreen):
                main_screen.diff_view.diff_set = self.diff_set
                main_screen.file_list.diff_set = self.diff_set
                main_screen.diff_view.refresh_current_file()
                main_screen.file_list._build_tree()
                main_screen.file_list.root.expand()
                if main_screen._show_comment_panel:
                    main_screen.comment_panel.refresh_comments()

            self.notify("Session reloaded from external changes")

        except Exception as e:
            self.notify(f"Failed to reload session: {e}", severity="error")

    def _reload_diff(self) -> None:
        """Reload the diff from the repository."""
        try:
            source = get_diff_source(
                repo_path=self.session.repo_path,
                staged=(self.session.diff_source_type == "staged"),
                branch=(self.session.diff_source_ref if self.session.diff_source_type == "branch" else None),
                commit=(self.session.diff_source_ref if self.session.diff_source_type == "commit" else None),
                pr=(int(self.session.diff_source_ref) if self.session.diff_source_type == "pr" else None),
            )
            self.diff_set = source.get_diff()
        except Exception as e:
            self.notify(f"Failed to reload diff: {e}", severity="warning")

    def _reload_diff_and_refresh(self) -> None:
        """Reload the diff and refresh the UI."""
        self._reload_diff()

        # Refresh the main screen with new diff
        from acre.screens.main import MainScreen
        main_screen = self.screen
        if isinstance(main_screen, MainScreen):
            main_screen.diff_view.diff_set = self.diff_set
            main_screen.file_list.diff_set = self.diff_set
            main_screen.diff_view.refresh_current_file()
            main_screen.file_list._build_tree()
            main_screen.file_list.root.expand()

        self.notify("Diff reloaded")

    def save_session(self) -> None:
        """Save the session to disk."""
        session_path = self._get_session_path()
        self.session.save(session_path)
        # Mark our save AFTER writing so mtime comparison works
        if self._watcher:
            self._watcher.mark_our_save()

    def action_help(self) -> None:
        """Show help screen."""
        from acre.screens.help import HelpScreen
        self.push_screen(HelpScreen())

    def on_unmount(self) -> None:
        """Called when app is unmounted."""
        if self._watcher:
            self._watcher.stop()
        if self._diff_watcher:
            self._diff_watcher.stop()
