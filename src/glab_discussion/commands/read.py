from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

from glab_discussion.api import glab_api
from glab_discussion.context import resolve_mr_context
from glab_discussion.formatter import format_discussion, format_discussions, format_draft_thread, group_drafts
from glab_discussion.models import Discussion, UserInfo, parse_discussion, parse_draft_note
from glab_discussion.sanitize import sanitize_filename_part, sanitize_path_part
from glab_discussion.terminal import is_interactive_terminal
from glab_discussion.users import display_name, enrich_discussions_with_bot_info, enrich_drafts_with_user_info


def _discussion_filename(discussion: Discussion, user_cache: dict[int, UserInfo]) -> str:
    """Compute filename for a discussion dump file."""
    first = discussion.first_note
    dt = sanitize_filename_part(first.created_at[:16])
    user = user_cache.get(first.author_id)
    name = sanitize_filename_part(display_name(user) if user else first.author_username)
    if user and user.is_bot:
        name = f"bot-{name}"
    short_id = sanitize_filename_part(discussion.id[:12])
    return f"{dt}-{name}-{short_id}.txt"


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def _safe_dump_file(output_dir: Path, filename: str) -> Path | None:
    """Return the path of a dump file named in .meta.json, or None if the name could point outside output_dir."""
    if not filename or "/" in filename or "\\" in filename or filename.startswith("."):
        return None
    path = output_dir / filename
    if path.resolve().parent != output_dir.resolve():
        return None
    return path


def _load_meta(output_dir: Path, meta_path: Path) -> dict[str, dict]:
    """Load .meta.json, hashing the existing files for entries written before content hashes were stored.

    Entries written by older versions carry `max_timestamp` instead of `hash`. Hashing the file on disk
    lets an unchanged thread stay unchanged instead of forcing a full rewrite. An entry whose file is
    missing gets no hash, so its thread is written again.
    """
    if not meta_path.exists():
        return {}
    meta: dict[str, dict] = json.loads(meta_path.read_text(encoding="utf-8"))
    for entry in meta.values():
        if "hash" in entry:
            continue
        path = _safe_dump_file(output_dir, entry.get("filename", ""))
        if path is not None and path.is_file():
            entry["hash"] = _content_hash(path.read_text(encoding="utf-8"))
    return meta


def run(args: argparse.Namespace) -> None:
    # 1. Resolve MR context
    ctx = resolve_mr_context(args)

    # 2. Fetch all discussions and the caller's drafts
    raw_discussions = glab_api(
        f"projects/{ctx.project_id}/merge_requests/{ctx.mr_iid}/discussions",
        paginate=True,
        hostname=ctx.hostname,
    )
    raw_drafts = glab_api(
        f"projects/{ctx.project_id}/merge_requests/{ctx.mr_iid}/draft_notes",
        paginate=True,
        hostname=ctx.hostname,
    )

    # 3. Parse discussions
    discussions = [parse_discussion(d) for d in raw_discussions]
    drafts = [parse_draft_note(d) for d in raw_drafts or []]

    # 4. Filter out system discussions
    discussions = [d for d in discussions if not d.is_system]

    # 5. Enrich with bot info
    user_cache = enrich_discussions_with_bot_info(discussions, ctx.hostname)
    enrich_drafts_with_user_info(drafts, ctx.hostname, user_cache)

    # 6. Determine dump mode
    if args.dump:
        dump_mode = True
    elif args.no_dump:
        dump_mode = False
    else:
        dump_mode = not is_interactive_terminal()

    # 7. Stdout mode
    if not dump_mode:
        print(format_discussions(discussions, ctx.mr_url, drafts))
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
    old_meta = _load_meta(output_dir, meta_path)

    # Each thread is (key, filename, content). The key is the discussion ID, or draft-{id} for a draft
    # that starts a new thread; publishing the draft removes that key and adds the discussion's.
    replies, standalone = group_drafts(discussions, drafts)
    threads: list[tuple[str, str, str]] = []
    for discussion in discussions:
        content = format_discussion(discussion, ctx.mr_url, replies.get(discussion.id, ()))
        threads.append((discussion.id, _discussion_filename(discussion, user_cache), content))
    for draft in standalone:
        threads.append((f"draft-{draft.id}", f"draft-{draft.id}.txt", format_draft_thread(draft)))

    new_meta: dict[str, dict] = {}
    new_files: list[str] = []
    updated_files: list[str] = []
    stale_files: list[str] = []

    for key, filename, content in threads:
        content_hash = _content_hash(content)
        new_meta[key] = {"filename": filename, "hash": content_hash}

        old_entry = old_meta.get(key)
        if (
            old_entry is not None
            and old_entry.get("hash") == content_hash
            and old_entry.get("filename") == filename
            and (output_dir / filename).is_file()
        ):
            continue

        (output_dir / filename).write_text(content, encoding="utf-8")

        if old_entry is None:
            new_files.append(filename)
        else:
            updated_files.append(filename)
            if old_entry.get("filename") != filename:
                stale_files.append(old_entry.get("filename", ""))

    # Delete files of threads that no longer exist, and files a thread was renamed away from
    deleted_files: list[str] = []
    for old_key, old_entry in old_meta.items():
        if old_key not in new_meta:
            stale_files.append(old_entry.get("filename", ""))
    current_files = {entry["filename"] for entry in new_meta.values()}
    for old_filename in stale_files:
        old_file = _safe_dump_file(output_dir, old_filename)
        if old_file is None or old_filename in current_files:
            continue
        if old_file.exists():
            old_file.unlink()
        deleted_files.append(old_filename)

    # Save updated meta
    meta_path.write_text(json.dumps(new_meta, indent=2) + "\n", encoding="utf-8")

    # Print summary
    is_first_run = not old_meta
    print(f"Discussions: {output_dir}/")
    if is_first_run:
        print(f"  synced {len(new_files)} discussion threads")
    elif new_files or updated_files or deleted_files:
        for f in updated_files:
            print(f"  updated: {f}")
        for f in new_files:
            print(f"  new: {f}")
        for f in deleted_files:
            print(f"  deleted: {f}")
        unchanged = len(threads) - len(new_files) - len(updated_files)
        if unchanged > 0:
            print(f"  ({unchanged} discussions up to date)")
    else:
        print(f"  ({len(threads)} discussions up to date)")
