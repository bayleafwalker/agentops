#!/usr/bin/env bash
# Claude Code SessionStart hook — if an unacknowledged handoff names this cwd,
# inject the successor prompt as additional context.
#
# This is the interactive half of the plan's launch step. `initialUserMessage`
# only applies to `claude -p`, so an interactive successor has no first message
# to carry the handoff; a SessionStart injection is the only seam. The
# background path (`claude --bg -p "$(agentops handoff prompt <file>)"`) does not
# need this and is unaffected: acking is still the successor's first action, and
# the ack guard, not this hook, is what prevents two live successors.
#
# Selection is deliberately narrow: successor.session_id must be null (an acked
# handoff belongs to someone else) and one of state.repos[].path must be this
# cwd or an ancestor of it. Newest handoff_id wins when several match, and the
# hook says so rather than picking silently.
#
# Env:
#   AGENTOPS_HANDOFF_DIR  where handoffs live; default agentops/docs/dispatch/handoffs
set -uo pipefail

EVENT="$(cat)"
command -v jq >/dev/null 2>&1 || exit 0

CWD="$(printf '%s' "$EVENT" | jq -r '.cwd // ""')"
[[ -n "$CWD" ]] || CWD="$PWD"
CWD="${CWD%/}"

DIR="${AGENTOPS_HANDOFF_DIR:-/projects/dev/agentops/docs/dispatch/handoffs}"
[[ -d "$DIR" ]] || exit 0

MATCH=""
for f in "$DIR"/*.json; do
  [[ -r "$f" ]] || continue
  case "$f" in *.sprintctl-bundle.json) continue ;; esac
  jq -e --arg cwd "$CWD" '
    (.successor.session_id == null)
    and ([ .state.repos[]?.path
           | rtrimstr("/")
           | select(. == $cwd or ($cwd | startswith(. + "/")))
         ] | length > 0)
  ' "$f" >/dev/null 2>&1 || continue
  # Newest by filename: the stem is <date>-<slug>.v<N>, so lexical order is
  # chronological within a day and version order within a slug.
  [[ -z "$MATCH" || "$f" > "$MATCH" ]] && MATCH="$f"
done

[[ -n "$MATCH" ]] || exit 0

PROMPT=""
if command -v agentops >/dev/null 2>&1; then
  PROMPT="$(timeout 15 agentops handoff prompt "$MATCH" 2>/dev/null || true)"
fi
if [[ -z "$PROMPT" ]]; then
  SCRIPT="/projects/dev/agentops/templates/dispatch/scripts/handoff.py"
  for py in python3 /usr/bin/python3 "$HOME/.local/bin/python3"; do
    if command -v "$py" >/dev/null 2>&1 && [[ -r "$SCRIPT" ]]; then
      PROMPT="$(timeout 15 "$py" "$SCRIPT" prompt "$MATCH" 2>/dev/null || true)"
      break
    fi
  done
fi
if [[ -z "$PROMPT" ]]; then
  printf '== HANDOFF WAITING ==\nAn unacknowledged handoff names this directory: %s\nIt could not be rendered here (no agentops handoff on PATH). Read the file.\n' "$MATCH"
  exit 0
fi

printf '== UNACKNOWLEDGED HANDOFF FOR THIS DIRECTORY ==\n'
printf 'File: %s\n' "$MATCH"
printf 'You are the successor unless the operator says otherwise. Ack before editing.\n\n'
printf '%s\n' "$PROMPT"
exit 0
