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
# This wrapper therefore does one thing the Python cannot: find an interpreter from a
# hook shell's PATH, which inherits neither a login shell nor direnv. With no python3 on
# it the session starts unbound, and says so on stderr rather than silently.
set -uo pipefail

_hook_src="${BASH_SOURCE[0]}"
{ [[ -L "$_hook_src" ]] && command -v readlink >/dev/null 2>&1 &&
  _hook_src="$(readlink -f -- "$_hook_src" 2>/dev/null || printf '%s' "$_hook_src")"; } || true
SCRIPT="${_hook_src%/hooks/*}/scripts/session_binding.py"

PY=""
for candidate in python3 /usr/bin/python3 "$HOME/.local/bin/python3"; do
  if command -v "$candidate" >/dev/null 2>&1; then PY="$candidate"; break; fi
done
if [[ -z "$PY" || ! -r "$SCRIPT" ]]; then
  printf 'session-binding: no python3 or missing %s; session starts unbound\n' \
    "$SCRIPT" >&2
  exit 0
fi

# A contradiction is a real finding and belongs on stderr, but a hook that fails the
# session start converts a diagnostic into an outage. The record is written, the reason
# is said, and the session proceeds.
"$PY" "$SCRIPT" || true
exit 0
