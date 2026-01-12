"""LLM integration for acre using Claude CLI subprocess."""

import json
import subprocess
from dataclasses import dataclass, field
from typing import Iterator

from acre.models.diff import DiffFile, DiffHunk


@dataclass
class LLMMessage:
    """A message in an LLM conversation."""

    role: str  # "user" or "assistant"
    content: str


@dataclass
class LLMSession:
    """An LLM conversation session."""

    messages: list[LLMMessage] = field(default_factory=list)
    context: str = ""  # Initial context (diff, file info, etc.)

    def add_user_message(self, content: str) -> None:
        """Add a user message to the conversation."""
        self.messages.append(LLMMessage(role="user", content=content))

    def add_assistant_message(self, content: str) -> None:
        """Add an assistant message to the conversation."""
        self.messages.append(LLMMessage(role="assistant", content=content))


class ClaudeCLIBackend:
    """LLM backend using the Claude CLI (claude command)."""

    def __init__(self):
        self._check_claude_cli()

    def _check_claude_cli(self) -> None:
        """Verify claude CLI is available."""
        try:
            result = subprocess.run(
                ["claude", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                raise RuntimeError("Claude CLI not working")
        except FileNotFoundError:
            raise RuntimeError(
                "Claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code"
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("Claude CLI timed out")

    def analyze(
        self,
        prompt: str,
        context: str | None = None,
        stream: bool = False,
    ) -> str | Iterator[str]:
        """Send a prompt to Claude and get a response.

        Args:
            prompt: The user's question or request
            context: Optional context to include (diff, file contents, etc.)
            stream: If True, return an iterator of chunks

        Returns:
            The response text, or an iterator of text chunks if streaming
        """
        # Build the full prompt with context
        full_prompt = ""
        if context:
            full_prompt = f"{context}\n\n{prompt}"
        else:
            full_prompt = prompt

        if stream:
            return self._stream_response(full_prompt)
        else:
            return self._get_response(full_prompt)

    def _get_response(self, prompt: str) -> str:
        """Get a complete response from Claude."""
        result = subprocess.run(
            ["claude", "--print", "--verbose", prompt],
            capture_output=True,
            text=True,
            timeout=120,  # 2 minute timeout
        )

        if result.returncode != 0:
            raise RuntimeError(f"Claude CLI error: {result.stderr}")

        return result.stdout.strip()

    def _stream_response(self, prompt: str) -> Iterator[str]:
        """Stream response from Claude using --output-format stream-json."""
        process = subprocess.Popen(
            ["claude", "--print", "--verbose", "--output-format", "stream-json", prompt],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # Line buffered
        )

        try:
            # Read JSON events line by line
            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    # Extract text from assistant message events
                    if event.get("type") == "assistant":
                        message = event.get("message", {})
                        for block in message.get("content", []):
                            if block.get("type") == "text":
                                yield block.get("text", "")
                    # Also handle content_block_delta for streaming chunks
                    elif event.get("type") == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            yield delta.get("text", "")
                except json.JSONDecodeError:
                    # Skip malformed lines
                    continue
        finally:
            process.wait()
            if process.returncode != 0:
                stderr = process.stderr.read()
                if stderr:
                    raise RuntimeError(f"Claude CLI error: {stderr}")


def build_analysis_context(
    file: DiffFile,
    hunk: DiffHunk | None = None,
    comments: list[str] | None = None,
) -> str:
    """Build context string for LLM analysis.

    Args:
        file: The diff file being analyzed
        hunk: Optional specific hunk to focus on
        comments: Optional list of existing comments

    Returns:
        Formatted context string
    """
    lines = []

    # File info
    lines.append(f"File: {file.path}")
    lines.append(f"Status: {file.status}")
    lines.append(f"Changes: +{file.added_lines} -{file.removed_lines}")
    lines.append("")

    # If specific hunk, show just that
    if hunk:
        lines.append("=== Hunk ===")
        lines.append(f"@@ -{hunk.old_start},{hunk.old_count} +{hunk.new_start},{hunk.new_count} @@")
        if hunk.header:
            lines.append(f"Context: {hunk.header}")
        lines.append("")
        for diff_line in hunk.lines:
            prefix = {
                "addition": "+",
                "deletion": "-",
                "context": " ",
            }.get(diff_line.line_type.value, " ")
            lines.append(f"{prefix}{diff_line.content}")
    else:
        # Show all hunks
        lines.append("=== Diff ===")
        for hunk in file.hunks:
            lines.append(f"@@ -{hunk.old_start},{hunk.old_count} +{hunk.new_start},{hunk.new_count} @@")
            if hunk.header:
                lines.append(f"  {hunk.header}")
            for diff_line in hunk.lines:
                prefix = {
                    "addition": "+",
                    "deletion": "-",
                    "context": " ",
                }.get(diff_line.line_type.value, " ")
                lines.append(f"{prefix}{diff_line.content}")
            lines.append("")

    # Existing comments
    if comments:
        lines.append("")
        lines.append("=== Existing Review Comments ===")
        for comment in comments:
            lines.append(f"- {comment}")

    return "\n".join(lines)


def get_analysis_prompts() -> dict[str, str]:
    """Get standard analysis prompts."""
    return {
        "review": (
            "Please review this code change. Focus on:\n"
            "1. Potential bugs or issues\n"
            "2. Code quality and readability\n"
            "3. Performance implications\n"
            "4. Security concerns\n"
            "Be concise and specific."
        ),
        "explain": (
            "Please explain what this code change does. "
            "Be concise and focus on the key functionality."
        ),
        "suggest": (
            "Please suggest improvements to this code. "
            "Focus on code quality, readability, and best practices."
        ),
        "security": (
            "Please analyze this code for security vulnerabilities. "
            "Focus on common issues like injection, authentication, data handling."
        ),
    }
