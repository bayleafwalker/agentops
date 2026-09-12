#!/usr/bin/env bash
# Oracle for the Transfer step: the Stop hook names the successor a session handed to.
#
# Scoped to that one outcome, following test-cost-hook-fields.sh rather than the whole
# T-set integration suite -- the change is a lookup and one conditional metadata key, and
# gating it on gate-log and the auditctl drain would gate it on unrelated code.
#
#   REQ-001 a session that is an acked handoff's predecessor publishes handed_off_to
#   REQ-002 a session with no handoff, or an unacked one, publishes no such key at all
#           (the un-handed-off event stays byte-identical to what it was before)
#   REQ-003 another session's handoff is not attributed to this one
#   REQ-004 the lookup is best-effort: a missing handoff directory still writes the record
set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
stop_hook="$(cd -- "$here/.." && pwd -P)/log-session-cost.sh"

tmp="$(mktemp -d)"
# Isolate the audit store, for the reason spelled out in test-cost-hook-fields.sh: this
# runs the real stop hook, which otherwise publishes fixture events into the live index.
mkdir -p "$tmp/store/.auditctl" && : > "$tmp/store/.auditctl/auditctl.db"
export AUDITCTL_DB="$tmp/store/.auditctl/auditctl.db"
export AUDITCTL_ARTIFACTS_ROOT="$tmp/store"
trap 'rm -rf "$tmp"' EXIT

fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

transcript="$tmp/transcript.jsonl"
cat > "$transcript" <<'JSONL'
{"type":"user","timestamp":"2026-09-12T10:00:00.000Z","message":{"role":"user","content":"do the thing"}}
{"type":"assistant","timestamp":"2026-09-12T10:00:10.000Z","message":{"role":"assistant","model":"claude-opus-5","usage":{"input_tokens":100,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"output_tokens":40},"content":[{"type":"tool_use","name":"Bash"}]}}
JSONL

# A handoff is written by handoff.py; only the two fields the lookup reads matter here, so
# the fixture carries them and nothing else. If the lookup ever needs a third field this
# fixture must grow -- that coupling is deliberate and visible.
handoffs="$tmp/handoffs"
mkdir -p "$handoffs"
write_handoff() { # <file> <predecessor-id> <successor-id-or-null>
  jq -n --arg p "$2" --arg s "$3" \
    '{predecessor: {session_id: $p},
      successor: {session_id: (if $s == "null" then null else $s end)}}' > "$handoffs/$1"
}

# `handoff_dir` unset means "do not pass AGENTOPS_HANDOFF_DIR", which is REQ-004's case.
run_stop() { # <session-id> [handoff_dir]
  local session="$1" dir="${2-}"
  jq -cn --arg t "$transcript" --arg s "$session" \
    '{transcript_path:$t, session_id:$s, cwd:"/projects/dev/agentops", hook_event_name:"Stop"}' \
    | env ${dir:+AGENTOPS_HANDOFF_DIR="$dir"} \
        AGENTOPS_COST_LOG="$tmp/costs.jsonl" \
        AUDITCTL_DB="$tmp/store/.auditctl/auditctl.db" \
        AUDITCTL_ARTIFACTS_ROOT="$tmp/store" \
        bash "$stop_hook"
}

# The record on disk carries no metadata, so the assertion has to read what was published.
# The NDJSON shard is auditctl's own output; grepping it for the session keeps the oracle
# on the event payload, which is where the field was asked to land.
published_metadata() { # <session-id> -> the metadata object of its newest event, or ''
  local session="$1"
  # auditctl chooses the shard path itself (a nested _artifacts/<store>/audit/ under the
  # root), so the search is by find, not by a fixed glob that would silently match nothing.
  find "$tmp/store" -name '*.ndjson' -type f -exec cat {} + 2>/dev/null \
    | jq -c --arg s "$session" \
        'select(.metadata.session == $s) | .metadata' 2>/dev/null | tail -n 1
}

# Publishing is optional by design (auditctl may not resolve), and without it the metadata
# assertions have nothing to read. Skip rather than report a failure the change did not cause.
write_handoff probe.json sess-probe succ-probe
run_stop sess-probe "$handoffs"
if [[ -z "$(published_metadata sess-probe)" ]]; then
  printf 'SKIP: auditctl published nothing, so metadata is unobservable here\n' >&2
  exit 0
fi

# --- REQ-001 ---------------------------------------------------------------------------
write_handoff 2026-09-12-a.v1.json sess-pred succ-live
run_stop sess-pred "$handoffs"
got="$(published_metadata sess-pred | jq -r '.handed_off_to // ""')"
[[ "$got" == "succ-live" ]] || fail "REQ-001: expected handed_off_to 'succ-live', got '$got'"

# --- REQ-002 ---------------------------------------------------------------------------
# An unacked handoff is a transfer that never happened. `has` rather than a value compare:
# emitting the key as null or "" would be a different event shape for every session that
# never handed off, which is exactly what the conditional exists to avoid.
write_handoff 2026-09-12-b.v1.json sess-unacked null
run_stop sess-unacked "$handoffs"
published_metadata sess-unacked | jq -e 'has("handed_off_to") | not' >/dev/null \
  || fail "REQ-002: an unacked handoff produced a handed_off_to key"

run_stop sess-nohandoff "$handoffs"
published_metadata sess-nohandoff | jq -e 'has("handed_off_to") | not' >/dev/null \
  || fail "REQ-002: a session with no handoff at all produced a handed_off_to key"

# --- REQ-003 ---------------------------------------------------------------------------
# sess-other is nobody's predecessor, but succ-live is sitting in the directory. A lookup
# that globbed the successor field without matching the predecessor would pass REQ-001 and
# fail here.
run_stop sess-other "$handoffs"
published_metadata sess-other | jq -e 'has("handed_off_to") | not' >/dev/null \
  || fail "REQ-003: another session's handoff was attributed to sess-other"

# --- REQ-004 ---------------------------------------------------------------------------
: > "$tmp/costs.jsonl"
run_stop sess-nodir "$tmp/does-not-exist"
grep -q '"session":"sess-nodir"' "$tmp/costs.jsonl" \
  || fail "REQ-004: a missing handoff directory cost the session its cost record"

printf 'ok: test-handed-off-to.sh (4 requirements)\n'
