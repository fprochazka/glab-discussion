#!/usr/bin/env bash
set -euo pipefail

CMD=$(jq -r '.tool_input.command // empty')

if [ -z "$CMD" ]; then
  exit 0
fi

REASON="Reading or writing MR discussions/notes via \`glab\` is blocked (matched: \`glab api .../discussions|notes\` or \`glab mr view --comments\`). Use the \`glab-discussion\` CLI instead: \`glab-discussion read|write|diff|resolve|edit|delete\`. Run \`glab-discussion --help\` for usage, or load the \`glab-discussion\` skill."

if printf '%s' "$CMD" | grep -qE 'glab[[:space:]]+api\b.*merge_requests[^"'"'"']*/(discussions|notes)' \
  || printf '%s' "$CMD" | grep -qE 'glab[[:space:]]+mr[[:space:]]+view\b.*--comments\b'; then
  jq -n --arg reason "$REASON" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: $reason
    }
  }'
fi

exit 0
