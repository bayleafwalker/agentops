#!/usr/bin/env bash
# Claude Code SessionStart hook — if an unacknowledged handoff names this cwd,
# inject the successor prompt as additional context.
#
# This is the interactive half of the plan's launch step. `initialUserMessage`
# only applies to `claude -p`, so an interactive successor has no first message
# to carry the handoff; a SessionStart injection is the only seam. The
# background path (`claude --bg "$(agentops handoff prompt <file>)"`) does not
# need this and is unaffected: acking is still the successor's first action, and
# the ack guard, not this hook, is what prevents two live successors.
#
# Selection is deliberately narrow: successor.session_id must be null (an acked
# handoff belongs to someone else), one of state.repos[].path must be this cwd or
# an ancestor of it, no newer version of the same slug may exist, and it must be
# newer (created_at) than every acked handoff for this cwd. Newest created_at wins
# when several match, and the hook says so rather than picking silently.
# Registered globally in ~/.claude/settings.json so it fires from any directory.
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

MATCH=""; MATCH_AT=""; ACKED_AT=""
for f in "$DIR"/*.json; do
  [[ -r "$f" ]] || continue
  case "$f" in *.sprintctl-bundle.json) continue ;; esac
  # "<created_at> <acked|open>" when a state.repos path is this cwd or an ancestor of it.
  _row="$(jq -er --arg cwd "$CWD" '
    select([ .state.repos[]?.path
             | rtrimstr("/")
             | select(. as $p | $cwd == $p or ($cwd | startswith($p + "/")))
           ] | length > 0)
    | "\(.created_at // "") \(if .successor.session_id == null then "open" else "acked" end)"
  ' "$f" 2>/dev/null)" || continue
  _at="${_row% *}"
  if [[ "${_row##* }" == acked ]]; then
    [[ "$_at" > "$ACKED_AT" ]] && ACKED_AT="$_at"
    continue
  fi
  # A chain supersedes its older links: once a newer file of the same slug exists
  # (any date, any version), an older unacked one is stale, not an open handoff.
  _stem="${f##*/}"; _stem="${_stem%.json}"; _slug="${_stem#[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]-}"; _slug="${_slug%.v[0-9]*}"
  _head="$(printf '%s\n' "$DIR"/*-"$_slug".v*.json | sort -V | tail -n 1)"
  [[ "$_head" == "$f" ]] || continue
  # Newest by created_at.
  [[ -z "$MATCH" || "$_at" > "$MATCH_AT" ]] && { MATCH="$f"; MATCH_AT="$_at"; }
done

# A handoff for this directory that some successor already took is newer than
# every open one: those were abandoned, not waiting.
[[ -z "$MATCH" || "$MATCH_AT" > "$ACKED_AT" ]] || MATCH=""
[[ -n "$MATCH" ]] || exit 0

# `agentops` on PATH, else the CLI in this hook's own repository (hooks/../bin/agentops), so a host
# that never linked the CLI into PATH (devbox) still runs this hook instead of skipping it.
_hook_src="${BASH_SOURCE[0]}"
{ [[ -L "$_hook_src" ]] && command -v readlink >/dev/null 2>&1 &&
  _hook_src="$(readlink -f -- "$_hook_src" 2>/dev/null || printf '%s' "$_hook_src")"; } || true
AGENTOPS="$(command -v agentops 2>/dev/null || true)"
[[ -n "$AGENTOPS" || ! -x "${_hook_src%/*}/../bin/agentops" ]] || AGENTOPS="${_hook_src%/*}/../bin/agentops"
PROMPT=""
if [[ -n "$AGENTOPS" ]]; then
  PROMPT="$(timeout 15 "$AGENTOPS" handoff prompt "$MATCH" 2>/dev/null || true)"
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
