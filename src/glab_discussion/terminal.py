from __future__ import annotations

import os
import sys


def is_interactive_terminal() -> bool:
    """Detect if running in an interactive terminal vs AI agent."""
    # Check for known AI agent environment variables
    ai_indicators = ["CLAUDECODE", "AIDER", "CURSOR", "GITHUB_COPILOT"]
    if any(os.environ.get(var) for var in ai_indicators):
        return False

    # Check TTY
    return sys.stdin.isatty() and sys.stdout.isatty()
