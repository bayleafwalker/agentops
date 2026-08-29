#!/usr/bin/env bash
# PostToolUse/Bash. After a push, verifies the work reached the CANONICAL remote.
#
# Catches the half-landed commit: a push to a replica succeeds, the canonical
# remote rejects it (protected branch), and nothing says so. Canonical comes from
# `git config claude.canonicalRemote`, else is inferred from .forgejo/workflows/.
set -uo pipefail
EVENT="$(cat 2>/dev/null || true)"
command -v jq >/dev/null 2>&1 || exit 0
CMD="$(printf '%s' "$EVENT" | jq -r '.tool_input.command // ""' 2>/dev/null)"
CWD="$(printf '%s' "$EVENT" | jq -r '.cwd // ""' 2>/dev/null)"
printf '%s' "$CMD" | grep -qE '(^|[ \t]|[|&;])git([ \t]+-[^ \t]+)*[ \t]+push([ \t]|$)' || exit 0

R="$(git -C "${CWD:-.}" rev-parse --show-toplevel 2>/dev/null)" || exit 0
CANON="$(git -C "$R" config claude.canonicalRemote 2>/dev/null || true)"
if [ -z "$CANON" ] && [ -d "$R/.forgejo/workflows" ]; then
  CANON="$(git -C "$R" remote -v 2>/dev/null | awk '/kotona\.app/ {print $1; exit}')"
fi
[ -n "$CANON" ] || exit 0
git -C "$R" remote get-url "$CANON" >/dev/null 2>&1 || exit 0

BR="$(git -C "$R" rev-parse --abbrev-ref HEAD 2>/dev/null)"
LOCAL="$(git -C "$R" rev-parse HEAD 2>/dev/null)"
REMOTE="$(git -C "$R" ls-remote "$CANON" "refs/heads/$BR" 2>/dev/null | awk '{print $1}')"
[ "$LOCAL" = "$REMOTE" ] && exit 0

jq -n --arg c "$CANON" --arg b "$BR" --arg l "${LOCAL:0:8}" --arg r "${REMOTE:0:8}" \
  '{hookSpecificOutput:{hookEventName:"PostToolUse",
    additionalContext:("WORK IS NOT LANDED ON THE CANONICAL REMOTE.\n\nAfter that push, local " + $b + " is at " + $l + " but canonical remote " + $c + " has " + (if $r == "" then "no such branch" else $r end) + ".\n\nA push that succeeded to a replica is not landed work. If the canonical remote rejected a protected branch, land it the documented way -- for a fast-forward-only branch, open a PR and merge via the REST API with Do=fast-forward-only. Do not report this work as done until the canonical remote carries it.")}}'
exit 0
