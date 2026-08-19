#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-18765}"
LOG="$(mktemp)"
trap 'kill "${SERVER_PID:-}" 2>/dev/null || true; rm -f "$LOG"' EXIT

export PYTHONPATH="$ROOT/reference${PYTHONPATH:+:$PYTHONPATH}"
export VUORO_DISPATCH_ID="demo-dispatch"
export VUORO_REPO_ID="demo-repo"
export VUORO_CONTEXT_ENDPOINT="http://127.0.0.1:$PORT"

python3 -m volatile_context.fake_service --port "$PORT" >"$LOG" 2>&1 &
SERVER_PID=$!

for _ in {1..30}; do
  if python3 - <<PY >/dev/null 2>&1
import urllib.request
urllib.request.urlopen("http://127.0.0.1:$PORT/not-used", timeout=0.1)
PY
  then
    break
  fi
  # A 404 still proves the listener is up; urllib raises, so check the process too.
  kill -0 "$SERVER_PID" 2>/dev/null || { cat "$LOG" >&2; exit 1; }
  sleep 0.05
done

printf '%s\n' '{"session_id":"demo-session","cwd":"/repo","hook_event_name":"SessionStart","source":"startup"}' \
  | python3 -m volatile_context.hook_adapter --harness codex
printf '\n'

# Unchanged turn: deliberately prints nothing.
printf '%s\n' '{"session_id":"demo-session","cwd":"/repo","hook_event_name":"UserPromptSubmit","prompt":"continue"}' \
  | python3 -m volatile_context.hook_adapter --harness codex
printf '\n'

python3 - <<PY
import json, urllib.request
payload = {
  "if_revision": "task:1",
  "actor": "agent:demo",
  "idempotency_key": "demo-1",
  "patch": {"state": "review"}
}
req = urllib.request.Request(
  "http://127.0.0.1:$PORT/demo/task/mutate",
  data=json.dumps(payload).encode(),
  headers={"Content-Type":"application/json"},
  method="POST"
)
print(urllib.request.urlopen(req).read().decode())
PY

printf '%s\n' '{"session_id":"demo-session","cwd":"/repo","hook_event_name":"PostToolUse","tool_name":"mcp__sprintctl__update_task","tool_input":{"task_id":"TASK-42","if_revision":"task:1"},"tool_response":{"new_revision":"task:2"}}' \
  | python3 -m volatile_context.hook_adapter --harness codex
printf '\n'
