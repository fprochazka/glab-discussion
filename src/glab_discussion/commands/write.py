from __future__ import annotations

import argparse
import sys

from glab_discussion.api import glab_api
from glab_discussion.context import resolve_mr_context


def run(args: argparse.Namespace) -> None:
    # 1. Resolve MR context
    ctx = resolve_mr_context(args)

    # 2. Read body
    body = sys.stdin.read() if args.body == "-" else args.body

    # 3. Validate mutually exclusive options
    if args.reply_to and args.file:
        print("Error: --reply-to and --file are mutually exclusive", file=sys.stderr)
        sys.exit(1)

    if args.file and args.new_line is None and args.old_line is None:
        print(
            "Error: --file requires at least one of --new-line or --old-line",
            file=sys.stderr,
        )
        sys.exit(1)

    # 4. Determine mode and execute
    if args.reply_to:
        # Reply to existing discussion
        glab_api(
            f"projects/{ctx.project_id}/merge_requests/{ctx.mr_iid}/discussions/{args.reply_to}/notes",
            method="POST",
            raw_fields={"body": body},
            hostname=ctx.hostname,
        )
        print(f"Replied to discussion {args.reply_to}")

    elif args.file:
        # Diff note mode - fetch versions to get SHAs
        versions = glab_api(
            f"projects/{ctx.project_id}/merge_requests/{ctx.mr_iid}/versions",
            hostname=ctx.hostname,
        )

        if args.commit:
            # Find version matching the given commit SHA
            version = None
            for v in versions:
                if v["head_commit_sha"] == args.commit:
                    version = v
                    break
            if version is None:
                print(
                    f"Error: no diff version found for commit {args.commit}",
                    file=sys.stderr,
                )
                sys.exit(1)
        else:
            version = versions[0]  # latest

        position: dict = {
            "position_type": "text",
            "base_sha": version["base_commit_sha"],
            "head_sha": version["head_commit_sha"],
            "start_sha": version["start_commit_sha"],
            "old_path": args.file,
            "new_path": args.file,
        }

        if args.new_line is not None:
            position["new_line"] = args.new_line
        if args.old_line is not None:
            position["old_line"] = args.old_line

        result = glab_api(
            f"projects/{ctx.project_id}/merge_requests/{ctx.mr_iid}/discussions",
            method="POST",
            json_body={"body": body, "position": position},
            hostname=ctx.hostname,
        )

        line = args.new_line if args.new_line is not None else args.old_line
        print(f"Created diff note on {args.file}:{line} (discussion {result['id']})")

    else:
        # New general discussion thread
        result = glab_api(
            f"projects/{ctx.project_id}/merge_requests/{ctx.mr_iid}/discussions",
            method="POST",
            raw_fields={"body": body},
            hostname=ctx.hostname,
        )
        print(f"Created discussion {result['id']}")
