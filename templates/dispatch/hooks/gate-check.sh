#!/usr/bin/env bash
# PreToolUse/Bash. Enforces a repo's .claude/gates.json.
#
# The DEFAULT IS ROUTINE. Anything not matching a gate runs without a prompt --
# including advancing main, PR create/merge and release cuts. Gating is opt-in
# and per project; absence of a declaration never means "ask".
#
# Three tiers:
#   routine            -- no prompt, agent acts
#   operator-approved  -- owner approves, then the AGENT performs it
#   operator-actioned  -- a HUMAN performs it; the agent must not
set -uo pipefail
EVENT="$(cat 2>/dev/null || true)"
command -v jq >/dev/null 2>&1 || exit 0

CMD="$(printf '%s' "$EVENT" | jq -r '.tool_input.command // ""' 2>/dev/null)"
CWD="$(printf '%s' "$EVENT" | jq -r '.cwd // ""' 2>/dev/null)"
[ -n "$CMD" ] || exit 0

ROOT="$(git -C "${CWD:-.}" rev-parse --show-toplevel 2>/dev/null || printf '%s' "${CWD:-.}")"
GATES="$ROOT/.claude/gates.json"
[ -r "$GATES" ] || exit 0

MATCHED="$(CMD="$CMD" jq -r '[ .gated[]? | . as $g | select(env.CMD | test($g.match)) ] | first | if . then .tier + " " + .reason else "" end' "$GATES" 2>/dev/null)"
TIER="${MATCHED%% *}"
REASON="${MATCHED#* }"
[ -n "$TIER" ] || exit 0

case "$TIER" in
  operator-actioned)
    jq -n --arg r "$REASON" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",
      permissionDecisionReason:("OPERATOR-ACTIONED: a human performs this, not the agent.\n\nReason: " + $r + "\n\nApproval alone is not sufficient at this tier. Stop, and tell the owner exactly what needs running and why. Do not re-issue this command.")}}' ;;
  operator-approved)
    jq -n --arg r "$REASON" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"ask",
      permissionDecisionReason:("OPERATOR-APPROVED: this project gates this operation.\n\nReason: " + $r + "\n\nYou may perform it once the owner approves.")}}' ;;
esac
exit 0
