"""Adapter between acre UI and OpenCodeReview models.

This module provides a facade that wraps OpenCodeReview's append-only
activity model with the mutable interface that acre's UI expects.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4
import subprocess
from functools import lru_cache

from opencodereview import (
    Review,
    Comment as OCRComment,
    ReviewMark,
    Resolution,
    Retraction,
    Author,
    Location,
    Subject,
    AgentContext,
    load as ocr_load,
    dump as ocr_dump,
)


# Format-specific LLM instructions
LLM_INSTRUCTIONS = {
    "xml": """\
OPENCODEREVIEW SESSION (XML FORMAT)
====================================

This file contains a code review in OpenCodeReview format.
The TUI (acre) will hot-reload when you save changes to this file.

HOW TO PARTICIPATE
------------------

1. FIND comments that need a response (no reply from you yet)
2. RESPOND by adding a reply inside the parent's <replies> element
3. Only ADD new comments if explicitly requested

ADDING A NEW COMMENT
--------------------

Append inside <activities>:

  <activity>
    <category>suggestion</category>
    <content>Your comment text here</content>
    <author><type>agent</type><name>Claude</name><model>opus</model></author>
    <location>
      <file>src/main.py</file>
      <lines><range><start>42</start><end>42</end></range></lines>
    </location>
  </activity>

REPLYING TO A COMMENT
---------------------

Find the comment and add inside its <replies>:

  <activity>
    <category>note</category>
    <content>Your reply text here</content>
    <author><type>agent</type><name>Claude</name><model>opus</model></author>
  </activity>

CATEGORIES: note, suggestion, issue, praise, question, task, security

IMPORTANT
---------
- Keep the XML valid - the TUI will fail to reload if syntax is broken
- Line numbers refer to the NEW file (after changes)
- Author: Always use type=agent with your name and model""",

    "yaml": """\
OPENCODEREVIEW SESSION (YAML FORMAT)
=====================================

This file contains a code review in OpenCodeReview format.
The TUI (acre) will hot-reload when you save changes to this file.

HOW TO PARTICIPATE
------------------

1. FIND comments that need a response (no reply from you yet)
2. RESPOND by adding a reply to the parent's replies list
3. Only ADD new comments if explicitly requested

ADDING A NEW COMMENT
--------------------

Append to the activities list:

- category: suggestion
  content: |
    Consider using a context manager here.
    This ensures the file is properly closed on exceptions.
  author:
    type: agent
    name: Claude
    model: opus
  location:
    file: src/main.py
    lines: [[42, 42]]

REPLYING TO A COMMENT
---------------------

Add to the parent comment's replies list:

- category: note
  content: |
    Good point! You could use a threading.Lock here,
    or consider using asyncio for better concurrency.
  author:
    type: agent
    name: Claude
    model: opus

CATEGORIES
----------
- note: General observation or context
- suggestion: Improvement that could be made
- issue: Problem that should be fixed
- praise: Positive feedback on good code
- question: Asking for clarification
- task: Action item to be done
- security: Security-related concern

IMPORTANT
---------
- Use literal block style (|) for multiline content
- Keep the YAML valid - the TUI will fail to reload if syntax is broken
- Line numbers refer to the NEW file (after changes)
- Author: Always use type: agent with your name and model""",

    "json": """\
OPENCODEREVIEW SESSION (JSON FORMAT)
=====================================

This file contains a code review in OpenCodeReview format.
The TUI (acre) will hot-reload when you save changes to this file.

HOW TO PARTICIPATE
------------------

1. FIND comments that need a response (no reply from you yet)
2. RESPOND by adding a reply to the parent's "replies" array
3. Only ADD new comments if explicitly requested

ADDING A NEW COMMENT
--------------------

Append to the "activities" array:

