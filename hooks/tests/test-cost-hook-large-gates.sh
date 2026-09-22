#!/usr/bin/env bash
# Oracle for one failure and only one: the auditctl row must survive a session
# whose accumulated gate array is larger than a single argv string may be.
#
# Linux caps ONE argv string at MAX_ARG_STRLEN -- 32 * page size, so 128 KiB on
# a 4 KiB-page host -- independently of ARG_MAX. log-session-cost.sh used to
# pass the whole gate array as `--argjson gates "$GATES"`, which is one
# argument, so a long session crossed that ceiling and execve failed E2BIG.
# Measured 2026-09-22: GATES was 169602 bytes against a 131072-byte per-argument
# cap on a host whose ARG_MAX is 2 MiB -- which is why the total was never the
# constraint and why "it fits in ARG_MAX" was the wrong thing to check.
#
# The failure was SILENT in the place anyone looks: the cost row still landed in
# the JSONL, and only the auditctl row vanished. So this asserts on the auditctl
# side, not the cost log.
#
# argv turned out NOT to be the binding constraint. auditctl refuses any event
# whose whole canonical NDJSON line exceeds MAX_EVENT_LINE_BYTES = 16 KiB
# (auditctl/auditctl/ndjson.py), which is an order of magnitude below the argv
# cap. So a 1200-row array of real gate rows can never be recorded inline, by
# any argv trick. REQ-002 and REQ-003 as originally written ("that row's `gates`
# is the real array, not a truncation or a stub", "`decisions` survives the same
# treatment") asserted an UNSATISFIABLE contract: they demanded the publisher
# violate auditctl's size limit, which is a deliberate contract and out of scope
# to widen. They are replaced below by the contract that is actually wanted --
# the row must never be lost, and when it cannot carry everything it must say so
# and say where the rest went. What is NOT weakened: a row must still appear
# (that is the regression), the counts must still be recorded, and the full
# arrays must still be recoverable in full, so nothing here would pass against
# the old code, which produced no row at all.
#
#   REQ-001 a gate array well over MAX_ARG_STRLEN still produces an auditctl row
#   REQ-002 that row is explicitly marked truncated and records the true counts
#           (1200 gates, 1 decision) rather than silently shedding them
#   REQ-003 the full gates and decisions arrays remain recoverable, whole, from
#           the location the row points at
#   REQ-004 the small-input path is unchanged: it still carries both arrays inline
set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
stop_hook="$(cd -- "$here/.." && pwd -P)/log-session-cost.sh"

