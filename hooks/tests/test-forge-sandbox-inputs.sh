#!/usr/bin/env bash
# Both harness input formats preserve sandbox detection and recognize escalation.
set -euo pipefail
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
for hook in forge-sandbox-guard.sh forge-sandbox-detector.sh; do
  for key in command cmd; do
    event="$(jq -cn --arg key "$key" '{tool_input:{($key):"git fetch origin",sandbox_permissions:"use_default"}}')"
    out="$(printf '%s' "$event" | "$here/$hook")"
    [[ -n "$out" ]] || { printf 'FAIL: %s missed sandboxed %s\n' "$hook" "$key"; exit 1; }
    if [[ "$hook" == forge-sandbox-guard.sh ]]; then
      [[ "$(jq -r '.hookSpecificOutput.permissionDecision' <<<"$out")" == deny ]]
    fi
    for escalation in '{"dangerouslyDisableSandbox":true}' '{"sandbox_permissions":"require_escalated"}'; do
      event="$(jq -cn --arg key "$key" --argjson escalation "$escalation" '{tool_input:({($key):"git fetch origin"} + $escalation)}')"
      out="$(printf '%s' "$event" | "$here/$hook")"
      [[ -z "$out" ]] || { printf 'FAIL: %s rejected escalated %s\n' "$hook" "$key"; exit 1; }
    done
  done
  event='{"turn_id":"codex-turn","tool_input":{"command":"git fetch origin"}}'
  out="$(printf '%s' "$event" | "$here/$hook")"
  [[ "$(jq -r '.hookSpecificOutput.additionalContext' <<<"$out")" == *"could not determine"* ]]
  [[ "$(jq -r '.hookSpecificOutput | has("permissionDecision")' <<<"$out")" == false ]]
  event='{"turn_id":"codex-turn","tool_input":{"command":"git fetch origin","sandbox_permissions":"use_default"}}'
  out="$(printf '%s' "$event" | "$here/$hook")"
  [[ -n "$out" ]]
  if [[ "$hook" == forge-sandbox-guard.sh ]]; then
    [[ "$(jq -r '.hookSpecificOutput.permissionDecision' <<<"$out")" == deny ]]
  fi
done
printf 'forge sandbox input tests passed (16 cases)\n'
