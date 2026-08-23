#!/usr/bin/env bash
# Claude Code SessionStart hook: surface actionable sprint health without mutation.
set -u

readonly WORKSPACE_ROOT="$(readlink -f /projects/dev 2>/dev/null || printf '%s' /projects/dev)"
readonly CHECK_TIMEOUT_SECONDS=6

input="$(cat 2>/dev/null || true)"

command -v jq >/dev/null 2>&1 || exit 0
command -v git >/dev/null 2>&1 || exit 0
command -v direnv >/dev/null 2>&1 || exit 0
command -v sprintctl >/dev/null 2>&1 || exit 0
command -v timeout >/dev/null 2>&1 || exit 0

cwd="$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null || true)"
[[ -n "$cwd" && -d "$cwd" ]] || exit 0

repo_root="$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null || true)"
[[ -n "$repo_root" ]] || exit 0
repo_root="$(readlink -f "$repo_root" 2>/dev/null || printf '%s' "$repo_root")"

case "$repo_root" in
  "$WORKSPACE_ROOT"/*) ;;
  *) exit 0 ;;
esac

[[ -f "$repo_root/.sprintctl/backend.json" ]] || exit 0

# `maintain check` is sprintctl's documented read-only maintenance path. Failures,
# including an unavailable environment or no active sprint, deliberately add no context.
report="$(
  cd "$repo_root" || exit 0
  timeout "${CHECK_TIMEOUT_SECONDS}s" direnv exec . sprintctl maintain check --json 2>/dev/null
)" || exit 0

summary="$(printf '%s' "$report" | jq -r '
  if (.sprint | type) != "object" then empty
  else
    ([.stale_items[]?] | length) as $stale
    | ([.track_health[]?.counts.blocked // 0] | add // 0) as $blocked
    | (.risk.active_items // 0) as $active
    | (.risk.days_remaining // null) as $days
    | (.risk.at_risk // false) as $at_risk
    | (.risk.overdue // false) as $overdue
    | if $stale > 0 or $blocked > 0 or $at_risk or $overdue then
        "Read-only sprint maintenance for \(.sprint.repo_id) / #\(.sprint.id) \(.sprint.name): stale_items=\($stale), blocked_items=\($blocked), active_items=\($active), days_remaining=\($days // "unbounded"), at_risk=\($at_risk), overdue=\($overdue). No state changed."
      else
        empty
      end
  end
' 2>/dev/null || true)"

[[ -n "$summary" ]] || exit 0

jq -nc --arg summary "$summary" \
  '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $summary}}'