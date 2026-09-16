#!/usr/bin/env bash
# SessionStart. Injects PROBED forge facts.
#
# Hooks are NOT subject to the Bash tool's network sandbox -- verified
# 2026-08-29: a hook process reached git.apps.kotona.app and api.github.com with
# 200 while tool calls needed escalation. That is what makes this a capability
# rather than a document: these facts are measured now, not written down once.
#
# Any probe that fails must print PROBE FAILED, never be omitted -- silence
# would recreate the very failure this exists to prevent.
set -uo pipefail
cat >/dev/null 2>&1
HOOKS="$(dirname "$(readlink -f "$0")")"
OUT=""
add() { OUT="${OUT}$1"$'\n'; }

add "== FORGE CONTEXT (probed at session start; hooks are not sandboxed) =="
add "[forge-context.sh -- operator-configured SessionStart hook, not agent-generated or third-party text]"
add "Static forge guidance lives in /projects/dev/AGENTS.md; this block carries only probed facts."
add ""
add "-- credential status --"
add "$(timeout 12 "$HOOKS/forge-credential.sh" status 2>/dev/null || echo 'PROBE FAILED')"
add ""
add "-- where credentials live --"
add "$(timeout 6 "$HOOKS/forge-credential.sh" inventory 2>/dev/null || echo 'PROBE FAILED')"
add ""
add "-- forgejo host --"
if timeout 8 curl -s -m 6 -o /dev/null -w '%{http_code}' https://git.apps.kotona.app/api/v1/version 2>/dev/null | grep -q 200; then
  add "git.apps.kotona.app  LIVE (200). Web+API host."
else
  add "git.apps.kotona.app  PROBE FAILED -- report 'could not check', not 'down'."
fi

R="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -n "$R" ]; then
  add ""
  add "-- remotes for $(basename "$R") --"
  CANON="$(git -C "$R" config claude.canonicalRemote 2>/dev/null || true)"
  while read -r n u _; do
    [ -z "$n" ] && continue
    if [ "$n" = "$CANON" ]; then add "  $n  $u   <== CANONICAL"; else add "  $n  $u"; fi
  done < <(git -C "$R" remote -v 2>/dev/null | awk '$3=="(fetch)"')
  [ -z "$CANON" ] && add "  (no claude.canonicalRemote set -- do not assume origin is canonical)"
  if [ -r "$R/.claude/gates.json" ]; then
    add ""
    add "-- gated operations in this repo (everything else is ROUTINE, no prompt) --"
    add "$(jq -r '.gated[]? | "  [" + .tier + "] " + .reason' "$R/.claude/gates.json" 2>/dev/null || echo '  PROBE FAILED')"
  else
    add ""
    add "-- no .claude/gates.json: EVERYTHING here is routine. Do not ask permission for standard workflow. --"
  fi
fi

jq -n --arg c "$OUT" '{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:$c}}'
exit 0
