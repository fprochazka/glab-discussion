#!/usr/bin/env bash
# SessionStart hook: tell the agent, once per session, when this plugin's Bash guard is
# running degraded.
#
# block-glab-api-discussions.sh decides with `bash-classify match`. Without a new enough
# bash-classify it falls back to matching raw command text, which wrongly denies commands
# that only mention `glab` in prose. A PreToolUse hook cannot say anything while allowing —
# only a deny reason reaches the model — so the advice has to be injected here instead.
#
# Prints nothing when bash-classify is present and new enough. Always exits 0.

set -uo pipefail

MIN_VERSION="0.10.0"

if ! command -v jq >/dev/null 2>&1; then
  exit 0
fi

# Same discovery as block-glab-api-discussions.sh.
BC=""
if command -v bash-classify >/dev/null 2>&1; then
  BC="bash-classify"
elif [ -x "$HOME/.local/bin/bash-classify" ]; then
  BC="$HOME/.local/bin/bash-classify"
fi

# advise FOUND INSTALL_COMMAND
advise() {
  local context
  context="The glab-discussion Claude Code plugin guards Bash calls with \`bash-classify match\`, which needs bash-classify >= $MIN_VERSION, but $1. Until that is fixed the plugin's PreToolUse hook falls back to matching raw command text, so it can wrongly block a command that only mentions \`glab\` — a heredoc, a commit message, a \`grep\` pattern. Tell the user about this and offer to run: $2"
  jq -n --arg ctx "$context" '{
    hookSpecificOutput: {
      hookEventName: "SessionStart",
      additionalContext: $ctx
    }
  }'
  exit 0
}

if [ -z "$BC" ]; then
  advise "it is not installed" "\`uv tool install bash-classify\`"
fi

RAW=$("$BC" --version 2>/dev/null | head -1) || RAW=""
VERSION=$(printf '%s' "$RAW" | awk '{print $2}')

# An unknown version is treated as too old: the hook cannot prove otherwise.
case "$VERSION" in
  '' | *[!0-9.]*)
    advise "its version could not be read" "\`uv tool install --force bash-classify\`"
    ;;
esac

if [ "$(printf '%s\n%s\n' "$MIN_VERSION" "$VERSION" | sort -V | head -1)" != "$MIN_VERSION" ]; then
  advise "the installed bash-classify $VERSION is outdated" "\`uv tool install --force bash-classify\`"
fi

exit 0
