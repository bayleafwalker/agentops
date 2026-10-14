#!/usr/bin/env bash
# Claude Code SessionStart hook: register this workstation's Claude Code instance in the
# Vuoro agent directory (once per host). Fail-open: never blocks a session, <= 3 s.
# NOT wired into settings.json by this change; see scripts/claude_agent_hooks.py.
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
timeout 3 python3 "$root/scripts/claude_agent_hooks.py" session-start >/dev/null 2>&1 || true
exit 0
