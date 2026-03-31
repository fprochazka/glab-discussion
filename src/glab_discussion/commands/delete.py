from __future__ import annotations

import argparse

from glab_discussion.api import glab_api
from glab_discussion.context import resolve_mr_context


def run(args: argparse.Namespace) -> None:
    ctx = resolve_mr_context(args)

    glab_api(
        f"projects/{ctx.project_id}/merge_requests/{ctx.mr_iid}/notes/{args.note_id}",
        method="DELETE",
        hostname=ctx.hostname,
    )

    print(f"Deleted note {args.note_id}")
