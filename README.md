# glab-discussion

CLI wrapper around GitLab Discussions REST API for listing, creating, and managing merge request discussions. Built on top of [`glab`](https://docs.gitlab.com/cli/) for authentication.

## Why

The `glab` CLI has no native support for merge request discussions. Reviewing comments, replying to threads, adding inline code review notes, and resolving discussions all require manual API calls with complex nested JSON payloads. This tool wraps those APIs into simple commands, with an incremental dump mode designed for AI agent workflows — each discussion thread gets its own file, only changed threads are rewritten, and bot authors are automatically tagged.

## Installation

```bash
uv tool install glab-discussion
```

### Claude Code plugin

The repo includes a Claude Code plugin with:

- a **skill** that teaches AI agents how to use `glab-discussion`
- a **PreToolUse hook** that blocks three command shapes and redirects the agent to `glab-discussion` instead. This keeps thread IDs, resolve state, and inline diff positions in scope rather than letting the agent wrangle raw API JSON.

```bash
claude plugin marketplace add fprochazka/glab-discussion
claude plugin install glab-discussion@fprochazka-glab-discussion
```

To upgrade after a new release:

```bash
uv tool install --force glab-discussion
uv tool install --force bash-classify
claude plugin marketplace update fprochazka-glab-discussion
claude plugin update glab-discussion@fprochazka-glab-discussion
```

The hook blocks:

| Rule | Shape |
|---|---|
| `mr-discussions-api` | `glab api` against the merge request `discussions`, `notes` and `draft_notes` endpoints that `glab-discussion` replaces. Reactions on a note (`notes/:id/award_emoji`) are allowed, since `glab-discussion` has no command for them |
| `mr-view-comments` | `glab mr view --comments`, its `-c` short form, and `--resolved` / `--unresolved`, which imply it |
| `mr-note` | `glab mr note`, except the read-only `glab mr note list` |

The verdict comes from [`bash-classify`](https://github.com/fprochazka/bash-classify), which parses the command and reports which of those shapes it actually *invokes*. Text that merely names one — a heredoc body, an `echo` argument, a commit message, a `grep` pattern — is not an invocation and is allowed, while a wrapper (`sudo`, `timeout`, `bash -c`, `xargs`) does not hide one.

Without bash-classify the hook still works, but in a degraded mode: it falls back to matching the raw command text. That is wrong in both directions — it denies anything that so much as mentions a blocked command, and it lets `glab mr view 42 -c` through, because the old pattern only ever knew the long `--comments` spelling. Every deny issued that way says so in its reason, and a SessionStart hook says the same thing once at the start of a session, so the agent can tell you to install or upgrade the tool (plugin SessionStart hooks need Claude Code 2.1.257 or newer; versions 2.1.216 to 2.1.252 silently skipped them).

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

Each note is printed with its ID as `(note:123)`. `read` also shows your own pending drafts, marked `[DRAFT]` with an ID like `(draft:45)`: a draft reply appears at the end of its thread, and a draft that starts a new thread gets its own file, `draft-45.txt`. GitLab shows drafts only to their author, so you never see anyone else's.

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

Add `--draft` to write any of these as a pending draft instead. Drafts stay private until you publish them with `drafts publish`, which posts them all as one review with one notification, instead of one notification per comment. `--resolve` on a draft reply resolves the thread when the review is published.

```bash
glab-discussion write --draft --file path/to/file.py --new-line 42 --body "Issue here"
glab-discussion write --draft --reply-to DISCUSSION_ID --resolve --body "Fixed, resolving"
```

Set `GLAB_DISCUSSION_WRITE_AS_DRAFT=true` to make `--draft` the default. It accepts `true`, `1`, `yes`, `false`, `0` and `no`; any other value is an error. `--no-draft` overrides it for one comment.

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

### edit

Edit the body of a note or of your draft. Pass the ID exactly as `read` prints it: `note:123` for a published note, `draft:45` for a draft. Draft IDs and note IDs are separate sequences and can be the same number on one MR, so a bare number is rejected.

```bash
glab-discussion edit note:123 --body "Updated text"
glab-discussion edit draft:45 --body "Updated draft"
echo "From stdin" | glab-discussion edit note:123 --body -
```

### delete

Delete a note or your draft. It takes the same `note:123` or `draft:45` IDs as `edit`.

```bash
glab-discussion delete note:123
glab-discussion delete draft:45
```

### drafts

Publish or delete all your drafts on the MR at once.

```bash
glab-discussion drafts publish                                  # publish all drafts as one review, verdict reviewed
glab-discussion drafts publish --body "Summary"                 # add a summary comment to the review
glab-discussion drafts publish --verdict requested-changes      # give another verdict
glab-discussion drafts publish --verdict approve                # publish and approve
glab-discussion drafts delete                                   # list the drafts that would be deleted
glab-discussion drafts delete --force                           # delete them
```

`--body` is added as one more general draft before publishing, so the summary is part of the review. Drafts cannot be internal, so there is no `--internal` option.

A review always carries a verdict: `--verdict` takes `reviewed`, `requested-changes` or `approve`, and needs GitLab 16.7 or newer. The verdict makes you a reviewer with a review state, and that is what lets the MR author re-request your review after they change the MR.

Without `--verdict`, the verdict is `reviewed`, but only if you have not given the MR a verdict yet. If you have already reviewed it, requested changes or approved it, `drafts publish` stops with an error and publishes nothing, so that it never replaces your earlier verdict silently: pass `--verdict` to say which verdict this review gives. With no drafts and no `--body`, `drafts publish` without `--verdict` fails with "nothing to publish" and does not change your review state.

Your earlier verdict is read from the MR's activity, not from your review state, because GitLab sets the review state to "review started" as soon as you create a draft. The newest of these system notes decides: your own approval, request for changes or review means a verdict; your own "unapproved", or a review requested from you or a review request removed from you, means none. An approval that is still on the MR always counts. This works on every GitLab that supports `--verdict`. Before GitLab 17.10, a review leaves no system note, so an earlier `reviewed` is not found and the default gives the MR `reviewed` again.

For every verdict:

- If you are not a reviewer of the MR, `drafts publish` first adds you, because GitLab sets a review state only for reviewers. This adds a system note to the MR and can create a to-do item for you. If GitLab does not add you, for example because the MR allows only one reviewer and somebody else is the reviewer, nothing is published.
- A new verdict replaces your previous one. GitLab before 19.2 does not do this on its own, so `drafts publish` first removes the previous verdict:
  - If you approved the MR and the new verdict is not `approve`, it revokes your approval. This adds an "unapproved" system note to the MR.
  - If the new verdict is not `requested-changes`, it removes your earlier request for changes, which otherwise keeps blocking the merge even after you mark the MR as reviewed. This needs GitLab EE 17.8 or newer. GitLab CE has no requests for changes that block the merge, so there is nothing to remove there.

  If a removal fails, nothing is published.
- The review is submitted with the `/submit_review` quick action. The command then reads the result back from GitLab and reports only what it confirmed. If the drafts were published but the verdict was not applied, it says so and exits with an error.

`drafts delete --force` deletes the drafts one by one and retries each failure. If some drafts still fail, it lists them and exits with an error; run it again to delete only the drafts that are left.

## Requirements

- [`glab` CLI](https://docs.gitlab.com/cli/) installed and authenticated
- Python 3.12+

The Claude Code plugin's hook additionally needs:

- `jq`
- [`bash-classify`](https://github.com/fprochazka/bash-classify) 0.10.0 or newer. Without it the hook still runs, but falls back to text patterns that can misfire: they deny commands that only mention a blocked command in a heredoc, a commit message or a `grep` pattern.

```bash
uv tool install bash-classify
```

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
