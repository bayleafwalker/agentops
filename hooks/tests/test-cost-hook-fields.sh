#!/usr/bin/env bash
# T-1 oracle, and only T-1: the four transcript-derived fields plus the log-path
# seam the test needs to observe them.
#
# Split out of test-session-telemetry.sh deliberately. That suite is the whole
# T-set's integration oracle -- it exercises gate-log.sh and the auditctl drain
# too -- so pointing a T-1-only packet at it gates one item's work on three
# items' code, and the packet can never go green however good the work is. A
# packet gets an oracle that covers exactly its own outcomes.
#
#   REQ-001 the cost record stays backward compatible
#   REQ-002 the counters are derived from the transcript, not the Stop payload
#   REQ-003 the log path is overridable so a test can observe the record
set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
stop_hook="$(cd -- "$here/.." && pwd -P)/log-session-cost.sh"

tmp="$(mktemp -d)"
# Isolate the audit store: these tests run the real stop hook, which publishes to
# whatever store resolution finds. Without this they write fixture events into the
# live agentops index -- 36 such events had accumulated there by 2026-08-29.
mkdir -p "$tmp/store/.auditctl" && : > "$tmp/store/.auditctl/auditctl.db"
export AUDITCTL_DB="$tmp/store/.auditctl/auditctl.db"
export AUDITCTL_ARTIFACTS_ROOT="$tmp/store"
trap 'rm -rf "$tmp"' EXIT

fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
assert_eq() { [[ "$2" == "$3" ]] || fail "$1: expected '$3', got '$2'"; }

# 2 real user turns (one meta, two tool_result turns excluded), 3 assistant
# messages, 4 tool_use blocks, 60s between first and last timestamp.
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
  local log="$1" extra="${2:-}"
  jq -cn --arg t "$transcript" --arg s "sess-t1" \
    '{transcript_path:$t, session_id:$s, cwd:"/projects/dev/agentops", hook_event_name:"Stop"}
     + (if $ENV.POISON == "1" then {turns:999, assistant_msgs:999, tool_calls:999, duration_s:999} else {} end)' \
    | POISON="$extra" AGENTOPS_COST_LOG="$log" \
      AUDITCTL_DB="$tmp/store/.auditctl/auditctl.db" AUDITCTL_ARTIFACTS_ROOT="$tmp/store" \
      bash "$stop_hook"
}

# --- REQ-003: without the seam the record is unobservable, so it comes first --
log="$tmp/costs.jsonl"
run_stop "$log"
[[ -s "$log" ]] || fail "REQ-003: AGENTOPS_COST_LOG was ignored, so no record could be observed"
row="$(tail -1 "$log")"

# --- REQ-002: derived from the transcript ------------------------------------
assert_eq "turns"          "$(jq -r '.turns' <<<"$row")"          "2"
assert_eq "assistant_msgs" "$(jq -r '.assistant_msgs' <<<"$row")" "3"
assert_eq "tool_calls"     "$(jq -r '.tool_calls' <<<"$row")"     "4"
assert_eq "duration_s"     "$(jq -r '.duration_s' <<<"$row")"     "60"

poisoned="$tmp/poisoned.jsonl"
POISON=1 run_stop "$poisoned" 1
prow="$(tail -1 "$poisoned")"
assert_eq "REQ-002 turns ignore the payload"      "$(jq -r '.turns' <<<"$prow")"      "2"
assert_eq "REQ-002 tool_calls ignore the payload" "$(jq -r '.tool_calls' <<<"$prow")" "4"
assert_eq "REQ-002 duration ignores the payload"  "$(jq -r '.duration_s' <<<"$prow")" "60"

# --- REQ-001: nothing that existed changed -----------------------------------
for f in ts project session runtime_session_id model in cache_write cache_read out cost_usd; do
  jq -e --arg f "$f" 'has($f)' <<<"$row" >/dev/null || fail "REQ-001: legacy field '$f' disappeared"
done
assert_eq "REQ-001 model" "$(jq -r '.model' <<<"$row")" "claude-opus-5"
assert_eq "REQ-001 in"    "$(jq -r '.in' <<<"$row")"    "120"
assert_eq "REQ-001 out"   "$(jq -r '.out' <<<"$row")"   "50"
jq -e '.cost_usd > 0' <<<"$row" >/dev/null || fail "REQ-001: cost_usd is no longer computed"

# --- REQ-012: the session identity reaches the typed field, not only the untyped one ----
# Measured 2026-08-29 across 1593 events in 11 stores: `runtime_session_id` was populated
# ZERO times while the same uuid sat 354 times in `metadata.session` beside it, because
# this hook wrote "" whenever no external runtime supplied one -- and "" is the shape the
# session-mechanization validators reject as blank. Asserted on the cost row, which is
# where the value is observable without a publisher; the audit event takes the same value
# through the same variable.
assert_eq "REQ-012 runtime_session_id falls back to this session" \
  "$(jq -r '.runtime_session_id' <<<"$row")" "sess-t1"

# ...and an external runtime still wins, since that is the id that identifies the run when
# one exists. Only the empty case changed.
ext_log="$tmp/costs-ext.jsonl"
jq -cn --arg t "$transcript" --arg s "sess-t1" \
  '{transcript_path:$t, session_id:$s, runtime_session_id:"runtime-9", cwd:"/projects/dev/agentops", hook_event_name:"Stop"}' \
  | AGENTOPS_COST_LOG="$ext_log" \
    AUDITCTL_DB="$tmp/store/.auditctl/auditctl.db" AUDITCTL_ARTIFACTS_ROOT="$tmp/store" \
    bash "$stop_hook"
assert_eq "REQ-012 an external runtime id still wins" \
  "$(jq -r '.runtime_session_id' <<<"$(tail -1 "$ext_log")")" "runtime-9"

# A placeholder must not reach a typed field: that is the untyped field's disease.
ph_log="$tmp/costs-ph.jsonl"
jq -cn --arg t "$transcript" \
  '{transcript_path:$t, cwd:"/projects/dev/agentops", hook_event_name:"Stop"}' \
  | AGENTOPS_COST_LOG="$ph_log" \
    AUDITCTL_DB="$tmp/store/.auditctl/auditctl.db" AUDITCTL_ARTIFACTS_ROOT="$tmp/store" \
    bash "$stop_hook"
assert_eq "REQ-012 'unknown' is not promoted into the typed field" \
  "$(jq -r '.runtime_session_id' <<<"$(tail -1 "$ph_log")")" ""

# The default must survive: a hook that only works under the test env is not the
# hook the sessions run.
grep -q 'AGENTOPS_COST_LOG:-/projects/dev/.claude/session-costs.jsonl' "$stop_hook" \
  || fail "REQ-003: the default log path was not preserved"

printf 'cost hook field tests passed (incl. REQ-012 typed session identity)\n'
