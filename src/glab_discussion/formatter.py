from __future__ import annotations

from collections.abc import Sequence

from glab_discussion.models import Discussion, DraftNote, Position


def _format_endpoint(old_line: int | None, new_line: int | None) -> str:
    """Format a single (old_line, new_line) pair as e.g. "new:47" or "old:10"."""
    parts: list[str] = []
    if new_line is not None:
        parts.append(f"new:{new_line}")
    if old_line is not None:
        parts.append(f"old:{old_line}")
    return " / ".join(parts)


def _position_lines(pos: Position) -> list[str]:
    lines = [f"File: {pos.new_path}"]
    if pos.line_range is not None:
        start = _format_endpoint(pos.line_range.start.old_line, pos.line_range.start.new_line)
        end = _format_endpoint(pos.line_range.end.old_line, pos.line_range.end.new_line)
        lines.append(f"Lines: {start} to {end}")
    else:
        line = _format_endpoint(pos.old_line, pos.new_line)
        if line:
            lines.append(f"Line: {line}")
    lines.append(f"Commit: {pos.head_sha}")
    return lines


def _draft_entry(draft: DraftNote) -> list[str]:
    bot_tag = " [BOT]" if draft.is_bot else ""
    draft_tag = "[DRAFT, resolves thread]" if draft.resolve_discussion else "[DRAFT]"
    # The draft API returns no timestamps, so a draft has none.
    return [f"@{draft.author_username}{bot_tag} {draft_tag} (draft:{draft.id}):", draft.body, ""]


def group_drafts(
    discussions: Sequence[Discussion], drafts: Sequence[DraftNote]
) -> tuple[dict[str, list[DraftNote]], list[DraftNote]]:
    """Split drafts into replies keyed by the discussion they belong to, and drafts shown as their own thread.

    A reply draft whose discussion is not in `discussions` is shown as its own thread, so it never disappears.
    """
    known_ids = {d.id for d in discussions}
    replies: dict[str, list[DraftNote]] = {}
    standalone: list[DraftNote] = []
    for draft in sorted(drafts, key=lambda d: d.id):
        if draft.discussion_id and draft.discussion_id in known_ids:
            replies.setdefault(draft.discussion_id, []).append(draft)
        else:
            standalone.append(draft)
    return replies, standalone


def format_discussion(discussion: Discussion, mr_url: str, reply_drafts: Sequence[DraftNote] = ()) -> str:
    """Format a discussion as a TXT block, with the caller's reply drafts after the published notes."""
    lines: list[str] = []

    first = discussion.first_note

    # Header
    lines.append(f"Discussion: {discussion.id}")

    if discussion.is_diff_note and first.position:
        lines.append("Type: DiffNote")
        lines.extend(_position_lines(first.position))
    elif discussion.individual_note and discussion.is_system:
        lines.append("Type: System")
    else:
        lines.append("Type: General")

    if any(n.resolvable for n in discussion.notes):
        lines.append(f"Resolved: {'yes' if discussion.resolved else 'no'}")

    # Discussion URL
    discussion_url = f"{mr_url}#note_{first.id}"
    lines.append(f"URL: {discussion_url}")

    lines.append("---")

    # Notes
    for note in discussion.notes:
        bot_tag = " [BOT]" if note.is_bot else ""
        # Simplify ISO timestamp: "2024-01-15T10:30:00.000Z" -> "2024-01-15 10:30:00"
        timestamp = note.created_at.replace("T", " ").split(".")[0]
        lines.append(f"[{timestamp}] @{note.author_username}{bot_tag} (note:{note.id}):")
        lines.append(note.body)
        lines.append("")

    for draft in reply_drafts:
        lines.extend(_draft_entry(draft))

    return "\n".join(lines)


def format_draft_thread(draft: DraftNote) -> str:
    """Format a draft that starts a new thread as a TXT block. It has no discussion ID and no URL yet."""
    lines = ["Discussion: (draft, not published)"]
    if draft.position:
        lines.append("Type: DiffNote")
        lines.extend(_position_lines(draft.position))
    else:
        lines.append("Type: General")
    if draft.discussion_id:
        # A reply to a discussion that `read` did not get, for example one deleted since.
        lines.append(f"Reply to: {draft.discussion_id}")
    lines.append("---")
    lines.extend(_draft_entry(draft))
    return "\n".join(lines)


def format_discussions(discussions: list[Discussion], mr_url: str, drafts: Sequence[DraftNote] = ()) -> str:
    """Format all discussions and the caller's drafts as a single TXT output."""
    discussions = [d for d in discussions if not d.is_system]  # Skip system notes (assigned to, added commit, etc.)
    replies, standalone = group_drafts(discussions, drafts)
    blocks = [format_discussion(d, mr_url, replies.get(d.id, ())) for d in discussions]
    blocks.extend(format_draft_thread(draft) for draft in standalone)
    return "\n\n".join(blocks)
