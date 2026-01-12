"""File watcher for session hot reload."""

import asyncio
from pathlib import Path
from typing import Callable

from watchfiles import awatch, Change


class SessionWatcher:
    """Watches a session file for external changes.

    When the file is modified externally, triggers a reload callback.
    Ignores changes made by the same process (via tracking our own saves).
    """

    def __init__(
        self,
        session_path: Path,
        on_change: Callable[[], None],
        debounce_ms: int = 500,
    ):
        """Initialize the watcher.

        Args:
            session_path: Path to the session YAML file
            on_change: Callback to invoke when file changes externally
            debounce_ms: Debounce time in milliseconds
        """
        self.session_path = session_path
        self.on_change = on_change
        self.debounce_ms = debounce_ms
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._last_save_mtime: float | None = None

    def mark_our_save(self) -> None:
        """Mark that we just saved the file.

        Call this after saving to prevent triggering reload for our own changes.
        """
        if self.session_path.exists():
            self._last_save_mtime = self.session_path.stat().st_mtime

    async def _watch_loop(self) -> None:
        """Main watch loop."""
        try:
            async for changes in awatch(
                self.session_path.parent,
                debounce=self.debounce_ms,
                stop_event=self._stop_event,
            ):
                # Check if our file was modified
                for change_type, changed_path in changes:
                    if Path(changed_path) == self.session_path:
                        if change_type in (Change.modified, Change.added):
                            # Check if this was our own save
                            if self.session_path.exists():
                                current_mtime = self.session_path.stat().st_mtime
                                if (
                                    self._last_save_mtime is not None
                                    and current_mtime == self._last_save_mtime
                                ):
                                    # This was our own save, ignore
                                    continue

                            # External change - trigger reload
                            self.on_change()

        except asyncio.CancelledError:
            pass

    def start(self) -> None:
        """Start watching the file."""
        if self._task is None or self._task.done():
            self._stop_event.clear()
            self._task = asyncio.create_task(self._watch_loop())

    def stop(self) -> None:
        """Stop watching the file."""
        self._stop_event.set()
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None

    @property
    def is_running(self) -> bool:
        """Check if the watcher is running."""
        return self._task is not None and not self._task.done()
