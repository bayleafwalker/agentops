#!/usr/bin/env bash
# PreToolUse wrapper for snip. snip's own hook answers permissionDecision
# "allow" for every command it matches, which would bypass the permission
# classifier for git push, kubectl delete, and anything else it filters.
# Keep the updatedInput rewrite and drop the decision entirely: the docs say
# updatedInput applies regardless of the decision, and an explicit "defer"
# was observed to leave subagent Bash calls without a result (2026-09-12).
# Fails open: on any error, print nothing.
set -o pipefail
SNIP="${SNIP_BIN:-/run/current-system/sw/bin/snip}"
[ -x "$SNIP" ] || exit 0
out="$("$SNIP" hook 2>/dev/null)" || exit 0
[ -n "$out" ] || exit 0
printf '%s' "$out" | jq -c '
  del(.hookSpecificOutput.permissionDecision)
  | del(.hookSpecificOutput.permissionDecisionReason)' 2>/dev/null || exit 0
