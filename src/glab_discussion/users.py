from __future__ import annotations

import json
from pathlib import Path

from glab_discussion.api import glab_api
from glab_discussion.models import Discussion, UserInfo
from glab_discussion.sanitize import sanitize_path_part

_CACHE_DIR = Path.home() / ".cache" / "glab-discussion"


def get_user_info(user_id: int, hostname: str) -> UserInfo:
    """Fetch user info, with file-based caching per hostname."""
    cache_dir = _CACHE_DIR / sanitize_path_part(hostname)
    cache_file = cache_dir / f"user-{user_id}.json"

    if cache_file.exists():
        data = json.loads(cache_file.read_text())
        return UserInfo(
            id=data["id"],
            username=data["username"],
            name=data["name"],
            is_bot=data.get("bot", False),
        )

    data = glab_api(f"users/{user_id}", hostname=hostname)

    cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    cache_file.write_text(json.dumps(data, indent=2))
    cache_file.chmod(0o600)

    return UserInfo(
        id=data["id"],
        username=data["username"],
        name=data["name"],
        is_bot=data.get("bot", False),
    )


def enrich_discussions_with_bot_info(discussions: list[Discussion], hostname: str) -> None:
    """Populate is_bot on all notes in discussions."""
    # Collect unique author IDs
    author_ids: set[int] = set()
    for d in discussions:
        for note in d.notes:
            author_ids.add(note.author_id)

    # Fetch user info for all unique authors
    user_cache: dict[int, UserInfo] = {}
    for uid in author_ids:
        user_cache[uid] = get_user_info(uid, hostname)

    # Enrich notes
    for d in discussions:
        for note in d.notes:
            note.is_bot = user_cache[note.author_id].is_bot
