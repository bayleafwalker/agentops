#!/usr/bin/env bash
# Claude Code PostToolUse Skill hook: record loaded skill digests in the session binding.
# Resolution and event filtering belong to scripts/session_binding.py.
set -uo pipefail

# The script is reached through the `agentops` CLI (`agentops session-binding` resolves to
# scripts/session_binding.py and execs it with this hook's stdio), not by a path relative to
# this file. No CLI available: skip recording silently and never fail the tool.
# `agentops` on PATH, else the CLI in this hook's own repository (hooks/../bin/agentops), so a host
# that never linked the CLI into PATH (devbox) still runs this hook instead of skipping it.
_hook_src="${BASH_SOURCE[0]}"
{ [[ -L "$_hook_src" ]] && command -v readlink >/dev/null 2>&1 &&
  _hook_src="$(readlink -f -- "$_hook_src" 2>/dev/null || printf '%s' "$_hook_src")"; } || true
AGENTOPS="$(command -v agentops 2>/dev/null || true)"
[[ -n "$AGENTOPS" || ! -x "${_hook_src%/*}/../bin/agentops" ]] || AGENTOPS="${_hook_src%/*}/../bin/agentops"
[[ -n "$AGENTOPS" ]] || exit 0

# Recording is observational. Keep stdin intact and never fail the tool invocation.
"$AGENTOPS" session-binding --record-skill || true
exit 0
