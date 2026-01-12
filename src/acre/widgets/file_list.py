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
        self.root.expand()

    def _build_tree(self) -> None:
        """Build the file tree from diff set."""
        self.root.remove_children()
        self._file_nodes.clear()

        for file in self.diff_set.files:
            label = self._format_file_label(file)
            node = self.root.add_leaf(label, data={"path": file.path})
            self._file_nodes[file.path] = node

    def _format_file_label(self, file: DiffFile) -> str:
        """Format the label for a file node."""
        file_state = self.session.files.get(file.path)
        reviewed = file_state.reviewed if file_state else False
        comment_count = file_state.comment_count if file_state else 0

        # Status icon
        status_icon = {
            "modified": "M",
            "added": "A",
            "deleted": "D",
            "renamed": "R",
        }[file.status]

        # Review status
        review_icon = "\u2713" if reviewed else "\u25cb"

        # Build label
        label = f"{review_icon} {status_icon} {file.path}"

        # Add comment count if any
        if comment_count > 0:
            label += f" ({comment_count})"

        # Add diff stats
        label += f" +{file.added_lines}/-{file.removed_lines}"

        return label

    def refresh_file(self, file_path: str) -> None:
        """Refresh the display for a specific file."""
        if file_path in self._file_nodes:
            node = self._file_nodes[file_path]
            # Find the file in diff_set
            for file in self.diff_set.files:
                if file.path == file_path:
                    node.set_label(self._format_file_label(file))
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
