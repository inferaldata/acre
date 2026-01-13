"""Main review screen."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from acre.core.session import save_session
from acre.models.comment import Comment
from acre.models.diff import DiffSet
from acre.models.review import ReviewSession
from acre.core.session import get_git_user
from acre.widgets.comment_input import CommentCancelled, CommentDeleted, CommentInput, CommentSubmitted
from acre.widgets.comment_panel import CommentPanel, CommentSelected
from acre.widgets.diff_view import DiffView
from acre.widgets.file_list import FileList, FileSelected, FileReviewToggled
from acre.widgets.llm_sidebar import LLMSidebar
from acre.widgets.resolved_panel import HunkResurrected, ResolvedPanel
from acre.widgets.splitter import VerticalSplitter
from acre.widgets.status_bar import StatusBar


class MainScreen(Screen):
    """Primary review screen with diff view and file list."""

    BINDINGS = [
        # Quit
        Binding("q", "quit", "Quit", show=True),
        Binding(":,q", "quit", "Quit", show=False),
        # Navigation
        Binding("j", "scroll_down", "Down", show=False),
        Binding("k", "scroll_up", "Up", show=False),
        Binding("ctrl+d", "half_page_down", "Half Page Down", show=False),
        Binding("ctrl+u", "half_page_up", "Half Page Up", show=False),
        Binding("ctrl+f", "page_down", "Page Down", show=False),
        Binding("ctrl+b", "page_up", "Page Up", show=False),
        Binding("g", "go_top", "Top", show=False),
        Binding("G", "go_bottom", "Bottom", show=False),
        # File/Hunk navigation
        Binding("}", "next_file", "} Next File", key_display="}", show=False),
        Binding("{", "prev_file", "{ Prev File", key_display="{", show=False),
        Binding("]", "next_hunk", "] Next Hunk", key_display="]", show=False),
        Binding("[", "prev_hunk", "[ Prev Hunk", key_display="[", show=False),
        # Comment navigation
        Binding("n", "next_comment", "Next", show=True),
        Binding("N", "prev_comment", "Prev", show=True),
        # Review actions
        Binding("r", "toggle_reviewed", "Reviewed", show=True),
        Binding("c", "add_comment", "Comment", show=True),
        Binding("C", "add_file_comment", "File Comment", show=False),
        Binding("e", "edit_comment", "Edit", show=True),
        Binding("x", "delete_comment", "Delete", show=True),
        # Panel control
        Binding("tab", "toggle_panel", "Toggle Panel", show=False),
        Binding("p", "toggle_comments", "Comments", show=True),
        Binding("`", "toggle_llm", "LLM", key_display="`", show=False),
        # Hunk resolution
        Binding("-", "resolve_or_toggle", "Resolve", key_display="-", show=True),
        # LLM actions
        Binding("a", "analyze", "Analyze", show=False),
        # Semantic mode
        Binding("s", "toggle_semantic", "Semantic", show=False),
        # Export (removed colon command for now - not supported in Textual this way)
    ]

    CSS = """
    MainScreen {
        layout: horizontal;
    }

    #file-panel {
        width: 35;
        min-width: 20;
        max-width: 60;
    }

    #diff-panel {
        width: 1fr;
    }

    #comment-panel {
        width: 40;
        min-width: 30;
        max-width: 60;
        border-left: solid $primary;
        display: none;
    }

    #llm-panel {
        width: 50;
        min-width: 30;
        max-width: 80;
        border-left: solid $accent;
        display: none;
    }

    #resolved-panel {
        width: 40;
        min-width: 30;
        max-width: 60;
        border-left: solid $success;
        display: none;
    }

    #status-bar {
        dock: bottom;
        height: 1;
        background: $primary;
    }
    """

    def __init__(
        self,
        diff_set: DiffSet,
        session: ReviewSession,
        semantic_mode: bool = False,
    ):
        super().__init__()
        self.diff_set = diff_set
        self.session = session
        self._show_file_panel = True
        self._show_comment_panel = False
        self._show_llm_panel = False
        self._show_resolved_panel = False
        self._semantic_mode = semantic_mode

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield FileList(
                diff_set=self.diff_set,
                session=self.session,
                id="file-panel",
            )
            yield VerticalSplitter(target_id="file-panel", min_size=20, max_size=60)
            yield DiffView(
                diff_set=self.diff_set,
                session=self.session,
                id="diff-panel",
            )
            yield CommentPanel(
                session=self.session,
                id="comment-panel",
            )
            yield ResolvedPanel(
                session=self.session,
                id="resolved-panel",
            )
            yield LLMSidebar(id="llm-panel")
        yield StatusBar(session=self.session, id="status-bar")
        yield Footer()

    @property
    def diff_view(self) -> DiffView:
        """Get the diff view widget."""
        return self.query_one("#diff-panel", DiffView)

    @property
    def file_list(self) -> FileList:
        """Get the file list widget."""
        return self.query_one("#file-panel", FileList)

    @property
    def comment_panel(self) -> CommentPanel:
        """Get the comment panel widget."""
        return self.query_one("#comment-panel", CommentPanel)

    @property
    def llm_panel(self) -> LLMSidebar:
        """Get the LLM sidebar widget."""
        return self.query_one("#llm-panel", LLMSidebar)

    @property
    def resolved_panel(self) -> ResolvedPanel:
        """Get the resolved panel widget."""
        return self.query_one("#resolved-panel", ResolvedPanel)

    # Navigation actions - delegate to diff view
    def action_scroll_down(self) -> None:
        self.diff_view.action_scroll_down()

    def action_scroll_up(self) -> None:
        self.diff_view.action_scroll_up()

    def action_half_page_down(self) -> None:
        self.diff_view.action_half_page_down()

    def action_half_page_up(self) -> None:
        self.diff_view.action_half_page_up()

    def action_page_down(self) -> None:
        self.diff_view.action_page_down()

    def action_page_up(self) -> None:
        self.diff_view.action_page_up()

    def action_go_top(self) -> None:
        self.diff_view.action_go_top()

    def action_go_bottom(self) -> None:
        self.diff_view.action_go_bottom()

    def action_next_file(self) -> None:
        self.diff_view.action_next_file()
        self._sync_file_selection()

    def action_prev_file(self) -> None:
        self.diff_view.action_prev_file()
        self._sync_file_selection()

    def action_next_hunk(self) -> None:
        self.diff_view.action_next_hunk()

    def action_prev_hunk(self) -> None:
        self.diff_view.action_prev_hunk()

    def action_next_comment(self) -> None:
        self.diff_view.action_next_comment()

    def action_prev_comment(self) -> None:
        self.diff_view.action_prev_comment()

    def _sync_file_selection(self) -> None:
        """Sync file list selection with current file in diff view."""
        current_file = self.diff_view.current_file
        if current_file:
            self.file_list.select_file(current_file.path)

    # Review actions
    def action_toggle_reviewed(self) -> None:
        """Toggle reviewed status for current file."""
        current_file = self.diff_view.current_file
        if current_file:
            self.session.toggle_reviewed(current_file.path)
            self.diff_view.refresh_current_file()
            self.file_list.refresh_file(current_file.path)
            self._update_status()
            self._auto_save()
            self.notify(
                f"Marked {current_file.path} as "
                f"{'reviewed' if self.session.files[current_file.path].reviewed else 'not reviewed'}"
            )

    def action_add_comment(self) -> None:
        """Add a line comment at cursor position or selection."""
        current_file = self.diff_view.current_file
        if not current_file:
            self.notify("No file selected", severity="warning")
            return

        # Check for visual selection
        start_line, end_line = self.diff_view.selection_range
        if start_line is not None and end_line is not None:
            # Use selection range
            self._open_comment_input(
                current_file.path,
                line_no=start_line,
                line_no_end=end_line,
            )
            # Clear visual selection after opening comment
            self.diff_view.clear_selection()
        else:
            # Use current line
            current_line = self.diff_view.current_line
            line_no = current_line.line_no if current_line else None
            is_deleted = False

            if current_line:
                from acre.models.diff import LineType
                is_deleted = current_line.line_type == LineType.DELETION

            self._open_comment_input(current_file.path, line_no, is_deleted_line=is_deleted)

    def action_add_file_comment(self) -> None:
        """Add a file-level comment."""
        current_file = self.diff_view.current_file
        if not current_file:
            self.notify("No file selected", severity="warning")
            return

        self._open_comment_input(current_file.path, line_no=None)

    def action_edit_comment(self) -> None:
        """Edit the comment at cursor position."""
        comment = self.diff_view.get_comment_at_cursor()
        if not comment:
            self.notify("No comment at cursor", severity="warning")
            return

        self._open_comment_input(
            comment.file_path,
            line_no=comment.line_no,
            line_no_end=comment.line_no_end,
            edit_comment=comment,
        )

    def action_delete_comment(self) -> None:
        """Delete the comment at cursor position."""
        comment = self.diff_view.get_comment_at_cursor()
        if not comment:
            self.notify("No comment at cursor", severity="warning")
            return

        self.session.remove_comment(comment)
        self.diff_view.refresh_current_file()
        self.file_list.refresh_file(comment.file_path)
        self._update_status()
        self._auto_save()

        if self._show_comment_panel:
            self.comment_panel.refresh_comments()

        self.notify(f"Deleted {comment.category.label} comment")

    def _get_hunk_context(self, line_no: int | None = None) -> str | None:
        """Get the hunk content for context when commenting.

        Returns the content of the hunk containing the given line,
        or the current hunk if no line specified.
        """
        current_file = self.diff_view.current_file
        if not current_file:
            return None

        # Find which hunk contains this line
        current_hunk = None
        if line_no is not None:
            for hunk in current_file.hunks:
                for line in hunk.lines:
                    if line.line_no == line_no:
                        current_hunk = hunk
                        break
                if current_hunk:
                    break
        else:
            # For file-level comments, use first hunk or None
            if current_file.hunks:
                current_hunk = current_file.hunks[0]

        if not current_hunk:
            return None

        # Format hunk content
        from acre.models.diff import LineType
        lines = [f"@@ {current_hunk.header} @@"]
        for line in current_hunk.lines:
            prefix = {
                LineType.ADDITION: "+",
                LineType.DELETION: "-",
                LineType.CONTEXT: " ",
            }.get(line.line_type, " ")
            # Strip trailing whitespace to ensure YAML uses literal block style
            lines.append(f"{prefix}{line.content}".rstrip())
        return "\n".join(lines)

    def _open_comment_input(
        self,
        file_path: str,
        line_no: int | None = None,
        line_no_end: int | None = None,
        is_deleted_line: bool = False,
        edit_comment: Comment | None = None,
    ) -> None:
        """Open the inline comment input panel."""
        # Remove any existing comment input
        for widget in self.query("CommentInput"):
            widget.remove()

        # Get hunk context for new comments (not edits)
        context = None
        if edit_comment is None:
            context = self._get_hunk_context(line_no)

        # Create and mount the comment input
        comment_input = CommentInput(
            file_path=file_path,
            line_no=line_no,
            line_no_end=line_no_end,
            is_deleted_line=is_deleted_line,
            edit_comment=edit_comment,
            context=context,
            id="comment-input-panel",
        )
        self.mount(comment_input)

    def on_comment_submitted(self, event: CommentSubmitted) -> None:
        """Handle comment submission from inline input."""
        comment = event.comment

        if event.is_edit:
            # Comment was already updated in place, just refresh views
            action = "Updated"
        else:
            # New comment - add to session
            self.session.add_comment(comment)
            action = "Added"

        self.diff_view.refresh_current_file()
        self.file_list.refresh_file(comment.file_path)
        self._update_status()
        self._auto_save()

        # Refresh comment panel if visible
        if self._show_comment_panel:
            self.comment_panel.refresh_comments()

        # Remove the comment input
        for widget in self.query("CommentInput"):
            widget.remove()

        cat_label = comment.category.label
        location = comment.location_short
        self.notify(f"{action} {cat_label} comment at {location}")

    def on_comment_cancelled(self, event: CommentCancelled) -> None:
        """Handle comment cancellation."""
        for widget in self.query("CommentInput"):
            widget.remove()

    def on_comment_deleted(self, event: CommentDeleted) -> None:
        """Handle comment deletion from input panel."""
        comment = event.comment
        self.session.remove_comment(comment)
        self.diff_view.refresh_current_file()
        self.file_list.refresh_file(comment.file_path)
        self._update_status()
        self._auto_save()

        if self._show_comment_panel:
            self.comment_panel.refresh_comments()

        # Remove the comment input
        for widget in self.query("CommentInput"):
            widget.remove()

        self.notify(f"Deleted {comment.category.label} comment")

    def on_file_selected(self, event: FileSelected) -> None:
        """Handle file selection from file list."""
        self.diff_view.select_file(event.file_path)

    def on_file_review_toggled(self, event: FileReviewToggled) -> None:
        """Handle file review toggle from file list."""
        file_path = event.file_path
        self.session.toggle_reviewed(file_path)
        self.file_list.refresh_file(file_path)
        # Also refresh diff view if it's showing this file
        if self.diff_view.current_file and self.diff_view.current_file.path == file_path:
            self.diff_view.refresh_current_file()
        self._update_status()
        self._auto_save()
        reviewed = self.session.files[file_path].reviewed if file_path in self.session.files else False
        self.notify(f"Marked {file_path} as {'reviewed' if reviewed else 'not reviewed'}")

    def action_toggle_panel(self) -> None:
        """Toggle file panel visibility."""
        file_panel = self.query_one("#file-panel")
        self._show_file_panel = not self._show_file_panel
        file_panel.display = self._show_file_panel

    def action_toggle_comments(self) -> None:
        """Toggle comment panel visibility."""
        comment_panel = self.query_one("#comment-panel")
        self._show_comment_panel = not self._show_comment_panel
        comment_panel.display = self._show_comment_panel
        if self._show_comment_panel:
            self.comment_panel.refresh_comments()

    def action_toggle_llm(self) -> None:
        """Toggle LLM sidebar visibility."""
        llm_panel = self.query_one("#llm-panel")
        self._show_llm_panel = not self._show_llm_panel
        llm_panel.display = self._show_llm_panel

    def action_resolve_or_toggle(self) -> None:
        """Resolve selected hunks, or toggle resolved panel if no selection."""
        if self.diff_view.visual_mode:
            # Resolve selected hunks
            self._resolve_selected_hunks()
        else:
            # Toggle resolved panel
            self._toggle_resolved_panel()

    def _toggle_resolved_panel(self) -> None:
        """Toggle resolved panel visibility."""
        resolved_panel = self.query_one("#resolved-panel")
        self._show_resolved_panel = not self._show_resolved_panel
        resolved_panel.display = self._show_resolved_panel
        if self._show_resolved_panel:
            self.resolved_panel.refresh_resolved()
            self.resolved_panel.focus()

    def _resolve_selected_hunks(self) -> None:
        """Mark selected hunks as resolved."""
        from acre.models.review import ResolvedHunk

        current_file = self.diff_view.current_file
        if not current_file:
            return

        selected_hunks = self.diff_view.get_selected_hunks()
        if not selected_hunks:
            self.notify("No hunks in selection", severity="warning")
            return

        file_state = self.session.get_file_state(current_file.path)
        resolved_count = 0

        for hunk_idx, hunk in selected_hunks:
            hunk_id = hunk.get_id(current_file.path)
            if not file_state.is_hunk_resolved(hunk_id):
                # Create preview from first 3 lines
                preview_lines = []
                for line in hunk.lines[:3]:
                    prefix = "+" if line.line_type.value == "addition" else "-" if line.line_type.value == "deletion" else " "
                    preview_lines.append(f"{prefix}{line.content}")

                resolved = ResolvedHunk(
                    hunk_id=hunk_id,
                    file_path=current_file.path,
                    old_start=hunk.old_start,
                    old_count=hunk.old_count,
                    new_start=hunk.new_start,
                    new_count=hunk.new_count,
                    header=hunk.header,
                    lines_preview="\n".join(preview_lines),
                    resolved_by=get_git_user(),
                )
                file_state.resolve_hunk(resolved)
                resolved_count += 1

        if resolved_count > 0:
            self.diff_view.clear_selection()
            self.diff_view._build_line_index()  # Rebuild to exclude resolved
            self.diff_view.refresh_current_file()
            if self._show_resolved_panel:
                self.resolved_panel.refresh_resolved()
            self._auto_save()

            plural = "s" if resolved_count > 1 else ""
            self.notify(f"Resolved {resolved_count} hunk{plural}")

    def on_hunk_resurrected(self, event: HunkResurrected) -> None:
        """Handle hunk resurrection from resolved panel."""
        file_state = self.session.files.get(event.file_path)
        if file_state and file_state.unresolve_hunk(event.hunk_id):
            # Rebuild diff view to show resurrected hunk
            self.diff_view._build_line_index()
            self.diff_view.refresh_current_file()
            self.resolved_panel.refresh_resolved()
            self._auto_save()
            self.notify("Hunk resurrected")

    def action_analyze(self) -> None:
        """Analyze current file with Claude."""
        current_file = self.diff_view.current_file
        if not current_file:
            self.notify("No file selected", severity="warning")
            return

        # Show LLM panel if not visible
        if not self._show_llm_panel:
            self.action_toggle_llm()

        # Get current hunk if we have a specific line
        current_hunk = None
        current_line = self.diff_view.current_line
        if current_line:
            # Find which hunk contains this line
            for hunk in current_file.hunks:
                if current_line in hunk.lines:
                    current_hunk = hunk
                    break

        # Trigger analysis
        self.llm_panel.analyze_file(current_file, current_hunk)

    def action_toggle_semantic(self) -> None:
        """Toggle semantic diff mode."""
        self._semantic_mode = not self._semantic_mode
        self.diff_view.set_semantic_mode(self._semantic_mode)
        mode_str = "enabled" if self._semantic_mode else "disabled"
        self.notify(f"Semantic diff mode {mode_str}")

    def action_export_clipboard(self) -> None:
        """Export review to clipboard."""
        from acre.models.export import ReviewExport
        import pyperclip

        export = ReviewExport(self.session)
        markdown = export.to_markdown()
        try:
            pyperclip.copy(markdown)
            self.notify("Review exported to clipboard!")
        except Exception as e:
            self.notify(f"Failed to copy to clipboard: {e}", severity="error")

    def action_quit(self) -> None:
        """Quit the application."""
        self.app.exit()

    def _update_status(self) -> None:
        """Update status bar."""
        status_bar = self.query_one("#status-bar", StatusBar)
        status_bar.refresh_status()

    def _auto_save(self) -> None:
        """Auto-save the session."""
        try:
            # Use app's method to include diff context and mark our save
            from acre.app import AcreApp
            if isinstance(self.app, AcreApp):
                self.app.save_session_with_context()
            else:
                save_session(self.session)
        except Exception as e:
            self.notify(f"Auto-save failed: {e}", severity="warning")

    def on_comment_selected(self, event: CommentSelected) -> None:
        """Handle comment selection from comment panel."""
        comment = event.comment
        # Navigate to the file containing the comment
        self.diff_view.select_file(comment.file_path)
        # Select the comment in the diff view
        self.diff_view.select_comment(comment.id)
        # Scroll to the comment line if it has one
        if comment.line_no:
            self.diff_view.scroll_to_line(comment.line_no)
