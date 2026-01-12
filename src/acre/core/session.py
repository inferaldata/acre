"""Session persistence for acre review sessions."""

import json
import subprocess
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml

from acre.models.comment import Comment, CommentCategory
from acre.models.review import FileReviewState, ReviewSession


@lru_cache(maxsize=1)
def get_git_user() -> str:
    """Get git user as 'Name <email>' format.

    Returns 'human' as fallback if git config is not available.
    """
    try:
        name = subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        email = subprocess.run(
            ["git", "config", "user.email"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        if name and email:
            return f"{name} <{email}>"
        return name or email or "human"
    except Exception:
        return "human"


# Custom string class to force literal block style in YAML
class LiteralStr(str):
    """String subclass that forces literal block style (|) in YAML output."""
    pass


class LiteralDumper(yaml.SafeDumper):
    """YAML Dumper that uses literal block style for LiteralStr and multiline strings."""
    pass


def _str_representer(dumper, data):
    """Use literal block style for LiteralStr and multiline strings."""
    # Check for LiteralStr first (it's a str subclass)
    if isinstance(data, LiteralStr):
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    # Use literal style for any multiline string
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


# Register for both str and LiteralStr to ensure proper dispatch
LiteralDumper.add_representer(str, _str_representer)
LiteralDumper.add_representer(LiteralStr, _str_representer)


# LLM instructions that appear in the first YAML document
LLM_INSTRUCTIONS = """\
ACRE CODE REVIEW SESSION
========================

This file contains a code review session that you can collaborate on.
The TUI (acre) will hot-reload when you save changes to this file.

HOW TO PARTICIPATE
------------------

1. READ the diff_context below to understand what code changed
2. FIND comments that need a response (llm_response is null or missing)
3. RESPOND to those comments by adding llm_response field
4. Only ADD new comments if explicitly requested in a comment

IMPORTANT: Only respond to "hanging" comments (where llm_response is null).
Do NOT add unsolicited comments unless a human comment asks for analysis.

COMMENT STRUCTURE
-----------------

Each comment in the files.<path>.comments list has these fields:

  - id: <uuid>              # Auto-generated, omit when adding new
  - author: "Agent (Model/Version)"  # Format: "Agent (Claude/Opus-4.5)" etc.
  - category: suggestion    # One of: note, suggestion, issue, praise, ai_analysis
  - content: "Your feedback here"
  - file_path: "path/to/file.py"
  - line_no: 42             # Line number, or null for file-level
  - line_no_end: null       # End line for ranges, or null
  - is_deleted_line: false  # true if commenting on a removed line
  - created_at: <iso-date>  # Auto-set, omit when adding new
  - updated_at: <iso-date>  # Auto-set, omit when adding new
  - llm_response: null      # Your response to a human comment

AUTHOR FORMAT
-------------

AI agents MUST use this author format: "Agent (Model/Version)"

Examples:
  - "Agent (Claude/Opus-4.5)"
  - "Agent (Claude/Sonnet-3.5)"
  - "Agent (GPT-4)"

Human authors use: "Name <email>" (auto-detected from git config)

ADDING A NEW COMMENT
--------------------

Find the file in the files section and append to its comments list:

  files:
    src/example.py:
      comments:
        - author: "Agent (Claude/Opus-4.5)"
          category: suggestion
          content: |
            Consider using a context manager here to ensure
            the file is properly closed on exceptions.
          file_path: src/example.py
          line_no: 42

RESPONDING TO A HUMAN COMMENT
-----------------------------

Find the human's comment and add llm_response:

  - id: "abc123"
    author: "Yurii Rashkovskii <yrashk@gmail.com>"
    category: issue
    content: "This might cause a race condition"
    llm_response: |
      Good catch! You could use a threading.Lock here,
      or consider using asyncio for better concurrency.

CATEGORIES EXPLAINED
--------------------

- note: General observation or context
- suggestion: Improvement that could be made
- issue: Problem that should be fixed
- praise: Positive feedback on good code
- ai_analysis: In-depth AI analysis (complexity, patterns, etc.)

IMPORTANT
---------

- Keep the YAML valid - the TUI will fail to reload if syntax is broken
- The id, created_at, updated_at fields are auto-generated - omit them
- Line numbers refer to the NEW file (after changes), unless is_deleted_line=true"""


def get_session_path(session: ReviewSession) -> Path:
    """Get the path for storing a session.

    Sessions are stored directly in the repo as .acre-review[.<ref>].yaml
    for easy access by LLMs.

    Naming convention:
    - Default (uncommitted, staged, branch): .acre-review.yaml
    - commit (-c): .acre-review.<commit>.yaml
    - pr (--pr): .acre-review.pr-<number>.yaml
    """
    base = ".acre-review"

    if session.diff_source_type == "commit" and session.diff_source_ref:
        # Use short commit hash if full hash provided
        ref = session.diff_source_ref[:7] if len(session.diff_source_ref) > 7 else session.diff_source_ref
        suffix = f".{ref}"
    elif session.diff_source_type == "pr" and session.diff_source_ref:
        suffix = f".pr-{session.diff_source_ref}"
    else:
        suffix = ""

    return session.repo_path / f"{base}{suffix}.yaml"


def session_to_dict(session: ReviewSession) -> dict:
    """Convert a session to a serializable dict.

    Note: repo_path is intentionally omitted as it's machine-specific.
    The repo_path is derived from the YAML file location when loading.
    """
    return {
        "id": session.id,
        "diff_source_type": session.diff_source_type,
        "diff_source_ref": session.diff_source_ref,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
        "notes": session.notes,
        "current_file_index": session.current_file_index,
        "scroll_position": session.scroll_position,
        "files": {
            path: {
                "file_path": state.file_path,
                "reviewed": state.reviewed,
                "comments": [
                    {
                        "id": c.id,
                        "author": c.author,
                        "category": c.category.value,
                        "content": c.content,
                        "file_path": c.file_path,
                        "line_no": c.line_no,
                        "line_no_end": c.line_no_end,
                        "is_deleted_line": c.is_deleted_line,
                        "created_at": c.created_at.isoformat(),
                        "updated_at": c.updated_at.isoformat(),
                        "context": LiteralStr(c.context) if c.context else None,
                        "llm_response": LiteralStr(c.llm_response) if c.llm_response else None,
                        "llm_session_id": c.llm_session_id,
                    }
                    for c in state.comments
                ],
            }
            for path, state in session.files.items()
        },
    }


def session_from_dict(data: dict, repo_path: Path) -> ReviewSession:
    """Restore a session from a dict.

    Args:
        data: The session data dict
        repo_path: The repository path (derived from YAML file location)
    """
    session = ReviewSession(
        repo_path=repo_path,
        diff_source_type=data["diff_source_type"],
        diff_source_ref=data.get("diff_source_ref"),
        id=data["id"],
        created_at=datetime.fromisoformat(data["created_at"]),
        updated_at=datetime.fromisoformat(data["updated_at"]),
        notes=data.get("notes", ""),
        current_file_index=data.get("current_file_index", 0),
        scroll_position=data.get("scroll_position", 0),
    )

    # Restore files
    for path, file_data in data.get("files", {}).items():
        comments = []
        for c_data in file_data.get("comments", []):
            # Handle optional fields that LLM may omit (per instructions)
            now = datetime.now()
            created_at = (
                datetime.fromisoformat(c_data["created_at"])
                if c_data.get("created_at")
                else now
            )
            updated_at = (
                datetime.fromisoformat(c_data["updated_at"])
                if c_data.get("updated_at")
                else created_at
            )

            # Build kwargs, only including id if present (otherwise use default)
            comment_kwargs = {
                "content": c_data["content"],
                "file_path": c_data.get("file_path", path),  # Default to parent file path
                "category": CommentCategory(c_data["category"]),
                "author": c_data.get("author", "human"),
                "line_no": c_data.get("line_no"),
                "line_no_end": c_data.get("line_no_end"),
                "is_deleted_line": c_data.get("is_deleted_line", False),
                "created_at": created_at,
                "updated_at": updated_at,
                "context": c_data.get("context"),
                "llm_response": c_data.get("llm_response"),
                "llm_session_id": c_data.get("llm_session_id"),
            }
            if c_data.get("id"):
                comment_kwargs["id"] = c_data["id"]

            comment = Comment(**comment_kwargs)
            comments.append(comment)

        state = FileReviewState(
            file_path=file_data["file_path"],
            reviewed=file_data.get("reviewed", False),
            comments=comments,
        )
        session.files[path] = state

    return session


def session_to_yaml(session: ReviewSession, diff_context: str = "") -> str:
    """Convert a session to multi-document YAML format.

    The YAML contains two documents:
    1. Instructions for LLM + diff context
    2. Session data

    Args:
        session: The session to serialize
        diff_context: Optional diff content for LLM context

    Returns:
        Multi-document YAML string
    """
    # Document 1: Instructions for LLM
    # Wrap in LiteralStr to force literal block style in YAML
    doc1 = {
        "instructions": LiteralStr(LLM_INSTRUCTIONS),
        "diff_context": LiteralStr(diff_context) if diff_context else "# Diff not included. Run 'git diff' to see changes.",
    }

    # Document 2: Session data
    doc2 = session_to_dict(session)

    # Serialize as multi-document YAML with literal block style for multiline strings
    yaml_output = yaml.dump(doc1, Dumper=LiteralDumper, default_flow_style=False, allow_unicode=True, sort_keys=False)
    yaml_output += "\n---\n"
    yaml_output += yaml.dump(doc2, Dumper=LiteralDumper, default_flow_style=False, allow_unicode=True, sort_keys=False)

    return yaml_output


def session_from_yaml(yaml_content: str, repo_path: Path) -> ReviewSession:
    """Parse a multi-document YAML session file.

    Args:
        yaml_content: Multi-document YAML string
        repo_path: The repository path (parent of YAML file)

    Returns:
        The parsed session
    """
    docs = list(yaml.safe_load_all(yaml_content))

    if len(docs) < 2:
        # Single document - just session data (old format or simplified)
        return session_from_dict(docs[0], repo_path)

    # Multi-document: doc[0] is instructions, doc[1] is session
    return session_from_dict(docs[1], repo_path)


def save_session(session: ReviewSession, diff_context: str = "") -> Path:
    """Save a session to disk in YAML format.

    The session is saved as .acre-review.yaml in the repo root.

    Args:
        session: The session to save
        diff_context: Optional diff content for LLM context

    Returns:
        Path where the session was saved
    """
    path = get_session_path(session)

    yaml_content = session_to_yaml(session, diff_context)
    with open(path, "w") as f:
        f.write(yaml_content)

    return path


def load_session(session_path: Path) -> ReviewSession:
    """Load a session from disk.

    Supports both YAML (new) and JSON (legacy) formats.
    The repo_path is derived from the session file's parent directory.

    Args:
        session_path: Path to the session file

    Returns:
        The loaded session
    """
    with open(session_path) as f:
        content = f.read()

    # Derive repo_path from file location
    repo_path = session_path.parent

    # Detect format - JSON starts with { or [
    if content.strip().startswith(("{", "[")):
        # Legacy JSON format
        data = json.loads(content)
        return session_from_dict(data, repo_path)

    # YAML format (single or multi-document)
    return session_from_yaml(content, repo_path)


def find_latest_session(
    repo_path: Path,
    diff_source_type: Literal["uncommitted", "staged", "branch", "commit", "pr"]
    | None = None,
    diff_source_ref: str | None = None,
) -> ReviewSession | None:
    """Find the session for a repo.

    Sessions are stored as .acre-review[.<ref>].yaml in the repo root.

    Args:
        repo_path: Repository path
        diff_source_type: Optional filter by diff source type
        diff_source_ref: Optional filter by diff source ref

    Returns:
        The session if found and matches filters, or None
    """
    # Create a temporary session to compute the expected path
    temp_session = ReviewSession(
        repo_path=repo_path,
        diff_source_type=diff_source_type or "uncommitted",
        diff_source_ref=diff_source_ref,
    )
    session_path = get_session_path(temp_session)

    if not session_path.exists():
        return None

    try:
        session = load_session(session_path)

        # Apply filters
        if diff_source_type and session.diff_source_type != diff_source_type:
            return None
        if diff_source_ref and session.diff_source_ref != diff_source_ref:
            return None

        return session
    except Exception:
        return None


def list_sessions(repo_path: Path) -> list[ReviewSession]:
    """List sessions for a repo.

    With the new format, there's at most one session per repo.

    Args:
        repo_path: Repository path

    Returns:
        List containing the session if it exists, empty otherwise
    """
    session = find_latest_session(repo_path)
    return [session] if session else []


def delete_session(session: ReviewSession) -> bool:
    """Delete a session from disk.

    Args:
        session: The session to delete

    Returns:
        True if deleted, False if not found
    """
    path = get_session_path(session)

    if path.exists():
        path.unlink()
        return True

    return False


def get_session_file_path(session: ReviewSession) -> Path:
    """Get the path where a session file is stored.

    Used for file watching.

    Args:
        session: The session

    Returns:
        Path to the session file
    """
    return get_session_path(session)
