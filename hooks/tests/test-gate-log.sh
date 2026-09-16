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
# Spec row M-5 then decided the question the REQ-003 probe used to leave open:
#
#   REQ-005 a gate tool name counts only as the *command word* -- the first
#           word of the command, or the first word after a shell separator
#           (| && || ;). The same name as an argument, inside a quoted string, or
#           as part of a longer word is not a gate and appends no row. The
#           AGENTOPS_GATE_PATTERN override is matched under the same rule.
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
  # Asserted per command rather than once at the end so a regression names the
  # command that produced the row instead of just a count that drifted.
  assert_eq "no row for non-matching '$cmd'" "$(rows)" "$expected"
done

# --- REQ-005: the matcher is anchored to the command word ---------------
# The gate surface is what actually ran. A tool name that only appears as an
# argument, inside a quoted string, or glued into a longer word did not run
# anything, and a row for it inflates the rework-round count the Stop hook drains
# into auditctl -- which is why the "no row" half of this block is a failure and
# no longer a finding.
anchored_gates=(
  "pytest -q"
  "pytest -q tests/test_x.py"
  "cargo test"
  "run_round_checks"
  "python -m unittest discover -s templates/dispatch/tests"
  "python templates/dispatch/scripts/hybrid_dispatch.py --packet p.json gate"
  "pytest -q | tail -5"
  "cargo test && echo done"
)
for cmd in "${anchored_gates[@]}"; do
  run_hook "$(event "$cmd" '{"stdout":"3 passed in 0.1s","stderr":""}')" || fail "hook exited non-zero for anchored gate '$cmd'"
  expected=$((expected + 1))
  assert_eq "exactly one row for anchored gate '$cmd'" "$(rows)" "$expected"
  assert_eq "row cmd for anchored gate" "$(tail -n 1 "$log" | jq -r '.cmd')" "$cmd"
  # M-5 changes the matcher only; the compound-command refusal stays where it was.
  case "$cmd" in
    *"|"*|*"&&"*)
      assert_eq "compound gate '$cmd' stays unattributable" "$(tail -n 1 "$log" | jq -r '.signal')" "unattributable" ;;
  esac
done

not_gates=(
  "echo pytest-is-not-here-as-a-command-word"
  'echo "run the pytest suite later"'
  'git commit -m "fix pytest fixture"'
  "ls -la"
  "git status"
)
for cmd in "${not_gates[@]}"; do
  run_hook "$(event "$cmd" '{"stdout":"","stderr":""}')" || fail "hook exited non-zero for non-gate '$cmd'"
  assert_eq "no row for non-gate '$cmd'" "$(rows)" "$expected"
done

# The override is a pattern, not an escape hatch from the anchoring rule: the same
# name still has to be the command word to count.
(
  export AGENTOPS_GATE_PATTERN="mise"
  run_hook "$(event "mise run gate" '{"stdout":"ok","stderr":""}')" || fail "hook exited non-zero under AGENTOPS_GATE_PATTERN"
)
expected=$((expected + 1))
assert_eq "override pattern matches as a command word" "$(rows)" "$expected"
(
  export AGENTOPS_GATE_PATTERN="mise"
  run_hook "$(event "echo promise-not-a-command" '{"stdout":"","stderr":""}')" || fail "hook exited non-zero under AGENTOPS_GATE_PATTERN"
)
assert_eq "override pattern is anchored too" "$(rows)" "$expected"

# Every row must be one JSON object per line.
jq -e 'type == "object"' "$log" >/dev/null || fail "gates log is not one JSON object per line"

# Rows for another session go to that session's file, not this one.
other_session="sess-t3-other"
printf '%s' "$(event "pytest -q" '{"stdout":"","stderr":""}' | jq -c --arg s "$other_session" '.session_id = $s')" | bash "$hook"
[[ -f "$AGENTOPS_GATE_LOG_DIR/gates-$other_session.jsonl" ]] || fail "gates-<session>.jsonl is not keyed by session_id"
assert_eq "other session did not write to this session's log" "$(rows)" "$expected"

printf 'PASS: gate-log oracle (T-3): %s rows, signals attributed, compound unattributable, non-matching ignored, no auditctl needed\n' "$expected"
