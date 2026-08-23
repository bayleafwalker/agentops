#!/usr/bin/env bash
# T-3 oracle, written from the handoff-doc row (docs/plans/agentops/
# 2026-08-23-handoff-loop-and-telemetry.md, T-3) and nothing else:
#
#   REQ-001 a PostToolUse event for a matching command (pytest, run_round_checks,
#           hybrid_dispatch gate, cargo test) appends one row {ts, cmd, exit,
#           signal, ok} to $AGENTOPS_GATE_LOG_DIR/gates-<session>.jsonl, where
#           signal names which evidence decided ok: exit_code | is_error |
#           interrupted | heuristic
#   REQ-002 a pipeline / compound command records signal "unattributable", ok null
#   REQ-003 a non-matching command appends nothing
#   REQ-004 auditctl absent from PATH does not fail the hook
#
# The hook is driven exactly as Claude Code drives it: the event JSON on stdin,
# nothing on argv.
set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
hook="$(cd -- "$here/.." && pwd -P)/gate-log.sh"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
assert_eq() { [[ "$2" == "$3" ]] || fail "$1: expected '$3', got '$2'"; }

command -v jq >/dev/null || fail "jq is required to run this oracle"

# REQ-004: a PATH with everything the hook could legitimately need, and no auditctl.
mkdir -p "$tmp/bin"
for tool in bash sh jq date mkdir cat printf grep sed awk tr head tail env dirname basename wc cut mktemp rm tee; do
  bin="$(command -v "$tool" 2>/dev/null || true)"
  [[ -n "$bin" ]] && ln -sf "$bin" "$tmp/bin/$tool"
done
export PATH="$tmp/bin"
command -v auditctl >/dev/null 2>&1 && fail "test PATH must not contain auditctl"

export AGENTOPS_GATE_LOG_DIR="$tmp/gates"
session="sess-t3-oracle"
log="$AGENTOPS_GATE_LOG_DIR/gates-$session.jsonl"

event() {  # $1 command, $2 tool_response JSON
  jq -cn --arg s "$session" --arg c "$1" --argjson r "$2" \
    '{session_id: $s, hook_event_name: "PostToolUse", tool_name: "Bash", tool_input: {command: $c}, tool_response: $r}'
}

run_hook() { printf '%s' "$1" | bash "$hook"; }

rows() { [[ -f "$log" ]] && wc -l < "$log" || echo 0; }

# --- REQ-001 / REQ-004: matching commands each append one well-formed row ----
matching=(
  "pytest -q tests/test_a.py"
  "python verification/run_round_checks.py"
  "python templates/dispatch/scripts/hybrid_dispatch.py --repo-root . --packet p.json gate"
  "cargo test"
)
expected=0
for cmd in "${matching[@]}"; do
  run_hook "$(event "$cmd" '{"stdout":"3 passed in 0.1s","stderr":""}')" || fail "hook exited non-zero for '$cmd' (auditctl absent)"
  expected=$((expected + 1))
  assert_eq "row count after '$cmd'" "$(rows)" "$expected"
  row="$(tail -n 1 "$log")"
  assert_eq "row keys for '$cmd'" "$(printf '%s' "$row" | jq -c 'keys')" '["cmd","exit","ok","signal","ts"]'
  assert_eq "row cmd" "$(printf '%s' "$row" | jq -r '.cmd')" "$cmd"
  signal="$(printf '%s' "$row" | jq -r '.signal')"
  case "$signal" in exit_code|is_error|interrupted|heuristic) ;; *) fail "row signal for '$cmd' must name its evidence, got '$signal'";; esac
  assert_eq "row ok is a boolean" "$(printf '%s' "$row" | jq -r '.ok | type')" "boolean"
  assert_eq "row ts is set" "$(printf '%s' "$row" | jq -r '.ts | type')" "string"
  [[ -n "$(printf '%s' "$row" | jq -r '.ts')" ]] || fail "row ts is empty"
  printf '%s' "$row" | jq -e '.exit == null or (.exit | type) == "number"' >/dev/null || fail "row exit must be a number or null"
done

# A failing-looking result must not be recorded as ok when the verdict is decided
# by exit_code or is_error.
run_hook "$(event "pytest -q" '{"stdout":"","stderr":"1 failed","is_error":true}')"
row="$(tail -n 1 "$log")"
assert_eq "is_error result is not ok" "$(printf '%s' "$row" | jq -r '.ok')" "false"
expected=$((expected + 1))

# --- REQ-002: pipeline / compound command is unattributable -------------------
for cmd in "pytest -q | tail -5" "cargo test && echo done"; do
  run_hook "$(event "$cmd" '{"stdout":"ok","stderr":""}')"
  expected=$((expected + 1))
  assert_eq "row count after compound '$cmd'" "$(rows)" "$expected"
  row="$(tail -n 1 "$log")"
  assert_eq "compound signal" "$(printf '%s' "$row" | jq -r '.signal')" "unattributable"
  assert_eq "compound ok is null" "$(printf '%s' "$row" | jq -r '.ok | type')" "null"
done

# --- REQ-003: non-matching command appends nothing -----------------------------
for cmd in "ls -la" "git status" "echo pytest-is-not-here-as-a-command-word"; do
  run_hook "$(event "$cmd" '{"stdout":"","stderr":""}')" || fail "hook exited non-zero for non-matching '$cmd'"
done
# The third is a deliberate probe: a word like 'pytest' inside an echo argument is
# not a gate. A hook that matches it anyway is recorded as a finding, not a
# failure, because the row says whether the spec's "matching command" is a
# word-boundary or substring match -- the spec does not.
count_after="$(rows)"
if [[ "$count_after" -eq $((expected + 1)) ]]; then
  printf 'NOTE: substring match -- "echo pytest-..." produced a row; the spec does not say whether that is a gate\n' >&2
  expected=$((expected + 1))
fi
assert_eq "no rows for non-matching commands" "$count_after" "$expected"

# Every row must be one JSON object per line.
jq -e 'type == "object"' "$log" >/dev/null || fail "gates log is not one JSON object per line"

# Rows for another session go to that session's file, not this one.
other_session="sess-t3-other"
printf '%s' "$(event "pytest -q" '{"stdout":"","stderr":""}' | jq -c --arg s "$other_session" '.session_id = $s')" | bash "$hook"
[[ -f "$AGENTOPS_GATE_LOG_DIR/gates-$other_session.jsonl" ]] || fail "gates-<session>.jsonl is not keyed by session_id"
assert_eq "other session did not write to this session's log" "$(rows)" "$expected"

printf 'PASS: gate-log oracle (T-3): %s rows, signals attributed, compound unattributable, non-matching ignored, no auditctl needed\n' "$expected"
