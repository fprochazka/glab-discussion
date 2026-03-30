from __future__ import annotations

import argparse
import re

from glab_discussion.api import glab_api, glab_mr_view_json
from glab_discussion.models import MrContext


def resolve_mr_context(args: argparse.Namespace) -> MrContext:
    """Resolve MR context from args (--mr-url, --hostname/--project/--mr-iid, or auto-detect)."""
    if getattr(args, "mr_url", None):
        return _parse_mr_url(args.mr_url)

    hostname = getattr(args, "hostname", None)
    project = getattr(args, "project", None)
    mr_iid = getattr(args, "mr_iid", None)

    if hostname and project and mr_iid:
        # Resolve project_id from project path
        project_path_encoded = project.replace("/", "%2F")
        project_data = glab_api(f"projects/{project_path_encoded}", hostname=hostname)
        return MrContext(
            hostname=hostname,
            project_id=project_data["id"],
            project_path=project,
            mr_iid=mr_iid,
            mr_url=f"https://{hostname}/{project}/-/merge_requests/{mr_iid}",
        )

    # Auto-detect from git branch
    mr_data = glab_mr_view_json(hostname=hostname)
    web_url = mr_data["web_url"]
    match = re.match(r"https?://([^/]+)/(.+)/-/merge_requests/(\d+)", web_url)
    if not match:
        raise ValueError(f"Cannot parse MR URL: {web_url}")

    return MrContext(
        hostname=match.group(1),
        project_id=mr_data["project_id"],
        project_path=match.group(2),
        mr_iid=mr_data["iid"],
        mr_url=web_url,
    )


def _parse_mr_url(url: str) -> MrContext:
    """Parse a GitLab MR URL into MrContext."""
    match = re.match(r"https?://([^/]+)/(.+)/-/merge_requests/(\d+)", url)
    if not match:
        raise ValueError(f"Invalid GitLab MR URL: {url}")

    hostname = match.group(1)
    project_path = match.group(2)
    mr_iid = int(match.group(3))
    project_path_encoded = project_path.replace("/", "%2F")

    project_data = glab_api(f"projects/{project_path_encoded}", hostname=hostname)

    return MrContext(
        hostname=hostname,
        project_id=project_data["id"],
        project_path=project_path,
        mr_iid=mr_iid,
        mr_url=url,
    )
