# acre - Agentic Code Review

A terminal code review tool where you and Claude review code together in real time.

You navigate diffs with vim keybindings. You add comments. In another terminal, Claude reads your comments and responds. acre hot-reloads and shows Claude's answers inline, right next to your questions.

```
┌─────────────────────────────────────────────────────────────────┐
│ acre                                          Files: 3/7 [████░]│
├──────────┬──────────────────────────────────────────────────────┤
│ Files    │ @@ -42,6 +42,8 @@ def process_data(items):          │
│          │      for item in items:                              │
│ ✓ api.py │ -        result = transform(item)                    │
│   auth.py│ +        if item is None:                            │
│   utils  │ +            continue                                │
│          │ +        result = transform(item)                    │
│          │                                                      │
│          │  ┃ [ISSUE] L44 (You): Could this cause issues with   │
│          │  ┃ the downstream aggregator?                        │
│          │  ┃   └─ Claude: Good catch! The aggregator expects   │
│          │  ┃      all items to be processed. Consider logging  │
│          │  ┃      skipped items instead of silently dropping.  │
└──────────┴──────────────────────────────────────────────────────┘
```

## How It Works

Your review session is stored in `.acre-review.yaml` - a file designed for both you and Claude to read and edit. The file contains the diff, your comments, and Claude's responses. When either of you saves changes, acre reloads instantly.

## Quick Start

```bash
cd acre
uv sync
uv run acre
```

That's it. acre reviews your uncommitted changes and creates `.acre-review.yaml` in your repo root.

## Usage

```bash
acre                    # Review uncommitted changes (default)
acre --staged           # Only staged changes
acre --branch main      # Changes vs main branch
acre --commit abc123    # A specific commit
acre --pr 42            # GitHub PR (requires gh CLI)
acre --new              # Start fresh, ignore existing session
```

Everything auto-saves. Close acre, come back later, your comments and progress are still there.

## Navigation

acre speaks vim. If you know vim, you already know acre.

| Key | What it does |
|-----|--------------|
| `j` / `k` | Scroll line by line |
| `Ctrl-d` / `Ctrl-u` | Half-page jumps |
| `Ctrl-f` / `Ctrl-b` | Full page jumps |
| `g` / `G` | Jump to top / bottom |
| `{` / `}` | Previous / next file |
| `[` / `]` | Previous / next hunk |
| `n` / `N` | Next / previous comment |

## Reviewing

| Key | What it does |
|-----|--------------|
| `r` | Mark current file as reviewed |
| `c` | Add comment at cursor (or on selection) |
| `C` | Add file-level comment |
| `e` | Edit comment at cursor |
| `x` | Delete comment at cursor |
| `v` | Visual mode - select lines, then `c` to comment on range |

## Panels

| Key | What it does |
|-----|--------------|
| `p` | Toggle comment panel (see all comments) |
| `` ` `` | Toggle LLM sidebar |
| `a` | Analyze current file with Claude |
| `Tab` | Toggle file panel |
| `q` | Quit |

## Comment Categories

When adding a comment, choose a category:

- **NOTE** - Observations, context, things to remember
- **SUGGESTION** - Ideas for improvement (not blocking)
- **ISSUE** - Problems that should be fixed
- **PRAISE** - Positive feedback (yes, this matters!)

## The Magic: LLM Collaboration

Here's where acre gets interesting.

The `.acre-review.yaml` file is designed to be read and written by LLMs. It includes:

1. **Instructions** for Claude on how to participate
2. **Diff context** so Claude can see what changed
3. **Your comments** with a place for Claude to respond

### Workflow

1. Run `acre` and add some comments
2. In another terminal: `cat .acre-review.yaml | claude "Review this and respond to my comments"`
3. Claude edits the file, adding `llm_response` to your comments
4. acre hot-reloads - Claude's responses appear inline!

Or just open the file in Claude Code and have a conversation about the code.

### What Claude Sees

```yaml
instructions: |
  This is an acre code review session.

  FIND comments that need a response (llm_response is null)
  RESPOND by adding llm_response field
  Only ADD new comments if explicitly requested

diff_context: |
  # src/api.py (modified)
  @@ -42,6 +42,8 @@
  -        result = transform(item)
  +        if item is None:
  +            continue
  +        result = transform(item)
---
files:
  src/api.py:
    comments:
      - author: "Jane Developer <jane@example.com>"
        content: "Could this silently drop data?"
        line_no: 44
        context: "@@ -42,6 +42,8 @@ ..."
        llm_response: null  # <-- Claude fills this in
```

Each comment includes the `context` field with the relevant hunk, so Claude has full visibility into what you're commenting on.

## Tips

**Visual selection**: Press `v` to enter visual mode, move to select lines, then `c` to comment on the range. Great for commenting on multi-line changes.

**File-level comments**: Press `C` (capital) to add a comment about the whole file, not a specific line.

**Comment navigation**: Use `n`/`N` to jump between comments. Works even for file-level comments at the top.

**Hot reload**: Edit `.acre-review.yaml` externally (with Claude, vim, whatever). acre picks up changes automatically.

**Session persistence**: Your session is tied to the diff source. `acre --branch main` and `acre --staged` maintain separate sessions.

## Development

```bash
git clone https://github.com/inferaldata/acre
cd acre/acre
uv sync
uv run acre
```

## Built With

- [Textual](https://textual.textualize.io/) - The TUI framework
- [Rich](https://rich.readthedocs.io/) - Terminal formatting
- [Click](https://click.palletsprojects.com/) - CLI interface
- [PyYAML](https://pyyaml.org/) - Session persistence
- [watchfiles](https://watchfiles.helpmanual.io/) - Hot reload

## License

MIT