{
  "category": "suggestion",
  "content": "Consider using a context manager here.\\nThis ensures the file is properly closed on exceptions.",
  "author": {"type": "agent", "name": "Claude", "model": "opus"},
  "location": {"file": "src/main.py", "lines": [[42, 42]]}
}

REPLYING TO A COMMENT
---------------------

Add to the parent comment's "replies" array:

{
  "category": "note",
  "content": "Good point! You could use a threading.Lock here,\\nor consider using asyncio for better concurrency.",
  "author": {"type": "agent", "name": "Claude", "model": "opus"}
}

CATEGORIES
----------
- note: General observation or context
- suggestion: Improvement that could be made
- issue: Problem that should be fixed
- praise: Positive feedback on good code
- question: Asking for clarification
- task: Action item to be done
- security: Security-related concern

IMPORTANT
---------
- Use \\n for newlines in content strings
- Keep the JSON valid - the TUI will fail to reload if syntax is broken
- Line numbers refer to the NEW file (after changes)
- Author: Always use "type": "agent" with your name and model""",
}


# Map acre diff source types to OCR subject types
DIFF_SOURCE_TO_SUBJECT = {
    "uncommitted": ("patch", "git-uncommitted"),
    "staged": ("patch", "git-staged"),
    "branch": ("patch", "git-branch"),
    "commit": ("commit", "git"),
    "pr": ("patch", "github-pr"),
}

# Map acre categories to OCR categories
ACRE_TO_OCR_CATEGORY = {
    "note": "note",
    "suggestion": "suggestion",
    "issue": "issue",
    "praise": "praise",
    "ai_analysis": "note",  # AI analysis maps to note with agent author
}

OCR_TO_ACRE_CATEGORY = {
    "note": "note",
    "suggestion": "suggestion",
    "issue": "issue",
    "praise": "praise",
    "question": "note",
    "task": "issue",
    "security": "issue",
}


@lru_cache(maxsize=1)
def get_git_user() -> tuple[str, str | None]:
    """Get git user as (name, email) tuple."""
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
        return (name or "Anonymous", email or None)
    except Exception:
        return ("Anonymous", None)


def make_human_author() -> Author:
    """Create an Author for the current git user."""
    name, email = get_git_user()
    return Author(name=name, email=email)


def make_agent_author(name: str = "Claude", model: str = "opus") -> Author:
    """Create an Author for an AI agent."""
    return Author(type="agent", name=name, model=model)


def is_agent_author(author: Author | None) -> bool:
    """Check if author is an AI agent."""
    return author is not None and author.type == "agent"


@dataclass
class CommentView:
    """A view of an OCR Comment adapted for acre's UI.

    This wraps an OCRComment and provides the interface acre expects.
    """
    _comment: OCRComment

    @property
    def id(self) -> str:
        return self._comment.id

    @property
    def content(self) -> str:
        return self._comment.content or ""

    @property
    def category(self) -> str:
        """Return acre-compatible category string."""
        return OCR_TO_ACRE_CATEGORY.get(self._comment.category, "note")

    @property
    def author(self) -> str:
        """Return author as string in acre format."""
        if self._comment.author is None:
            return "human"
        a = self._comment.author
        if a.type == "agent":
            model = a.model or "unknown"
            return f"Agent ({a.name}/{model})"
        if a.email:
            return f"{a.name} <{a.email}>"
        return a.name or "human"

    @property
    def is_ai(self) -> bool:
        return is_agent_author(self._comment.author)

    @property
    def file_path(self) -> str:
        if self._comment.location:
            return self._comment.location.file or ""
        return ""

    @property
    def line_no(self) -> int | None:
        if self._comment.location and self._comment.location.lines:
            return self._comment.location.lines[0][0]
        return None

    @property
    def line_no_end(self) -> int | None:
        if self._comment.location and self._comment.location.lines:
            return self._comment.location.lines[0][1]
        return None

    @property
    def is_deleted_line(self) -> bool:
        # OCR doesn't have this concept directly
        return False

    @property
    def line_range(self) -> tuple[int, int] | None:
        if self.line_no is None:
            return None
        end = self.line_no_end if self.line_no_end else self.line_no
        return (min(self.line_no, end), max(self.line_no, end))

    @property
    def is_range(self) -> bool:
        return self.line_no is not None and self.line_no_end is not None and self.line_no != self.line_no_end

    def covers_line(self, line_no: int) -> bool:
        if self.line_no is None:
            return False
        if self.line_no_end is None:
            return self.line_no == line_no
        start, end = self.line_range
        return start <= line_no <= end

    @property
    def created_at(self) -> datetime:
        if self._comment.created:
            return datetime.fromisoformat(self._comment.created.replace("Z", "+00:00"))
        return datetime.now()

    @property
    def updated_at(self) -> datetime:
        return self.created_at

    @property
    def llm_response(self) -> str | None:
        """Get the first agent reply as llm_response."""
        for reply in self._comment.replies:
            if is_agent_author(reply.author):
                return reply.content
        return None

    @property
    def replies(self) -> list["CommentView"]:
        """Get all replies as CommentViews."""
        return [CommentView(_comment=r) for r in self._comment.replies]

    @property
    def context(self) -> str | None:
        # Context is not stored in OCR - derived from location
        return None

    @property
    def location(self) -> str:
        """Get formatted location string for export."""
        if self.line_no is None:
            return f"`{self.file_path}`"
        elif self.is_range:
            start, end = self.line_range
            return f"`{self.file_path}:{start}-{end}`"
        else:
            return f"`{self.file_path}:{self.line_no}`"

    @property
    def location_short(self) -> str:
        if self.line_no is None:
            return "file"
        elif self.is_range:
            start, end = self.line_range
            return f"L{start}-{end}"
        else:
            return f"L{self.line_no}"


@dataclass
class FileReviewState:
    """Review state for a single file, computed from OCR activities."""

    file_path: str
    _session: "AcreSession"

    @property
    def reviewed(self) -> bool:
        """Check if file is marked as reviewed."""
        return self._session._is_file_reviewed(self.file_path)

    @property
    def comments(self) -> list[CommentView]:
        """Get comments for this file."""
        return self._session._get_file_comments(self.file_path)

    @property
    def comment_count(self) -> int:
        return len(self.comments)

    @property
    def resolved_hunks(self) -> list[dict]:
        """Get resolved hunks for this file."""
        return self._session._get_file_resolved_hunks(self.file_path)

    def is_hunk_resolved(self, hunk_id: str) -> bool:
        """Check if a hunk is resolved."""
        return self._session._is_hunk_resolved(self.file_path, hunk_id)


@dataclass
class AcreSession:
    """Wraps OCR Review with acre-specific operations.

    This adapter provides the mutable interface acre expects while
    using OCR's append-only activity model underneath.
    """

    review: Review
    repo_path: Path
    diff_source_type: Literal["uncommitted", "staged", "branch", "commit", "pr"]
    diff_source_ref: str | None = None
    format: str = "xml"

    # Cached state computed from activities
    _file_paths: list[str] = field(default_factory=list)

    @classmethod
    def new(
        cls,
        repo_path: Path,
        diff_source_type: Literal["uncommitted", "staged", "branch", "commit", "pr"],
        diff_source_ref: str | None = None,
        format: str = "xml",
    ) -> "AcreSession":
        """Create a new session."""
        subject_type, provider = DIFF_SOURCE_TO_SUBJECT[diff_source_type]

        subject = Subject(
            type=subject_type,
            provider=provider,
            provider_ref=diff_source_ref,
            repo=str(repo_path),
        )

        review = Review(
            subject=subject,
            agent_context=AgentContext(instructions=LLM_INSTRUCTIONS.get(format, "")),
        )

        return cls(
            review=review,
            repo_path=repo_path,
            diff_source_type=diff_source_type,
            diff_source_ref=diff_source_ref,
            format=format,
        )

    @classmethod
    def load(cls, path: Path, format: str = "xml") -> "AcreSession":
        """Load a session from disk."""
        review = ocr_load(path)

        # Extract metadata from subject
        repo_path = path.parent
        diff_source_type = "uncommitted"
        diff_source_ref = None

        if review.subject:
            if review.subject.repo:
                repo_path = Path(review.subject.repo)
            if review.subject.provider:
                # Reverse map provider to diff_source_type
                for dtype, (_, prov) in DIFF_SOURCE_TO_SUBJECT.items():
                    if prov == review.subject.provider:
                        diff_source_type = dtype
                        break
            diff_source_ref = review.subject.provider_ref

        session = cls(
            review=review,
            repo_path=repo_path,
            diff_source_type=diff_source_type,
            diff_source_ref=diff_source_ref,
            format=format,
        )

        # Initialize file paths from existing activities
        session._rebuild_file_paths()

        return session

    def save(self, path: Path) -> None:
        """Save session to disk.

        Uses load/dump pattern to avoid overwriting concurrent changes.
        Since OCR is append-only, we merge any external activities before saving.
        """
        # Update instructions for current format
        if self.review.agent_context is None:
            self.review.agent_context = AgentContext()
        self.review.agent_context.instructions = LLM_INSTRUCTIONS.get(self.format, "")

        # Load current file to check for external changes
        if path.exists():
            try:
                disk_review = ocr_load(path)
                # Merge any activities from disk that we don't have
                our_ids = {a.id for a in self.review.activities}
                for activity in disk_review.activities:
                    if activity.id not in our_ids:
                        # External activity - add it to our review
                        self.review.activities.append(activity)
            except Exception:
                # If load fails, just save our version
                pass

        ocr_dump(self.review, path)

    def _rebuild_file_paths(self) -> None:
        """Rebuild file paths from activities."""
        paths = set()
        for activity in self.review.activities:
            if hasattr(activity, "location") and activity.location:
                if activity.location.file:
                    paths.add(activity.location.file)
        self._file_paths = sorted(paths)

    def init_files(self, file_paths: list[str]) -> None:
        """Initialize file list."""
        self._file_paths = list(file_paths)

    # Properties matching ReviewSession interface

    @property
    def id(self) -> str:
        # Use first activity ID or generate one
        if self.review.activities:
            return self.review.activities[0].id
        return str(uuid4())

    @property
    def created_at(self) -> datetime:
        # Find earliest activity
        for activity in self.review.activities:
            if activity.created:
                return datetime.fromisoformat(activity.created.replace("Z", "+00:00"))
        return datetime.now()

    @property
    def updated_at(self) -> datetime:
        # Find latest activity
        latest = None
        for activity in self.review.activities:
            if activity.created:
                dt = datetime.fromisoformat(activity.created.replace("Z", "+00:00"))
                if latest is None or dt > latest:
                    latest = dt
        return latest or datetime.now()

    @property
    def notes(self) -> str:
        return ""

    @property
    def files(self) -> dict[str, FileReviewState]:
        """Get file states dict."""
        return {
            path: FileReviewState(file_path=path, _session=self)
            for path in self._file_paths
        }

    @property
    def reviewed_count(self) -> int:
        return sum(1 for p in self._file_paths if self._is_file_reviewed(p))

    @property
    def total_files(self) -> int:
        return len(self._file_paths)

    @property
    def all_comments(self) -> list[CommentView]:
        """Get all visible comments."""
        comments = []
        visible = self.review.get_visible_activities()
        for activity in visible:
            if isinstance(activity, OCRComment):
                comments.append(CommentView(_comment=activity))
        return sorted(
            comments,
            key=lambda c: (c.file_path, c.line_no if c.line_no else 0)
        )

    @property
    def total_comments(self) -> int:
        return len(self.all_comments)

    def get_file_state(self, file_path: str) -> FileReviewState:
        """Get file review state."""
        if file_path not in self._file_paths:
            self._file_paths.append(file_path)
        return FileReviewState(file_path=file_path, _session=self)

    # Internal query methods

    def _is_file_reviewed(self, file_path: str) -> bool:
        """Check if file has an active reviewed mark."""
        visible = self.review.get_visible_activities()
        for activity in visible:
            if isinstance(activity, ReviewMark) and activity.category == "reviewed":
                if activity.location and activity.location.file == file_path:
                    # File-level review mark (no lines)
                    if not activity.location.lines:
                        return True
        return False

    def _get_file_reviewed_mark_id(self, file_path: str) -> str | None:
        """Get the ID of the file's reviewed mark, if any."""
        visible = self.review.get_visible_activities()
        for activity in visible:
            if isinstance(activity, ReviewMark) and activity.category == "reviewed":
                if activity.location and activity.location.file == file_path:
                    if not activity.location.lines:
                        return activity.id
        return None

    def _get_file_comments(self, file_path: str) -> list[CommentView]:
        """Get visible comments for a file."""
        comments = []
        visible = self.review.get_visible_activities()
        for activity in visible:
            if isinstance(activity, OCRComment):
                if activity.location and activity.location.file == file_path:
                    comments.append(CommentView(_comment=activity))
        return comments

    def _get_file_resolved_hunks(self, file_path: str) -> list[dict]:
        """Get resolved hunks for a file as dicts."""
        hunks = []
        visible = self.review.get_visible_activities()
        for activity in visible:
            if isinstance(activity, ReviewMark) and activity.category == "reviewed":
                if activity.location and activity.location.file == file_path:
                    if activity.location.lines:
                        # This is a hunk review, not file-level
                        for start, end in activity.location.lines:
                            hunks.append({
                                "id": activity.id,
                                "hunk_id": f"{file_path}::{start}-{end}",
                                "file_path": file_path,
                                "old_start": start,
                                "old_count": end - start + 1,
                                "new_start": start,
                                "new_count": end - start + 1,
                                "header": "",
                                "lines_preview": "",
                            })
        return hunks

    def _is_hunk_resolved(self, file_path: str, hunk_id: str) -> bool:
        """Check if a hunk is resolved."""
        # hunk_id format: "file_path::hash" or custom format
        for hunk in self._get_file_resolved_hunks(file_path):
            if hunk["hunk_id"] == hunk_id:
                return True
        return False

    def _get_hunk_review_mark_id(self, file_path: str, hunk_id: str) -> str | None:
        """Get the ID of a hunk's review mark."""
        for hunk in self._get_file_resolved_hunks(file_path):
            if hunk["hunk_id"] == hunk_id:
                return hunk["id"]
        return None

    # Mutation methods (append activities)

    def add_comment(
        self,
        content: str,
        file_path: str,
        category: str = "note",
        line_no: int | None = None,
        line_no_end: int | None = None,
        is_agent: bool = False,
        agent_name: str = "Claude",
        agent_model: str = "opus",
    ) -> CommentView:
        """Add a comment."""
        # Map acre category to OCR
        ocr_category = ACRE_TO_OCR_CATEGORY.get(category, "note")

        # Create author
        if is_agent:
            author = make_agent_author(agent_name, agent_model)
        else:
            author = make_human_author()

        # Create location
        location = None
        if file_path:
            lines = None
            if line_no is not None:
                end = line_no_end if line_no_end else line_no
                lines = [(line_no, end)]
            location = Location(file=file_path, lines=lines)

        comment = OCRComment(
            category=ocr_category,
            content=content,
            author=author,
            location=location,
        )

        self.review.activities.append(comment)
        return CommentView(_comment=comment)

    def add_reply(
        self,
        parent_id: str,
        content: str,
        is_agent: bool = True,
        agent_name: str = "Claude",
        agent_model: str = "opus",
    ) -> CommentView | None:
        """Add a reply to a comment."""
        # Find parent comment
        for activity in self.review.activities:
            if isinstance(activity, OCRComment) and activity.id == parent_id:
                if is_agent:
                    author = make_agent_author(agent_name, agent_model)
                else:
                    author = make_human_author()

                reply = OCRComment(
                    category="note",
                    content=content,
                    author=author,
                    addresses=[parent_id],
                )
                activity.replies.append(reply)
                return CommentView(_comment=reply)
        return None

    def resolve_comment(self, comment_id: str) -> None:
        """Resolve a comment (mark as addressed)."""
        resolution = Resolution(
            category="resolved",
            addresses=[comment_id],
            author=make_human_author(),
        )
        self.review.activities.append(resolution)

    def edit_comment(
        self,
        comment_id: str,
        new_content: str,
    ) -> CommentView | None:
        """Edit a comment by creating a new one that supersedes it."""
        # Find original comment
        for activity in self.review.activities:
            if isinstance(activity, OCRComment) and activity.id == comment_id:
                new_comment = OCRComment(
                    category=activity.category,
                    content=new_content,
                    author=activity.author,
                    location=activity.location,
                    supersedes=[comment_id],
                )
                self.review.activities.append(new_comment)
                return CommentView(_comment=new_comment)
        return None

    def toggle_reviewed(self, file_path: str) -> bool:
        """Toggle reviewed status for a file."""
        existing_id = self._get_file_reviewed_mark_id(file_path)

        if existing_id:
            # Currently reviewed - retract the mark
            retraction = Retraction(
                category="retract",
                addresses=[existing_id],
                author=make_human_author(),
            )
            self.review.activities.append(retraction)
            return False
        else:
            # Not reviewed - add a mark
            mark = ReviewMark(
                category="reviewed",
                location=Location(file=file_path),
                author=make_human_author(),
            )
            self.review.activities.append(mark)
            return True

    def resolve_hunk(
        self,
        file_path: str,
        hunk_id: str,
        old_start: int,
        old_count: int,
        new_start: int,
        new_count: int,
        header: str = "",
        lines_preview: str = "",
    ) -> None:
        """Mark a hunk as reviewed."""
        mark = ReviewMark(
            category="reviewed",
            location=Location(file=file_path, lines=[(new_start, new_start + new_count - 1)]),
            author=make_human_author(),
            content=f"Hunk: {header}" if header else None,
        )
        self.review.activities.append(mark)

    def unresolve_hunk(self, file_path: str, hunk_id: str) -> bool:
        """Unmark a hunk as reviewed."""
        mark_id = self._get_hunk_review_mark_id(file_path, hunk_id)
        if mark_id:
            retraction = Retraction(
                category="retract",
                addresses=[mark_id],
                author=make_human_author(),
            )
            self.review.activities.append(retraction)
            return True
        return False

    def touch(self) -> None:
        """No-op since OCR tracks activity timestamps automatically."""
        pass


def get_session_path(
    repo_path: Path,
    diff_source_type: str,
    diff_source_ref: str | None,
    format: str = "xml",
) -> Path:
    """Get the path for storing a session.

    Naming convention:
    - Default (uncommitted, staged, branch): .opencodereview.{ext}
    - commit (-c): .opencodereview.<commit>.{ext}
    - pr (--pr): .opencodereview.pr-<number>.{ext}
    """
    ext = format
    base = ".opencodereview"

    if diff_source_type == "commit" and diff_source_ref:
        ref = diff_source_ref[:7] if len(diff_source_ref) > 7 else diff_source_ref
        suffix = f".{ref}"
    elif diff_source_type == "pr" and diff_source_ref:
        suffix = f".pr-{diff_source_ref}"
    else:
        suffix = ""

    return repo_path / f"{base}{suffix}.{ext}"
