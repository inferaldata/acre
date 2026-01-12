"""File list sidebar widget."""

from textual.binding import Binding
from textual.message import Message
from textual.widgets import Tree
from textual.widgets.tree import TreeNode

from acre.models.diff import DiffSet, DiffFile
from acre.models.review import ReviewSession


class FileReviewToggled(Message):
    """Message sent when file review status is toggled from file list."""

    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path


class FileList(Tree):
    """Sidebar showing files with review status."""

    BINDINGS = [
        Binding("r", "toggle_reviewed", "Toggle Reviewed", show=False),
    ]

    DEFAULT_CSS = """
    FileList {
        background: $surface;
        scrollbar-gutter: stable;
    }

    FileList > .tree--guides {
        color: $primary-darken-2;
    }

    FileList > .tree--cursor {
        background: $primary;
    }
    """

    def __init__(
        self,
        diff_set: DiffSet,
        session: ReviewSession,
        **kwargs,
    ):
        super().__init__(diff_set.source_description, **kwargs)
        self.diff_set = diff_set
        self.session = session
        self._file_nodes: dict[str, TreeNode] = {}

    def on_mount(self) -> None:
        """Build the file tree on mount."""
        self._build_tree()
        self.root.expand_all()

    def _build_tree(self) -> None:
        """Build the file tree from diff set with directory hierarchy.

        Collapses empty directories: app/models/file.py shows as:
            app/models/
                file.py
        instead of:
            app/
                models/
                    file.py
        """
        self.root.remove_children()
        self._file_nodes.clear()
        self._dir_nodes: dict[str, TreeNode] = {}

        # Sort files by path for consistent ordering
        sorted_files = sorted(self.diff_set.files, key=lambda f: f.path)

        # First pass: count children per directory to know which can be collapsed
        dir_children: dict[str, set[str]] = {}  # dir -> set of immediate child names
        for file in sorted_files:
            parts = file.path.split("/")
            for i in range(len(parts)):
                dir_path = "/".join(parts[:i]) if i > 0 else ""
                child = parts[i]
                if dir_path not in dir_children:
                    dir_children[dir_path] = set()
                dir_children[dir_path].add(child)

        def should_collapse(dir_path: str) -> bool:
            """Check if directory has exactly one child that is also a directory."""
            if dir_path not in dir_children:
                return False
            children = dir_children[dir_path]
            if len(children) != 1:
                return False
            # Check if the single child is a directory (has its own children)
            child = next(iter(children))
            child_path = f"{dir_path}/{child}" if dir_path else child
            return child_path in dir_children

        for file in sorted_files:
            parts = file.path.split("/")

            # Find collapsed directory segments
            # Merge consecutive directories that have only one child
            current_node = self.root
            i = 0

            while i < len(parts) - 1:  # Process directories, not the filename
                # Start building a collapsed path segment
                segment_start = i
                segment_parts = [parts[i]]
                current_dir = "/".join(parts[:i + 1])

                # Keep extending while this dir should be collapsed
                while should_collapse(current_dir) and i + 1 < len(parts) - 1:
                    i += 1
                    segment_parts.append(parts[i])
                    current_dir = "/".join(parts[:i + 1])

                # Create the collapsed directory path
                collapsed_name = "/".join(segment_parts) + "/"
                collapsed_path = "/".join(parts[:i + 1])

                if collapsed_path not in self._dir_nodes:
                    dir_node = current_node.add(collapsed_name, data={"dir": collapsed_path})
                    self._dir_nodes[collapsed_path] = dir_node
                    current_node = dir_node
                else:
                    current_node = self._dir_nodes[collapsed_path]

                i += 1

            # Add the file as a leaf under the current directory
            filename = parts[-1]
            label = self._format_file_label(file, filename)
            node = current_node.add_leaf(label, data={"path": file.path})
            self._file_nodes[file.path] = node

    def _format_file_label(self, file: DiffFile, display_name: str | None = None):
        """Format the label for a file node with colored status.

        Args:
            file: The diff file
            display_name: Name to display (defaults to full path)
        """
        from rich.text import Text

        file_state = self.session.files.get(file.path)
        reviewed = file_state.reviewed if file_state else False
        comment_count = file_state.comment_count if file_state else 0

        # Status icon and color
        status_config = {
            "modified": ("M", "yellow"),
            "added": ("A", "green"),
            "deleted": ("D", "red"),
            "renamed": ("R", "blue"),
            "untracked": ("U", "cyan"),
        }
        status_icon, status_color = status_config.get(file.status, ("?", "white"))

        # Review status
        review_icon = "\u2713" if reviewed else "\u25cb"

        # Build label with display name (filename only in tree view)
        name = display_name if display_name else file.path

        # Build Rich Text with colors
        label = Text()
        label.append(f"{review_icon} ")
        label.append(status_icon, style=status_color)
        label.append(f" {name}")

        # Add comment count if any
        if comment_count > 0:
            label.append(f" ({comment_count})", style="magenta")

        # Add diff stats
        label.append(f" +{file.added_lines}", style="green")
        label.append("/")
        label.append(f"-{file.removed_lines}", style="red")

        return label

    def refresh_file(self, file_path: str) -> None:
        """Refresh the display for a specific file."""
        if file_path in self._file_nodes:
            node = self._file_nodes[file_path]
            # Find the file in diff_set
            for file in self.diff_set.files:
                if file.path == file_path:
                    # Extract just the filename for display
                    filename = file_path.split("/")[-1]
                    node.set_label(self._format_file_label(file, filename))
                    break

    def select_file(self, file_path: str) -> None:
        """Select a file in the tree."""
        if file_path in self._file_nodes:
            node = self._file_nodes[file_path]
            self.select_node(node)
            # Use Tree's scroll_to_node instead of node.scroll_visible
            self.scroll_to_node(node)

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Handle file selection."""
        if event.node.data and "path" in event.node.data:
            file_path = event.node.data["path"]
            # Post message to parent to sync diff view
            self.post_message(FileSelected(file_path))

    def action_toggle_reviewed(self) -> None:
        """Toggle reviewed status for the currently selected file."""
        # Get currently selected node
        if self.cursor_node and self.cursor_node.data and "path" in self.cursor_node.data:
            file_path = self.cursor_node.data["path"]
            self.post_message(FileReviewToggled(file_path))


class FileSelected(Message):
    """Message sent when a file is selected in the file list."""

    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path
