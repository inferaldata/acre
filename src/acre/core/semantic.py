"""Semantic diff analysis using Python's AST module.

Provides AST-based analysis for Python files, identifying structural changes
like function additions, removals, and modifications.
"""

import ast
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class ChangeType(Enum):
    """Type of structural change."""

    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    MOVED = "moved"


@dataclass
class StructuralChange:
    """Represents a structural change in code."""

    change_type: ChangeType
    element_type: str  # "function", "class", "method", "import"
    name: str
    old_lineno: int | None = None
    new_lineno: int | None = None
    details: str = ""


@dataclass
class SemanticAnalysis:
    """Result of semantic analysis comparing two code versions."""

    language: str
    changes: list[StructuralChange] = field(default_factory=list)
    is_supported: bool = True
    error: str | None = None

    @property
    def has_structural_changes(self) -> bool:
        """Check if there are any structural changes."""
        return len(self.changes) > 0

    def summary(self) -> str:
        """Generate a human-readable summary of changes."""
        if not self.is_supported:
            return f"Semantic analysis not supported: {self.error}"

        if not self.changes:
            return "No structural changes detected"

        lines = []
        by_type = {}
        for change in self.changes:
            by_type.setdefault(change.change_type, []).append(change)

        if ChangeType.ADDED in by_type:
            for c in by_type[ChangeType.ADDED]:
                lines.append(f"+ {c.element_type} {c.name}")

        if ChangeType.REMOVED in by_type:
            for c in by_type[ChangeType.REMOVED]:
                lines.append(f"- {c.element_type} {c.name}")

        if ChangeType.MODIFIED in by_type:
            for c in by_type[ChangeType.MODIFIED]:
                lines.append(f"~ {c.element_type} {c.name}")

        if ChangeType.MOVED in by_type:
            for c in by_type[ChangeType.MOVED]:
                lines.append(f"→ {c.element_type} {c.name}")

        return "\n".join(lines)


def _extract_python_elements(source: str) -> dict[str, tuple[str, int, str]]:
    """Extract function and class definitions from Python source.

    Returns:
        Dict mapping name -> (element_type, lineno, signature/base_classes)
    """
    elements = {}

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return elements

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            # Build function signature
            args = []
            for arg in node.args.args:
                args.append(arg.arg)
            sig = f"({', '.join(args)})"
            element_type = "async function" if isinstance(node, ast.AsyncFunctionDef) else "function"
            elements[node.name] = (element_type, node.lineno, sig)

        elif isinstance(node, ast.ClassDef):
            # Get base classes
            bases = [ast.unparse(base) if hasattr(ast, "unparse") else "..." for base in node.bases]
            base_str = f"({', '.join(bases)})" if bases else ""
            elements[node.name] = ("class", node.lineno, base_str)

            # Also extract methods
            for item in node.body:
                if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                    method_name = f"{node.name}.{item.name}"
                    args = []
                    for arg in item.args.args:
                        args.append(arg.arg)
                    sig = f"({', '.join(args)})"
                    element_type = "async method" if isinstance(item, ast.AsyncFunctionDef) else "method"
                    elements[method_name] = (element_type, item.lineno, sig)

    return elements


def analyze_python_diff(old_source: str, new_source: str) -> SemanticAnalysis:
    """Analyze structural changes between two Python source versions.

    Args:
        old_source: Original Python source code
        new_source: Modified Python source code

    Returns:
        SemanticAnalysis with list of structural changes
    """
    analysis = SemanticAnalysis(language="python")

    try:
        old_elements = _extract_python_elements(old_source)
        new_elements = _extract_python_elements(new_source)
    except Exception as e:
        analysis.is_supported = False
        analysis.error = str(e)
        return analysis

    old_names = set(old_elements.keys())
    new_names = set(new_elements.keys())

    # Added elements
    for name in new_names - old_names:
        elem_type, lineno, sig = new_elements[name]
        analysis.changes.append(
            StructuralChange(
                change_type=ChangeType.ADDED,
                element_type=elem_type,
                name=name,
                new_lineno=lineno,
                details=sig,
            )
        )

    # Removed elements
    for name in old_names - new_names:
        elem_type, lineno, sig = old_elements[name]
        analysis.changes.append(
            StructuralChange(
                change_type=ChangeType.REMOVED,
                element_type=elem_type,
                name=name,
                old_lineno=lineno,
                details=sig,
            )
        )

    # Modified elements (same name but different signature or moved)
    for name in old_names & new_names:
        old_type, old_lineno, old_sig = old_elements[name]
        new_type, new_lineno, new_sig = new_elements[name]

        if old_sig != new_sig:
            analysis.changes.append(
                StructuralChange(
                    change_type=ChangeType.MODIFIED,
                    element_type=new_type,
                    name=name,
                    old_lineno=old_lineno,
                    new_lineno=new_lineno,
                    details=f"{old_sig} -> {new_sig}",
                )
            )
        elif abs(old_lineno - new_lineno) > 5:  # Significant move
            analysis.changes.append(
                StructuralChange(
                    change_type=ChangeType.MOVED,
                    element_type=new_type,
                    name=name,
                    old_lineno=old_lineno,
                    new_lineno=new_lineno,
                    details=f"line {old_lineno} -> {new_lineno}",
                )
            )

    # Sort by new line number (or old if removed)
    analysis.changes.sort(key=lambda c: c.new_lineno or c.old_lineno or 0)

    return analysis


def detect_language(file_path: str) -> str | None:
    """Detect programming language from file extension.

    Returns:
        Language name or None if not recognized
    """
    suffix = Path(file_path).suffix.lower()
    language_map = {
        ".py": "python",
        ".pyi": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".jsx": "javascript",
        ".tsx": "typescript",
        ".java": "java",
        ".go": "go",
        ".rs": "rust",
        ".rb": "ruby",
        ".c": "c",
        ".cpp": "cpp",
        ".h": "c",
        ".hpp": "cpp",
    }
    return language_map.get(suffix)


def analyze_file_diff(
    file_path: str,
    old_content: str,
    new_content: str,
) -> SemanticAnalysis:
    """Analyze structural changes in a file diff.

    Currently only supports Python. Other languages return unsupported.

    Args:
        file_path: Path to the file (used to detect language)
        old_content: Original file content
        new_content: Modified file content

    Returns:
        SemanticAnalysis with structural changes
    """
    language = detect_language(file_path)

    if language == "python":
        return analyze_python_diff(old_content, new_content)
    elif language:
        return SemanticAnalysis(
            language=language,
            is_supported=False,
            error=f"Semantic analysis for {language} not yet implemented",
        )
    else:
        return SemanticAnalysis(
            language="unknown",
            is_supported=False,
            error="Unknown file type",
        )


class SemanticDiffProvider:
    """Provides semantic diff analysis for diff files.

    This class can be used to augment regular line-based diffs with
    structural change information.
    """

    def __init__(self, repo_path: Path | None = None):
        """Initialize the provider.

        Args:
            repo_path: Optional path to repository for fetching file contents
        """
        self.repo_path = repo_path
        self._cache: dict[str, SemanticAnalysis] = {}

    def analyze(
        self,
        file_path: str,
        old_content: str,
        new_content: str,
    ) -> SemanticAnalysis:
        """Analyze a file's structural changes.

        Results are cached by file path.
        """
        if file_path in self._cache:
            return self._cache[file_path]

        analysis = analyze_file_diff(file_path, old_content, new_content)
        self._cache[file_path] = analysis
        return analysis

    def clear_cache(self) -> None:
        """Clear the analysis cache."""
        self._cache.clear()