command -v jq >/dev/null || { echo "SKIP: jq not available"; exit 0; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

# Isolate the audit store, or these fixtures land in the live agentops index.
mkdir -p "$tmp/store/.auditctl" && : > "$tmp/store/.auditctl/auditctl.db"
mkdir -p "$tmp/gates"

transcript="$tmp/transcript.jsonl"
cat > "$transcript" <<'JSONL'
{"type":"user","timestamp":"2026-09-22T10:00:00.000Z","message":{"role":"user","content":"do the thing"}}
{"type":"assistant","timestamp":"2026-09-22T10:00:10.000Z","message":{"role":"assistant","model":"claude-opus-5","usage":{"input_tokens":100,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"output_tokens":40},"content":[{"type":"tool_use","name":"Bash"}]}}
JSONL

# --- the fixture: a gate log whose serialised array is far past 128 KiB -------
# Built by row count against a measured target rather than a magic number, so
# the fixture stays over the cap if the row shape changes.
session="sess-large-gates"
gate_file="$tmp/gates/gates-$session.jsonl"
: > "$gate_file"
padding="$(printf 'x%.0s' $(seq 1 200))"
for i in $(seq 1 1200); do
  jq -cn --arg cmd "pytest -q run-$i $padding" --argjson i "$i" \
    '{kind:"gate", cmd:$cmd, ok:true, ts:"2026-09-22T10:00:00Z", seq:$i}' >> "$gate_file"
done
# One decision row too, so REQ-003 has a subject.
jq -cn --arg d "denied: $padding" '{kind:"decision", detail:$d}' >> "$gate_file"

gates_bytes="$(jq -cs '[ .[] | select(.kind != "decision") ]' "$gate_file" | wc -c)"
# MAX_ARG_STRLEN is 32 pages. Compute it rather than assuming 4 KiB pages.
page="$(getconf PAGESIZE 2>/dev/null || echo 4096)"
max_arg_strlen=$(( 32 * page ))
if (( gates_bytes <= max_arg_strlen )); then
  fail "fixture is not over the cap: gates is $gates_bytes bytes, MAX_ARG_STRLEN is $max_arg_strlen -- this test would pass without proving anything"
fi
printf 'fixture: gates=%s bytes, MAX_ARG_STRLEN=%s bytes\n' "$gates_bytes" "$max_arg_strlen"

run_stop() {
  local sess="$1" log="$2"
  jq -cn --arg t "$transcript" --arg s "$sess" \
    '{transcript_path:$t, session_id:$s, cwd:"/projects/dev/agentops", hook_event_name:"Stop"}' \
    | AGENTOPS_COST_LOG="$log" \
      AGENTOPS_GATE_LOG_DIR="$tmp/gates" \
      AUDITCTL_DB="$tmp/store/.auditctl/auditctl.db" \
      AUDITCTL_ARTIFACTS_ROOT="$tmp/store" \
      bash "$stop_hook"
}

audit_row_for() {
  # The auditctl row carries the session id in its metadata, not in a ref.
  local sess="$1"
  find "$tmp/store" -name '*.ndjson' -o -name '*.jsonl' 2>/dev/null \
    | xargs -r cat 2>/dev/null \
    | jq -c --arg s "$sess" 'select((.metadata.session // .metadata.runtime_session_id) == $s)' \
    | tail -1
}

# --- REQ-001 / REQ-002 / REQ-003 ---------------------------------------------
log="$tmp/costs.jsonl"
run_stop "$session" "$log"

[[ -s "$log" ]] || fail "REQ-001 precondition: no cost row at all, so the hook did not run"

row="$(audit_row_for "$session")"
if [[ -z "$row" ]]; then
  # Distinguish "auditctl is not installed here" from the regression. If the
  # binary is absent the hook returns early by design and there is nothing to
  # assert -- but we must not report that as a pass.
  if ! command -v auditctl >/dev/null 2>&1 && [[ ! -x /projects/dev/agentops/scripts/auditctl ]]; then
    echo "SKIP: auditctl not resolvable here; the argv-size path is untested on this host"
    exit 0
  fi
  fail "REQ-001: the cost row landed but the auditctl row did not -- this is the E2BIG regression, gates went back through argv"
fi

# REQ-002: the row says plainly that it is bounded, and keeps the counts.
jq -e '.metadata.truncated == true' <<<"$row" >/dev/null \
  || fail "REQ-002: the row is bounded but is not marked truncated -- that is silent data loss"
jq -e '(.metadata.truncated_reason // "") != ""' <<<"$row" >/dev/null \
  || fail "REQ-002: no truncated_reason, so nothing states why the arrays are missing"

got_gates="$(jq -r '.metadata.gates_count' <<<"$row")"
[[ "$got_gates" == "1200" ]] || fail "REQ-002: gates_count is $got_gates, expected 1200"

got_decisions="$(jq -r '.metadata.decisions_count' <<<"$row")"
[[ "$got_decisions" == "1" ]] || fail "REQ-002: decisions_count is $got_decisions, expected 1"

# The event must actually be within auditctl's canonical limit, or it only
# happened to land here and would be refused by a real store.
row_bytes="$(printf '%s\n' "$row" | wc -c)"
(( row_bytes <= 16384 )) \
  || fail "REQ-002: the published event line is $row_bytes bytes, over the 16384-byte canonical limit"

# REQ-003: the full arrays are recoverable, whole, from where the row points.
full_path="$(jq -r '.metadata.full_payload_path // ""' <<<"$row")"
[[ -n "$full_path" ]] || fail "REQ-003: the row does not say where the full arrays went"
[[ -s "$full_path" ]] || fail "REQ-003: full_payload_path '$full_path' does not exist or is empty"
[[ "$(jq -r '.gates | length' "$full_path")" == "1200" ]] \
  || fail "REQ-003: the sidecar holds $(jq -r '.gates | length' "$full_path") gate rows, expected all 1200"
[[ "$(jq -r '.decisions | length' "$full_path")" == "1" ]] \
  || fail "REQ-003: the sidecar lost the decision row"
jq -e '.gates[0] | has("cmd") and has("ok")' "$full_path" >/dev/null \
  || fail "REQ-003: gate rows lost their shape in transit"

# --- REQ-004: the ordinary small case still works ----------------------------
small="sess-small-gates"
: > "$tmp/gates/gates-$small.jsonl"
jq -cn '{kind:"gate", cmd:"pytest -q", ok:true}' >> "$tmp/gates/gates-$small.jsonl"
run_stop "$small" "$tmp/costs-small.jsonl"
srow="$(audit_row_for "$small")"
[[ -n "$srow" ]] || fail "REQ-004: the small-input path stopped producing an auditctl row"
[[ "$(jq -r '.metadata.gates | length' <<<"$srow")" == "1" ]] \
  || fail "REQ-004: small gate array did not survive"
jq -e '.metadata.truncated == null' <<<"$srow" >/dev/null \
  || fail "REQ-004: the small case was bounded; it fits and must be published whole"

echo "PASS: test-cost-hook-large-gates.sh"
