from __future__ import annotations

import argparse
import os
import sys

from glab_discussion.api import glab_api
from glab_discussion.context import resolve_mr_context
from glab_discussion.models import MrContext

DRAFT_ENV_VAR = "GLAB_DISCUSSION_WRITE_AS_DRAFT"
_TRUE_VALUES = {"true", "1", "yes"}
_FALSE_VALUES = {"false", "0", "no", ""}


def build_position(version: dict, file: str, new_line: int | None, old_line: int | None) -> dict:
    """Build the `position` of a diff note on one line of `file` in the given MR diff version."""
    position: dict = {
        "position_type": "text",
        "base_sha": version["base_commit_sha"],
        "head_sha": version["head_commit_sha"],
        "start_sha": version["start_commit_sha"],
        "old_path": file,
        "new_path": file,
    }

    if new_line is not None:
        position["new_line"] = new_line
    if old_line is not None:
        position["old_line"] = old_line

    return position


def write_as_draft(args: argparse.Namespace) -> bool:
    """Decide whether to write a draft: --draft or --no-draft win, otherwise GLAB_DISCUSSION_WRITE_AS_DRAFT decides."""
    if getattr(args, "draft", False):
        return True
    if getattr(args, "no_draft", False):
        return False

    value = os.environ.get(DRAFT_ENV_VAR, "")
    normalized = value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False

    print(
        f"Error: {DRAFT_ENV_VAR} is set to '{value}', which is not a known value."
        " Set it to true, 1, yes, false, 0 or no, or pass --draft or --no-draft.",
        file=sys.stderr,
    )
    sys.exit(1)


def _select_version(ctx: MrContext, commit: str | None) -> dict:
    versions = glab_api(
        f"projects/{ctx.project_id}/merge_requests/{ctx.mr_iid}/versions",
        hostname=ctx.hostname,
    )

    if not commit:
        return versions[0]  # latest

    # Find version matching the given commit SHA
    for v in versions:
        if v["head_commit_sha"] == commit:
            return v
    print(
        f"Error: no diff version found for commit {commit}",
        file=sys.stderr,
    )
    sys.exit(1)


def run(args: argparse.Namespace) -> None:
    # 1. Validate options before any API call
    if args.reply_to and args.file:
        print("Error: --reply-to and --file are mutually exclusive", file=sys.stderr)
        sys.exit(1)

    if args.file and args.new_line is None and args.old_line is None:
        print(
            "Error: --file requires at least one of --new-line or --old-line",
            file=sys.stderr,
        )
        sys.exit(1)

    draft = write_as_draft(args)
    resolve = getattr(args, "resolve", False)

    if resolve and not (draft and args.reply_to):
        print(
            "Error: --resolve works only on a draft reply. Use it with --reply-to and --draft,"
            " or resolve a thread directly with 'glab-discussion resolve'.",
            file=sys.stderr,
        )
        sys.exit(1)

    # 2. Resolve MR context
    ctx = resolve_mr_context(args)

    # 3. Read body
    body = sys.stdin.read() if args.body == "-" else args.body

    # 4. Determine mode and execute
    if draft:
        _write_draft(args, ctx, body, resolve)
        return

    if args.reply_to:
        # Reply to existing discussion
        result = glab_api(
            f"projects/{ctx.project_id}/merge_requests/{ctx.mr_iid}/discussions/{args.reply_to}/notes",
            method="POST",
            raw_fields={"body": body},
            hostname=ctx.hostname,
        )
        print(f"Replied to discussion {args.reply_to} (note:{result['id']}) - {ctx.mr_url}#note_{result['id']}")

    elif args.file:
        # Diff note mode - fetch versions to get SHAs
        version = _select_version(ctx, args.commit)
        position = build_position(version, args.file, args.new_line, args.old_line)

        result = glab_api(
            f"projects/{ctx.project_id}/merge_requests/{ctx.mr_iid}/discussions",
            method="POST",
            json_body={"body": body, "position": position},
            hostname=ctx.hostname,
        )

        line = args.new_line if args.new_line is not None else args.old_line
        note_id = result["notes"][0]["id"]
        print(
            f"Created diff note on {args.file}:{line} (discussion {result['id']}, note:{note_id})"
            f" - {ctx.mr_url}#note_{note_id}"
        )

    else:
        # New general discussion thread
        result = glab_api(
            f"projects/{ctx.project_id}/merge_requests/{ctx.mr_iid}/discussions",
            method="POST",
            raw_fields={"body": body},
            hostname=ctx.hostname,
        )
        note_id = result["notes"][0]["id"]
        print(f"Created discussion {result['id']} (note:{note_id}) - {ctx.mr_url}#note_{note_id}")


def _write_draft(args: argparse.Namespace, ctx: MrContext, body: str, resolve: bool) -> None:
    payload: dict = {"note": body}
    if args.reply_to:
        payload["in_reply_to_discussion_id"] = args.reply_to
        if resolve:
            payload["resolve_discussion"] = True
        target = f"reply to discussion {args.reply_to}" + (", resolves the thread" if resolve else "")
    elif args.file:
        version = _select_version(ctx, args.commit)
        payload["position"] = build_position(version, args.file, args.new_line, args.old_line)
        line = args.new_line if args.new_line is not None else args.old_line
        target = f"diff note on {args.file}:{line}"
    else:
        target = "new thread"

    result = glab_api(
        f"projects/{ctx.project_id}/merge_requests/{ctx.mr_iid}/draft_notes",
        method="POST",
        json_body=payload,
        hostname=ctx.hostname,
    )

    print(f"Created draft:{result['id']} ({target}). Only you can see it until 'glab-discussion drafts publish'.")
