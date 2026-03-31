# glab-discussion

CLI wrapper around GitLab Discussions REST API for listing, creating, and managing merge request discussions. Built on top of [`glab`](https://docs.gitlab.com/cli/) for authentication.

## Why

The `glab` CLI has no native support for merge request discussions. Reviewing comments, replying to threads, adding inline code review notes, and resolving discussions all require manual API calls with complex nested JSON payloads. This tool wraps those APIs into simple commands, with an incremental dump mode designed for AI agent workflows — each discussion thread gets its own file, only changed threads are rewritten, and bot authors are automatically tagged.

## Installation

```bash
uv tool install glab-discussion
```

### Claude Code plugin

The repo includes a Claude Code plugin with a skill that teaches AI agents how to use `glab-discussion`.

```bash
claude plugin marketplace add fprochazka/glab-discussion
claude plugin install glab-discussion@fprochazka-glab-discussion
```

To upgrade after a new release:

```bash
uv tool install --force glab-discussion
claude plugin marketplace update fprochazka-glab-discussion
claude plugin update glab-discussion@fprochazka-glab-discussion
```

## Usage

By default, the MR is auto-detected from the current git branch (via `glab mr view`). Override with `--mr-url` or `--hostname`/`--project`/`--mr-iid`.

### read

Read MR discussions. Prints to stdout by default, or writes per-thread files with `--dump`. In non-interactive environments (AI agents, piped output), `--dump` is the default.

```bash
glab-discussion read                 # auto-detect MR from git branch
glab-discussion read --dump          # one file per thread, incrementally updated
glab-discussion read --dump --full   # clear and rewrite all files
glab-discussion read --no-dump       # force stdout even in non-interactive mode
```

### write

Create a new discussion, reply to a thread, or add an inline diff note.

```bash
glab-discussion write --body "Comment text"
glab-discussion write --reply-to DISCUSSION_ID --body "Reply"
glab-discussion write --file path/to/file.py --new-line 42 --body "Issue here"
glab-discussion write --file path/to/file.py --old-line 10 --body "Was wrong"
echo "From stdin" | glab-discussion write --body -
```

`--new-line` corresponds to the file on the MR source branch — if the branch is checked out locally, local file line numbers match directly. `--old-line` refers to the target branch version.

### diff

Show the MR diff annotated with old/new line numbers, so you know which line numbers to use with `write --new-line` or `--old-line`.

```bash
glab-discussion diff
glab-discussion diff --file path/to/file.py
glab-discussion diff --version 3
```

### resolve

Resolve or unresolve a discussion.

```bash
glab-discussion resolve DISCUSSION_ID
glab-discussion resolve DISCUSSION_ID --unresolve
```

## Requirements

- [`glab` CLI](https://docs.gitlab.com/cli/) installed and authenticated
- Python 3.12+

## Development

```bash
git clone https://github.com/fprochazka/glab-discussion.git
cd glab-discussion
uv sync --dev
```

Run tests and linting:

```bash
uv run ruff format .
uv run ruff check .
uv run pytest
```

## Releasing

Version is derived automatically from git tags via `hatch-vcs` — no manual version bumping needed.

Before tagging, bump the version in both plugin manifest files:

- `coding-agent-plugins/claude-code/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`

Wait for CI to pass on master, then tag, push, and create a GitHub release:

```bash
# Review changes since last release
git log $(git describe --tags --abbrev=0)..HEAD --oneline

git tag v<version>
git push origin v<version>
gh release create v<version> --title "v<version>" --notes "..."
```

The `publish.yml` GitHub Action builds and publishes to PyPI automatically via trusted publishing.
