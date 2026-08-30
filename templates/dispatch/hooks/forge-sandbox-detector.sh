#!/usr/bin/env bash
# PostToolUse/Bash. THE PRIMARY DEFENCE against silent sandbox failures.
#
# Unlike a PreToolUse deny (whose support is unverified here), PostToolUse
# hooks are known to run. This fires after a network command that was NOT
# sandbox-escalated and warns loudly, so an empty result is never mistaken for
# a fact. It cannot prevent the call; it prevents the wrong conclusion.
set -uo pipefail
EVENT="$(cat 2>/dev/null || true)"
command -v jq >/dev/null 2>&1 || exit 0

CMD="$(printf '%s' "$EVENT" | jq -r '.tool_input.command // ""' 2>/dev/null)"
ESC="$(printf '%s' "$EVENT" | jq -r '.tool_input.dangerouslyDisableSandbox // false' 2>/dev/null)"
[ "$ESC" = "true" ] && exit 0

MATCH="$(printf '%s' "$CMD" | sed -E 's/"[^"]*"//g; s/'\''[^'\'']*'\''//g')"
NET='(^|[[:space:]]|[|&;]|/)(gh|fj|curl|wget|hcloud)([[:space:]]|$)'
GITNET='(^|[[:space:]]|[|&;])git([[:space:]]+-[^[:space:]]+)*[[:space:]]+(push|fetch|pull|clone|ls-remote)([[:space:]]|$)'
[[ "$MATCH" =~ $NET || "$MATCH" =~ $GITNET ]] || exit 0

jq -n '{hookSpecificOutput:{hookEventName:"PostToolUse",
  additionalContext:"SANDBOXED NETWORK CALL -- RESULT IS NOT EVIDENCE.\n\nThe command just run reaches the network but was issued WITHOUT dangerouslyDisableSandbox: true. In the tool sandbox such calls return exit 0 with empty output and no error. Whatever you just saw -- especially an empty result, a 000 status, or a DNS failure -- describes the sandbox, not the world.\n\nRe-run it now with dangerouslyDisableSandbox: true before drawing any conclusion. Do NOT report absence, an outage, or a missing credential on the strength of that output, and do NOT ask the owner about it. Sandbox escalation is yours to perform autonomously."}}'
exit 0
