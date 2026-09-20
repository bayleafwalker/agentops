#!/usr/bin/env bash
# Sourced helper (WL-D1, agentops#2434). The four guard hooks that deny or ask
# (bounded-read-guard.sh, nfs-workspace-guard.sh, forge-sandbox-guard.sh,
# gate-check.sh) leave no row in the per-session gate log that
# hooks/log-session-cost.sh drains into auditctl at Stop, so denials were
# invisible to cost and rework reporting. This file adds RECORDING of a
# decision a guard hook already made -- it never influences what any hook
# denies or allows, and it never changes the caller's exit code or stdout.
#
#   emit_decision <hook> <rule_id> <tool> <deny|ask>
#
# Appends one row {"kind":"decision","ts":<UTC ISO>,"hook":..,"rule_id":..,
# "tool":..,"policy_decision":..} to $GATE_DIR/gates-$SESSION.jsonl.
#
# GATE_DIR is resolved the same way hooks/gate-log.sh resolves it:
# AGENTOPS_GATE_LOG_DIR, falling back to /projects/dev/.claude/state.
#
# The session id is read from $EVENT -- the raw hook event JSON on stdin,
# the same source and the same `.session_id` field hooks/gate-log.sh reads.
# Because this file is *sourced* into the caller's shell rather than run as
# a subprocess, the caller's own `$EVENT` (every guard hook already captures
# the event into a variable of exactly this name) is visible here without
# needing to be passed as an argument or re-read from stdin, which by the
# time a hook is ready to call this has usually already been consumed.
#
# Silent no-op -- never a row, never a failure the caller observes -- when:
#   - jq is unavailable
#   - the caller has no $EVENT, or its .session_id is absent/empty/null
#   - the gate directory cannot be created
# Unlike gate-log.sh, a missing session id is never written as "unknown":
# an unattributable decision row would be worse than no row at all for
# something nothing yet consumes.
emit_decision() {
  local hook="$1" rule_id="$2" tool="$3" policy_decision="$4"

  command -v jq >/dev/null 2>&1 || return 0

  local session
  session="$(printf '%s' "${EVENT:-}" | jq -r '.session_id // empty' 2>/dev/null)"
  [ -n "$session" ] || return 0

  local gate_dir="${AGENTOPS_GATE_LOG_DIR:-/projects/dev/.claude/state}"
  mkdir -p "$gate_dir" 2>/dev/null || return 0

  jq -cn \
    --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg hook "$hook" \
    --arg rule_id "$rule_id" \
    --arg tool "$tool" \
    --arg policy_decision "$policy_decision" \
    '{kind: "decision", ts: $ts, hook: $hook, rule_id: $rule_id, tool: $tool, policy_decision: $policy_decision}' \
    >> "$gate_dir/gates-$session.jsonl" 2>/dev/null

  return 0
}
