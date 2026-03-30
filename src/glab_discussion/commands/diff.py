from __future__ import annotations

import argparse
import re
import sys

from glab_discussion.api import glab_api
from glab_discussion.context import resolve_mr_context

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)$")


def annotate_diff(diff_text: str) -> list[str]:
    """Parse unified diff and produce annotated lines with old/new line numbers."""
    lines = diff_text.split("\n")
    result: list[str] = []
    old_line = 0
    new_line = 0

    for line in lines:
        hunk_match = HUNK_RE.match(line)
        if hunk_match:
            old_line = int(hunk_match.group(1))
            new_line = int(hunk_match.group(2))
            # Print hunk header without line numbers
            result.append(f"{'':>5} | {'':>5} | {line}")
            continue

        if old_line == 0 and new_line == 0:
            # Before any hunk, skip diff headers (---, +++ etc)
            continue

        if line.startswith("-"):
            result.append(f"{old_line:>5} | {'':>5} | {line}")
            old_line += 1
        elif line.startswith("+"):
            result.append(f"{'':>5} | {new_line:>5} | {line}")
            new_line += 1
        elif line.startswith(" ") or line == "":
            if old_line > 0 or new_line > 0:
                result.append(f"{old_line:>5} | {new_line:>5} | {line}")
                old_line += 1
                new_line += 1
        # Skip "\ No newline at end of file"

    return result


def run(args: argparse.Namespace) -> None:
    ctx = resolve_mr_context(args)

    # Fetch MR diff versions
    versions = glab_api(
        f"projects/{ctx.project_id}/merge_requests/{ctx.mr_iid}/versions",
        hostname=ctx.hostname,
    )

    if not versions:
        print("No diff versions found.", file=sys.stderr)
        sys.exit(1)

    # Select version
    version = None
    if getattr(args, "version", None) is not None:
        for v in versions:
            if v["id"] == args.version:
                version = v
                break
        if version is None:
            print(f"Version {args.version} not found.", file=sys.stderr)
            sys.exit(1)
    else:
        version = versions[0]  # latest

    version_id = version["id"]

    # Fetch the full version detail (includes diffs inline)
    version_detail = glab_api(
        f"projects/{ctx.project_id}/merge_requests/{ctx.mr_iid}/versions/{version_id}",
        hostname=ctx.hostname,
    )

    diffs = version_detail.get("diffs", [])
    if not diffs:
        print("No diffs found for this version.", file=sys.stderr)
        sys.exit(1)

    # Filter by file if requested
    file_filter = getattr(args, "file", None)
    if file_filter:
        diffs = [d for d in diffs if d.get("new_path") == file_filter or d.get("old_path") == file_filter]
        if not diffs:
            print(f"No diffs found for file: {file_filter}", file=sys.stderr)
            sys.exit(1)

    # Print version header
    print(f"Version: {version_id}")
    print(f"base_sha: {version['base_commit_sha']}")
    print(f"head_sha: {version['head_commit_sha']}")
    print(f"start_sha: {version['start_commit_sha']}")

    # Print each diff
    for diff_entry in diffs:
        old_path = diff_entry.get("old_path", "")
        new_path = diff_entry.get("new_path", "")
        diff_text = diff_entry.get("diff", "")

        print()
        print(f"--- a/{old_path}")
        print(f"+++ b/{new_path}")

        if diff_text:
            annotated = annotate_diff(diff_text)
            for line in annotated:
                print(line)
