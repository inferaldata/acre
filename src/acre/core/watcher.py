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


class DiffWatcher:
    """Watches the repository for file changes to reload diff.

    Triggers when any tracked file changes, to pick up new code changes.
    """

    def __init__(
        self,
        repo_path: Path,
        on_change: Callable[[], None],
        session_file: Path | None = None,
        debounce_ms: int = 1000,
    ):
        """Initialize the watcher.

        Args:
            repo_path: Path to the repository root
            on_change: Callback to invoke when files change
            session_file: Session file to ignore (already watched separately)
            debounce_ms: Debounce time in milliseconds
        """
        self.repo_path = repo_path
        self.on_change = on_change
        self.session_file = session_file
        self.debounce_ms = debounce_ms
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def _watch_loop(self) -> None:
        """Main watch loop."""
        try:
            async for changes in awatch(
                self.repo_path,
                debounce=self.debounce_ms,
                stop_event=self._stop_event,
                recursive=True,
            ):
                # Filter out session file and .git directory changes
                relevant_changes = []
                for change_type, changed_path in changes:
                    path = Path(changed_path)
                    # Skip .git directory
                    if ".git" in path.parts:
                        continue
                    # Skip session file (watched separately)
                    if self.session_file and path == self.session_file:
                        continue
                    # Skip hidden files
                    if path.name.startswith("."):
                        continue
                    relevant_changes.append((change_type, changed_path))

                if relevant_changes:
                    self.on_change()

        except asyncio.CancelledError:
            pass

    def start(self) -> None:
        """Start watching the repository."""
        if self._task is None or self._task.done():
            self._stop_event.clear()
            self._task = asyncio.create_task(self._watch_loop())

    def stop(self) -> None:
        """Stop watching."""
        self._stop_event.set()
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None

    @property
    def is_running(self) -> bool:
        """Check if the watcher is running."""
        return self._task is not None and not self._task.done()
