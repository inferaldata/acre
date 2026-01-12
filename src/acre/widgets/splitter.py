"""Draggable splitter for resizing panels."""

from textual.events import MouseDown, MouseMove, MouseUp
from textual.widget import Widget
from textual.reactive import reactive


class VerticalSplitter(Widget, can_focus=False):
    """A vertical splitter bar that can be dragged to resize adjacent panels."""

    SCOPED_CSS = False

    DEFAULT_CSS = """
    VerticalSplitter {
        width: 1;
        height: 100%;
        background: $primary;
    }

    VerticalSplitter:hover {
        background: $accent;
    }

    VerticalSplitter.-dragging {
        background: $accent;
    }
    """

    dragging: reactive[bool] = reactive(False)

    def __init__(
        self,
        target_id: str,
        min_size: int = 20,
        max_size: int = 80,
        **kwargs,
    ):
        """Initialize the splitter.

        Args:
            target_id: ID of the widget to resize (the left panel)
            min_size: Minimum width of the target panel
            max_size: Maximum width of the target panel
        """
        super().__init__(**kwargs)
        self.target_id = target_id
        self.min_size = min_size
        self.max_size = max_size
        self._drag_start_x: int | None = None
        self._initial_width: int | None = None

    def on_mouse_down(self, event: MouseDown) -> None:
        """Start dragging."""
        self.dragging = True
        self._drag_start_x = event.screen_x
        target = self.screen.query_one(f"#{self.target_id}")
        self._initial_width = target.size.width
        self.capture_mouse()
        event.stop()

    def on_mouse_move(self, event: MouseMove) -> None:
        """Handle drag movement."""
        if not self.dragging or self._drag_start_x is None:
            return

        delta = event.screen_x - self._drag_start_x
        new_width = self._initial_width + delta

        # Clamp to bounds
        new_width = max(self.min_size, min(self.max_size, new_width))

        # Update target panel width
        target = self.screen.query_one(f"#{self.target_id}")
        target.styles.width = new_width

        event.stop()

    def on_mouse_up(self, event: MouseUp) -> None:
        """Stop dragging."""
        if self.dragging:
            self.dragging = False
            self._drag_start_x = None
            self._initial_width = None
            self.release_mouse()
            event.stop()

    def watch_dragging(self, dragging: bool) -> None:
        """Update styles when dragging state changes."""
        self.set_class(dragging, "-dragging")

    def render(self) -> str:
        """Render empty - the background color is the visual."""
        return ""
