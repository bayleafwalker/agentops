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
# (auditctl/auditctl/ndjson.py), an order of magnitude below the argv cap. So a
# 1200-row array of real gate rows can never be recorded inline, by any argv
# trick.
#
# REVISED 2026-09-22 (operator decision, delegated). The arrays no longer travel
# in the row AT ALL, rather than travelling when they happen to fit: nine of ten
# live gate logs exceed the limit on their own, nothing downstream reads
# metadata.gates, and a row shape that varies with payload size is its own trap.
# So the "truncated" concept is gone -- there is no bounded-vs-full distinction
# left to mark, because every row is the same shape.
#
# What this file asserts is therefore narrower AND stricter than before. It is
# NOT weakened: nothing here passes against the original code, which produced no
# row at all for this fixture, and the "arrays must be absent" assertion is new.
#
#   REQ-001 a gate array well over every limit still produces an auditctl row
#   REQ-002 that row carries the true counts, and carries NEITHER array
#   REQ-003 the full gates and decisions arrays are recoverable, whole, from the
#           path the row points at
#   REQ-004 a SMALL gate log produces exactly the same shape -- the row does not
#           become richer just because the payload was short
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

# REQ-002: the counts are recorded, and neither array is in the row.
got_gates="$(jq -r '.metadata.gates_count' <<<"$row")"
[[ "$got_gates" == "1200" ]] || fail "REQ-002: gates_count is $got_gates, expected 1200"

got_decisions="$(jq -r '.metadata.decisions_count' <<<"$row")"
[[ "$got_decisions" == "1" ]] || fail "REQ-002: decisions_count is $got_decisions, expected 1"

jq -e '.metadata | (has("gates") or has("decisions")) | not' <<<"$row" >/dev/null \
  || fail "REQ-002: an array is present in the published row; the arrays must never travel there"

# The event must actually be within auditctl's canonical limit, or it only
# happened to land here and would be refused by a real store.
row_bytes="$(printf '%s\n' "$row" | wc -c)"
(( row_bytes <= 16384 )) \
  || fail "REQ-002: the published event line is $row_bytes bytes, over the 16384-byte canonical limit"

# REQ-003: the full arrays are recoverable, whole, from where the row points.
full_path="$(jq -r '.metadata.gates_path // ""' <<<"$row")"
[[ -n "$full_path" ]] || fail "REQ-003: the row does not say where the full arrays went"
[[ -s "$full_path" ]] || fail "REQ-003: gates_path '$full_path' does not exist or is empty"
[[ "$(jq -r '.gates | length' "$full_path")" == "1200" ]] \
  || fail "REQ-003: the sidecar holds $(jq -r '.gates | length' "$full_path") gate rows, expected all 1200"
[[ "$(jq -r '.decisions | length' "$full_path")" == "1" ]] \
  || fail "REQ-003: the sidecar lost the decision row"
jq -e '.gates[0] | has("cmd") and has("ok")' "$full_path" >/dev/null \
  || fail "REQ-003: gate rows lost their shape on the way to the sidecar"

# --- REQ-004: the ordinary small case still works ----------------------------
small="sess-small-gates"
: > "$tmp/gates/gates-$small.jsonl"
jq -cn '{kind:"gate", cmd:"pytest -q", ok:true}' >> "$tmp/gates/gates-$small.jsonl"
run_stop "$small" "$tmp/costs-small.jsonl"
srow="$(audit_row_for "$small")"
[[ -n "$srow" ]] || fail "REQ-004: the small-input path stopped producing an auditctl row"
# The point of REQ-004 is now the OPPOSITE of what it used to be. It used to
# assert that a short payload is published whole; it now asserts that a short
# payload is published in exactly the same shape as a long one. A row that got
# richer when the session happened to be short is the trap this decision
# removed: a query written against it returns wrong answers on a long session,
# silently, and nothing about the two rows says they differ.
[[ "$(jq -r '.metadata.gates_count' <<<"$srow")" == "1" ]] \
  || fail "REQ-004: small gate count did not survive"
jq -e '.metadata | (has("gates") or has("decisions")) | not' <<<"$srow" >/dev/null \
  || fail "REQ-004: the small case carries an array inline; the shape must not vary with size"
small_path="$(jq -r '.metadata.gates_path // ""' <<<"$srow")"
[[ -s "$small_path" ]] || fail "REQ-004: the small case wrote no sidecar"
[[ "$(jq -r '.gates | length' "$small_path")" == "1" ]] \
  || fail "REQ-004: the small case's gate row did not reach the sidecar"
# Same key set in both rows, which is the invariant the whole decision buys.
big_keys="$(jq -Sc '.metadata | keys' <<<"$row")"
small_keys="$(jq -Sc '.metadata | keys' <<<"$srow")"
[[ "$big_keys" == "$small_keys" ]] \
  || fail "REQ-004: row shape varies with payload size. 1200-row session: $big_keys ; 1-row session: $small_keys"

echo "PASS: test-cost-hook-large-gates.sh"
