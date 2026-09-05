#!/usr/bin/env bash
# Test suite for block-glab-api-discussions.sh and check-bash-classify.sh.
#
# Every case is run in three environments, because the hook has to behave sensibly in all
# of them:
#
#   real  the installed bash-classify (>= MIN_VERSION; the script fails loudly if absent)
#   old   a stub that answers like a pre-0.10.0 binary: no `matches` key in its output
#   none  no bash-classify on PATH and a HOME with no ~/.local/bin/bash-classify
#
# In `old` and `none` the hook falls back to the text patterns it used before, which
# over-block: shell text that merely *names* a blocked command is denied. Those rows are
# not a bug in the test, they are the degraded behaviour being pinned — and every deny
# from the fallback has to carry a note telling the agent why.
#
# The SessionStart hook is checked in the same three environments — silent in `real`, and
# advising the agent in the other two — plus a fourth where the binary answers `--version`
# with something no version can be read from.
#
# Exits non-zero if any case fails.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="$HERE/block-glab-api-discussions.sh"
CHECK="$HERE/check-bash-classify.sh"
CASES="$HERE/test-cases"
MIN_VERSION="0.10.0"

if [ ! -x "$HOOK" ]; then
  echo "hook not executable: $HOOK" >&2
  exit 2
fi

if [ ! -x "$CHECK" ]; then
  echo "hook not executable: $CHECK" >&2
  exit 2
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required to run this test suite" >&2
  exit 2
fi

# ---------------------------------------------------------------- environments

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

REAL_PATH="$PATH"
REAL_HOME="$HOME"

# PATH with every directory that holds a bash-classify removed.
clean_path() {
  local out="" dir
  local -a dirs
  IFS=: read -ra dirs <<< "$PATH"
  for dir in "${dirs[@]}"; do
    [ -n "$dir" ] || continue
    [ -e "$dir/bash-classify" ] && continue
    out="${out:+$out:}$dir"
  done
  printf '%s' "$out"
}
CLEAN_PATH=$(clean_path)

mkdir -p "$TMP/home-empty" "$TMP/bin-old"
cat > "$TMP/bin-old/bash-classify" <<'STUB'
#!/usr/bin/env bash
# Stands in for a pre-0.10.0 bash-classify: it does not know the `match` subcommand, so it
# ignores the arguments, classifies stdin and exits 0 — with no `matches` key in sight.
if [ "${1:-}" = "--version" ]; then
  echo "bash-classify 0.9.1"
  exit 0
fi
cat > /dev/null
cat <<'JSON'
{"expression":"...","classification":"EXTERNAL_EFFECTS","risk":"MEDIUM","directories":[],"write_paths":[],"read_paths":[],"commands":[],"redirects":[],"parse_warnings":[]}
JSON
STUB
chmod +x "$TMP/bin-old/bash-classify"

mkdir -p "$TMP/bin-badversion"
cat > "$TMP/bin-badversion/bash-classify" <<'STUB'
#!/usr/bin/env bash
# A binary whose --version output carries no version number. Unknown is not "new enough".
if [ "${1:-}" = "--version" ]; then
  echo "bash-classify (development build)"
  exit 0
fi
cat > /dev/null
echo '{"matches":[],"parse_warnings":[]}'
STUB
chmod +x "$TMP/bin-badversion/bash-classify"

version_ge() {
  [ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -1)" = "$2" ]
}

if ! command -v bash-classify >/dev/null 2>&1; then
  echo "bash-classify is not installed; the 'real' mode cannot run." >&2
  echo "install it with: uv tool install bash-classify" >&2
  exit 2
fi
FOUND_VERSION=$(bash-classify --version 2>/dev/null | awk '{print $2}')
if [ -z "$FOUND_VERSION" ] || ! version_ge "$FOUND_VERSION" "$MIN_VERSION"; then
  echo "bash-classify ${FOUND_VERSION:-<unknown>} is too old; this suite needs >= $MIN_VERSION" >&2
  echo "upgrade it with: uv tool install --force bash-classify" >&2
  exit 2
fi

# ---------------------------------------------------------------- case runner

MODE=""
pass=0
fail=0
mode_fail=0

