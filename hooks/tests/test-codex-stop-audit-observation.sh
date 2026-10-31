#!/usr/bin/env bash
# Codex Stop produces a per-turn audit observation, never a Claude cost row.
set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
hooks_dir="$(cd -- "$here/.." && pwd -P)"
stop_hook="$hooks_dir/log-session-cost.sh"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

git_init() {
  git init -q -b main "$1"
  git -C "$1" -c user.name=fixture -c user.email=fixture@example.invalid \
    -c core.hooksPath=/dev/null commit -q --allow-empty -m fixture
}

launch="$tmp/launch"
target="$tmp/target"
mkdir -p "$launch/.auditctl" "$target/subdir"
: > "$launch/.auditctl/auditctl.db"
git_init "$launch"
git_init "$target"

stub_dir="$tmp/bin"
mkdir -p "$stub_dir"
cat > "$stub_dir/auditctl" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$(pwd -P)" >> "$AUDITCTL_PWD_LOG"
printf '%s\t%s\n' "${AUDITCTL_DB-<unset>}" "${AUDITCTL_ARTIFACTS_ROOT-<unset>}" >> "$AUDITCTL_PINS_LOG"
printf '%s\n' "$*" >> "$AUDITCTL_ARGS_LOG"
while (($#)); do
  if [[ "$1" == --metadata ]]; then printf '%s\n' "$2" >> "$AUDITCTL_META_LOG"; fi
  shift
done
if [[ "${AUDITCTL_FAIL:-0}" == 1 ]]; then echo "fixture publish failure" >&2; exit 17; fi
STUB
chmod +x "$stub_dir/auditctl"

export AUDITCTL_PWD_LOG="$tmp/pwd.log"
export AUDITCTL_PINS_LOG="$tmp/pins.log"
export AUDITCTL_ARGS_LOG="$tmp/args.log"
export AUDITCTL_META_LOG="$tmp/meta.log"
export AGENTOPS_COST_LOG="$tmp/costs.jsonl"
export AGENTOPS_AUDIT_FAILURE_LOG="$tmp/audit-failures.jsonl"
export AUDITCTL_BIN="$stub_dir/auditctl"

run_event() {
  local event="$1" fail="${2:-0}"
  ( cd "$launch" && printf '%s' "$event" | env \
      AUDITCTL_DB="$launch/.auditctl/auditctl.db" \
      AUDITCTL_ARTIFACTS_ROOT="$launch" \
      AGENTOPS_COST_LOG="$AGENTOPS_COST_LOG" \
      AGENTOPS_AUDIT_FAILURE_LOG="$AGENTOPS_AUDIT_FAILURE_LOG" \
      AGENTOPS_GATE_LOG_DIR="$tmp/gates" \
      AUDITCTL_BIN="$AUDITCTL_BIN" AUDITCTL_FAIL="$fail" \
      AUDITCTL_PWD_LOG="$AUDITCTL_PWD_LOG" AUDITCTL_PINS_LOG="$AUDITCTL_PINS_LOG" \
      AUDITCTL_ARGS_LOG="$AUDITCTL_ARGS_LOG" AUDITCTL_META_LOG="$AUDITCTL_META_LOG" \
      bash "$stop_hook" )
}

fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
assert_eq() { [[ "$2" == "$3" ]] || fail "$1: expected '$3', got '$2'"; }

codex_event="$(jq -cn --arg cwd "$target/subdir" \
  '{session_id:"codex-session-1",turn_id:"turn-7",cwd:$cwd,transcript_path:"/missing/codex-transcript.jsonl"}')"
run_event "$codex_event"
[[ -f "$AUDITCTL_ARGS_LOG" ]] || fail "Codex Stop was not published to auditctl"
assert_eq "one Codex audit write" "$(wc -l < "$AUDITCTL_ARGS_LOG")" "1"
assert_eq "Codex event routed from verified event cwd" "$(cat "$AUDITCTL_PWD_LOG")" "$target/subdir"
assert_eq "verified event route drops launch pins" "$(cat "$AUDITCTL_PINS_LOG")" $'<unset>\t<unset>'
grep -q -- '--type workflow.session --source codex-hook --actor codex-hook' "$AUDITCTL_ARGS_LOG" \
  || fail "Codex event used the wrong audit type or source"
jq -s -e '.[0] == {harness:"codex",session:"codex-session-1",turn_id:"turn-7",project:"subdir"}' \
  "$AUDITCTL_META_LOG" >/dev/null || fail "Codex observation metadata changed"
[[ ! -e "$AGENTOPS_COST_LOG" ]] || fail "Codex transcript produced a Claude cost row"

# Missing identity must be skipped rather than fabricated, while remaining failure-open.
missing_id="$(jq -cn --arg cwd "$target" '{session_id:"codex-session-2",turn_id:"",cwd:$cwd}')"
run_event "$missing_id"
assert_eq "missing turn ID is skipped" "$(wc -l < "$AUDITCTL_ARGS_LOG")" "1"
missing_session="$(jq -cn --arg cwd "$target" '{session_id:"",turn_id:"turn-8",cwd:$cwd}')"
run_event "$missing_session"
assert_eq "missing session ID is skipped" "$(wc -l < "$AUDITCTL_ARGS_LOG")" "1"
[[ ! -e "$AGENTOPS_COST_LOG" ]] || fail "missing Codex identity produced a Claude cost row"

# An event without cwd uses the existing launch fallback and labels project unknown.
no_cwd="$(jq -cn '{session_id:"codex-session-3",turn_id:"turn-9"}')"
run_event "$no_cwd"
assert_eq "no-cwd route retains launch" "$(tail -n1 "$AUDITCTL_PWD_LOG")" "$launch"
expected_pins="$(printf '%s\t%s' "$launch/.auditctl/auditctl.db" "$launch")"
assert_eq "no-cwd route retains explicit pins" \
  "$(tail -n1 "$AUDITCTL_PINS_LOG")" "$expected_pins"
jq -s -e '.[1] == {harness:"codex",session:"codex-session-3",turn_id:"turn-9",project:"unknown"}' \
  "$AUDITCTL_META_LOG" >/dev/null || fail "absent cwd did not produce an unknown project label"

# Publisher errors are logged, but never fail the harness Stop hook.
failed_event="$(jq -cn --arg cwd "$target" \
  '{session_id:"codex-session-4",turn_id:"turn-10",cwd:$cwd}')"
run_event "$failed_event" 1 || fail "audit publisher failure escaped the Stop hook"
grep -q 'fixture publish failure' "$AGENTOPS_AUDIT_FAILURE_LOG" \
  || fail "Codex publisher failure was not captured"
[[ ! -e "$AGENTOPS_COST_LOG" ]] || fail "Codex event wrote a Claude cost row"

# When the real publisher is installed, verify the Codex event reaches a shard
# in the fixture repository, not only the stub's argv.
real="${AUDITCTL_REAL_BIN:-$HOME/.local/bin/auditctl}"
if [[ -x "$real" ]]; then
  real_event="$(jq -cn --arg cwd "$target" \
    '{session_id:"codex-real-session",turn_id:"codex-real-turn",cwd:$cwd}')"
  ( cd "$launch" && printf '%s' "$real_event" | env \
      -u AUDITCTL_DB -u AUDITCTL_ARTIFACTS_ROOT \
      AGENTOPS_COST_LOG="$AGENTOPS_COST_LOG" \
      AGENTOPS_AUDIT_FAILURE_LOG="$AGENTOPS_AUDIT_FAILURE_LOG" \
      AGENTOPS_GATE_LOG_DIR="$tmp/gates" AUDITCTL_BIN="$real" \
      bash "$stop_hook" ) || fail "real auditctl integration failed"
  jq -s -e 'any(.[]; (.type == "workflow.session" or .event_type == "workflow.session")
      and .source == "codex-hook" and .metadata.harness == "codex"
      and .metadata.session == "codex-real-session"
      and .metadata.turn_id == "codex-real-turn")' \
      "$target"/_artifacts/target/audit/events-*.ndjson >/dev/null \
      || fail "real auditctl did not persist the Codex turn in the fixture store"

  # The live failure: a workspace process inherits pins for a nested checkout.
  # Its existing SQLite ledger must receive the observation, with no fake Git
  # repository and no global AUDITCTL environment override.
  workspace="$tmp/workspace"
  mkdir -p "$workspace/.auditctl" "$workspace/.git" "$workspace/launch"
  python3 - "$workspace/.auditctl/auditctl.db" <<'PY'
import sqlite3, sys
with sqlite3.connect(sys.argv[1]) as db:
    db.execute("CREATE TABLE fixture (id INTEGER)")
PY
  printf '%s\n' workspace > "$workspace/.auditctl-id"
  git_init "$workspace/launch"
  workspace_event="$(jq -cn --arg cwd "$workspace" \
    '{session_id:"codex-workspace-session",turn_id:"codex-workspace-turn",cwd:$cwd}')"
  ( cd "$workspace" && printf '%s' "$workspace_event" | env -u DIRENV_DIR \
      AUDITCTL_DB="$workspace/launch/.auditctl/auditctl.db" AUDITCTL_ARTIFACTS_ROOT="$workspace/launch" \
      AGENTOPS_COST_LOG="$AGENTOPS_COST_LOG" AGENTOPS_GATE_LOG_DIR="$tmp/gates" \
      AGENTOPS_AUDIT_FAILURE_LOG="$AGENTOPS_AUDIT_FAILURE_LOG" AUDITCTL_BIN="$real" \
      bash "$stop_hook" ) || fail "workspace Codex hook failed"
  jq -s -e 'any(.[]; .source == "codex-hook"
      and .metadata.turn_id == "codex-workspace-turn"
      and .resolved_context.repo_id == "workspace")' \
      "$workspace"/_artifacts/workspace/audit/events-*.ndjson >/dev/null \
      || fail "Codex workspace observation was misfiled into the child checkout"
  [[ ! -d "$workspace/launch/_artifacts" ]] || fail "child checkout received workspace evidence"
fi

printf 'Codex Stop audit observation tests passed\n'
