from __future__ import annotations

import re


def sanitize_filename_part(s: str) -> str:
    """Replace non-alphanumeric characters with dashes for filesystem safety."""
    return re.sub(r"[^a-zA-Z0-9]", "-", s)


def sanitize_path_part(s: str) -> str:
    """Sanitize a string for use as a single directory name (no path traversal)."""
    sanitized = re.sub(r"[^a-zA-Z0-9._-]", "-", s)
    sanitized = sanitized.strip(".").replace("..", "")
    return sanitized or "unknown"
