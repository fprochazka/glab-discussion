from __future__ import annotations

import argparse

from glab_discussion.api import glab_api
from glab_discussion.context import resolve_mr_context
from glab_discussion.ids import NoteRef


def run(args: argparse.Namespace) -> None:
    ctx = resolve_mr_context(args)
    ref: NoteRef = args.note_ref

    resource = "draft_notes" if ref.is_draft else "notes"
    glab_api(
        f"projects/{ctx.project_id}/merge_requests/{ctx.mr_iid}/{resource}/{ref.id}",
        method="DELETE",
        hostname=ctx.hostname,
    )

    print(f"Deleted {ref}")
