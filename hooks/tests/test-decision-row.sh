#!/usr/bin/env bash
# Oracle for WL-D1 (agentops#2434): hooks/lib/emit-decision.sh and the
# kind == "decision" handling in hooks/log-session-cost.sh.
#
#   REQ-001 each deny/ask emit appends exactly one {"kind":"decision", ...} row
#           to the session's gate log, interleaved with ordinary gate-log.sh rows
#   REQ-002 decision rows never enter the `gates` array or the rework count that
#           hooks/log-session-cost.sh publishes -- only ordinary gate rows do
#   REQ-003 rework_rounds on this interleaved fixture equals the same formula
#           applied to the gate rows alone, and matches the plain (no-decision)
#           fixture already covered by hooks/tests/test-gate-log.sh
#   REQ-004 the auditctl payload carries a `decisions` array beside `gates`,
#           with all three decision rows, and does not mutate `gates` or
#           `rework_rounds`
#
# Session fixture, in call order (two denies, one ask, interleaved with a
# failed-then-retried gate command):
#   1. pytest fails                          (gate-log.sh: ordinary gate row)
#   2. bounded-read-guard.sh denies a read    (decision row: deny)
#   3. gate-check.sh denies (operator-actioned) (decision row: deny)
#   4. pytest retried, passes                (gate-log.sh: ordinary gate row)
#   5. gate-check.sh asks (operator-approved) (decision row: ask)
set -uo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
hooks_dir="$(cd -- "$here/.." && pwd -P)"
bounded_read_hook="$hooks_dir/bounded-read-guard.sh"
gate_check_hook="$hooks_dir/gate-check.sh"
gate_log_hook="$hooks_dir/gate-log.sh"
stop_hook="$hooks_dir/log-session-cost.sh"

fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
assert_eq() { [[ "$2" == "$3" ]] || fail "$1: expected '$3', got '$2'"; }

command -v jq >/dev/null || fail "jq is required to run this oracle"

tmp="$(mktemp -d)"
mkdir -p "$tmp/store/.auditctl" && : > "$tmp/store/.auditctl/auditctl.db"
export AUDITCTL_DB="$tmp/store/.auditctl/auditctl.db"
export AUDITCTL_ARTIFACTS_ROOT="$tmp/store"
trap 'rm -rf "$tmp"' EXIT

session="sess-decision-row"
gatedir="$tmp/gates"
gatefile="$gatedir/gates-$session.jsonl"

# A throwaway project with a .claude/gates.json so gate-check.sh has something
# to match against. Not a git repo: gate-check.sh's own ROOT resolution falls
# back to $CWD when `git -C "$CWD" rev-parse --show-toplevel` fails, so this
# fixture needs no git operation of its own.
proj="$tmp/proj"
mkdir -p "$proj/.claude"
cat > "$proj/.claude/gates.json" <<'JSON'
{"gated":[
  {"match":"^dangerous-deny-cmd","tier":"operator-actioned","reason":"test deny"},
  {"match":"^dangerous-ask-cmd","tier":"operator-approved","reason":"test ask"}
]}
JSON

big="$tmp/big.md"
seq 1 733 > "$big"

run_gate_hook() {  # run_gate_hook <cmd> <tool_response-json>
  jq -cn --arg s "$session" --arg c "$1" --argjson r "$2" \
    '{session_id:$s, hook_event_name:"PostToolUse", tool_name:"Bash", tool_input:{command:$c}, tool_response:$r}' \
    | AGENTOPS_GATE_LOG_DIR="$gatedir" bash "$gate_log_hook"
}

run_bounded_read_deny() {
  jq -cn --arg s "$session" --arg c "cat $big" \
    '{session_id:$s, hook_event_name:"PreToolUse", tool_name:"Bash", tool_input:{command:$c}}' \
    | AGENTOPS_GATE_LOG_DIR="$gatedir" bash "$bounded_read_hook" >/dev/null
}

run_gate_check() {  # run_gate_check <cmd>
  jq -cn --arg s "$session" --arg c "$1" --arg cwd "$proj" \
    '{session_id:$s, hook_event_name:"PreToolUse", tool_name:"Bash", tool_input:{command:$c}, cwd:$cwd}' \
    | AGENTOPS_GATE_LOG_DIR="$gatedir" bash "$gate_check_hook" >/dev/null
}

# --- the interleaved fixture -----------------------------------------------------------
run_gate_hook "pytest -q" '{"stdout":"","stderr":"1 failed","is_error":true}'
run_bounded_read_deny
run_gate_check "dangerous-deny-cmd"
run_gate_hook "pytest -q" '{"stdout":"3 passed","stderr":""}'
run_gate_check "dangerous-ask-cmd"

[[ -s "$gatefile" ]] || fail "no gate file was written for '$session'"

# --- REQ-001: exactly three decision rows, interleaved with two gate rows -------------
all_rows="$(jq -cs '.' "$gatefile")"
n_all="$(jq 'length' <<<"$all_rows")"
assert_eq "REQ-001 total rows" "$n_all" "5"

