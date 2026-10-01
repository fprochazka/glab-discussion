from __future__ import annotations

import argparse
import sys

from glab_discussion.api import glab_api
from glab_discussion.context import resolve_mr_context
from glab_discussion.ids import NoteRef
from glab_discussion.models import is_inline_draft_position

# The position fields the draft notes API accepts back on update.
_POSITION_KEYS = ("position_type", "base_sha", "start_sha", "head_sha", "old_path", "new_path", "old_line", "new_line")


def run(args: argparse.Namespace) -> None:
    ctx = resolve_mr_context(args)
    ref: NoteRef = args.note_ref

    body = sys.stdin.read() if args.body == "-" else args.body

    mr_path = f"projects/{ctx.project_id}/merge_requests/{ctx.mr_iid}"
    if ref.is_draft:
        draft_path = f"{mr_path}/draft_notes/{ref.id}"
        # Works around a GitLab API bug present since 16.3 (commit f17012fd): `PUT .../draft_notes/:id` sets
        # `position` to nil when the request does not send one, which turns an inline draft into a general
        # one. The UI's own route does not do this. Send the existing position back with the new text.
        draft = glab_api(draft_path, hostname=ctx.hostname)
        position = (draft or {}).get("position") or {}
        if is_inline_draft_position(position):
            kept = {key: position.get(key) for key in _POSITION_KEYS}
            if position.get("line_range"):
                kept["line_range"] = position["line_range"]
            glab_api(draft_path, method="PUT", json_body={"note": body, "position": kept}, hostname=ctx.hostname)
        else:
            glab_api(draft_path, method="PUT", raw_fields={"note": body}, hostname=ctx.hostname)
    else:
        glab_api(
            f"{mr_path}/notes/{ref.id}",
            method="PUT",
            raw_fields={"body": body},
            hostname=ctx.hostname,
        )

    print(f"Edited {ref}")
