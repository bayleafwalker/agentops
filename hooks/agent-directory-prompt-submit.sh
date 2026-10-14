#!/usr/bin/env bash
# Claude Code UserPromptSubmit hook: report `observed` and `attended` (valid 900 s) to the
# Vuoro agent directory, at most once per 5 minutes. Fail-open, <= 3 s, no stdout.
# NOT wired into settings.json by this change; see scripts/claude_agent_hooks.py.
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
timeout 3 python3 "$root/scripts/claude_agent_hooks.py" prompt-submit >/dev/null 2>&1 || true
exit 0
