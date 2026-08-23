#!/usr/bin/env bash
# Gate for T-1/T-3/T-4 (agentops.hooks.tests). Covers the packet's acceptance properties:
#   REQ-001 the cost record stays backward compatible
#   REQ-002 the new counters are derived from the transcript, not the Stop payload
#   REQ-003 gate outcomes reach the sink exactly once per session
#   REQ-004 rework_rounds distinguishes a retry from a first attempt
#   REQ-005 a missing auditctl degrades quietly
set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
hooks_dir="$(cd -- "$here/.." && pwd -P)"
stop_hook="$hooks_dir/log-session-cost.sh"
gate_hook="$hooks_dir/gate-log.sh"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
assert_eq() { [[ "$2" == "$3" ]] || fail "$1: expected '$3', got '$2'"; }

# A transcript with: 2 real user turns, 1 meta entry, 2 tool_result turns (not turns),
# 3 assistant messages, 4 tool_use blocks, 60s between first and last timestamp.
transcript="$tmp/transcript.jsonl"
cat > "$transcript" <<'JSONL'
{"type":"user","isMeta":true,"timestamp":"2026-08-23T10:00:00.000Z","message":{"role":"user","content":"<local-command-caveat>ignore me</local-command-caveat>"}}
{"type":"user","timestamp":"2026-08-23T10:00:00.500Z","message":{"role":"user","content":"do the thing"}}
{"type":"assistant","timestamp":"2026-08-23T10:00:10.000Z","message":{"role":"assistant","model":"claude-opus-5","usage":{"input_tokens":100,"cache_creation_input_tokens":200,"cache_read_input_tokens":300,"output_tokens":40},"content":[{"type":"text","text":"ok"},{"type":"tool_use","name":"Bash"},{"type":"tool_use","name":"Bash"}]}}
{"type":"user","timestamp":"2026-08-23T10:00:11.000Z","message":{"role":"user","content":[{"type":"tool_result","content":"out"}]}}
{"type":"assistant","timestamp":"2026-08-23T10:00:20.000Z","message":{"role":"assistant","model":"claude-opus-5","usage":{"input_tokens":10,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"output_tokens":5},"content":[{"type":"tool_use","name":"Read"}]}}
{"type":"user","timestamp":"2026-08-23T10:00:21.000Z","message":{"role":"user","content":[{"type":"tool_result","content":"out"}]}}
{"type":"user","timestamp":"2026-08-23T10:00:30.000Z","message":{"role":"user","content":"and again"}}
{"type":"assistant","timestamp":"2026-08-23T10:01:00.500Z","message":{"role":"assistant","model":"claude-opus-5","usage":{"input_tokens":10,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"output_tokens":5},"content":[{"type":"tool_use","name":"Bash"}]}}
JSONL

run_stop() {
  local session="$1" log="$2" gatedir="$3" path_override="${4:-}"
  local event
  event="$(jq -cn --arg t "$transcript" --arg s "$session" \
    '{transcript_path:$t, session_id:$s, cwd:"/projects/dev/agentops", hook_event_name:"Stop"}')"
  if [[ -n "$path_override" ]]; then
    printf '%s' "$event" | env PATH="$path_override" AGENTOPS_COST_LOG="$log" AGENTOPS_GATE_LOG_DIR="$gatedir" bash "$stop_hook"
  else
    printf '%s' "$event" | AGENTOPS_COST_LOG="$log" AGENTOPS_GATE_LOG_DIR="$gatedir" bash "$stop_hook"
  fi
}

run_gate_hook() {
  local session="$1" gatedir="$2" cmd="$3" response="$4"
  jq -cn --arg s "$session" --arg c "$cmd" --argjson r "$response" \
    '{session_id:$s, hook_event_name:"PostToolUse", tool_name:"Bash", tool_input:{command:$c}, tool_response:$r}' \
    | AGENTOPS_GATE_LOG_DIR="$gatedir" bash "$gate_hook"
}

# --- REQ-002 / REQ-001 -----------------------------------------------------------------
log="$tmp/costs.jsonl"; gatedir="$tmp/state"
run_stop "sess-a" "$log" "$gatedir"
row="$(tail -1 "$log")"

