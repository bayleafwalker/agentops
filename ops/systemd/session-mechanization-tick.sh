#!/usr/bin/env bash
# Runs one reconcile-tick or scribe-tick pass across every configured
# project. Called by the session-mechanization-{reconcile,scribe}.service
# units; not meant to be invoked with an unset MODE.
#
# Projects are configured in session-mechanization-projects.conf as
# whitespace-separated "project:root" pairs, e.g.:
#   agentops:/projects/dev/_artifacts/agentops
set -euo pipefail

MODE="${1:?usage: session-mechanization-tick.sh reconcile-tick|scribe-tick}"
AGENTOPS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONF="${SESSION_MECHANIZATION_PROJECTS_CONF:-$AGENTOPS_ROOT/ops/systemd/session-mechanization-projects.conf}"

if [[ ! -r "$CONF" ]]; then
  echo "session-mechanization-tick: no readable project config at $CONF, nothing to do" >&2
  exit 0
fi

status=0
while read -r pair; do
  [[ -z "$pair" || "$pair" == \#* ]] && continue
  project="${pair%%:*}"
  root="${pair#*:}"
  python3 "$AGENTOPS_ROOT/templates/dispatch/scripts/session_mechanization_trigger.py" \
    "$MODE" --project "$project" --root "$root" || status=1
done < "$CONF"

exit "$status"