decisions="$(jq -c '[.[] | select(.kind == "decision")]' <<<"$all_rows")"
assert_eq "REQ-001 decision row count" "$(jq 'length' <<<"$decisions")" "3"
assert_eq "REQ-001 decision policy_decisions" \
  "$(jq -c '[.[].policy_decision] | sort' <<<"$decisions")" '["ask","deny","deny"]'
jq -e '[.[] | (has("ts") and has("hook") and has("rule_id") and has("tool") and has("policy_decision"))] | all' \
  <<<"$decisions" >/dev/null || fail "REQ-001: a decision row is missing a required field"

gates_only="$(jq -c '[.[] | select(.kind != "decision")]' <<<"$all_rows")"
assert_eq "REQ-002 gate row count unaffected" "$(jq 'length' <<<"$gates_only")" "2"
jq -e '[.[] | has("cmd")] | all' <<<"$gates_only" >/dev/null || fail "REQ-002: a gate row lost its shape"

# --- REQ-003: rework_rounds, computed the same way log-session-cost.sh computes it,
# is unaffected by the interleaved decision rows -------------------------------------
rework_of() {
  jq -n --argjson rows "$1" '
    $rows as $r
    | [ range(0; ($r | length))
        | select($r[.].ok == false)
        | . as $i
        | select([ $r[($i + 1):][] | select(.cmd == $r[$i].cmd) ] | length > 0)
      ] | length'
}
assert_eq "REQ-003 rework over gate rows alone" "$(rework_of "$gates_only")" "1"
# Decision rows have no .ok/.cmd, so running the same formula over *all* rows (as it
# would be run if the exclusion in log-session-cost.sh were ever dropped) must still
# not be silently wrong -- select(.ok == false) is false for a row with no .ok key.
assert_eq "REQ-003 decision rows cannot masquerade as gate rows" "$(rework_of "$all_rows")" "1"

# The plain fixture hooks/tests/test-gate-log.sh already covers (no decision rows at
# all) must land on the same rework_rounds this fixture does, for the same shape of
# gate rows -- i.e. this item changes nothing about plain sessions.
plain='[{"cmd":"pytest -q","ok":false},{"cmd":"pytest -q","ok":true}]'
assert_eq "REQ-003 matches the plain (no-decision) fixture" "$(rework_of "$plain")" "$(rework_of "$gates_only")"

# --- REQ-004: the auditctl payload carries `decisions` beside `gates` -----------------
pubdir="$tmp/pub"; mkdir -p "$pubdir"
cat > "$pubdir/auditctl" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$AUDITCTL_STUB_LOG"
STUB
chmod +x "$pubdir/auditctl"
export AUDITCTL_STUB_LOG="$tmp/auditctl-calls.log"

transcript="$tmp/transcript.jsonl"
cat > "$transcript" <<JSONL
{"type":"user","timestamp":"2026-09-20T10:00:00.000Z","message":{"role":"user","content":"do the thing"}}
{"type":"assistant","timestamp":"2026-09-20T10:00:10.000Z","message":{"role":"assistant","model":"claude-opus-5","usage":{"input_tokens":10,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"output_tokens":5},"content":[{"type":"tool_use","name":"Bash"}]}}
JSONL

stop_event="$(jq -cn --arg t "$transcript" --arg s "$session" \
  '{transcript_path:$t, session_id:$s, cwd:"/projects/dev/agentops", hook_event_name:"Stop"}')"
printf '%s' "$stop_event" \
  | env PATH="$pubdir:$PATH" AGENTOPS_COST_LOG="$tmp/costs.jsonl" AGENTOPS_GATE_LOG_DIR="$gatedir" \
        AUDITCTL_DB="$AUDITCTL_DB" AUDITCTL_ARTIFACTS_ROOT="$AUDITCTL_ARTIFACTS_ROOT" \
        bash "$stop_hook" || fail "Stop hook exited non-zero"

[[ -s "$AUDITCTL_STUB_LOG" ]] || fail "REQ-004: nothing was published to auditctl"
call="$(tail -1 "$AUDITCTL_STUB_LOG")"
meta="$(sed -n 's/.*--metadata //p' <<<"$call")"

jq -e 'has("decisions")' <<<"$meta" >/dev/null || fail "REQ-004: published payload has no 'decisions' key"
assert_eq "REQ-004 published decisions count" "$(jq '.decisions | length' <<<"$meta")" "3"
assert_eq "REQ-004 published gates count unaffected" "$(jq '.gates | length' <<<"$meta")" "2"
assert_eq "REQ-004 published rework_rounds unaffected" "$(jq -r '.rework_rounds' <<<"$meta")" "1"
assert_eq "REQ-004 published decisions match the log" \
  "$(jq -Sc '.decisions | sort' <<<"$meta")" "$(jq -Sc 'sort' <<<"$decisions")"

# --- gate log is preserved (read, not drained), matching gate-log.sh's own contract ----
assert_eq "gate file rows survive publication" "$(wc -l < "$gatefile")" "5"

printf 'PASS: decision-row oracle (WL-D1): 3 decision rows, 2 gate rows unchanged, rework_rounds=1 before and after, decisions published beside gates\n'
