"""Resolved hunks panel widget for viewing and resurrecting resolved hunks."""

from rich.markup import escape as rich_escape
from rich.text import Text
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.message import Message
from textual.widgets import Static

from acre.models.ocr_adapter import AcreSession


class HunkResurrected(Message):
    """Message sent when a hunk is resurrected."""

    def __init__(self, hunk_id: str, file_path: str):
        super().__init__()
        self.hunk_id = hunk_id
        self.file_path = file_path


class ResolvedPanel(VerticalScroll):
    """Panel showing resolved (hidden) hunks with option to resurrect."""

    BINDINGS = [
        Binding("+", "resurrect", "Resurrect", show=True),
        Binding("=", "resurrect", "Resurrect", show=False),  # Same key without Shift
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]

    DEFAULT_CSS = """
    ResolvedPanel {
        background: $surface;
        border-left: solid $success;
        min-width: 30;
        max-width: 60;
    }

    ResolvedPanel .resolved-header {
        background: $success-darken-2;
        color: $text;
        padding: 0 1;
        text-style: bold;
    }

    ResolvedPanel .resolved-item {
        padding: 0 1;
        margin-bottom: 1;
    }

    ResolvedPanel .resolved-item:hover {
        background: $surface-lighten-1;
    }

    ResolvedPanel .resolved-selected {
        background: $success-darken-1;
    }

    ResolvedPanel .no-resolved {
        color: $text-muted;
        padding: 1;
        text-align: center;
    }
    """

    def __init__(self, session: AcreSession, **kwargs):
        super().__init__(**kwargs)
        self.session = session
        # Resolved hunks are now dicts from the adapter
        self._resolved_by_id: dict[str, dict] = {}
        self._selected_hunk_id: str | None = None
        self._widget_counter = 0

    def compose(self):
        """Render the resolved hunks list."""
        yield Static("Resolved Hunks", classes="resolved-header")
        yield from self._render_resolved()

    def _get_all_resolved(self) -> list[dict]:
        """Get all resolved hunks across all files."""
        resolved = []
        for file_state in self.session.files.values():
            resolved.extend(file_state.resolved_hunks)
        return sorted(resolved, key=lambda r: (r["file_path"], r["old_start"]))

    def _render_resolved(self):
        """Render all resolved hunks."""
        self._resolved_by_id.clear()
        resolved = self._get_all_resolved()

        if not resolved:
            yield Static(
                "No resolved hunks.\nUse '-' with selection\nto resolve hunks.",
                classes="no-resolved",
            )
            return

        for i, rh in enumerate(resolved, 1):
            hunk_id = rh["hunk_id"]
            self._resolved_by_id[hunk_id] = rh

            # Format: file:lines (header preview)
            location = f"{rh['file_path']}:{rh['old_start']}"
            header = rh.get("header", "")
            lines_preview_text = rh.get("lines_preview", "")
            header_preview = header[:30] + "..." if len(header) > 30 else header
            lines_preview = lines_preview_text[:40] + "..." if len(lines_preview_text) > 40 else lines_preview_text

            markup = (
                f"[green]{i}.[/green] [dim]{rich_escape(location)}[/dim]\n"
            )
            if header_preview:
                markup += f"  [dim]@@ {rich_escape(header_preview)} @@[/dim]\n"
            if lines_preview:
                # Show first line of preview
                first_line = lines_preview.split('\n')[0] if lines_preview else ""
                markup += f"  {rich_escape(first_line)}"

            classes = "resolved-item"
            if self._selected_hunk_id == hunk_id:
                classes += " resolved-selected"

            self._widget_counter += 1
            widget = Static(
                Text.from_markup(markup),
                classes=classes,
                id=f"resolved-widget-{self._widget_counter}",
            )
            widget._hunk_id = hunk_id
            yield widget

    def action_resurrect(self) -> None:
        """Resurrect the selected hunk."""
        if self._selected_hunk_id and self._selected_hunk_id in self._resolved_by_id:
            rh = self._resolved_by_id[self._selected_hunk_id]
            self.post_message(HunkResurrected(rh["hunk_id"], rh["file_path"]))

    def action_cursor_down(self) -> None:
        """Move cursor down."""
        resolved = self._get_all_resolved()
        if not resolved:
            return

        if self._selected_hunk_id is None:
            self._selected_hunk_id = resolved[0]["hunk_id"]
        else:
            for i, rh in enumerate(resolved):
                if rh["hunk_id"] == self._selected_hunk_id:
                    if i < len(resolved) - 1:
                        self._selected_hunk_id = resolved[i + 1]["hunk_id"]
                    break
        self.refresh_resolved()

    def action_cursor_up(self) -> None:
        """Move cursor up."""
        resolved = self._get_all_resolved()
        if not resolved:
            return

        if self._selected_hunk_id is None:
            self._selected_hunk_id = resolved[-1]["hunk_id"]
        else:
            for i, rh in enumerate(resolved):
                if rh["hunk_id"] == self._selected_hunk_id:
                    if i > 0:
                        self._selected_hunk_id = resolved[i - 1]["hunk_id"]
                    break
        self.refresh_resolved()

    def on_click(self, event) -> None:
        """Handle clicks on resolved items."""
        widget = event.widget
        while widget and widget is not self:
            if hasattr(widget, "_hunk_id"):
                self._selected_hunk_id = widget._hunk_id
                self.refresh_resolved()
                break
            widget = widget.parent

    def refresh_resolved(self) -> None:
        """Refresh the resolved display."""
        # Remove old items
        widgets_to_remove = list(self.query(".resolved-item, .no-resolved"))
        for widget in widgets_to_remove:
            widget.remove()
        # Add new items
        for widget in self._render_resolved():
            self.mount(widget)
