# acre - Agentic Code Review

A terminal-based code review TUI inspired by [tuicr](https://github.com/agavra/tuicr), built with Python and [Textual](https://textual.textualize.io/).

## Features

- **Infinite scroll diff view** - All changed files in continuous scroll (GitHub-style)
- **Vim keybindings** - j/k, Ctrl-d/u, g/G, {/} (files), [/] (hunks)
- **Commenting system** - Line-level and file-level with categories (Note, Suggestion, Issue, Praise)
- **Review tracking** - Mark files as reviewed, persistent progress
- **Clipboard export** - Structured Markdown optimized for LLM consumption
- **Multiple diff sources** - Uncommitted, staged, branch comparisons, commits, PRs
- **LLM integration** - Send context to Claude for intelligent analysis

## Installation

```bash
uv add acre
```

## Usage

```bash
# Review uncommitted changes
acre review

# Review staged changes only
acre review --staged

# Review changes vs a branch
acre review --branch main

# Review a specific commit
acre review --commit abc123

# Review a GitHub PR
acre review --pr 42
```

## Keybindings

| Key | Action |
|-----|--------|
| j/k | Scroll down/up |
| Ctrl-d/u | Half page down/up |
| Ctrl-f/b | Full page down/up |
| g/G | Go to top/bottom |
| {/} | Previous/next file |
| [/] | Previous/next hunk |
| r | Toggle file reviewed |
| c | Add line comment |
| C | Add file comment |
| Tab | Toggle panel focus |
| ` | Toggle LLM sidebar |
| a | Analyze with Claude |
| :clip | Export to clipboard |
| q | Quit |

## Export Format

Comments are exported in a structured Markdown format optimized for LLM consumption:

```markdown
I reviewed your code and have the following comments. Please address them.

Comment types: ISSUE (problems to fix), SUGGESTION (improvements), NOTE (observations), PRAISE (positive feedback)

1. **[ISSUE]** `src/main.py:42` - This could cause a null pointer exception
2. **[SUGGESTION]** `src/main.py:67` - Consider using a context manager
3. **[NOTE]** `tests/test_main.py` - Missing test coverage for edge cases
```

## Development

```bash
# Clone and install
git clone ...
cd acre
uv sync

# Run
uv run acre review
```

## License

MIT