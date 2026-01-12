"""LLM sidebar widget for displaying Claude responses."""

from rich.markup import escape as rich_escape
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Input, Static, LoadingIndicator
from textual.worker import Worker, get_current_worker

from acre.core.llm import ClaudeCLIBackend, build_analysis_context, get_analysis_prompts
from acre.models.diff import DiffFile, DiffHunk


class LLMSidebar(VerticalScroll):
    """Sidebar for LLM interaction."""

    DEFAULT_CSS = """
    LLMSidebar {
        background: $surface;
        border-left: solid $accent;
        width: 50;
        min-width: 30;
        max-width: 80;
    }

    LLMSidebar .llm-header {
        background: $accent-darken-2;
        color: $text;
        padding: 0 1;
        text-style: bold;
    }

    LLMSidebar .llm-status {
        color: $text-muted;
        padding: 0 1;
    }

    LLMSidebar .llm-response {
        padding: 1;
    }

    LLMSidebar .llm-user-message {
        background: $primary-darken-3;
        padding: 0 1;
        margin-bottom: 1;
    }

    LLMSidebar .llm-assistant-message {
        padding: 0 1;
        margin-bottom: 1;
    }

    LLMSidebar #llm-input {
        dock: bottom;
        height: 3;
        border-top: solid $primary;
    }

    LLMSidebar .llm-prompt-hint {
        color: $text-muted;
        padding: 0 1;
        height: 1;
    }

    LLMSidebar #llm-spinner {
        height: 1;
        padding: 0 1;
    }

    LLMSidebar .llm-streaming {
        color: $accent;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._backend: ClaudeCLIBackend | None = None
        self._messages: list[tuple[str, str]] = []  # (role, content)
        self._current_file: DiffFile | None = None
        self._current_hunk: DiffHunk | None = None
        self._is_loading = False
        self._streaming_content = ""
        self._current_worker: Worker | None = None

    def compose(self) -> ComposeResult:
        yield Static("Claude Assistant", classes="llm-header")
        yield Static("Press 'a' to analyze current file", classes="llm-status", id="llm-status")
        yield LoadingIndicator(id="llm-spinner")
        yield Static("", classes="llm-response", id="llm-response")
        yield Static("Type follow-up question, Enter to send", classes="llm-prompt-hint")
        yield Input(placeholder="Ask a follow-up...", id="llm-input")

    def on_mount(self) -> None:
        """Initialize the LLM backend."""
        # Hide spinner initially
        self.query_one("#llm-spinner", LoadingIndicator).display = False

        try:
            self._backend = ClaudeCLIBackend()
            self.query_one("#llm-status", Static).update("Ready - press 'a' to analyze")
        except RuntimeError as e:
            self.query_one("#llm-status", Static).update(f"[red]{e}[/red]")

    def analyze_file(self, file: DiffFile, hunk: DiffHunk | None = None) -> None:
        """Start analysis of a file or hunk."""
        if not self._backend:
            self.notify("Claude CLI not available", severity="error")
            return

        if self._is_loading:
            self.notify("Analysis already in progress", severity="warning")
            return

        self._current_file = file
        self._current_hunk = hunk
        self._messages.clear()

        # Build context and prompt
        context = build_analysis_context(file, hunk)
        prompts = get_analysis_prompts()
        prompt = prompts["review"]

        self._run_analysis(prompt, context)

    def _run_analysis(self, prompt: str, context: str | None = None) -> None:
        """Run analysis in a background worker thread."""
        self._is_loading = True
        self._streaming_content = ""

        # Show spinner
        spinner = self.query_one("#llm-spinner", LoadingIndicator)
        spinner.display = True

        self.query_one("#llm-status", Static).update("[yellow]Analyzing...[/yellow]")

        # Store prompt for message history
        full_prompt = prompt
        if context:
            full_prompt = f"[Context provided]\n{prompt}"
        self._messages.append(("user", full_prompt))

        # Run in worker thread
        self._current_worker = self.run_worker(
            self._stream_analysis(prompt, context),
            name="llm_analysis",
            thread=True,
        )

    async def _stream_analysis(self, prompt: str, context: str | None) -> str:
        """Stream analysis from Claude in a worker thread."""
        worker = get_current_worker()

        try:
            # Use streaming mode
            for chunk in self._backend.analyze(prompt, context, stream=True):
                if worker.is_cancelled:
                    break
                self._streaming_content += chunk
                # Update UI from worker thread (call_from_thread is on App)
                self.app.call_from_thread(self._update_streaming_display)

            return self._streaming_content
        except Exception as e:
            self.app.call_from_thread(self._show_error, str(e))
            raise

    def _update_streaming_display(self) -> None:
        """Update display with streaming content (called from main thread)."""
        response_widget = self.query_one("#llm-response", Static)

        lines = []
        # Show previous messages
        for role, content in self._messages[:-1]:  # Exclude current user message
            if role == "user":
                preview = content[:100] + "..." if len(content) > 100 else content
                lines.append(f"[dim]You:[/dim] {rich_escape(preview)}")
            else:
                lines.append(f"[bold]Claude:[/bold]\n{rich_escape(content)}")
            lines.append("")

        # Show current user message
        if self._messages:
            role, content = self._messages[-1]
            if role == "user":
                preview = content[:100] + "..." if len(content) > 100 else content
                lines.append(f"[dim]You:[/dim] {rich_escape(preview)}")
                lines.append("")

        # Show streaming response
        lines.append(f"[bold cyan]Claude:[/bold cyan]\n{rich_escape(self._streaming_content)}[blink]▌[/blink]")

        response_widget.update(Text.from_markup("\n".join(lines)))
        # Scroll to bottom
        self.scroll_end(animate=False)

    def _show_error(self, error: str) -> None:
        """Show error message (called from main thread)."""
        self.query_one("#llm-status", Static).update(f"[red]Error: {error}[/red]")

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle worker completion."""
        if event.worker.name != "llm_analysis":
            return

        if event.state == event.worker.state.SUCCESS:
            # Add assistant message
            self._messages.append(("assistant", self._streaming_content))
            self._update_display()
            self.query_one("#llm-status", Static).update("[green]Analysis complete[/green]")

        elif event.state == event.worker.state.ERROR:
            self.query_one("#llm-status", Static).update("[red]Analysis failed[/red]")

        elif event.state == event.worker.state.CANCELLED:
            self.query_one("#llm-status", Static).update("[yellow]Analysis cancelled[/yellow]")

        # Hide spinner and reset state when done
        if event.state in (event.worker.state.SUCCESS, event.worker.state.ERROR, event.worker.state.CANCELLED):
            self._is_loading = False
            self._current_worker = None
            spinner = self.query_one("#llm-spinner", LoadingIndicator)
            spinner.display = False

    def _update_display(self) -> None:
        """Update the response display with all messages."""
        response_widget = self.query_one("#llm-response", Static)

        lines = []
        for role, content in self._messages:
            if role == "user":
                # Show abbreviated user message
                preview = content[:100] + "..." if len(content) > 100 else content
                lines.append(f"[dim]You:[/dim] {rich_escape(preview)}")
            else:
                lines.append(f"[bold]Claude:[/bold]\n{rich_escape(content)}")
            lines.append("")

        response_widget.update(Text.from_markup("\n".join(lines)))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle follow-up question input."""
        if not event.value.strip():
            return

        if not self._backend:
            self.notify("Claude CLI not available", severity="error")
            return

        if self._is_loading:
            self.notify("Please wait for current analysis", severity="warning")
            return

        question = event.value.strip()
        event.input.value = ""

        # Build context from current file if we have one
        context = None
        if self._current_file:
            context = build_analysis_context(self._current_file, self._current_hunk)

        self._run_analysis(question, context)

    def clear(self) -> None:
        """Clear the conversation."""
        # Cancel any running worker
        if self._current_worker and not self._current_worker.is_finished:
            self._current_worker.cancel()

        self._messages.clear()
        self._current_file = None
        self._current_hunk = None
        self._streaming_content = ""
        self.query_one("#llm-response", Static).update("")
        self.query_one("#llm-status", Static).update("Cleared - press 'a' to analyze")
