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
command -v agentops >/dev/null 2>&1 || exit 0

# A contradiction is a real finding and belongs on stderr, but a hook that fails the
# session start converts a diagnostic into an outage. The record is written, the reason
# is said, and the session proceeds.
agentops session-binding || true
exit 0
