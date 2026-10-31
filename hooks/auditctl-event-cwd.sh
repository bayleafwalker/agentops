#!/usr/bin/env bash
# Shared event-side audit routing for Stop and SubagentStop (agentops#2547/#2591).
# Sourced only. Select a real Git worktree or initialized workspace ledger when both audit pins are
# unset or point into the launch tree (the hook's cwd tree, or the direnv tree in
# DIRENV_DIR when the session has since moved). Explicit external overrides and invalid
# event paths preserve launch-directory publication. Never changes the caller.

# Event paths require a .git file, .git/HEAD, or an initialized SQLite index
# with an explicit .auditctl-id. The identity marker opts a non-Git workspace
# into capture; an incidental ancestor index must not acquire its descendants.
# An empty workspace-level .git directory, bare .auditctl directory, or empty
# index file is insufficient. A workspace with a real index already has its
# own capture identity; routing it does not create a scope or a Git repository.
# Prefer builtins because hooks can run with a restricted PATH.
_auditctl_initialized_index() {
  local magic="" scope=""
  [[ -f "$1/.auditctl/auditctl.db" && -f "$1/.auditctl-id" ]] || return 1
  IFS= read -r scope < "$1/.auditctl-id" || [[ -n "$scope" ]] || return 1
  [[ "$scope" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ ]] || return 1
  IFS= LC_ALL=C read -r -N 15 magic < "$1/.auditctl/auditctl.db" || return 1
  [[ "$magic" == "SQLite format 3" ]]
}
_auditctl_git_top() {
  local p="$1" strict="${2:-}"
  [[ "$p" == /* ]] || return 1  # "${p%/*}" never shortens a relative path: no loop
  while :; do
    _auditctl_initialized_index "$p" && { printf '%s' "$p"; return 0; }
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
  shift
  [[ -z "$v" ]] && return 0
  for t in "$@"; do
    [[ -n "$t" && ( "$v" == "$t" || "$v" == "$t"/* ) ]] && return 0
  done
  return 1
}
auditctl_event_cwd() {
  local event="$1" _event_cwd _event_top _proc_top _proc_top_l _dir _dir_top _workspace
  _event_cwd="$(printf '%s' "$event" | jq -r '.cwd // ""' 2>/dev/null || true)"
  if [[ "$_event_cwd" == /* && -d "$_event_cwd" ]]; then
    # Physical paths on both sides, so a symlinked mount cannot make one tree look like two.
    _event_cwd="$(cd -- "$_event_cwd" 2>/dev/null && pwd -P)" || _event_cwd=""
  else
    _event_cwd=""
  fi
  if [[ -n "$_event_cwd" ]]; then
    _event_top="$(_auditctl_git_top "$_event_cwd" strict)" || _event_top=""
    _workspace=""
    if [[ -n "$_event_top" && ! -f "$_event_top/.git" && ! -f "$_event_top/.git/HEAD" ]]; then
      _workspace=1
    fi
    _proc_top="$(_auditctl_git_top "$(pwd -P 2>/dev/null || printf '%s' "$PWD")")" || _proc_top=""
    _proc_top_l="$(_auditctl_git_top "$PWD")" || _proc_top_l=""
    # The harness can run the hook in the session's CURRENT directory while the env still
    # carries the direnv export of the tree the session was launched in: DIRENV_DIR
    # ("-<dir>") names that tree. Count it as a launch tree too, so a session launched in
    # agentops that works in sprintctl does not file sprintctl's events into agentops.
    _dir="${DIRENV_DIR-}"; _dir="${_dir#-}"; _dir_top=""
    [[ "$_dir" == /* ]] && { _dir_top="$(_auditctl_git_top "$_dir")" || _dir_top=""; }
    # Workspace sessions can inherit a nested checkout's pins even when
    # the hook already runs in the event directory and DIRENV_DIR is absent.
    if [[ -n "$_event_top" && -n "$_proc_top" ]] &&
       [[ -n "$_workspace" || "$_event_top" != "$_proc_top" || ( -n "$_dir_top" && "$_event_top" != "$_dir_top" ) ]] &&
       _auditctl_pin_is_launch "${AUDITCTL_DB-}" "$_proc_top" "$_proc_top_l" "$_dir_top" "$_dir" &&
       _auditctl_pin_is_launch "${AUDITCTL_ARTIFACTS_ROOT-}" "$_proc_top" "$_proc_top_l" "$_dir_top" "$_dir"; then
      printf '%s' "$_event_cwd"
    fi
  fi
  return 0
}
