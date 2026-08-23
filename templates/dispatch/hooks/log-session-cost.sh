#!/usr/bin/env bash
# Claude Code Stop hook — append session cost estimate to /projects/dev/.claude/session-costs.jsonl
# Receives Stop event JSON on stdin: session_id, transcript_path, cwd, hook_event_name
set -euo pipefail

LOG="/projects/dev/.claude/session-costs.jsonl"

EVENT="$(cat)"
TRANSCRIPT="$(echo "$EVENT" | jq -r '.transcript_path // ""')"
SESSION="$(echo "$EVENT" | jq -r '.session_id // "unknown"')"
RUNTIME_SESSION="$(echo "$EVENT" | jq -r '.runtime_session_id // empty')"
RUNTIME_SESSION="${RUNTIME_SESSION:-${SPRINTCTL_RUNTIME_SESSION_ID:-${CODEX_THREAD_ID:-}}}"
PROJ="$(echo "$EVENT" | jq -r '.cwd // ""' | xargs basename 2>/dev/null || basename "$PWD")"

if [[ -z "$TRANSCRIPT" || ! -f "$TRANSCRIPT" ]]; then
  # No transcript — log a zero entry so the session is still recorded
  jq -cn \
    --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg proj "$PROJ" \
    --arg session "$SESSION" \
    --arg runtime_session "$RUNTIME_SESSION" \
    '{ts:$ts, project:$proj, session:$session, runtime_session_id:($runtime_session // ""), model:"unknown", in:0, cache_write:0, cache_read:0, out:0, cost_usd:0}' \
    >> "$LOG"
  exit 0
fi

# Pricing per million tokens (approximate, 2025 rates):
#   opus:   $15 input / $75 output / $18.75 cache_write / $1.50 cache_read
#   haiku:  $0.80 input / $4 output / $1.00 cache_write / $0.08 cache_read
#   sonnet: $3 input / $15 output / $3.75 cache_write / $0.30 cache_read
jq -rcs \
  --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg proj "$PROJ" \
  --arg session "$SESSION" \
  --arg runtime_session "$RUNTIME_SESSION" \
  '
  [ .[] | select(.message.role == "assistant" and .message.usage != null) ]
  | {
      model: ([ .[].message.model ] | map(select(. != null)) | last // "unknown"),
      in:          ([ .[].message.usage.input_tokens                  // 0 ] | add // 0),
      cache_write: ([ .[].message.usage.cache_creation_input_tokens   // 0 ] | add // 0),
      cache_read:  ([ .[].message.usage.cache_read_input_tokens       // 0 ] | add // 0),
      out:         ([ .[].message.usage.output_tokens                 // 0 ] | add // 0)
    }
  | . + {
      cost_usd: (
        (.in          / 1000000 * (if .model | test("opus")  then 15   elif .model | test("haiku") then 0.80 else 3    end)) +
        (.cache_write / 1000000 * (if .model | test("opus")  then 18.75 elif .model | test("haiku") then 1.00 else 3.75 end)) +
        (.cache_read  / 1000000 * (if .model | test("opus")  then 1.50  elif .model | test("haiku") then 0.08 else 0.30 end)) +
        (.out         / 1000000 * (if .model | test("opus")  then 75   elif .model | test("haiku") then 4    else 15   end))
      )
    }
  | {ts: $ts, project: $proj, session: $session, runtime_session_id: $runtime_session} + .
  ' "$TRANSCRIPT" >> "$LOG"
