from __future__ import annotations

import argparse
import sys

from glab_discussion.api import glab_api
from glab_discussion.context import resolve_mr_context


def run(args: argparse.Namespace) -> None:
    ctx = resolve_mr_context(args)

    body = sys.stdin.read() if args.body == "-" else args.body

    glab_api(
        f"projects/{ctx.project_id}/merge_requests/{ctx.mr_iid}/notes/{args.note_id}",
        method="PUT",
        raw_fields={"body": body},
        hostname=ctx.hostname,
    )

    print(f"Edited note {args.note_id}")
