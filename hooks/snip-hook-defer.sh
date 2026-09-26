#!/usr/bin/env bash
# PreToolUse wrapper for snip. snip's own hook answers permissionDecision
# "allow" for every command it matches, which would bypass the permission
# classifier for git push, kubectl delete, and anything else it filters.
# Keep the updatedInput rewrite and drop the decision entirely: the docs say
# updatedInput applies regardless of the decision, and an explicit "defer"
# was observed to leave subagent Bash calls without a result (2026-09-12).
# Inside a harness-isolated worktree (<repo>/.claude/worktrees/<name>) skip the
# rewrite: Claude Code's worktree-isolation guard sees `snip run -- git ...` as
# git launched by an unknown program and refuses it, which blocked every git
# call of every isolated workflow agent (2026-09-26, 8 of 8 fixers).
# Fails open: on any error, print nothing.
set -o pipefail
SNIP="${SNIP_BIN:-/run/current-system/sw/bin/snip}"
[ -x "$SNIP" ] || exit 0
input="$(cat)"
cwd="$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null)"
case "$cwd" in */.claude/worktrees/*) exit 0 ;; esac
out="$(printf '%s' "$input" | "$SNIP" hook 2>/dev/null)" || exit 0
[ -n "$out" ] || exit 0
printf '%s' "$out" | jq -c '
  del(.hookSpecificOutput.permissionDecision)
  | del(.hookSpecificOutput.permissionDecisionReason)' 2>/dev/null || exit 0
