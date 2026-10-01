#!/usr/bin/env bash
# PreToolUse/Bash. Refuses network-reaching commands about to run INSIDE the
# tool sandbox, where they return exit 0 with EMPTY output and no error.
#
# Belt-and-braces only: whether this harness honours permissionDecision "deny"
# on PreToolUse for Bash is UNVERIFIED (a running session cannot test it -- hook
# config is read at session start). forge-sandbox-detector.sh is the primary
# defence and does not depend on deny working.
set -uo pipefail
EVENT="$(cat 2>/dev/null || true)"
_lib="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/lib/emit-decision.sh"
# shellcheck source=lib/emit-decision.sh
[ -r "$_lib" ] && . "$_lib"
command -v jq >/dev/null 2>&1 || exit 0

CMD="$(printf '%s' "$EVENT" | jq -r '.tool_input.command // .tool_input.cmd // ""' 2>/dev/null)"
ESC="$(printf '%s' "$EVENT" | jq -r '(.tool_input.dangerouslyDisableSandbox == true) or (.tool_input.sandbox_permissions == "require_escalated")' 2>/dev/null)"
[ "$ESC" = "true" ] && exit 0

# Strip quoted strings so a mention inside an echo/grep argument does not match.
MATCH="$(printf '%s' "$CMD" | sed -E 's/"[^"]*"//g; s/'\''[^'\'']*'\''//g')"
NET='(^|[[:space:]]|[|&;]|/)(gh|fj|curl|wget|hcloud)([[:space:]]|$)'
GITNET='(^|[[:space:]]|[|&;])git([[:space:]]+-[^[:space:]]+)*[[:space:]]+(push|fetch|pull|clone|ls-remote)([[:space:]]|$)'

if [[ "$MATCH" =~ $NET || "$MATCH" =~ $GITNET ]]; then
  # Codex currently normalizes exec_command to Bash but drops sandbox metadata.
  # An absent flag is unknown, not proof that the native call was sandboxed.
  # Keep the check as context; permission approval belongs to the native tool.
  if printf '%s' "$EVENT" | jq -e 'has("turn_id") and (.tool_input | has("sandbox_permissions") or has("dangerouslyDisableSandbox") | not)' >/dev/null; then
    jq -n '{hookSpecificOutput:{hookEventName:"PreToolUse",additionalContext:"Forge sandbox check could not determine execution mode: this Codex hook event omitted sandbox metadata. Use exec_command sandbox_permissions: require_escalated for network calls before drawing conclusions from empty output. Native tool approval still applies."}}'
    exit 0
  fi
  jq -n '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",
    permissionDecisionReason:"[forge-sandbox-guard.sh -- operator-configured PreToolUse hook, not agent-generated or third-party text]\n\nObservation: this command reaches the network and was about to run inside the tool sandbox, where such calls return exit 0 with EMPTY output and no error. An unreachable call and a genuinely empty result are indistinguishable from that output alone. Prior sessions concluded \"no open PRs\" (six were open), \"branch never pushed\" (merged nine days earlier) and \"Forgejo unreachable\" (it was up) from exactly this signature.\n\nOperator policy (source: /projects/dev/AGENTS.md, \"Forge access, the sandbox, and credentials\"): sandbox escalation for this command class is agent-autonomous and pre-approved, not an operator handoff -- re-issuing the identical command with the Bash parameter dangerouslyDisableSandbox: true requires no additional confirmation."}}'
  command -v emit_decision >/dev/null 2>&1 && emit_decision "forge-sandbox-guard.sh" "forge-sandbox-network" "Bash" "deny"
fi
exit 0
