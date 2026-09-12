#!/usr/bin/env bash
# PreToolUse wrapper for snip. snip's own hook answers permissionDecision
# "allow" for every command it matches, which would bypass the permission
# classifier for git push, kubectl delete, and anything else it filters.
# Keep the updatedInput rewrite, replace the decision with "defer" so the
# normal permission flow still runs. Fails open: on any error, print nothing.
set -o pipefail
SNIP="${SNIP_BIN:-/run/current-system/sw/bin/snip}"
[ -x "$SNIP" ] || exit 0
out="$("$SNIP" hook 2>/dev/null)" || exit 0
[ -n "$out" ] || exit 0
printf '%s' "$out" | jq -c '
  if .hookSpecificOutput.permissionDecision == "allow"
  then .hookSpecificOutput.permissionDecision = "defer"
     | .hookSpecificOutput.permissionDecisionReason = "snip rewrite; permission deferred to normal flow"
  else . end' 2>/dev/null || exit 0
