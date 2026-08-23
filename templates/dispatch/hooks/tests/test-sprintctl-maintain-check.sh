#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# The hook set is versioned here (agentops/templates/dispatch/hooks) and symlinked into
# /projects/dev/.claude/hooks; the test exercises the versioned copy next to it.
hooks_root="$(cd -- "$script_dir/.." && pwd -P)"
hook_path="$hooks_root/sprintctl-maintain-check.sh"
# The hook only reports for repos under /projects/dev, so the fixture root must live there.
temporary_root="$(mktemp -d /projects/dev/.claude/sprintctl-hook-test.XXXXXX)"
mock_bin="$temporary_root/mock-bin"
call_log="$temporary_root/sprintctl-calls.log"

cleanup() {
  rm -rf -- "$temporary_root"
}
trap cleanup EXIT

[[ -x "$hook_path" ]] || {
  printf 'hook is not executable: %s\n' "$hook_path" >&2
  exit 1
}

mkdir -p "$temporary_root/.sprintctl" "$mock_bin"
printf '{}\n' > "$temporary_root/.sprintctl/backend.json"

cat > "$mock_bin/git" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

if [[ "$1" == "-C" && "$3" == "rev-parse" && "$4" == "--show-toplevel" ]]; then
  printf '%s\n' "$2"
  exit 0
fi
exit 1
EOF

cat > "$mock_bin/direnv" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

if [[ "$1" == "exec" && "$2" == "." ]]; then
  shift 2
  exec "$@"
fi
exit 1
EOF

cat > "$mock_bin/timeout" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

shift
exec "$@"
EOF

cat > "$mock_bin/sprintctl" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

printf '%s\n' "$*" >> "$HOOK_CALL_LOG"
[[ "$1" == "maintain" && "$2" == "check" && "$3" == "--json" ]] || exit 2
cat "$HOOK_REPORT_FILE"
EOF

chmod 755 "$mock_bin/git" "$mock_bin/direnv" "$mock_bin/timeout" "$mock_bin/sprintctl"

event_json="$(jq -nc --arg cwd "$temporary_root" '{cwd: $cwd}')"
actionable_report="$temporary_root/actionable.json"
healthy_report="$temporary_root/healthy.json"

printf '%s\n' '{"sprint":{"repo_id":"test-repo","id":7,"name":"Test sprint"},"stale_items":[{"id":1}],"track_health":[{"counts":{"blocked":2}}],"risk":{"active_items":5,"days_remaining":3,"at_risk":true,"overdue":false}}' > "$actionable_report"
printf '%s\n' '{"sprint":{"repo_id":"test-repo","id":7,"name":"Test sprint"},"stale_items":[],"track_health":[{"counts":{"blocked":0}}],"risk":{"active_items":1,"days_remaining":14,"at_risk":false,"overdue":false}}' > "$healthy_report"

run_hook() {
  local report_path="$1"

  printf '%s\n' "$event_json" | \
    PATH="$mock_bin:$PATH" \
    HOOK_CALL_LOG="$call_log" \
    HOOK_REPORT_FILE="$report_path" \
    "$hook_path"
}

actionable_output="$(run_hook "$actionable_report")"
jq -e '
  .hookSpecificOutput.hookEventName == "SessionStart"
  and (.hookSpecificOutput.additionalContext | contains("stale_items=1"))
  and (.hookSpecificOutput.additionalContext | contains("blocked_items=2"))
  and (.hookSpecificOutput.additionalContext | contains("No state changed."))
' <<< "$actionable_output" >/dev/null
grep -Fx -- 'maintain check --json' "$call_log" >/dev/null

: > "$call_log"
healthy_output="$(run_hook "$healthy_report")"
[[ -z "$healthy_output" ]] || {
  printf 'healthy report unexpectedly emitted hook context\n' >&2
  exit 1
}
grep -Fx -- 'maintain check --json' "$call_log" >/dev/null

printf 'sprintctl maintenance hook tests passed\n'