#!/usr/bin/env bash
# Opt-in once-per-native-session reminder. It never writes a semantic note itself.
set -uo pipefail
[[ -n "${AGENTOPS_SESSION_NOTES_ROOT:-}" && -n "${AGENTOPS_SESSION_NOTES_REPO_ROOT:-}" ]] || exit 0
hook="$(readlink -f -- "${BASH_SOURCE[0]}")" || exit 0
args=(stop-gate --root "$AGENTOPS_SESSION_NOTES_ROOT"
      --repo-root "$AGENTOPS_SESSION_NOTES_REPO_ROOT")
[[ -z "${AGENTOPS_SESSION_NOTES_STATE_ROOT:-}" ]] || args+=(--state-root "$AGENTOPS_SESSION_NOTES_STATE_ROOT")
python3 "${hook%/*}/../scripts/session_notes.py" "${args[@]}" || true
