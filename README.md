# glab-discussion

CLI wrapper around GitLab Discussions REST API for listing, creating, and managing merge request discussions.

## Installation

```bash
uv tool install glab-discussion
```

## Usage

All subcommands accept `--mr-url` or `--hostname`/`--project`/`--mr-iid` to identify the merge request.

### read

Read and display MR discussions.

```bash
glab-discussion read --mr-url https://gitlab.com/group/project/-/merge_requests/123
glab-discussion read --dump          # structured data output
glab-discussion read --dump --full   # force full rewrite
```

### write

Create a new discussion or reply to an existing one.

```bash
glab-discussion write --body "Comment text" --mr-url ...
glab-discussion write --body "Reply" --reply-to DISCUSSION_ID --mr-url ...
glab-discussion write --body "Diff note" --file path/to/file.py --new-line 42 --mr-url ...
echo "From stdin" | glab-discussion write --body - --mr-url ...
```

### diff

Show MR diff information.

```bash
glab-discussion diff --mr-url ...
glab-discussion diff --file path/to/file.py --mr-url ...
glab-discussion diff --version 3 --mr-url ...
```

### resolve

Resolve or unresolve a discussion.

```bash
glab-discussion resolve DISCUSSION_ID --mr-url ...
glab-discussion resolve DISCUSSION_ID --unresolve --mr-url ...
```

## Claude Code plugin

The repo includes a Claude Code plugin with a skill that teaches AI agents how to use `glab-discussion`.

```bash
# Install the CLI
uv tool install glab-discussion

# Add the marketplace and install the plugin
claude plugin marketplace add fprochazka/glab-discussion
claude plugin install glab-discussion@fprochazka-glab-discussion
```

To upgrade after a new release:

```bash
uv tool install --force glab-discussion
claude plugin marketplace update fprochazka-glab-discussion
claude plugin update glab-discussion@fprochazka-glab-discussion
```

## Requirements

- `glab` CLI installed and authenticated
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
