#!/usr/bin/env bash
# Claude Code SessionStart hook -- resolve the session-scoped half of the
# resolved-context invariant once, and never again for this session.
#
# The work is in scripts/session_binding.py, not here, and deliberately so. The binding
# has to resolve this host's environment record, and `resolve_environment_record` already
# does that -- hostname normalization, `.example` exclusion, ambiguity refusal and all.
# Re-deriving those rules in shell is the exact defect docs/contracts/session-resolved-
# context.md exists to end: "two independent resolutions that happen to agree are not one
# resolution", and agreement by imitation breaks whenever either side changes.
#
# This wrapper therefore only hands off to the `agentops` CLI, which finds the interpreter.
set -uo pipefail

# The script is reached through the `agentops` CLI (`agentops session-binding` resolves to
# scripts/session_binding.py and execs it with this hook's stdio), not by a path relative to
# this file. No CLI on PATH: the session starts unbound, silently, and never fails.
# `agentops` on PATH, else the CLI in this hook's own repository (hooks/../bin/agentops), so a host
# that never linked the CLI into PATH (devbox) still runs this hook instead of skipping it.
_hook_src="${BASH_SOURCE[0]}"
{ [[ -L "$_hook_src" ]] && command -v readlink >/dev/null 2>&1 &&
  _hook_src="$(readlink -f -- "$_hook_src" 2>/dev/null || printf '%s' "$_hook_src")"; } || true
AGENTOPS="$(command -v agentops 2>/dev/null || true)"
[[ -n "$AGENTOPS" || ! -x "${_hook_src%/*}/../bin/agentops" ]] || AGENTOPS="${_hook_src%/*}/../bin/agentops"
[[ -n "$AGENTOPS" ]] || exit 0

# A contradiction is a real finding and belongs on stderr, but a hook that fails the
# session start converts a diagnostic into an outage. The record is written, the reason
# is said, and the session proceeds.
"$AGENTOPS" session-binding || true
exit 0
