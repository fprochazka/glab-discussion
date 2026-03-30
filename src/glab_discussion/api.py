from __future__ import annotations

import json
import subprocess
from typing import Any


class GlabApiError(Exception):
    def __init__(self, message: str, stderr: str = "", returncode: int = 1):
        super().__init__(message)
        self.stderr = stderr
        self.returncode = returncode


def glab_api(
    endpoint: str,
    *,
    method: str | None = None,
    fields: dict[str, str] | None = None,
    raw_fields: dict[str, str] | None = None,
    hostname: str | None = None,
    paginate: bool = False,
) -> Any:
    """Call glab api and return parsed JSON response."""
    cmd = ["glab", "api", endpoint]
    if method:
        cmd.extend(["-X", method])
    if hostname:
        cmd.extend(["--hostname", hostname])
    if paginate:
        cmd.append("--paginate")
    if fields:
        for k, v in fields.items():
            cmd.extend(["-F", f"{k}={v}"])
    if raw_fields:
        for k, v in raw_fields.items():
            cmd.extend(["-f", f"{k}={v}"])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise GlabApiError(
            f"glab api failed: {result.stderr.strip()}",
            stderr=result.stderr,
            returncode=result.returncode,
        )

    if not result.stdout.strip():
        return None
    return json.loads(result.stdout)


def glab_mr_view_json(hostname: str | None = None) -> dict:
    """Run glab mr view --output json to get current MR info."""
    cmd = ["glab", "mr", "view", "--output", "json"]
    if hostname:
        cmd.extend(["--hostname", hostname])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise GlabApiError(
            f"glab mr view failed: {result.stderr.strip()}",
            stderr=result.stderr,
            returncode=result.returncode,
        )
    return json.loads(result.stdout)
