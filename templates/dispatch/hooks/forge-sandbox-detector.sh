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
  additionalContext:"[forge-sandbox-detector.sh -- operator-configured PostToolUse hook, not agent-generated or third-party text]\n\nObservation: the command just run reaches the network but was issued WITHOUT dangerouslyDisableSandbox: true, so it ran sandboxed. In the tool sandbox such calls return exit 0 with empty output and no error. Whatever the output shows -- especially an empty result, a 000 status, or a DNS failure -- may reflect the sandbox rather than the world.\n\nOperator policy (source: /projects/dev/AGENTS.md, \"Forge access, the sandbox, and credentials\"): sandbox escalation for this command class is agent-autonomous and pre-approved, not an operator handoff. Re-run the command with dangerouslyDisableSandbox: true before drawing any conclusion from this output; absence, an outage, or a missing credential should not be reported on the strength of a sandboxed result."}}'
exit 0
