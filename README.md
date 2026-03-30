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
