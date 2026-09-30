#!/usr/bin/env bash
# Oracle for agentops#2547: the Stop hook publishes from the SESSION's working directory.
#
# The harness runs the Stop hook in the directory the session was launched in, with that
# directory's direnv exports (agentops/.envrc pins AUDITCTL_DB and AUDITCTL_ARTIFACTS_ROOT
# to agentops, and auditctl honours AUDITCTL_DB before its CWD), while the event's `.cwd`
# says where the session works now. Before this fix a session launched in agentops that moved into a vuoro-cloud
# worktree filed every workflow.session event into agentops's store, and vuoro-cloud's
# store went stale while the repository was busy (audit_freshness --git-activity:
# "vuoro-cloud: capture failure").
#
#   REQ-2547-1 event `.cwd` inside ANOTHER git work tree -> the publisher runs there, with
#              the launch repository's AUDITCTL_DB / AUDITCTL_ARTIFACTS_ROOT removed
#   REQ-2547-2 event `.cwd` in a subdirectory / a linked worktree -> the same
#   REQ-2547-5 event `.cwd` inside the launch work tree -> nothing changes (cwd and env),
#              so a deliberate pooling export keeps working
#   REQ-2547-6 a pin pointing OUTSIDE the launch work tree is an explicit override (an
#              operator, every other hook test's fixture store) -> nothing changes
#   REQ-2547-3 event `.cwd` outside any git work tree (even under a bare `.auditctl`
#              index, or under a parent with an EMPTY `.git` directory, as /projects/dev
#              has), missing, relative or absent -> the process CWD (the pre-fix
#              behaviour: a misfiled event is recoverable, a lost one is not)
#   REQ-2547-4 end to end with the real auditctl, when installed, with AUDITCTL_DB pinned to
#              the launch repo as agentops/.envrc does: an event whose `.cwd` is a linked
#              worktree lands in the MAIN checkout's store, not the launch repo's
#
# Every write stays inside a temp dir: cost/gate logs are redirected, and REQ-1..3 stub
# auditctl on PATH.
set -uo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
stop_hook="$(cd -- "$here/.." && pwd -P)/log-session-cost.sh"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
tmp="$(cd -- "$tmp" && pwd -P)"

fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
assert_eq() { [[ "$2" == "$3" ]] || fail "$1: expected '$3', got '$2'"; }

transcript="$tmp/transcript.jsonl"
cat > "$transcript" <<'JSONL'
{"type":"user","timestamp":"2026-09-30T10:00:00.000Z","message":{"role":"user","content":"go"}}
{"type":"assistant","timestamp":"2026-09-30T10:00:10.000Z","message":{"role":"assistant","model":"claude-opus-5-5","usage":{"input_tokens":10,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"output_tokens":4},"content":[{"type":"tool_use","name":"Bash"}]}}
JSONL

stub_dir="$tmp/bin"; mkdir -p "$stub_dir"
cat > "$stub_dir/auditctl" <<'STUB'
#!/usr/bin/env bash
printf '%s|%s|%s\n' "$(pwd -P)" "${AUDITCTL_DB-<unset>}" "${AUDITCTL_ARTIFACTS_ROOT-<unset>}" >> "$AUDITCTL_PWD_LOG"
STUB
chmod +x "$stub_dir/auditctl"
export AUDITCTL_PWD_LOG="$tmp/pwd.log"
gatedir="$tmp/state"; mkdir -p "$gatedir"

git_init() { git init -q -b main "$1" && git -C "$1" -c user.name=t -c user.email=t@t \
  -c core.hooksPath=/dev/null commit -q --allow-empty -m init >/dev/null 2>&1; }

launch="$tmp/launch"; git_init "$launch"          # where the session was started
target="$tmp/target"; git_init "$target"          # where it works now
mkdir -p "$target/sub/dir"
git -C "$target" worktree add -q -b wt "$tmp/target-wt" 2>/dev/null || fail "setup: worktree"
plain="$tmp/not-a-repo"; mkdir -p "$plain"
# /projects/dev's geometry: an empty `.git` directory at the workspace root, a real
# repository nested inside it.
fakews="$tmp/workspace"; mkdir -p "$fakews/.git" "$fakews/not-a-repo"
git_init "$fakews/nested"
indexonly="$tmp/index-only"; mkdir -p "$indexonly/.auditctl" "$indexonly/work"
: > "$indexonly/.auditctl/auditctl.db"