# _check EXPECT COMMAND LABEL
#
# EXPECT is ALLOW, BLOCK, or BLOCK+<substring the deny reason must contain>.
_check() {
  local expect="$1" cmd="$2" label="$3"
  local want_note="" out rc got reason problem=""

  case "$expect" in
    BLOCK+*)
      want_note="${expect#BLOCK+}"
      expect="BLOCK"
      ;;
  esac

  out=$(jq -nc --arg c "$cmd" '{tool_input:{command:$c}}' | "$HOOK" 2>/dev/null)
  rc=$?
  if [ "$rc" -ne 0 ]; then
    problem="hook exited $rc (it must always exit 0)"
  fi

  if [ -n "$out" ]; then got=BLOCK; else got=ALLOW; fi
  if [ "$got" != "$expect" ]; then
    problem="${problem:+$problem; }expected $expect"
  fi

  if [ "$got" = "BLOCK" ] && [ -z "$problem" ]; then
    reason=$(printf '%s' "$out" | jq -r '.hookSpecificOutput.permissionDecisionReason // ""' 2>/dev/null)
    if [ -n "$want_note" ]; then
      case "$reason" in
        *"$want_note"*) ;;
        *) problem="deny reason does not mention '$want_note'" ;;
      esac
    else
      case "$MODE" in
        real)
          case "$reason" in
            *"(matched rule:"*) ;;
            *) problem="${problem:+$problem; }deny reason does not name the matched rule" ;;
          esac
          case "$reason" in
            *"Note:"*) problem="${problem:+$problem; }deny in real mode carries a degraded-mode note" ;;
          esac
          ;;
        old)
          case "$reason" in
            *"is outdated"*"uv tool install --force bash-classify"*) ;;
            *) problem="deny reason does not tell the agent bash-classify is outdated" ;;
          esac
          ;;
        none)
          case "$reason" in
            *"is not installed"*"uv tool install bash-classify"*) ;;
            *) problem="deny reason does not tell the agent bash-classify is missing" ;;
          esac
          ;;
      esac
    fi
  fi

  if [ -z "$problem" ]; then
    pass=$((pass + 1))
    printf '[ok]   %-5s %-6s | %s\n' "$MODE" "$got" "$label"
  else
    fail=$((fail + 1))
    mode_fail=$((mode_fail + 1))
    printf '[FAIL] %-5s %-6s | %s\n       %s\n' "$MODE" "$got" "$label" "$problem"
  fi
}

# _session_check EXPECT
#
# EXPECT is QUIET (no output at all) or SAY+<substring the additionalContext must carry>.
_session_check() {
  local expect="$1" want="" out rc ctx problem=""

  case "$expect" in
    SAY+*)
      want="${expect#SAY+}"
      expect="SAY"
      ;;
  esac

  out=$("$CHECK" 2>/dev/null)
  rc=$?
  if [ "$rc" -ne 0 ]; then
    problem="hook exited $rc (it must always exit 0)"
  fi

  if [ "$expect" = "QUIET" ]; then
    [ -n "$out" ] && problem="${problem:+$problem; }expected no output, got: $out"
  elif [ -z "$out" ]; then
    problem="${problem:+$problem; }expected advice mentioning '$want', got no output"
  else
    ctx=$(printf '%s' "$out" | jq -r '.hookSpecificOutput.additionalContext // ""' 2>/dev/null)
    if [ "$(printf '%s' "$out" | jq -r '.hookSpecificOutput.hookEventName // ""' 2>/dev/null)" != "SessionStart" ]; then
      problem="${problem:+$problem; }output is not a SessionStart hookSpecificOutput"
    else
      case "$ctx" in
        *"$want"*) ;;
        *) problem="${problem:+$problem; }advice does not mention '$want'" ;;
      esac
    fi
  fi

  if [ -z "$problem" ]; then
    pass=$((pass + 1))
    printf '[ok]   %-5s %-6s | %s\n' "$MODE" "$expect" "check-bash-classify.sh"
  else
    fail=$((fail + 1))
    mode_fail=$((mode_fail + 1))
    printf '[FAIL] %-5s %-6s | %s\n       %s\n' "$MODE" "$expect" "check-bash-classify.sh" "$problem"
  fi
}