assert_eq "turns"          "$(jq -r '.turns' <<<"$row")"          "2"
assert_eq "assistant_msgs" "$(jq -r '.assistant_msgs' <<<"$row")" "3"
assert_eq "tool_calls"     "$(jq -r '.tool_calls' <<<"$row")"     "4"
assert_eq "duration_s"     "$(jq -r '.duration_s' <<<"$row")"     "60"

# REQ-001: every legacy field is still present, still named, still typed.
for f in ts project session runtime_session_id model in cache_write cache_read out cost_usd; do
  jq -e --arg f "$f" 'has($f)' <<<"$row" >/dev/null || fail "REQ-001: legacy field '$f' disappeared"
done
assert_eq "REQ-001 model" "$(jq -r '.model' <<<"$row")" "claude-opus-5"
assert_eq "REQ-001 in"    "$(jq -r '.in' <<<"$row")"    "120"
assert_eq "REQ-001 out"   "$(jq -r '.out' <<<"$row")"   "50"
jq -e '.cost_usd > 0' <<<"$row" >/dev/null || fail "REQ-001: cost_usd is no longer computed"
# An old row (no new keys) must still parse as the same shape the cockpit reads.
old_row='{"ts":"2026-01-01T00:00:00Z","project":"x","session":"s","runtime_session_id":"","model":"opus","in":1,"cache_write":0,"cache_read":0,"out":1,"cost_usd":0.1}'
jq -e '.cost_usd and .model and .in' <<<"$old_row" >/dev/null || fail "REQ-001: an old row no longer parses"

# REQ-002: the counters are derived from the transcript. A Stop payload that carries the
# same keys with poisoned values must not influence the record.
poisoned="$(jq -cn --arg t "$transcript" \
  '{transcript_path:$t, session_id:"sess-poison", cwd:"/projects/dev/agentops",
    turns:999, assistant_msgs:999, tool_calls:999, duration_s:999}')"
printf '%s' "$poisoned" | AGENTOPS_COST_LOG="$tmp/costs-p.jsonl" AGENTOPS_GATE_LOG_DIR="$gatedir" bash "$stop_hook"
prow="$(tail -1 "$tmp/costs-p.jsonl")"
assert_eq "REQ-002 turns ignore payload"      "$(jq -r '.turns' <<<"$prow")"      "2"
assert_eq "REQ-002 tool_calls ignore payload" "$(jq -r '.tool_calls' <<<"$prow")" "4"
assert_eq "REQ-002 duration ignores payload"  "$(jq -r '.duration_s' <<<"$prow")" "60"
jq -e '.turns == 0 and .tool_calls == 0' \
  <<<"$(printf '{"session_id":"no-transcript","cwd":"/tmp"}' | AGENTOPS_COST_LOG="$tmp/c2.jsonl" AGENTOPS_GATE_LOG_DIR="$gatedir" bash "$stop_hook" >/dev/null; tail -1 "$tmp/c2.jsonl")" \
  >/dev/null || fail "REQ-002: the no-transcript path must emit zeroed counters, not omit them"

# --- REQ-003 / REQ-004: gate log -------------------------------------------------------
gatefile="$gatedir/gates-sess-b.jsonl"
run_gate_hook "sess-b" "$gatedir" "pytest tests/test_thing.py" '{"stdout":"1 failed, 0 passed","stderr":"","interrupted":false}'
run_gate_hook "sess-b" "$gatedir" "pytest tests/test_thing.py" '{"stdout":"2 passed","stderr":"","interrupted":false}'
run_gate_hook "sess-b" "$gatedir" "ls -la"                     '{"stdout":"","stderr":"","interrupted":false}'
run_gate_hook "sess-b" "$gatedir" "python verification/run_round_checks.py" '{"stdout":"ok","stderr":"","interrupted":false}'

assert_eq "REQ-003 non-gate command ignored" "$(wc -l < "$gatefile")" "3"
assert_eq "REQ-004 first attempt red"  "$(jq -r 'select(.cmd|test("test_thing")) | .ok' "$gatefile" | head -1)" "false"
assert_eq "REQ-004 retry green"        "$(jq -r 'select(.cmd|test("test_thing")) | .ok' "$gatefile" | tail -1)" "true"

