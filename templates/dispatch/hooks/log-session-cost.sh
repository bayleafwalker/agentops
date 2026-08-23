#!/usr/bin/env bash
# Claude Code Stop hook — append a session record to /projects/dev/.claude/session-costs.jsonl
# and (T-4) publish the same session to auditctl as a workflow.session event.
#
# Receives Stop event JSON on stdin: session_id, transcript_path, cwd, hook_event_name.
#
# T-1 added turns / assistant_msgs / tool_calls / duration_s to the record. Every field the
# cockpit already reads (apps/web/lib/cockpit/costs.js) keeps its name, position and type:
# the new keys are additive, and an old row still parses.
set -euo pipefail

LOG="${AGENTOPS_COST_LOG:-/projects/dev/.claude/session-costs.jsonl}"
GATE_DIR="${AGENTOPS_GATE_LOG_DIR:-/projects/dev/.claude/state}"

EVENT="$(cat)"
TRANSCRIPT="$(echo "$EVENT" | jq -r '.transcript_path // ""')"
SESSION="$(echo "$EVENT" | jq -r '.session_id // "unknown"')"
RUNTIME_SESSION="$(echo "$EVENT" | jq -r '.runtime_session_id // empty')"
RUNTIME_SESSION="${RUNTIME_SESSION:-${SPRINTCTL_RUNTIME_SESSION_ID:-${CODEX_THREAD_ID:-}}}"
PROJ="$(echo "$EVENT" | jq -r '.cwd // ""' | xargs basename 2>/dev/null || basename "$PWD")"

GATE_FILE="$GATE_DIR/gates-$SESSION.jsonl"

# --- T-4: gate outcomes collected by gate-log.sh during this session -------------------
# rework_rounds = a red gate followed by a later retry of the same command.
if [[ -s "$GATE_FILE" ]]; then
  GATES="$(jq -cs '.' "$GATE_FILE" 2>/dev/null || echo '[]')"
else
  GATES='[]'
fi
REWORK="$(printf '%s' "$GATES" | jq '
  . as $rows
  | [ range(0; ($rows | length))
      | select($rows[.].ok == false)
      | . as $i
      | select([ $rows[($i + 1):][] | select(.cmd == $rows[$i].cmd) ] | length > 0)
    ] | length' 2>/dev/null || echo 0)"

emit_record() {
  local record="$1"
  printf '%s\n' "$record" >> "$LOG"

  # auditctl is optional: a missing publisher must never cost the session its cost row.
  command -v auditctl >/dev/null 2>&1 || return 0
  # A Stop hook does not inherit direnv, so the artifacts root has to be defaulted here or
  # every write fails with "AUDITCTL_ARTIFACTS_ROOT is required for audit writes".
  export AUDITCTL_ARTIFACTS_ROOT="${AUDITCTL_ARTIFACTS_ROOT:-/projects/dev}"
  local summary metadata
  summary="$(printf '%s' "$record" | jq -r '"session \(.project): \(.turns) turns, \(.tool_calls) tool calls, $\(.cost_usd * 100 | round / 100)"')"
  metadata="$(printf '%s' "$record" | jq -c \
      --argjson gates "$GATES" --argjson rework "${REWORK:-0}" \
      '{session, runtime_session_id, turns, assistant_msgs, tool_calls, duration_s, cost_usd,
        model, project, gates: $gates, rework_rounds: $rework}')"
  # No --ref: auditctl allows only wi:/ka:/ad:/sha:/pr:/sprint:/capsule: prefixes, so the
  # session id travels in the metadata instead of being rejected as an invalid ref.
  auditctl add --type workflow.session --source claude-hook --actor claude-hook \
    --summary "$summary" --metadata "$metadata" >/dev/null 2>&1 || true
}

if [[ -z "$TRANSCRIPT" || ! -f "$TRANSCRIPT" ]]; then
  # No transcript — log a zero entry so the session is still recorded
  RECORD="$(jq -cn \
    --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg proj "$PROJ" \
    --arg session "$SESSION" \
    --arg runtime_session "$RUNTIME_SESSION" \
    '{ts:$ts, project:$proj, session:$session, runtime_session_id:($runtime_session // ""), model:"unknown", in:0, cache_write:0, cache_read:0, out:0, cost_usd:0, turns:0, assistant_msgs:0, tool_calls:0, duration_s:0}')"
  emit_record "$RECORD"
  rm -f "$GATE_FILE"
  exit 0
fi

# Pricing per million tokens (approximate, 2025 rates):
#   opus:   $15 input / $75 output / $18.75 cache_write / $1.50 cache_read
#   haiku:  $0.80 input / $4 output / $1.00 cache_write / $0.08 cache_read
#   sonnet: $3 input / $15 output / $3.75 cache_write / $0.30 cache_read
RECORD="$(jq -rcs \
  --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg proj "$PROJ" \
  --arg session "$SESSION" \
  --arg runtime_session "$RUNTIME_SESSION" \
  '
  . as $rows
  # Counters are derived from the transcript: the Stop payload carries none of them.
  # A turn is a user message the person actually sent — not a tool_result (array content)
  # and not a harness-injected meta entry.
  | ([ $rows[] | select(.type == "user" and (.isMeta != true) and ((.message.content | type) == "string")) ] | length) as $turns
  | ([ $rows[] | select(.type == "assistant") ] | length) as $assistant_msgs
  | ([ $rows[] | select(.type == "assistant") | .message.content[]? | select(.type == "tool_use") ] | length) as $tool_calls
  | ([ $rows[] | .timestamp // empty | sub("\\.[0-9]+Z$"; "Z") | fromdateiso8601? // empty ]) as $stamps
  | (if ($stamps | length) > 1 then (($stamps | max) - ($stamps | min)) else 0 end) as $duration_s
  | [ $rows[] | select(.message.role == "assistant" and .message.usage != null) ]
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
  | {ts: $ts, project: $proj, session: $session, runtime_session_id: $runtime_session}
    + . + {turns: $turns, assistant_msgs: $assistant_msgs, tool_calls: $tool_calls, duration_s: $duration_s}
  ' "$TRANSCRIPT")"

emit_record "$RECORD"
rm -f "$GATE_FILE"
