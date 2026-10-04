#!/usr/bin/env bash
# Shared event-side audit routing for Stop and SubagentStop (agentops#2547/#2591).
# Sourced only. Select another real git worktree only when both audit pins are
# unset or point into the launch tree. Explicit external overrides and invalid
# event paths preserve launch-directory publication. Never changes the caller.

_auditctl_git_top() {
  local p="$1" strict="${2:-}"
  [[ "$p" == /* ]] || return 1  # "${p%/*}" never shortens a relative path: no loop
  while :; do
    if [[ -n "$strict" ]]; then
      [[ -f "$p/.git" || -f "$p/.git/HEAD" ]] && { printf '%s' "$p"; return 0; }
    else
      [[ -e "$p/.git" ]] && { printf '%s' "$p"; return 0; }
    fi
    [[ "$p" == "/" || -z "$p" ]] && return 1
    p="${p%/*}"; [[ -n "$p" ]] || p="/"
  done
}
# A pin is dropped only when it is unset or describes the launch work tree -- what a
# direnv export there looks like. A pin pointing anywhere else is a deliberate override
# (an operator, a test fixture) and is honoured as before, cwd included. The match is a
# plain PATH PREFIX on the pin string against the launch tree's physical and logical
# roots -- no canonicalisation of the pin itself, so a pin spelled through a different
# symlink than both roots counts as "elsewhere" and is kept (the safe direction).
_auditctl_pin_is_launch() {
  local v="$1" t
  [[ -z "$v" ]] && return 0
  for t in "$_proc_top" "$_proc_top_l"; do
    [[ -n "$t" && ( "$v" == "$t" || "$v" == "$t"/* ) ]] && return 0
  done
  return 1
}
auditctl_event_cwd() {
  local event="$1" _event_cwd _event_top _proc_top _proc_top_l
  _event_cwd="$(printf '%s' "$event" | jq -r '.cwd // ""' 2>/dev/null || true)"
  if [[ "$_event_cwd" == /* && -d "$_event_cwd" ]]; then
    # Physical paths on both sides, so a symlinked mount cannot make one tree look like two.
    _event_cwd="$(cd -- "$_event_cwd" 2>/dev/null && pwd -P)" || _event_cwd=""
  else
    _event_cwd=""
  fi
  if [[ -n "$_event_cwd" ]]; then
    _event_top="$(_auditctl_git_top "$_event_cwd" strict)" || _event_top=""
    _proc_top="$(_auditctl_git_top "$(pwd -P 2>/dev/null || printf '%s' "$PWD")")" || _proc_top=""
    _proc_top_l="$(_auditctl_git_top "$PWD")" || _proc_top_l=""
    if [[ -n "$_event_top" && -n "$_proc_top" && "$_event_top" != "$_proc_top" ]] &&
       _auditctl_pin_is_launch "${AUDITCTL_DB-}" && _auditctl_pin_is_launch "${AUDITCTL_ARTIFACTS_ROOT-}"; then
      printf '%s' "$_event_cwd"
    fi
  fi
  return 0
}
