from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from glab_discussion.api import glab_api
from glab_discussion.context import resolve_mr_context
from glab_discussion.formatter import format_discussion, format_discussions
from glab_discussion.models import Discussion, UserInfo, parse_discussion
from glab_discussion.sanitize import sanitize_filename_part, sanitize_path_part
from glab_discussion.terminal import is_interactive_terminal
from glab_discussion.users import display_name, enrich_discussions_with_bot_info


def _discussion_filename(discussion: Discussion, user_cache: dict[int, UserInfo]) -> str:
    """Compute filename for a discussion dump file."""
    first = discussion.first_note
    dt = sanitize_filename_part(first.created_at.split(".")[0])
    user = user_cache.get(first.author_id)
    name = sanitize_filename_part(display_name(user) if user else first.author_username)
    if user and user.is_bot:
        name = f"bot-{name}"
    short_id = sanitize_filename_part(discussion.id[:12])
    return f"{dt}-{name}-{short_id}.txt"


def run(args: argparse.Namespace) -> None:
    # 1. Resolve MR context
    ctx = resolve_mr_context(args)

    # 2. Fetch all discussions
    raw_discussions = glab_api(
        f"projects/{ctx.project_id}/merge_requests/{ctx.mr_iid}/discussions",
        paginate=True,
        hostname=ctx.hostname,
    )

    # 3. Parse discussions
    discussions = [parse_discussion(d) for d in raw_discussions]

    # 4. Filter out system discussions
    discussions = [d for d in discussions if not d.is_system]

    # 5. Enrich with bot info
    user_cache = enrich_discussions_with_bot_info(discussions, ctx.hostname)

    # 6. Determine dump mode
    if args.dump:
        dump_mode = True
    elif args.no_dump:
        dump_mode = False
    else:
        dump_mode = not is_interactive_terminal()

    # 7. Stdout mode
    if not dump_mode:
        print(format_discussions(discussions, ctx.mr_url))
        return

    # 8. Dump mode
    tmp = Path(tempfile.gettempdir())
    output_dir = tmp / "glab-discussion" / sanitize_path_part(ctx.hostname) / f"mr-{ctx.mr_iid}"
    force_full = args.full

    if force_full and output_dir.exists():
        import shutil

        shutil.rmtree(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    meta_path = output_dir / ".meta.json"
    if meta_path.exists():
        old_meta: dict[str, dict] = json.loads(meta_path.read_text())
    else:
        old_meta = {}

    new_meta: dict[str, dict] = {}
    new_files: list[str] = []
    updated_files: list[str] = []

    for discussion in discussions:
        filename = _discussion_filename(discussion, user_cache)
        max_ts = discussion.max_timestamp
        did = discussion.id

        new_meta[did] = {"max_timestamp": max_ts, "filename": filename}

        # Check if we can skip (--full always writes since dir was cleared)
        if did in old_meta:
            old_entry = old_meta[did]
            if old_entry.get("max_timestamp") == max_ts:
                continue

        # Write the file
        content = format_discussion(discussion, ctx.mr_url)
        (output_dir / filename).write_text(content)

        if did in old_meta:
            updated_files.append(filename)
        else:
            new_files.append(filename)

    # Delete files for discussions that no longer exist
    deleted_files: list[str] = []
    for old_did, old_entry in old_meta.items():
        if old_did not in new_meta:
            old_filename = old_entry.get("filename", "")
            if not old_filename or "/" in old_filename or "\\" in old_filename or old_filename.startswith("."):
                continue
            old_file = output_dir / old_filename
            if old_file.resolve().parent != output_dir.resolve():
                continue
            if old_file.exists():
                old_file.unlink()
            deleted_files.append(old_filename)

    # Save updated meta
    meta_path.write_text(json.dumps(new_meta, indent=2) + "\n")

    # Print summary
    print(f"Discussions: {output_dir}/")
    if new_files or updated_files or deleted_files:
        for f in updated_files:
            print(f"  updated: {f}")
        for f in new_files:
            print(f"  new: {f}")
        for f in deleted_files:
            print(f"  deleted: {f}")
    else:
        print("  (no changes)")