# run_hook <event-cwd|__absent__> [auditctl-dir] [db-pin] [root-pin]
#   -> echoes "<publisher CWD>|<AUDITCTL_DB>|<ROOT>"
# The hook always starts in $launch with the launch repo's pins exported, as a session
# launched there under direnv does.
run_hook() {
  local cwd="$1" bindir="${2:-$stub_dir}" event
  local db="${3:-$launch/.auditctl/auditctl.db}" root="${4:-$launch}"
  if [[ "$cwd" == __absent__ ]]; then
    event="$(jq -cn --arg t "$transcript" '{transcript_path:$t, session_id:"s-2547", hook_event_name:"Stop"}')"
  else
    event="$(jq -cn --arg t "$transcript" --arg c "$cwd" \
      '{transcript_path:$t, session_id:"s-2547", cwd:$c, hook_event_name:"Stop"}')"
  fi
  : > "$AUDITCTL_PWD_LOG"
  ( cd -- "$launch" && printf '%s' "$event" | env \
      AUDITCTL_DB="$db" AUDITCTL_ARTIFACTS_ROOT="$root" \
      PATH="$bindir:$PATH" AUDITCTL_BIN="$bindir/auditctl" \
      AGENTOPS_COST_LOG="$tmp/costs.jsonl" AGENTOPS_GATE_LOG_DIR="$gatedir" \
      AGENTOPS_AUDIT_FAILURE_LOG="$tmp/fail.jsonl" \
      AGENTOPS_HARNESS_EVIDENCE_ROOT="$tmp/no-harness" bash "$stop_hook" ) \
    || fail "hook exited non-zero for cwd=$cwd"
  tail -n1 "$AUDITCTL_PWD_LOG" 2>/dev/null
}

pinned="$launch|$launch/.auditctl/auditctl.db|$launch"
assert_eq "REQ-2547-1 other repo root" "$(run_hook "$target")"          "$target|<unset>|<unset>"
assert_eq "REQ-2547-2 subdirectory"    "$(run_hook "$target/sub/dir")"  "$target/sub/dir|<unset>|<unset>"
assert_eq "REQ-2547-2 worktree"        "$(run_hook "$tmp/target-wt")"   "$tmp/target-wt|<unset>|<unset>"
assert_eq "REQ-2547-5 launch repo"     "$(run_hook "$launch")"          "$pinned"
mkdir -p "$launch/deep"
assert_eq "REQ-2547-5 launch subdir"   "$(run_hook "$launch/deep")"     "$pinned"
elsewhere_db="$tmp/fixture-store/.auditctl/auditctl.db"
assert_eq "REQ-2547-6 override db pin" \
  "$(run_hook "$target" "" "$elsewhere_db" "$tmp/fixture-store")" \
  "$launch|$elsewhere_db|$tmp/fixture-store"
assert_eq "REQ-2547-6 override root pin" \
  "$(run_hook "$target" "" "$launch/.auditctl/auditctl.db" "$tmp/fixture-store")" \
  "$launch|$launch/.auditctl/auditctl.db|$tmp/fixture-store"
assert_eq "REQ-2547-3 non-repo cwd"    "$(run_hook "$plain")"           "$pinned"
assert_eq "REQ-2547-3 empty .git root" "$(run_hook "$fakews")"          "$pinned"
assert_eq "REQ-2547-3 empty .git sub"  "$(run_hook "$fakews/not-a-repo")" "$pinned"
assert_eq "REQ-2547-1 repo in empty .git root" "$(run_hook "$fakews/nested")" \
  "$fakews/nested|<unset>|<unset>"
assert_eq "REQ-2547-3 bare index"      "$(run_hook "$indexonly/work")"  "$pinned"
assert_eq "REQ-2547-3 missing cwd"     "$(run_hook "$tmp/gone")"        "$pinned"
assert_eq "REQ-2547-3 relative cwd"    "$(run_hook "relative/path")"   "$pinned"
assert_eq "REQ-2547-3 absent cwd"      "$(run_hook __absent__)"         "$pinned"
[[ -s "$tmp/costs.jsonl" ]] || fail "the cost row was not written"

# --- REQ-2547-4: the real publisher, when this host has it --------------------------------
# Every path it can reach is under $tmp: the launch pins point at $tmp/launch and the event
# cwd is a worktree of $tmp/target, so no real store can be written. CI (HOME in a temp
# dir) skips this unless AUDITCTL_REAL_BIN is given.
real=""
for c in "${AUDITCTL_REAL_BIN:-}" "$HOME/.local/bin/auditctl"; do
  [[ -n "$c" && -x "$c" ]] && ! head -c4 "$c" 2>/dev/null | grep -q $'\x7fELF' && { real="$c"; break; }
done
if [[ -n "$real" ]]; then
  real_dir="$tmp/realbin"; mkdir -p "$real_dir"; ln -s "$real" "$real_dir/auditctl"
  run_hook "$tmp/target-wt" "$real_dir" >/dev/null
  ls "$target"/_artifacts/target/audit/events-*.ndjson >/dev/null 2>&1 \
    || fail "REQ-2547-4: no shard in the main checkout's store for a worktree session ($(cat "$tmp/fail.jsonl" 2>/dev/null))"
  if compgen -G "$launch/_artifacts/*/audit/events-*.ndjson" >/dev/null; then
    fail "REQ-2547-4: the event was filed in the launch repository's store"
  fi
  msg="REQ-2547-4 checked with $real"
else
  msg="REQ-2547-4 skipped (no auditctl publisher on this host)"
fi

printf 'PASS: Stop hook publishes from the event cwd (agentops#2547); %s\n' "$msg"