# run_case EXPECT_REAL EXPECT_OLD EXPECT_NONE COMMAND
run_case() {
  local expect
  case "$MODE" in
    real) expect="$1" ;;
    old) expect="$2" ;;
    none) expect="$3" ;;
  esac
  _check "$expect" "$4" "$4"
}

# run_file EXPECT_REAL EXPECT_OLD EXPECT_NONE RELATIVE_PATH
run_file() {
  local expect cmd
  case "$MODE" in
    real) expect="$1" ;;
    old) expect="$2" ;;
    none) expect="$3" ;;
  esac
  if [ ! -f "$CASES/$4" ]; then
    echo "[FAIL] missing test case file: $CASES/$4"
    fail=$((fail + 1))
    mode_fail=$((mode_fail + 1))
    return
  fi
  cmd=$(cat "$CASES/$4")
  _check "$expect" "$cmd" "$4"
}

# ---------------------------------------------------------------- the cases

all_cases() {
  #         real   old    none   command
  # ---------------- glab api against MR discussions/notes ----------------
  run_case BLOCK BLOCK BLOCK 'glab api "projects/:id/merge_requests/42/discussions" --paginate'
  run_case BLOCK BLOCK BLOCK 'glab api projects/mygroup%2Fmyrepo/merge_requests/42/discussions'
  run_case BLOCK BLOCK BLOCK 'glab api projects/123/merge_requests/5/discussions/abc/notes'
  run_case BLOCK BLOCK BLOCK 'glab api projects/123/merge_requests/5/notes'
  run_case BLOCK BLOCK BLOCK 'glab api projects/123/merge_requests/5/notes/99 -X DELETE'
  run_case BLOCK BLOCK BLOCK 'glab api "projects/123/merge_requests/5/discussions/abc" -X PUT -F resolved=true'
  run_case BLOCK BLOCK BLOCK "glab api 'projects/foo/merge_requests/1/discussions/X/notes/42' -X PUT"
  run_case BLOCK BLOCK BLOCK 'cd /tmp && glab api "projects/:id/merge_requests/42/discussions" > /tmp/out.json 2>&1; echo EXIT=$?'
  run_case BLOCK BLOCK BLOCK 'glab  api  "projects/x/merge_requests/9/discussions"'

  # ---------------- glab mr view --comments ----------------
  run_case BLOCK BLOCK BLOCK 'glab mr view 42 --comments'
  run_case BLOCK BLOCK BLOCK 'glab mr view 42 -R mygroup/myrepo --comments -F json'
  run_case BLOCK BLOCK BLOCK 'cd /repo && glab mr view 42 --comments'
  # The short flag is a documented gap in degraded mode: the old text pattern only ever
  # looked for the long form.
  run_case BLOCK ALLOW ALLOW 'glab mr view 42 -c'
  run_case BLOCK ALLOW ALLOW 'glab mr view -wc 42'
  # `--resolved` and `--unresolved` imply `--comments`; the old text pattern only ever
  # looked for the flag itself, so degraded mode lets them through.
  run_case BLOCK ALLOW ALLOW 'glab mr view 42 --unresolved'
  run_case BLOCK ALLOW ALLOW 'glab mr view 42 --resolved'

  # ---------------- glab mr note ----------------
  run_case BLOCK BLOCK BLOCK 'glab mr note'
  run_case BLOCK BLOCK BLOCK 'glab mr note 42'
  run_case BLOCK BLOCK BLOCK 'glab mr note 42 -m "hi"'
  run_case BLOCK BLOCK BLOCK 'glab mr note 42 --message "hi"'
  run_case BLOCK BLOCK BLOCK 'glab mr note 42 -R mygroup/myrepo -m "x"'
  run_case BLOCK BLOCK BLOCK 'glab mr note my-branch-name -m "text"'
  run_case BLOCK BLOCK BLOCK 'glab mr note resolve'
  run_case BLOCK BLOCK BLOCK 'glab mr note resolve DISC_ID'
  run_case BLOCK BLOCK BLOCK 'glab mr note reopen DISC_ID'

  # `glab mr note list` only reads. The rules file spares it with an `except`; the text
  # pattern cannot tell it apart from a write, so degraded mode still denies it.
  run_case ALLOW BLOCK BLOCK 'glab mr note list'
  run_case ALLOW BLOCK BLOCK 'glab mr note list 42'
  run_case ALLOW BLOCK BLOCK 'glab mr note list -R mygroup/myrepo'
  run_case ALLOW BLOCK BLOCK 'glab  mr  note  list'

  # `except` spares `glab mr note list` and nothing else — these are writes.
  run_case BLOCK BLOCK BLOCK 'glab mr note create 42 -m x'
  run_case BLOCK BLOCK BLOCK 'glab mr note update 42 NOTE_ID -m x'
  run_case BLOCK BLOCK BLOCK 'glab mr note delete 42 NOTE_ID'

  # ---------------- wrappers do not launder a blocked command ----------------
  run_case BLOCK BLOCK BLOCK 'sudo glab mr note 42 -m hi'
  run_case BLOCK BLOCK BLOCK 'timeout 60 glab api "projects/:id/merge_requests/42/discussions"'
  run_case BLOCK BLOCK BLOCK 'bash -c "glab mr note 42 -m hi"'
  run_case BLOCK BLOCK BLOCK 'xargs -I{} glab api "projects/{}/merge_requests/42/notes" < ids.txt'
  run_case BLOCK BLOCK BLOCK '/usr/bin/glab api "projects/:id/merge_requests/42/discussions"'

  # An expression the parser cannot fully read: `matches` proves nothing, so the hook has
  # to fall back and say so.
  run_case 'BLOCK+could not fully parse' BLOCK BLOCK 'eval "glab mr note $(("'

  # ---------------- unrelated glab commands ----------------
  run_case ALLOW ALLOW ALLOW 'glab mr view 42'
  run_case ALLOW ALLOW ALLOW 'glab mr view 42 -R mygroup/myrepo -F json'
  run_case ALLOW ALLOW ALLOW 'glab mr diff 42'
  run_case ALLOW ALLOW ALLOW 'glab mr list'
  run_case ALLOW ALLOW ALLOW 'glab mr create'
  run_case ALLOW ALLOW ALLOW 'glab mr approve 42'
  run_case ALLOW ALLOW ALLOW 'glab mr todo 42'

  # ---------------- unrelated glab api calls ----------------
  run_case ALLOW ALLOW ALLOW 'glab api projects/mygroup%2Fmyrepo/merge_requests/42'
  run_case ALLOW ALLOW ALLOW 'glab api "projects/mygroup%2Fmyrepo"'
  run_case ALLOW ALLOW ALLOW 'glab api "projects?search=myrepo"'
  run_case ALLOW ALLOW ALLOW 'glab api "projects?search=x" --hostname gitlab.example.com'

  # ---------------- unrelated commands ----------------
  run_case ALLOW ALLOW ALLOW 'jq ".[] | {id}" /tmp/out.json'
  run_case ALLOW ALLOW ALLOW 'git status'
  run_case ALLOW ALLOW ALLOW 'glab-discussion read'
  run_case ALLOW ALLOW ALLOW 'glab-discussion write --body "x"'
  run_case ALLOW ALLOW ALLOW 'glab auth status'
  run_case ALLOW ALLOW ALLOW ''

  # ---------------- text that only mentions a blocked command ----------------
  # The whole point of matching on parsed commands: these are prose, not invocations.
  run_case ALLOW BLOCK BLOCK 'echo "use glab mr note 42 -m x instead of the API"'
  run_case ALLOW BLOCK BLOCK 'grep -rn "glab mr view --comments" ~/.claude/'

  # ---------------- multi-line cases, one per file ----------------
  run_file BLOCK BLOCK BLOCK block/api-discussions-export-host-loop.sh
  run_file BLOCK BLOCK BLOCK block/api-discussions-heredoc-then-call.sh
  run_file BLOCK BLOCK BLOCK block/api-reply-post-heredoc-body.sh
  run_file BLOCK BLOCK BLOCK block/api-new-diff-note-position-fields.sh
  run_file BLOCK BLOCK BLOCK block/mr-note-heredoc-body.sh
  run_file BLOCK BLOCK BLOCK block/heredoc-then-pipe-to-blocked.sh

  # The brief that was wrongly denied on 2026-09-04 — the reason this hook was rewritten.
  run_file ALLOW BLOCK BLOCK allow/heredoc-brief-2026-09-04.sh
  run_file ALLOW BLOCK BLOCK allow/heredoc-brief-mentions-blocked-commands.sh
  run_file ALLOW BLOCK BLOCK allow/heredoc-report-mentions-blocked.sh
  run_file ALLOW BLOCK BLOCK allow/heredoc-skill-custom-delimiter.sh
  run_file ALLOW BLOCK BLOCK allow/heredoc-skill-phrase-split-across-lines.sh
  run_file ALLOW BLOCK BLOCK allow/git-commit-heredoc-message.sh
  run_file ALLOW BLOCK BLOCK allow/git-commit-inline-message.sh
  run_file ALLOW ALLOW ALLOW allow/python-heredoc-triple-quoted-mention.sh
  run_file ALLOW ALLOW ALLOW allow/mr-update-then-view.sh
}

