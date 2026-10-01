---
name: glab-discussion
description: >-
  This skill should be used when the user asks to "read MR discussions",
  "list MR comments", "reply to a discussion", "resolve a discussion",
  "edit a comment", "delete a comment", "add a diff note", "review MR comments",
  "dump discussions", "show MR diff for commenting", "review an MR",
  "write review comments", "publish drafts", "submit a review", or needs to interact with
  GitLab merge request discussions or draft notes. Provides CLI reference for the glab-discussion tool.
---

# glab-discussion CLI

CLI for listing, creating, and managing GitLab merge request discussions.

**The MR is auto-detected from the current git branch** — no flags needed when the
source branch is checked out. Do not pass context flags unless auto-detection fails.
If it does, run `glab-discussion <command> --help` to see override options.

## Subcommands

### read — Read discussions

```bash
glab-discussion read                    # auto-selects dump mode in non-interactive environments
glab-discussion read --dump             # write per-thread TXT files, incrementally updated
glab-discussion read --dump --full      # force full rewrite of all files
glab-discussion read --no-dump          # print to stdout instead
```

Writes one TXT file per discussion thread to `/tmp/glab-discussion/<host>/mr-<iid>/`.
Incremental — only rewrites files when content has changed. Prints a summary of new/updated/deleted files.

Each file contains:
- Header: discussion ID, type (General/DiffNote), resolved status, file/line for diff notes, URL
- Body: chronological notes with timestamps, usernames, note IDs `(note:<id>)`, `[BOT]` for bot accounts
- Your own pending drafts, after the published notes of their thread: `@user [DRAFT] (draft:<id>):`, or
  `[DRAFT, resolves thread]` when publishing the draft resolves the thread. Drafts have no timestamp.
  A draft that starts a new thread gets its own file `draft-<id>.txt` with the header `Discussion: (draft, not published)`.

Pass note and draft IDs to `edit` and `delete` exactly as `read` prints them: `note:123` or `draft:123`.
A bare number is rejected, because a draft and a note on one MR can have the same number.

### diff — Show commentable diff with line numbers

```bash
glab-discussion diff                              # all changed files
glab-discussion diff --file src/Foo.java          # single file
glab-discussion diff --version <version_id>       # specific diff version
```

Outputs an annotated diff showing both old and new line numbers for each line.
Use these line numbers with `write --new-line` or `write --old-line`.

Output format:
```
Version: <id>
base_sha: <sha>
head_sha: <sha>
start_sha: <sha>

--- a/src/Foo.java
+++ b/src/Foo.java
  old | new |
   41 |  41 |      var x = 1;
   42 |     | -    var y = old();
      |  42 | +    var y = newMethod();
   43 |  43 |      var z = 3;
```

### write — Create discussion, reply, or diff note

```bash
# New general discussion thread
glab-discussion write --body "Starting a thread"
glab-discussion write --body -                          # read body from stdin

# Reply to existing thread
glab-discussion write --reply-to <discussion_id> --body "My reply"

# Diff note on a specific line
glab-discussion write --file src/Foo.java --new-line 42 --body "Issue here"
glab-discussion write --file src/Foo.java --old-line 10 --body "Was wrong"
glab-discussion write --file src/Foo.java --new-line 42 --commit <sha> --body "On this version"
```

**Modes** (mutually exclusive):
- `--reply-to <discussion_id>` — reply to an existing thread
- `--file <path>` — create a diff note (requires `--new-line` and/or `--old-line`)
- Neither — create a new general discussion thread

**Line numbers:** `--new-line` corresponds to the file on the MR source branch (HEAD).
If the source branch is checked out locally, local file line numbers match `--new-line` directly —
no need to run `glab-discussion diff` first. `--old-line` refers to the target branch version.

`--commit <sha>` optionally pins to a specific diff version (matched against `head_commit_sha`). Without it, uses the latest version.

**Drafts:** add `--draft` to any mode to write a pending draft instead of a published comment. The output prints the
new ID as `draft:<id>` (published comments print `note:<id>`). With a draft reply, `--resolve` resolves the thread when the draft
is published. `GLAB_DISCUSSION_WRITE_AS_DRAFT=true` makes `--draft` the default; `--no-draft` overrides it.
When the variable made the comment a draft, the output says so on a second line.
See "Giving a review" below for when to use drafts.

### resolve — Resolve/unresolve a discussion

```bash
glab-discussion resolve <discussion_id>
glab-discussion resolve <discussion_id> --unresolve
```

