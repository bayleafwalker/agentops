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

# Metanarrative model status. The model is only worth having if it shows up in
# ordinary work, so this runs where the operator already looks. It is read-only,
# prints nothing when there are no records, and must never fail the session.
#
# The scope is the repository this hook already resolved -- from the payload `cwd`, through
# git, at the top of this file -- and not `basename "$PWD"`. Those are two different
# questions: $PWD is the hook *process's* directory, which is whatever the harness happened
# to leave it at. Pairing a scope derived one way with a store root derived another is the
# 2026-08-29 misrouting exactly, one tool over, and it had already happened: an empty
# `agentops/_artifacts/vuoro/model` on this workstation is the fingerprint of scope `vuoro`
# resolved against root `/projects/dev/agentops`.
META="$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")/../scripts/metanarrative.py"
model_status=""
if [[ -x "$META" ]]; then
  model_status="$(python3 "$META" --scope "$(basename "$repo_root")" status 2>/dev/null \
    | grep -vE '^\(no model records yet\)$' || true)"
fi

# One JSON object, and nothing after it. This block used to `printf` its lines *following*
# the object below, which makes the hook's whole stdout unparseable -- a SessionStart hook
# is read as JSON, so appending prose does not add a note beside the context, it discards
# the context along with the note. The oracle has been failing on exactly that since the
# block was added ("jq: parse error ... line 2"), which is the defect reporting itself.
# `if`, not `[[ … ]] && …`. This hook runs under `set -u` alone, so the `&&` form is safe
# today; it stops being safe the moment anyone adds `set -e`, and the branch it would break
# is the empty one -- a repository with no model records, which is the common case and the
# one the oracle never reaches, since its fixture always has claims.
context="$summary"
if [[ -n "$model_status" ]]; then
  context="$context"$'\n\n'"$model_status"
fi

jq -nc --arg context "$context" \
  '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $context}}'
