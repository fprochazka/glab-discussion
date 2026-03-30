from __future__ import annotations

from glab_discussion.models import Discussion


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
        line_parts: list[str] = []
        if pos.new_line is not None:
            line_parts.append(f"new:{pos.new_line}")
        if pos.old_line is not None:
            line_parts.append(f"old:{pos.old_line}")
        if line_parts:
            lines.append(f"Line: {' / '.join(line_parts)}")
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
        lines.append(f"[{timestamp}] @{note.author_username}{bot_tag}:")
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