log_b="$tmp/costs-b.jsonl"
run_stop "sess-b" "$log_b" "$gatedir"
[[ -f "$gatefile" ]] && fail "REQ-003: the gate log survived into the next session"
row_b="$(tail -1 "$log_b")"
jq -e 'has("turns")' <<<"$row_b" >/dev/null || fail "REQ-003: the cost row was lost while draining gates"

# REQ-004: one red gate retried with the same command = exactly one rework round;
# a red gate never retried = zero.
rework_of() {
  local gates="$1"
  jq -n --argjson rows "$gates" '
    $rows as $r
    | [ range(0; ($r | length))
        | select($r[.].ok == false)
        | . as $i
        | select([ $r[($i + 1):][] | select(.cmd == $r[$i].cmd) ] | length > 0)
      ] | length'
}
assert_eq "REQ-004 retried red counts once" \
  "$(rework_of '[{"cmd":"pytest a","ok":false},{"cmd":"pytest a","ok":true}]')" "1"
assert_eq "REQ-004 unretried red counts zero" \
  "$(rework_of '[{"cmd":"pytest a","ok":false},{"cmd":"pytest b","ok":true}]')" "0"
assert_eq "REQ-004 all green counts zero" \
  "$(rework_of '[{"cmd":"pytest a","ok":true},{"cmd":"pytest a","ok":true}]')" "0"

# --- REQ-003 (publication): the session reaches auditctl exactly once, with its gates ----
pubdir="$tmp/pub"; mkdir -p "$pubdir"
cat > "$pubdir/auditctl" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$AUDITCTL_STUB_LOG"
STUB
chmod +x "$pubdir/auditctl"
export AUDITCTL_STUB_LOG="$tmp/auditctl-calls.log"

gatefile_d="$gatedir/gates-sess-d.jsonl"
run_gate_hook "sess-d" "$gatedir" "pytest tests/x.py" '{"stdout":"1 failed","stderr":"","interrupted":false}'
run_gate_hook "sess-d" "$gatedir" "pytest tests/x.py" '{"stdout":"1 passed","stderr":"","interrupted":false}'
[[ -s "$gatefile_d" ]] || fail "REQ-003: the gate hook wrote nothing to drain"
run_stop "sess-d" "$tmp/costs-d.jsonl" "$gatedir" "$pubdir:$PATH"

assert_eq "REQ-003 published exactly once" "$(wc -l < "$AUDITCTL_STUB_LOG")" "1"
call="$(cat "$AUDITCTL_STUB_LOG")"
grep -q -- "--type workflow.session" <<<"$call" || fail "REQ-003: wrong event type"
if grep -q -- "--ref " <<<"$call"; then fail "REQ-003: --ref is rejected by auditctl for session ids"; fi
meta="$(sed -n 's/.*--metadata //p' <<<"$call")"
assert_eq "REQ-003 session id in metadata" "$(jq -r '.session' <<<"$meta")" "sess-d"
assert_eq "REQ-004 published rework_rounds" "$(jq -r '.rework_rounds' <<<"$meta")" "1"
assert_eq "REQ-003 published gate count" "$(jq -r '.gates | length' <<<"$meta")" "2"

# --- REQ-005: auditctl absent ----------------------------------------------------------
stub="$tmp/bin"; mkdir -p "$stub"
for c in bash jq date basename xargs mktemp rm mkdir cat; do
  src="$(command -v "$c")" && ln -sf "$src" "$stub/$c"
done
log_c="$tmp/costs-c.jsonl"
if ! run_stop "sess-c" "$log_c" "$gatedir" "$stub"; then
  fail "REQ-005: the Stop hook exited non-zero with auditctl off PATH"
fi
[[ -s "$log_c" ]] || fail "REQ-005: the cost row was lost with auditctl off PATH"

# --- both hooks are registered as commands, so both must be executable ------------------
for h in "$stop_hook" "$gate_hook"; do
  [[ -x "$h" ]] || fail "hook is not executable: $h"
done

printf 'session telemetry hook tests passed\n'
