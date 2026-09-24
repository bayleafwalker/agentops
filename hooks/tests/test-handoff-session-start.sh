#!/usr/bin/env bash
# Gate for handoff-session-start.sh selection, found when the hook moved to the global
# settings on 2026-09-24: in /projects/dev/agentops it injected the superseded
# program-long-goal-handler.v1 although v2 was already acked, and from a subdirectory of a
# handoff repo it injected nothing at all.
#
#   REQ-040 a cwd below a handoff repo path matches (jq `$cwd | startswith(. + "/")` rebound `.`)
#   REQ-041 a sibling that only shares a string prefix does not match
#   REQ-042 the newest version of a slug wins, by version order (v10 after v9)
#   REQ-043 an older link of a chain is never injected once a newer link exists
#   REQ-044 an open handoff older than an acked one for the same cwd is abandoned, not waiting
#   REQ-045 an open handoff newer than every acked one is still injected
set -uo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
hook="$(cd -- "$here/.." && pwd -P)/handoff-session-start.sh"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
assert_eq() { [[ "$2" == "$3" ]] || fail "$1: expected '$3', got '$2'"; }

repo=/projects/dev/agentops
# mk <file> <session_id or ""> <created_at>
mk() {
  jq -n --arg s "$2" --arg t "$3" --arg r "$repo" \
    '{created_at:$t, successor:{session_id:(if $s == "" then null else $s end)}, state:{repos:[{path:$r}]}}' \
    >"$tmp/$1"
}
# Prints the injected handoff's file name, or nothing.
pick() {
  printf '{"cwd":"%s"}' "$1" | AGENTOPS_HANDOFF_DIR="$tmp" "$hook" |
    grep -o '[0-9]\{4\}-[0-9-]*[a-z-]*\.v[0-9]*\.json' | head -n 1 | sed 's#.*/##'
}

mk 2026-09-24-chain.v9.json "" 2026-09-24T01:00:00Z
mk 2026-09-24-chain.v10.json "" 2026-09-24T02:00:00Z
assert_eq REQ-040 "$(pick "$repo/hooks")" 2026-09-24-chain.v10.json
assert_eq REQ-041 "$(pick "${repo}2")" ""
assert_eq REQ-042 "$(pick "$repo")" 2026-09-24-chain.v10.json

mk 2026-09-24-chain.v10.json acked 2026-09-24T02:00:00Z
assert_eq REQ-043 "$(pick "$repo")" ""

mk 2026-09-23-other.v1.json "" 2026-09-23T12:00:00Z
assert_eq REQ-044 "$(pick "$repo")" ""

mk 2026-09-24-other.v1.json "" 2026-09-24T03:00:00Z
assert_eq REQ-045 "$(pick "$repo")" 2026-09-24-other.v1.json

printf 'ok: handoff-session-start selection (REQ-040..045)\n'
