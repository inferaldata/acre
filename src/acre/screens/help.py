"""Help screen showing keybindings."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static


HELP_TEXT = """\
[bold]acre - Agentic Code Review[/bold]

[bold cyan]Navigation[/bold cyan]
  j / k         Scroll down / up
  Ctrl+d / u    Half page down / up
  Ctrl+f / b    Full page down / up
  g / G         Go to top / bottom
  { / }         Previous / next file
  [ / ]         Previous / next hunk

[bold cyan]Review Actions[/bold cyan]
  r             Toggle file as reviewed
  c             Add comment at cursor line
  C             Add file-level comment
  e             Edit comment at cursor
  x             Delete comment at cursor
  n / N         Next / previous comment

[bold cyan]Visual Selection[/bold cyan]
  v / V         Toggle visual mode (select lines)
  Escape        Cancel selection

[bold cyan]Panels[/bold cyan]
  Tab           Toggle file list panel
  p             Toggle comments panel
  `             Toggle LLM sidebar

[bold cyan]Other[/bold cyan]
  a             Analyze with Claude
  s             Toggle semantic diff mode
  ?             Show this help
  q             Quit

[dim]Press Escape or ? to close[/dim]
"""


class HelpScreen(ModalScreen):
    """Modal help screen."""

    BINDINGS = [
        Binding("escape", "close", "Close", show=False),
        Binding("?", "close", "Close", show=False),
        Binding("q", "close", "Close", show=False),
    ]

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }

    HelpScreen > VerticalScroll {
        width: 60;
        height: 80%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield Static(HELP_TEXT)

    def action_close(self) -> None:
        """Close the help screen."""
        self.dismiss()
