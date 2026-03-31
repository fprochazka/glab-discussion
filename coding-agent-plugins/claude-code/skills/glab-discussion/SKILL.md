---
name: glab-discussion
description: >-
  This skill should be used when the user asks to "read MR discussions",
  "list MR comments", "reply to a discussion", "resolve a discussion",
  "edit a comment", "delete a comment", "add a diff note", "review MR comments",
  "dump discussions", "show MR diff for commenting", or needs to interact with
  GitLab merge request discussions. Provides CLI reference for the glab-discussion tool.
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

### resolve — Resolve/unresolve a discussion

```bash
glab-discussion resolve <discussion_id>
glab-discussion resolve <discussion_id> --unresolve
```

### edit — Edit an existing note

```bash
glab-discussion edit <note_id> --body "Updated text"
glab-discussion edit <note_id> --body -                          # read body from stdin
```

### delete — Delete a note

```bash
glab-discussion delete <note_id>
```

## Resolving GitLab UI URLs

GitLab UI links to specific notes use `#note_<id>` anchors (e.g.
`https://gitlab.example.com/group/project/-/merge_requests/123#note_456789`).
To find the discussion thread for a note URL, grep the dump files for the note ID:

```bash
grep -rl "note:456789" /tmp/glab-discussion/<host>/mr-<iid>/
```

The matching file contains the full thread. The discussion ID is in the file header
and also in the filename suffix.

## Typical AI Workflow

1. **Read discussions:** `glab-discussion read`
2. **Review dumped files:** Read the TXT files to understand discussion threads
3. **Check diff context:** `glab-discussion diff --file <path>` to see commentable lines
4. **Reply:** `glab-discussion write --reply-to <id> --body "..."`
5. **Add diff note:** `glab-discussion write --file <path> --new-line <n> --body "..."`
6. **Edit a note:** `glab-discussion edit <note_id> --body "..."`
7. **Delete a note:** `glab-discussion delete <note_id>`
8. **Resolve:** `glab-discussion resolve <id>`
9. **Re-read:** `glab-discussion read` to see updated state (incremental, only changed files)

