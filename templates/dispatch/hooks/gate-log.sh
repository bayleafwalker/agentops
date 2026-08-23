#!/usr/bin/env bash
# Claude Code PostToolUse hook (T-3) — append one gate outcome per matching Bash
# command to a per-session gates log that the Stop hook (T-4) drains into auditctl.
#
# Matched commands are the gate surface named in the pathway §5 gate set: pytest,
# run_round_checks, hybrid_dispatch gate, cargo test. Anything else is ignored.
#
# The Bash tool result carries no exit code (verified against transcripts 2026-08-23),
# so `ok` is decided from the strongest signal available and `signal` records which one
# was used. A consumer that needs certainty must read `signal`, not just `ok`.
set -uo pipefail

GATE_DIR="${AGENTOPS_GATE_LOG_DIR:-/projects/dev/.claude/state}"
GATE_PATTERN="${AGENTOPS_GATE_PATTERN:-(pytest|run_round_checks|hybrid_dispatch(\.py)?[[:space:]].*[[:space:]]gate|cargo[[:space:]]+test|unittest[[:space:]]+discover)}"

EVENT="$(cat)"
command -v jq >/dev/null 2>&1 || exit 0

CMD="$(printf '%s' "$EVENT" | jq -r '.tool_input.command // ""')"
[[ -n "$CMD" ]] || exit 0
[[ "$CMD" =~ $GATE_PATTERN ]] || exit 0

SESSION="$(printf '%s' "$EVENT" | jq -r '.session_id // "unknown"')"
mkdir -p "$GATE_DIR" 2>/dev/null || exit 0

printf '%s' "$EVENT" | jq -c \
  --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg cmd "$CMD" '
  .tool_response as $r
  | ($r | if type == "object" then . else {} end) as $o
  | (($o.stdout // "") + "\n" + ($o.stderr // "") + "\n" + ($r | if type == "string" then . else "" end)) as $text
  | (if ($o | has("exit_code")) then {exit: ($o.exit_code | tonumber?), signal: "exit_code"}
     elif ($o.is_error // false) or ($o | has("error")) then {exit: 1, signal: "is_error"}
     elif ($o.interrupted // false) then {exit: null, signal: "interrupted"}
     elif ($text | test("\\bFAILED\\b|\\bFAIL\\b|\\bfailures?=[1-9]|[1-9][0-9]* (failed|error)|Traceback \\(most recent|AssertionError|error(\\[|:)|exit(ed)? (code )?[1-9]"))
       then {exit: null, signal: "heuristic"}
     else {exit: 0, signal: "heuristic"} end) as $verdict
  | {ts: $ts, cmd: $cmd, exit: $verdict.exit, signal: $verdict.signal,
     ok: (if $verdict.signal == "exit_code" then ($verdict.exit == 0)
          elif $verdict.exit == 0 then true else false end)}
  ' >> "$GATE_DIR/gates-$SESSION.jsonl" 2>/dev/null || exit 0

exit 0
