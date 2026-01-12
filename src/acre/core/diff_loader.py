"""Load diffs using the unidiff library."""

from pathlib import Path

from unidiff import PatchSet

from acre.models.diff import DiffSet


def load_diff_from_text(
    diff_text: str,
    description: str,
    base_ref: str | None = None,
    head_ref: str | None = None,
) -> DiffSet:
    """Parse diff text into a DiffSet.

    Args:
        diff_text: Raw unified diff text
        description: Human-readable description of the diff source
        base_ref: Optional base reference (branch/commit)
        head_ref: Optional head reference (branch/commit)

    Returns:
        DiffSet containing parsed diff data
    """
    patch_set = PatchSet(diff_text)
    return DiffSet.from_unidiff(
        patch_set,
        description=description,
        base_ref=base_ref,
        head_ref=head_ref,
    )


def load_diff_from_file(
    file_path: Path,
    description: str | None = None,
    encoding: str = "utf-8",
) -> DiffSet:
    """Load diff from a file.

    Args:
        file_path: Path to the diff file
        description: Optional description (defaults to filename)
        encoding: File encoding

    Returns:
        DiffSet containing parsed diff data
    """
    patch_set = PatchSet.from_filename(str(file_path), encoding=encoding)
    return DiffSet.from_unidiff(
        patch_set,
        description=description or file_path.name,
    )
