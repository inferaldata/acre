"""Command-line interface for acre."""

from pathlib import Path

import click

from acre.app import AcreApp
from acre.core.diff_source import get_diff_source
from acre.core.session import load_session
from acre.models.review import ReviewSession


@click.command()
@click.version_option()
@click.option("--staged", is_flag=True, help="Review staged changes only")
@click.option("--branch", "-b", help="Review changes from base branch (base...HEAD)")
@click.option("--commit", "-c", help="Review a specific commit")
@click.option("--pr", type=int, help="Review a GitHub PR (requires gh CLI)")
@click.option(
    "--repo",
    "-r",
    type=click.Path(exists=True, path_type=Path),
    default=".",
    help="Repository path (default: current directory)",
)
@click.option("--semantic", is_flag=True, help="Enable semantic diff mode (AST-based)")
@click.option("--new", is_flag=True, help="Start a new session (ignore existing)")
def cli(
    staged: bool,
    branch: str | None,
    commit: str | None,
    pr: int | None,
    repo: Path,
    semantic: bool,
    new: bool,
):
    """acre - Agentic Code Review TUI.

    Review code changes with vim keybindings, add structured comments,
    and collaborate with AI via the .acre-review.yaml file.

    All session state is persisted in .acre-review.yaml in the repo root.
    Edit this file with Claude or other LLMs to add comments and responses.

    Examples:

        acre                       # Uncommitted changes (default)
        acre --staged              # Only staged changes
        acre --branch main         # Changes vs main branch
        acre --commit abc123       # Specific commit
        acre --pr 42               # GitHub PR #42
        acre --new                 # Force new session
    """
    repo_path = repo.resolve()

    # Determine diff source type and ref
    if staged:
        source_type = "staged"
        source_ref = None
    elif branch:
        source_type = "branch"
        source_ref = branch
    elif commit:
        source_type = "commit"
        source_ref = commit
    elif pr:
        source_type = "pr"
        source_ref = str(pr)
    else:
        source_type = "uncommitted"
        source_ref = None

    # Create diff source
    source = get_diff_source(
        repo_path=repo_path,
        staged=staged,
        branch=branch,
        commit=commit,
        pr=pr,
    )

    # Load diff
    try:
        diff_set = source.get_diff()
    except Exception as e:
        raise click.ClickException(f"Failed to load diff: {e}")

    if not diff_set.files:
        click.echo("No changes to review.")
        return

    # Check for existing session file
    session = None
    session_file = repo_path / ".acre-review.yaml"

    if session_file.exists() and not new:
        try:
            session = load_session(session_file)
            click.echo(f"Resuming session from {session.updated_at.strftime('%Y-%m-%d %H:%M')}")
            click.echo(f"  {session.total_comments} comments, {session.reviewed_count}/{session.total_files} reviewed")
            click.echo(f"  (use --new to start fresh)")
        except Exception as e:
            click.echo(f"Warning: Could not load existing session: {e}", err=True)
            click.echo("Starting new session.", err=True)
            session = None

    # Create new session if needed
    if session is None:
        session = ReviewSession(
            repo_path=repo_path,
            diff_source_type=source_type,
            diff_source_ref=source_ref,
        )
        session.init_files([f.path for f in diff_set.files])

    # Run app (auto-saves to .acre-review.yaml on changes)
    app = AcreApp(diff_set=diff_set, session=session, semantic_mode=semantic)
    app.run()


if __name__ == "__main__":
    cli()
