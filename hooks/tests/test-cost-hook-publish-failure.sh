#!/usr/bin/env bash
# Oracle for the failure REPORT, not the failure itself.
#
# For a month the hook published with `>/dev/null 2>&1 || true`. auditctl was
# printing a precise, actionable error -- "audit event exceeds the 16384-byte
# canonical NDJSON limit" -- and the hook threw it away, so 1417 audit rows went
# missing between 2026-08-23 and 2026-09-22 (630 workflow.session rows against
# 2047 cost rows; 82 of 158 sessions produced no audit row at all) with nothing
# anywhere recording that a publish had ever failed. The size bug is fixed
# elsewhere. THIS test exists because the next publish failure will have a
# different cause, and the only thing that generalises is that a failure must
# leave a trace.
#
# A falsification pass on 2026-09-22 reported the runtime guard real but its
# regression protection ABSENT: the whole error-reporting block could be deleted
# and the suite stayed green, which by the operator's standing rule makes it
# untrusted code rather than a trusted check. This file is that missing oracle.
#
#   REQ-001 a failed publish still leaves the session unharmed: hook exits 0
#   REQ-002 the cost row still lands, because the cost log is not auditctl's
#   REQ-003 the failure is recorded durably, with the exit status
#   REQ-004 auditctl's own stderr is preserved, not discarded -- that text is the
#           whole reason this failure went unread for a month
#   REQ-005 a SUCCESSFUL publish writes no failure row (or the log would cry wolf
#           on every session and be ignored again)
set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
hooks_dir="$(cd -- "$here/.." && pwd -P)"
stop_hook="$hooks_dir/log-session-cost.sh"

command -v jq >/dev/null || { echo "SKIP: jq not available"; exit 0; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

mkdir -p "$tmp/store/.auditctl" && : > "$tmp/store/.auditctl/auditctl.db"
mkdir -p "$tmp/gates" "$tmp/bin"

transcript="$tmp/transcript.jsonl"
cat > "$transcript" <<'JSONL'
{"type":"user","timestamp":"2026-09-22T10:00:00.000Z","message":{"role":"user","content":"do the thing"}}
{"type":"assistant","timestamp":"2026-09-22T10:00:10.000Z","message":{"role":"assistant","model":"claude-opus-5","usage":{"input_tokens":100,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"output_tokens":40},"content":[{"type":"tool_use","name":"Bash"}]}}
JSONL

# A publisher that always fails, with a distinctive message. Injected by shadowing
# the resolver's answer through PATH, so the hook's own resolution logic is
# exercised rather than bypassed.
STUB_MESSAGE="stub refused this event: canonical line too long"
cat > "$tmp/bin/auditctl" <<STUB
#!/usr/bin/env bash
printf '%s\n' "$STUB_MESSAGE" >&2
exit 3
STUB
chmod +x "$tmp/bin/auditctl"

run_stop() {
  local sess="$1" log="$2" failure_log="$3" extra_path="${4:-}"
  : > "$tmp/gates/gates-$sess.jsonl"
  jq -cn '{kind:"gate", cmd:"pytest -q", ok:true}' >> "$tmp/gates/gates-$sess.jsonl"
  jq -cn --arg t "$transcript" --arg s "$sess" \
    '{transcript_path:$t, session_id:$s, cwd:"/projects/dev/agentops", hook_event_name:"Stop"}' \
    | PATH="${extra_path:+$extra_path:}$PATH" \
      AGENTOPS_COST_LOG="$log" \
      AGENTOPS_GATE_LOG_DIR="$tmp/gates" \
      AGENTOPS_AUDIT_FAILURE_LOG="$failure_log" \
      AUDITCTL_DB="$tmp/store/.auditctl/auditctl.db" \
      AUDITCTL_ARTIFACTS_ROOT="$tmp/store" \
      bash "$stop_hook"
}

# --- the failing publish -----------------------------------------------------
log="$tmp/costs.jsonl"
failure_log="$tmp/failures.jsonl"
set +e
run_stop "sess-publish-fails" "$log" "$failure_log" "$tmp/bin"
hook_rc=$?
set -e

# REQ-001
[[ "$hook_rc" == "0" ]] || fail "REQ-001: the hook exited $hook_rc; a failed publish must never cost the session its turn"

# REQ-002
[[ -s "$log" ]] || fail "REQ-002: the cost row did not land, although only auditctl failed"

# REQ-003
if [[ ! -s "$failure_log" ]]; then
  # Distinguish "the stub was never reached" from "the guard is gone". If the
  # hook could not resolve any publisher it returns early by design and there is
  # nothing to report -- but that must not read as a pass.
  fail "REQ-003: auditctl exited 3 and nothing was recorded anywhere. Either the failure-reporting block is missing, or the stub publisher was never reached (check auditctl_bin resolution)."
fi
row="$(tail -1 "$failure_log")"
jq -e . >/dev/null 2>&1 <<<"$row" || fail "REQ-003: the failure row is not valid JSON: $row"

got_rc="$(jq -r '.exit_status' <<<"$row")"
[[ "$got_rc" == "3" ]] || fail "REQ-003: exit_status is '$got_rc', expected 3 -- the status must be recorded, not just the fact of failure"

got_session="$(jq -r '.session' <<<"$row")"
[[ "$got_session" == "sess-publish-fails" ]] || fail "REQ-003: session is '$got_session'; a failure that cannot be attributed to a session is not actionable"

# REQ-004 -- the specific regression. An empty or placeholder stderr field means
# the error text was discarded again, which is exactly the old behaviour.
got_stderr="$(jq -r '.stderr // ""' <<<"$row")"
[[ -n "$got_stderr" ]] || fail "REQ-004: no stderr recorded; auditctl's error text is the thing that went unread for a month"
case "$got_stderr" in
  *"stub refused this event"*) ;;
  *) fail "REQ-004: stderr is '$got_stderr', which does not contain the publisher's actual message -- the error text was not preserved" ;;
esac

# --- REQ-005: a successful publish must stay quiet ---------------------------
quiet_failure_log="$tmp/failures-quiet.jsonl"
set +e
run_stop "sess-publish-succeeds" "$tmp/costs-quiet.jsonl" "$quiet_failure_log"
quiet_rc=$?
set -e
[[ "$quiet_rc" == "0" ]] || fail "REQ-005: the hook exited $quiet_rc on the ordinary path"
if [[ -s "$quiet_failure_log" ]]; then
  # Only a real failure justifies a row. If the host has no working auditctl at
  # all this branch cannot be reached, because the hook returns before publishing.
  fail "REQ-005: a failure row was written for a publish that was not reported as failing: $(tail -1 "$quiet_failure_log")"
fi

echo "PASS: test-cost-hook-publish-failure.sh"
