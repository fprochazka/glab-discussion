from __future__ import annotations

import argparse

from glab_discussion.api import glab_api
from glab_discussion.context import resolve_mr_context


def run(args: argparse.Namespace) -> None:
    ctx = resolve_mr_context(args)
    resolved = not args.unresolve

    glab_api(
        f"projects/{ctx.project_id}/merge_requests/{ctx.mr_iid}/discussions/{args.discussion_id}",
        method="PUT",
        fields={"resolved": str(resolved).lower()},
        hostname=ctx.hostname,
    )

    action = "Resolved" if resolved else "Unresolved"
    print(f"{action} discussion {args.discussion_id}")