# ---------------------------------------------------------------- run

for MODE in real old none; do
  case "$MODE" in
    real)
      PATH="$REAL_PATH"
      HOME="$REAL_HOME"
      ;;
    old)
      PATH="$TMP/bin-old:$CLEAN_PATH"
      HOME="$TMP/home-empty"
      ;;
    none)
      PATH="$CLEAN_PATH"
      HOME="$TMP/home-empty"
      ;;
  esac
  export PATH HOME

  mode_fail=0
  echo "================ mode: $MODE ================"
  all_cases
  case "$MODE" in
    real) _session_check QUIET ;;
    old) _session_check 'SAY+is outdated' ;;
    none) _session_check 'SAY+it is not installed' ;;
  esac
  echo "---------------- mode $MODE: $([ "$mode_fail" -eq 0 ] && echo "all cases passed" || echo "$mode_fail failed")"
  echo
done

PATH="$REAL_PATH"
HOME="$REAL_HOME"
export PATH HOME

# ---------------------------------------------------------------- unparseable version

# A binary that answers --version with something this hook cannot read is treated as too
# old: it cannot prove otherwise.
echo "================ mode: unparseable-version ================"
MODE="badver"
mode_fail=0
PATH="$TMP/bin-badversion:$CLEAN_PATH"
HOME="$TMP/home-empty"
export PATH HOME
_session_check 'SAY+version could not be read'
PATH="$REAL_PATH"
HOME="$REAL_HOME"
export PATH HOME
echo

