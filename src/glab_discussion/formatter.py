from __future__ import annotations

from glab_discussion.models import Discussion


def _format_endpoint(old_line: int | None, new_line: int | None) -> str:
    """Format a single (old_line, new_line) pair as e.g. "new:47" or "old:10"."""
    parts: list[str] = []
    if new_line is not None:
        parts.append(f"new:{new_line}")
    if old_line is not None:
        parts.append(f"old:{old_line}")
    return " / ".join(parts)


def format_discussion(discussion: Discussion, mr_url: str) -> str:
    """Format a discussion as a TXT block."""
    lines: list[str] = []

    first = discussion.first_note

    # Header
    lines.append(f"Discussion: {discussion.id}")

    if discussion.is_diff_note and first.position:
        lines.append("Type: DiffNote")
        pos = first.position
        lines.append(f"File: {pos.new_path}")
        if pos.line_range is not None:
            start = _format_endpoint(pos.line_range.start.old_line, pos.line_range.start.new_line)
            end = _format_endpoint(pos.line_range.end.old_line, pos.line_range.end.new_line)
            lines.append(f"Lines: {start} to {end}")
        else:
            line = _format_endpoint(pos.old_line, pos.new_line)
            if line:
                lines.append(f"Line: {line}")
        lines.append(f"Commit: {pos.head_sha}")
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

    return "\n".join(lines)


def format_discussions(discussions: list[Discussion], mr_url: str) -> str:
    """Format all discussions as a single TXT output."""
    blocks: list[str] = []
    for d in discussions:
        if d.is_system:
            continue  # Skip system notes (assigned to, added commit, etc.)
        blocks.append(format_discussion(d, mr_url))
    return "\n\n".join(blocks)
