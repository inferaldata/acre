"""Diff view widget with vim-style navigation and visual selection."""

from rich.markup import escape as rich_escape
from rich.text import Text
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static

from acre.core.semantic import SemanticDiffProvider, SemanticAnalysis
from acre.models.comment import Comment
from acre.models.diff import DiffFile, DiffHunk, DiffLine, DiffSet, LineType
from acre.models.review import ReviewSession


class CommentAction(Message):
    """Message for comment actions (edit/delete)."""

    def __init__(self, action: str, comment: Comment):
        super().__init__()
        self.action = action  # "edit" or "delete"
        self.comment = comment


class SelectionChanged(Message):
    """Message sent when line selection changes."""

    def __init__(self, start_line: int | None, end_line: int | None, file_path: str | None):
        super().__init__()
        self.start_line = start_line
        self.end_line = end_line
        self.file_path = file_path


class DiffView(VerticalScroll):
    """Infinite scroll diff viewer with vim keybindings and visual selection."""

    # Disable native text selection - we use our own visual mode
    ALLOW_SELECT = False

    BINDINGS = [
        Binding("v", "toggle_visual", "Visual Mode", show=False),
        Binding("escape", "cancel_selection", "Cancel", show=False),
        Binding("V", "visual_line", "Visual Line", show=False),
        Binding("n", "next_comment", "Next", show=True),
        Binding("N", "prev_comment", "Prev", show=True),
    ]

    DEFAULT_CSS = """
    DiffView {
        background: $background;
    }

    DiffView .file-header {
        background: $primary-darken-2;
        color: $text;
        padding: 0 1;
        text-style: bold;
    }

    DiffView .file-reviewed {
        background: $success-darken-2;
    }

    DiffView .hunk-header {
        background: $surface-darken-1;
        color: $text-muted;
        padding: 0 1;
    }

    DiffView .diff-content {
        padding: 0 1;
    }

    DiffView .inline-comment {
        background: $warning-darken-3;
        padding: 0 1;
        margin: 0 0 0 4;
        border-left: thick $warning;
    }
    """

    def __init__(
        self,
        diff_set: DiffSet,
        session: ReviewSession,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.diff_set = diff_set
        self.session = session
        self._current_file_index = 0
        self._current_line_index = 0  # Line index within current file's diff lines
        self._file_positions: dict[int, int] = {}  # file_index -> scroll position
        self._all_lines: list[tuple[int, int, "DiffLine"]] = []  # (file_idx, hunk_idx, line)
        self._semantic_mode = False
        self._semantic_provider = SemanticDiffProvider()
        # Visual mode state
        self._visual_mode = False
        self._visual_anchor_index: int | None = None  # Line index where visual mode started
        # Mouse selection state
        self._mouse_selecting = False
        self._mouse_anchor_index: int | None = None
        # Comment selection state
        self._selected_comment_id: str | None = None
        self._build_line_index()

    def _build_line_index(self) -> None:
        """Build a flat index of all diff lines for navigation."""
        self._all_lines = []
        for file_idx, file in enumerate(self.diff_set.files):
            if not file.is_binary:
                for hunk_idx, hunk in enumerate(file.hunks):
                    for line in hunk.lines:
                        self._all_lines.append((file_idx, hunk_idx, line))

    def _get_file_lines(self, file_index: int) -> list[DiffLine]:
        """Get all diff lines for a specific file."""
        lines = []
        if 0 <= file_index < len(self.diff_set.files):
            file = self.diff_set.files[file_index]
            if not file.is_binary:
                for hunk in file.hunks:
                    lines.extend(hunk.lines)
        return lines

    @property
    def visual_mode(self) -> bool:
        """Check if visual mode is active."""
        return self._visual_mode

    @property
    def selection_range(self) -> tuple[int | None, int | None]:
        """Get the current selection range as (start_line_no, end_line_no).

        Returns line numbers, not indices. Returns (None, None) if no selection.
        """
        if not self._visual_mode or self._visual_anchor_index is None:
            return (None, None)

        file_lines = self._get_file_lines(self._current_file_index)
        if not file_lines:
            return (None, None)

        anchor_idx = self._visual_anchor_index
        current_idx = self._current_line_index

        # Get actual line numbers
        start_idx = min(anchor_idx, current_idx)
        end_idx = max(anchor_idx, current_idx)

        if start_idx < 0 or end_idx >= len(file_lines):
            return (None, None)

        start_line = file_lines[start_idx].line_no
        end_line = file_lines[end_idx].line_no

        return (start_line, end_line)

    def action_toggle_visual(self) -> None:
        """Toggle visual mode for line selection."""
        if self._visual_mode:
            self._visual_mode = False
            self._visual_anchor_index = None
        else:
            self._visual_mode = True
            self._visual_anchor_index = self._current_line_index
        self.refresh_current_file()
        self._notify_selection_changed()

    def action_visual_line(self) -> None:
        """Start visual line mode (same as v for now)."""
        self.action_toggle_visual()

    def action_cancel_selection(self) -> None:
        """Cancel visual mode and comment selection."""
        changed = False
        if self._visual_mode:
            self._visual_mode = False
            self._visual_anchor_index = None
            changed = True
        if self._selected_comment_id is not None:
            self._selected_comment_id = None
            changed = True
        if changed:
            self.refresh_current_file()
            self._notify_selection_changed()

    def _notify_selection_changed(self) -> None:
        """Post a message about selection change."""
        start, end = self.selection_range
        file_path = self.current_file.path if self.current_file else None
        self.post_message(SelectionChanged(start, end, file_path))

    def _is_line_selected(self, line_index: int) -> bool:
        """Check if a line index is within the current selection."""
        if not self._visual_mode or self._visual_anchor_index is None:
            return False

        anchor = self._visual_anchor_index
        current = self._current_line_index
        start = min(anchor, current)
        end = max(anchor, current)

        return start <= line_index <= end

    def compose(self):
        """Render only the current file."""
        if self.diff_set.files:
            yield self._render_file(self.diff_set.files[self._current_file_index], self._current_file_index)

    def _build_file_content(self, file: DiffFile, index: int) -> str:
        """Build the markup content for a file's diff."""
        file_state = self.session.files.get(file.path)
        reviewed = file_state.reviewed if file_state else False

        # Build content
        lines = []

        # File header - escape path to prevent markup interpretation
        status_icon = {"modified": "M", "added": "A", "deleted": "D", "renamed": "R"}[
            file.status
        ]
        escaped_path = rich_escape(file.path)
        review_mark = " [green]✓[/green]" if reviewed else ""
        semantic_mark = " [cyan][S][/cyan]" if self._semantic_mode else ""
        visual_mark = " [magenta][V][/magenta]" if self._visual_mode and index == self._current_file_index else ""
        lines.append(
            f"[bold]{status_icon} {escaped_path}{review_mark}{semantic_mark}{visual_mark}[/bold] "
            f"[dim]+{file.added_lines} -{file.removed_lines}[/dim]"
        )

        # Show semantic analysis summary if enabled
        if self._semantic_mode and not file.is_binary:
            analysis = self._get_semantic_analysis(file)
            if analysis and analysis.is_supported and analysis.has_structural_changes:
                lines.append("[cyan]Structural changes:[/cyan]")
                for line in analysis.summary().split("\n"):
                    lines.append(f"  [cyan]{rich_escape(line)}[/cyan]")
                lines.append("")

        # Show file-level comments (line_no is None) at the top
        if file_state:
            file_level_comments = [c for c in file_state.comments if c.line_no is None]
            if file_level_comments:
                for comment in file_level_comments:
                    lines.append(self._format_inline_comment(comment))
                lines.append("")  # Blank line after file-level comments

        if file.is_binary:
            lines.append("[dim]Binary file[/dim]")
        else:
            line_idx = 0  # Track line index for selection highlighting
            for hunk in file.hunks:
                # Hunk header - escape header content
                hunk_info = f"@@ -{hunk.old_start},{hunk.old_count} +{hunk.new_start},{hunk.new_count} @@"
                if hunk.header:
                    hunk_info += f" {rich_escape(hunk.header)}"
                lines.append(f"[dim]{hunk_info}[/dim]")

                # Diff lines with inline comments
                for diff_line in hunk.lines:
                    is_selected = index == self._current_file_index and self._is_line_selected(line_idx)
                    is_cursor = index == self._current_file_index and line_idx == self._current_line_index
                    line_text = self._format_diff_line(diff_line, file.path, is_selected, is_cursor)
                    lines.append(line_text)

                    # Add inline comments after the line they're attached to
                    if file_state and diff_line.line_no:
                        for comment in file_state.comments:
                            # For range comments, show on first line of range
                            # For single-line comments, show on the exact line
                            if comment.is_range:
                                show = diff_line.line_no == comment.line_range[0]
                            else:
                                show = comment.line_no == diff_line.line_no
                            if show:
                                lines.append(self._format_inline_comment(comment))

                    line_idx += 1

        lines.append("")  # Blank line between files

        return "\n".join(lines)

    def _render_file(self, file: DiffFile, index: int) -> Widget:
        """Render a single file's diff as a widget."""
        content = self._build_file_content(file, index)

        container = Static(
            Text.from_markup(content),
            classes="diff-content",
            id=f"file-{index}",
        )
        return container

    def _format_diff_line(self, diff_line: DiffLine, file_path: str, is_selected: bool = False, is_cursor: bool = False) -> str:
        """Format a single diff line with colors, selection, and comment markers."""
        prefix = {
            LineType.ADDITION: "+",
            LineType.DELETION: "-",
            LineType.CONTEXT: " ",
            LineType.HEADER: " ",
        }[diff_line.line_type]

        color = {
            LineType.ADDITION: "green",
            LineType.DELETION: "red",
            LineType.CONTEXT: "",
            LineType.HEADER: "dim",
        }[diff_line.line_type]

        # Line number
        line_no = diff_line.line_no
        line_no_str = f"{line_no:4d}" if line_no else "    "

        # Check for comments on this line - use colored bar prefix
        comment_bar = " "  # Default: space
        file_state = self.session.files.get(file_path)
        if file_state and line_no:
            for comment in file_state.comments:
                if comment.covers_line(line_no):
                    # Color based on comment category
                    bar_colors = {
                        "note": "blue",
                        "suggestion": "cyan",
                        "issue": "red",
                        "praise": "green",
                    }
                    bar_color = bar_colors.get(comment.category.value, "yellow")
                    comment_bar = f"[{bar_color}]┃[/{bar_color}]"
                    break

        # Escape any markup in content
        content = rich_escape(diff_line.content)

        # Build the line with optional selection/cursor highlighting
        if is_selected:
            # Selection highlight - use reverse video effect
            bg = "on magenta"
            if color:
                return f"{comment_bar}[{bg}][dim]{line_no_str}[/dim] [{color}]{prefix}{content}[/{color}][/{bg}]"
            else:
                return f"{comment_bar}[{bg}][dim]{line_no_str}[/dim] {prefix}{content}[/{bg}]"
        elif is_cursor and not self._visual_mode:
            # Cursor line (when not in visual mode)
            bg = "on #333333"
            if color:
                return f"{comment_bar}[{bg}][dim]{line_no_str}[/dim] [{color}]{prefix}{content}[/{color}][/{bg}]"
            else:
                return f"{comment_bar}[{bg}][dim]{line_no_str}[/dim] {prefix}{content}[/{bg}]"
        else:
            if color:
                return f"{comment_bar}[dim]{line_no_str}[/dim] [{color}]{prefix}{content}[/{color}]"
            else:
                return f"{comment_bar}[dim]{line_no_str}[/dim] {prefix}{content}"

    def _format_inline_comment(self, comment: Comment) -> str:
        """Format an inline comment for display."""
        category_colors = {
            "note": "blue",
            "suggestion": "cyan",
            "issue": "red",
            "praise": "green",
            "ai_analysis": "magenta",
        }
        color = category_colors.get(comment.category.value, "yellow")

        # AI comments get a cyan tint
        if comment.is_ai:
            color = "cyan"

        # Truncate long comments
        content = comment.content
        if len(content) > 80:
            content = content[:77] + "..."

        location = comment.location_short
        escaped_content = rich_escape(content)

        # Check if this comment is selected
        is_selected = self._selected_comment_id == comment.id
        bg = "on #444444" if is_selected else ""
        bg_start = f"[{bg}]" if bg else ""
        bg_end = f"[/{bg}]" if bg else ""

        # Author badge
        author_badge = "[dim cyan](AI)[/dim cyan] " if comment.is_ai else ""

        # Format: ┃ [CATEGORY] location (author): content (edit: e | delete: x)
        # Bar at very beginning of line
        lines = [
            f"[{color}]┃[/{color}]     "
            f"{bg_start}"
            f"[bold {color}][{comment.category.label}][/bold {color}] "
            f"[{color}]{location}[/{color}] "
            f"{author_badge}"
            f"{escaped_content} "
            f"[dim](e:edit x:del)[/dim]"
            f"{bg_end}"
        ]

        # Show LLM response if present
        if comment.llm_response:
            response = comment.llm_response
            if len(response) > 100:
                response = response[:97] + "..."
            escaped_response = rich_escape(response)
            lines.append(
                f"[{color}]┃[/{color}]       "
                f"[dim cyan]└─ AI: {escaped_response}[/dim cyan]"
            )

        return "\n".join(lines)

    @property
    def current_file(self) -> DiffFile | None:
        """Get the currently focused file."""
        if 0 <= self._current_file_index < len(self.diff_set.files):
            return self.diff_set.files[self._current_file_index]
        return None

    @property
    def current_file_index(self) -> int:
        """Get index of current file."""
        return self._current_file_index

    @property
    def current_line(self) -> DiffLine | None:
        """Get the current diff line under cursor."""
        file_lines = self._get_file_lines(self._current_file_index)
        if 0 <= self._current_line_index < len(file_lines):
            return file_lines[self._current_line_index]
        return None

    @property
    def current_line_index(self) -> int:
        """Get the current line index within the file."""
        return self._current_line_index

    def get_comment_at_cursor(self) -> Comment | None:
        """Get the comment at the current cursor position, if any.

        First checks if a comment is selected (via n/N navigation), then
        checks for comments covering the current line.
        """
        file_state = self.session.files.get(self.current_file.path) if self.current_file else None
        if not file_state:
            return None

        # First check if we have a selected comment (from n/N navigation)
        if self._selected_comment_id:
            for comment in file_state.comments:
                if comment.id == self._selected_comment_id:
                    return comment

        # Otherwise check for comments on current line
        current_line = self.current_line
        if not current_line or not current_line.line_no:
            return None

        for comment in file_state.comments:
            if comment.covers_line(current_line.line_no):
                return comment
        return None

    def refresh_current_file(self) -> None:
        """Refresh the display of the current file."""
        if not self.current_file:
            return

        content = self._build_file_content(self.current_file, self._current_file_index)
        try:
            file_widget = self.query_one(f"#file-{self._current_file_index}", Static)
            # Use refresh() with the new content via update
            file_widget.update(Text.from_markup(content))
        except Exception:
            # Widget might not exist or be in invalid state, rebuild
            self._rebuild_view()

    def _rebuild_view(self) -> None:
        """Rebuild the entire view for the current file."""
        # Remove all existing file widgets
        for widget in self.query(".diff-content"):
            widget.remove()
        # Mount the current file
        if self.current_file:
            self.mount(self._render_file(self.current_file, self._current_file_index))
            self.scroll_home()

    # Navigation actions
    def action_scroll_down(self) -> None:
        """Scroll down one line and move line cursor."""
        self.scroll_relative(y=1)
        file_lines = self._get_file_lines(self._current_file_index)
        if self._current_line_index < len(file_lines) - 1:
            self._current_line_index += 1
            self.refresh_current_file()
            if self._visual_mode:
                self._notify_selection_changed()

    def action_scroll_up(self) -> None:
        """Scroll up one line and move line cursor."""
        self.scroll_relative(y=-1)
        if self._current_line_index > 0:
            self._current_line_index -= 1
            self.refresh_current_file()
            if self._visual_mode:
                self._notify_selection_changed()

    def action_half_page_down(self) -> None:
        """Scroll down half a page."""
        self.scroll_relative(y=self.size.height // 2)

    def action_half_page_up(self) -> None:
        """Scroll up half a page."""
        self.scroll_relative(y=-(self.size.height // 2))

    def action_page_down(self) -> None:
        """Scroll down a full page."""
        self.scroll_relative(y=self.size.height)

    def action_page_up(self) -> None:
        """Scroll up a full page."""
        self.scroll_relative(y=-self.size.height)

    def action_go_top(self) -> None:
        """Go to top of diff."""
        self.scroll_home()
        self._current_file_index = 0
        self._current_line_index = 0

    def action_go_bottom(self) -> None:
        """Go to bottom of diff."""
        self.scroll_end()
        self._current_file_index = len(self.diff_set.files) - 1
        file_lines = self._get_file_lines(self._current_file_index)
        self._current_line_index = max(0, len(file_lines) - 1)

    def action_next_file(self) -> None:
        """Jump to next file."""
        if self._current_file_index < len(self.diff_set.files) - 1:
            self._current_file_index += 1
            self._current_line_index = 0  # Reset to first line of new file
            self._visual_mode = False  # Clear visual mode when changing files
            self._visual_anchor_index = None
            self._rebuild_view()

    def action_prev_file(self) -> None:
        """Jump to previous file."""
        if self._current_file_index > 0:
            self._current_file_index -= 1
            self._current_line_index = 0  # Reset to first line of new file
            self._visual_mode = False  # Clear visual mode when changing files
            self._visual_anchor_index = None
            self._rebuild_view()

    def action_next_hunk(self) -> None:
        """Jump to next hunk."""
        # TODO: Implement hunk-level navigation
        self.action_scroll_down()

    def action_prev_hunk(self) -> None:
        """Jump to previous hunk."""
        # TODO: Implement hunk-level navigation
        self.action_scroll_up()

    def _scroll_to_file(self, file_index: int) -> None:
        """Scroll to show the specified file."""
        try:
            file_widget = self.query_one(f"#file-{file_index}")
            file_widget.scroll_visible()
        except Exception:
            pass

    def select_file(self, file_path: str) -> None:
        """Select a file by path and show it."""
        for i, file in enumerate(self.diff_set.files):
            if file.path == file_path:
                if i != self._current_file_index:
                    self._current_file_index = i
                    self._current_line_index = 0
                    self._visual_mode = False
                    self._visual_anchor_index = None
                    self._rebuild_view()
                break

    def set_semantic_mode(self, enabled: bool) -> None:
        """Enable or disable semantic diff mode."""
        self._semantic_mode = enabled
        # Refresh current file display
        self.refresh_current_file()

    def _get_semantic_analysis(self, file: DiffFile) -> SemanticAnalysis | None:
        """Get semantic analysis for a file if in semantic mode."""
        if not self._semantic_mode:
            return None

        # Build old and new content from the diff
        old_lines = []
        new_lines = []

        for hunk in file.hunks:
            for diff_line in hunk.lines:
                if diff_line.line_type == LineType.DELETION:
                    old_lines.append(diff_line.content)
                elif diff_line.line_type == LineType.ADDITION:
                    new_lines.append(diff_line.content)
                else:  # Context
                    old_lines.append(diff_line.content)
                    new_lines.append(diff_line.content)

        old_content = "\n".join(old_lines)
        new_content = "\n".join(new_lines)

        if not old_content and not new_content:
            return None

        return self._semantic_provider.analyze(file.path, old_content, new_content)

    def clear_selection(self) -> None:
        """Clear visual selection."""
        if self._visual_mode:
            self._visual_mode = False
            self._visual_anchor_index = None
            self.refresh_current_file()

    def select_comment(self, comment_id: str | None) -> None:
        """Select a comment by ID."""
        if self._selected_comment_id != comment_id:
            self._selected_comment_id = comment_id
            self.refresh_current_file()

    def scroll_to_line(self, line_no: int) -> None:
        """Scroll to show a specific line number."""
        file_lines = self._get_file_lines(self._current_file_index)
        for i, line in enumerate(file_lines):
            if line.line_no == line_no:
                self._current_line_index = i
                # Scroll to roughly the right position
                # Each line is approximately 1 unit of scroll
                self.scroll_to(y=max(0, i - 5))
                self.refresh_current_file()
                break

    def _scroll_to_comment(self, comment: Comment) -> None:
        """Scroll to show a comment, handling file-level comments."""
        if comment.line_no:
            self.scroll_to_line(comment.line_no)
        else:
            # File-level comment: scroll to top of file
            self.scroll_home()
            self._current_line_index = 0

    def action_next_comment(self) -> None:
        """Navigate to the next comment in the current file."""
        if not self.current_file:
            return

        file_state = self.session.files.get(self.current_file.path)
        if not file_state or not file_state.comments:
            self.notify("No comments in this file", severity="warning")
            return

        comments = sorted(file_state.comments, key=lambda c: c.line_no or 0)

        if not self._selected_comment_id:
            # Select first comment
            self._selected_comment_id = comments[0].id
            self._scroll_to_comment(comments[0])
        else:
            # Find current and select next
            current_idx = None
            for i, c in enumerate(comments):
                if c.id == self._selected_comment_id:
                    current_idx = i
                    break

            if current_idx is not None and current_idx < len(comments) - 1:
                next_comment = comments[current_idx + 1]
                self._selected_comment_id = next_comment.id
                self._scroll_to_comment(next_comment)
            else:
                # Wrap to first comment
                self._selected_comment_id = comments[0].id
                self._scroll_to_comment(comments[0])

        self.refresh_current_file()

    def action_prev_comment(self) -> None:
        """Navigate to the previous comment in the current file."""
        if not self.current_file:
            return

        file_state = self.session.files.get(self.current_file.path)
        if not file_state or not file_state.comments:
            self.notify("No comments in this file", severity="warning")
            return

        comments = sorted(file_state.comments, key=lambda c: c.line_no or 0)

        if not self._selected_comment_id:
            # Select last comment
            self._selected_comment_id = comments[-1].id
            self._scroll_to_comment(comments[-1])
        else:
            # Find current and select previous
            current_idx = None
            for i, c in enumerate(comments):
                if c.id == self._selected_comment_id:
                    current_idx = i
                    break

            if current_idx is not None and current_idx > 0:
                prev_comment = comments[current_idx - 1]
                self._selected_comment_id = prev_comment.id
                self._scroll_to_comment(prev_comment)
            else:
                # Wrap to last comment
                self._selected_comment_id = comments[-1].id
                self._scroll_to_comment(comments[-1])

        self.refresh_current_file()

    def on_mouse_down(self, event) -> None:
        """Handle mouse down for line selection."""
        # Stop propagation to prevent native text selection
        event.stop()
        line_idx = self._get_line_index_at_y(event.y)
        if line_idx is not None:
            self._mouse_selecting = True
            self._mouse_anchor_index = line_idx
            self._visual_mode = True
            self._visual_anchor_index = line_idx
            self._current_line_index = line_idx
            self.refresh_current_file()

    def on_mouse_move(self, event) -> None:
        """Handle mouse move for line selection."""
        if self._mouse_selecting:
            # Stop propagation during selection
            event.stop()
            line_idx = self._get_line_index_at_y(event.y)
            if line_idx is not None and line_idx != self._current_line_index:
                self._current_line_index = line_idx
                self.refresh_current_file()

    def on_mouse_up(self, event) -> None:
        """Handle mouse up to end selection."""
        if self._mouse_selecting:
            event.stop()
            self._mouse_selecting = False
            self._notify_selection_changed()

    def _get_line_index_at_y(self, y: int) -> int | None:
        """Get the diff line index at a given y coordinate.

        Simple approximation based on scroll position and line count.
        """
        file_lines = self._get_file_lines(self._current_file_index)
        if not file_lines:
            return None

        # Simple calculation: y + scroll offset, adjusted for header
        # This is approximate but fast
        adjusted_y = y + int(self.scroll_y) - 2  # -2 for file header and first hunk header

        # Clamp to valid range
        line_idx = max(0, min(adjusted_y, len(file_lines) - 1))
        return line_idx