### edit — Edit a note or a draft

```bash
glab-discussion edit note:<id> --body "Updated text"
glab-discussion edit draft:<id> --body "Updated draft"
glab-discussion edit note:<id> --body -                          # read body from stdin
```

### delete — Delete a note or a draft

```bash
glab-discussion delete note:<id>
glab-discussion delete draft:<id>
```

### drafts — Publish or delete all your drafts

```bash
glab-discussion drafts publish                                   # publish all drafts as one review, verdict reviewed
glab-discussion drafts publish --body "Summary of the review"    # add a summary comment, published as part of the review
glab-discussion drafts publish --verdict requested-changes       # verdict: reviewed | requested-changes | approve
glab-discussion drafts delete                                    # list what would be deleted, delete nothing
glab-discussion drafts delete --force                            # delete all drafts
```

`drafts publish` fails with "nothing to publish" when there are no drafts and neither `--body` nor `--verdict` is given.

Every review carries a verdict, because the reviewer status and review state let the MR author re-request your review.
Without `--verdict` the verdict is `reviewed`, but only when you have not given the MR a verdict yet. If you have (reviewed,
requested changes or approved), `drafts publish` exits non-zero and publishes nothing: decide which verdict this review gives,
asking the user if unsure, and pass `--verdict` explicitly.
The earlier verdict comes from the MR's system notes (your approval, request for changes or review, minus a later
"unapproved" or a review request for you), not from the review state, which turns to "review started" when you create a draft.

`--verdict` needs GitLab 16.7 or newer. GitLab sets a verdict only for reviewers, so if you are not a reviewer, `drafts publish`
adds you first: this adds a system note to the MR and can create a to-do item for you. If GitLab does not add you (for example,
the MR allows only one reviewer and someone else is it), nothing is published.

A new verdict replaces your previous one: before publishing, the command revokes your approval when the new verdict is not
`approve` (this adds an "unapproved" system note), and removes your earlier request for changes when the new verdict is not
`requested-changes` (GitLab EE 17.8+). If a removal fails, nothing is published. After publishing, the command reads the verdict
back and exits non-zero if the drafts were published but the verdict was not applied; tell the user what it reports.
There is no `--internal`: drafts cannot be internal.

`drafts delete --force` retries each failed delete. If some drafts still fail, it lists them and exits non-zero;
run it again, it deletes only the drafts that are left.

## Giving a review

Use `--draft` only when giving a review with many comments on one MR. Every published comment notifies everyone who
watches the MR, once per comment. Drafts arrive as one review with one notification, and the author reads them together.
Single replies and quick answers stay normal comments.

1. Write each review comment with `write --draft` (inline with `--file`/`--new-line`, replies with `--reply-to`).
2. Check the drafts with `glab-discussion read` before publishing; fix them with `edit draft:<id>` or `delete draft:<id>`.
3. Publish with `glab-discussion drafts publish`, optionally with `--body` and `--verdict` (default `reviewed` on a first review).
4. To approve together with the review, use `drafts publish --verdict approve`.

Drafts are private to the GitLab user whose token created them. When glab runs as the user, the user sees your drafts
in the review panel of the GitLab UI and can edit and submit them there instead.

## Resolving GitLab UI URLs

GitLab UI links to specific notes use `#note_<id>` anchors (e.g.
`https://gitlab.example.com/group/project/-/merge_requests/123#note_456789`).
To find the discussion thread for a note URL, grep the dump files for the note ID:

```bash
grep -rl "note:456789" /tmp/glab-discussion/<host>/mr-<iid>/
```

The matching file contains the full thread. The discussion ID is in the file header
and also in the filename suffix.

A draft never appears in a URL: GitLab links only to published notes.

## Typical AI Workflow

1. **Read discussions:** `glab-discussion read`
2. **Review dumped files:** Read the TXT files to understand discussion threads
3. **Check diff context:** `glab-discussion diff --file <path>` to see commentable lines
4. **Reply:** `glab-discussion write --reply-to <id> --body "..."`
5. **Add diff note:** `glab-discussion write --file <path> --new-line <n> --body "..."`
6. **Edit a note:** `glab-discussion edit note:<id> --body "..."`
7. **Delete a note:** `glab-discussion delete note:<id>`
8. **Resolve:** `glab-discussion resolve <id>`
9. **Re-read:** `glab-discussion read` to see updated state (incremental, only changed files)

