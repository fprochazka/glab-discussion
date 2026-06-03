#!/usr/bin/env bash
# Test suite for block-glab-api-discussions.sh
# Runs representative BLOCK/ALLOW cases; exits non-zero on any mismatch.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
HOOK="$HERE/block-glab-api-discussions.sh"

if [ ! -x "$HOOK" ]; then
  echo "hook not executable: $HOOK" >&2
  exit 2
fi

pass=0
fail=0

run_case() {
  local expect="$1" cmd="$2" out got
  out=$(jq -nc --arg c "$cmd" '{tool_input:{command:$c}}' | "$HOOK")
  if [ -n "$out" ]; then got=BLOCK; else got=ALLOW; fi
  if [ "$got" = "$expect" ]; then
    pass=$((pass + 1))
    printf '[ok]   expect=%-5s got=%-5s | %s\n' "$expect" "$got" "$cmd"
  else
    fail=$((fail + 1))
    printf '[FAIL] expect=%-5s got=%-5s | %s\n' "$expect" "$got" "$cmd"
  fi
}

# ---------------- BLOCK: glab api to MR discussions/notes ----------------
run_case BLOCK 'glab api "projects/:id/merge_requests/42/discussions" --paginate'
run_case BLOCK 'glab api projects/mygroup%2Fmyrepo/merge_requests/42/discussions'
run_case BLOCK 'glab api projects/123/merge_requests/5/discussions/abc/notes'
run_case BLOCK 'glab api projects/123/merge_requests/5/notes'
run_case BLOCK 'glab api projects/123/merge_requests/5/notes/99 -X DELETE'
run_case BLOCK 'glab api "projects/123/merge_requests/5/discussions/abc" -X PUT -F resolved=true'
run_case BLOCK "glab api 'projects/foo/merge_requests/1/discussions/X/notes/42' -X PUT"
run_case BLOCK 'cd /tmp && glab api "projects/:id/merge_requests/42/discussions" > /tmp/out.json 2>&1; echo EXIT=$?'
run_case BLOCK 'glab  api  "projects/x/merge_requests/9/discussions"'

# ---------------- BLOCK: glab mr view --comments ----------------
run_case BLOCK 'glab mr view 42 --comments'
run_case BLOCK 'glab mr view 42 -R mygroup/myrepo --comments -F json'
run_case BLOCK 'cd /repo && glab mr view 42 --comments'

# ---------------- BLOCK: glab mr note (and sub-subcommands) ----------------
run_case BLOCK 'glab mr note'
run_case BLOCK 'glab mr note 42'
run_case BLOCK 'glab mr note 42 -m "hi"'
run_case BLOCK 'glab mr note 42 --message "hi"'
run_case BLOCK 'glab mr note 42 -R mygroup/myrepo -m "x"'
run_case BLOCK 'glab mr note my-branch-name -m "text"'
run_case BLOCK 'glab mr note list'
run_case BLOCK 'glab mr note list 42'
run_case BLOCK 'glab mr note list -R mygroup/myrepo'
run_case BLOCK 'glab mr note resolve'
run_case BLOCK 'glab mr note resolve DISC_ID'
run_case BLOCK 'glab mr note reopen DISC_ID'
run_case BLOCK 'glab  mr  note  list'

# ---------------- ALLOW: unrelated glab commands ----------------
run_case ALLOW 'glab mr view 42'
run_case ALLOW 'glab mr view 42 -R mygroup/myrepo -F json'
run_case ALLOW 'glab mr diff 42'
run_case ALLOW 'glab mr list'
run_case ALLOW 'glab mr create'
run_case ALLOW 'glab mr approve 42'
run_case ALLOW 'glab mr todo 42'

# ---------------- ALLOW: award emoji (reactions) under notes ----------------
run_case ALLOW 'glab api projects/123/merge_requests/5/notes/99/award_emoji -X POST -f name=recycle'
run_case ALLOW 'glab api "projects/:id/merge_requests/20/notes/1996757/award_emoji" -f name=thumbsup'
run_case ALLOW 'glab api projects/123/merge_requests/5/notes/99/award_emoji/7 -X DELETE'
run_case ALLOW 'glab api projects/mygroup%2Fmyrepo/merge_requests/42/award_emoji'

# ---------------- ALLOW: unrelated glab api calls ----------------
run_case ALLOW 'glab api projects/mygroup%2Fmyrepo/merge_requests/42'
run_case ALLOW 'glab api "projects/mygroup%2Fmyrepo"'
run_case ALLOW 'glab api "projects?search=myrepo"'
run_case ALLOW 'glab api "projects?search=x" --hostname gitlab.example.com'

# ---------------- ALLOW: unrelated commands / pipeline stages ----------------
run_case ALLOW 'jq ".[] | {id}" /tmp/out.json'
run_case ALLOW 'git status'
run_case ALLOW 'glab-discussion read'
run_case ALLOW 'glab-discussion write --body "x"'
run_case ALLOW 'glab auth status'

# ---------------- Empty / missing command ----------------
run_case ALLOW ''

echo
echo "passed: $pass"
echo "failed: $fail"
[ "$fail" -eq 0 ]
