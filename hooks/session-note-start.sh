#!/usr/bin/env bash
# Opt-in semantic-note injection. This is distinct from handoff-session-start.sh.
# Install only where the context builder does not already supply these notes.
# Both roots must be explicitly configured for the participating checkout.
set -uo pipefail
[[ -n "${AGENTOPS_SESSION_NOTES_ROOT:-}" && -n "${AGENTOPS_SESSION_NOTES_REPO_ROOT:-}" ]] || exit 0
hook="$(readlink -f -- "${BASH_SOURCE[0]}")" || exit 0
args=(latest --hook --kind handover --root "$AGENTOPS_SESSION_NOTES_ROOT"
      --repo-root "$AGENTOPS_SESSION_NOTES_REPO_ROOT")
[[ -z "${AGENTOPS_SESSION_NOTES_STATE_ROOT:-}" ]] || args+=(--state-root "$AGENTOPS_SESSION_NOTES_STATE_ROOT")
python3 "${hook%/*}/../scripts/session_notes.py" "${args[@]}" || true