# ---------------------------------------------------------------- broken rules file

# A rules file the tool refuses is a plugin bug, not something the agent can fix. The hook
# still has to fall back rather than let everything through.
echo "================ mode: broken-rules ================"
MODE="broken"
mkdir -p "$TMP/broken"
cp "$HOOK" "$TMP/broken/"
printf 'rules:\n  - name: no-command-key\n' > "$TMP/broken/blocked-commands.yaml"
BROKEN_HOOK="$TMP/broken/$(basename "$HOOK")"

broken_case() {
  local expect="$1" cmd="$2" out got reason problem=""
  out=$(jq -nc --arg c "$cmd" '{tool_input:{command:$c}}' | "$BROKEN_HOOK" 2>/dev/null)
  if [ -n "$out" ]; then got=BLOCK; else got=ALLOW; fi
  if [ "$got" != "${expect%%+*}" ]; then
    problem="expected ${expect%%+*}"
  elif [ "$got" = "BLOCK" ]; then
    reason=$(printf '%s' "$out" | jq -r '.hookSpecificOutput.permissionDecisionReason // ""')
    case "$reason" in
      *"match failed"*) ;;
      *) problem="deny reason does not report the failed match" ;;
    esac
  fi
  if [ -z "$problem" ]; then
    pass=$((pass + 1))
    printf '[ok]   %-5s %-6s | %s\n' "$MODE" "$got" "$cmd"
  else
    fail=$((fail + 1))
    printf '[FAIL] %-5s %-6s | %s\n       %s\n' "$MODE" "$got" "$cmd" "$problem"
  fi
}

broken_case BLOCK 'glab mr note 42 -m hi'
broken_case ALLOW 'glab mr list'
echo

echo "passed: $pass"
echo "failed: $fail"
[ "$fail" -eq 0 ]
