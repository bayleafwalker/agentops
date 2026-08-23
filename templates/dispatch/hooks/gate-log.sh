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
#
# A compound command is a special case worth refusing rather than guessing about: in
# `pytest ... | tail -5` the status belongs to `tail`, and the failure text may be exactly
# what got filtered out. Such a row is recorded with signal "unattributable" and ok null --
# an honest gap that rework_rounds skips, rather than a verdict that is wrong in whichever
# direction the text happened to fall.
set -uo pipefail

GATE_DIR="${AGENTOPS_GATE_LOG_DIR:-/projects/dev/.claude/state}"
GATE_PATTERN="${AGENTOPS_GATE_PATTERN:-(pytest|run_round_checks|hybrid_dispatch(\.py)?[[:space:]].*[[:space:]]gate|cargo[[:space:]]+test|unittest[[:space:]]+discover)}"
# M-5: a gate name counts only as a command word. It must sit on shell-word
# boundaries -- preceded by the start of the string, whitespace, a shell
# separator, or a path component, and followed by whitespace, a separator, the
# end of the string, or an executable script suffix. Quoted text is an argument
# to something else and is dropped before matching; the row still carries the
# original command.
GATE_ANCHOR="(^|[[:space:]]|[|&;]|/)($GATE_PATTERN)([[:space:]]|[|&;]|$|\\.(py|sh|bash|zsh|pl|rb|js|ts|php|lua))"

EVENT="$(cat)"
command -v jq >/dev/null 2>&1 || exit 0

CMD="$(printf '%s' "$EVENT" | jq -r '.tool_input.command // ""')"
[[ -n "$CMD" ]] || exit 0
MATCH_CMD="$(printf '%s' "$CMD" | sed -E "s/\"[^\"]*\"//g; s/'[^']*'//g")"
[[ "$MATCH_CMD" =~ $GATE_ANCHOR ]] || exit 0

SESSION="$(printf '%s' "$EVENT" | jq -r '.session_id // "unknown"')"
mkdir -p "$GATE_DIR" 2>/dev/null || exit 0

printf '%s' "$EVENT" | jq -c \
  --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg cmd "$CMD" '
  .tool_response as $r
  | ($r | if type == "object" then . else {} end) as $o
  | (($o.stdout // "") + "\n" + ($o.stderr // "") + "\n" + ($r | if type == "string" then . else "" end)) as $text
  | ($cmd | test("[|]|&&|[|][|]|;")) as $compound
  | (if ($o | has("exit_code")) then {exit: ($o.exit_code | tonumber?), signal: "exit_code"}
     elif ($o.is_error // false) or ($o | has("error")) then {exit: 1, signal: "is_error"}
     elif ($o.interrupted // false) then {exit: null, signal: "interrupted"}
     elif $compound then {exit: null, signal: "unattributable"}
     elif ($text | test("\\bFAILED\\b|\\bFAIL\\b|\\bfailures?=[1-9]|[1-9][0-9]* (failed|error)|Traceback \\(most recent|AssertionError|error(\\[|:)|exit(ed)? (code )?[1-9]"))
       then {exit: null, signal: "heuristic"}
     else {exit: 0, signal: "heuristic"} end) as $verdict
  | {ts: $ts, cmd: $cmd, exit: $verdict.exit, signal: $verdict.signal,
     ok: (if $verdict.signal == "exit_code" then ($verdict.exit == 0)
          elif $verdict.signal == "unattributable" then null
          elif $verdict.signal == "interrupted" then false
          elif $verdict.exit == 0 then true else false end)}
  ' >> "$GATE_DIR/gates-$SESSION.jsonl" 2>/dev/null || exit 0

exit 0
