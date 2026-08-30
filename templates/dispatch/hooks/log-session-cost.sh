#!/usr/bin/env bash
# Claude Code Stop hook — append a session record to /projects/dev/.claude/session-costs.jsonl
# and (T-4) publish the same session to auditctl as a workflow.session event.
#
# Receives Stop event JSON on stdin: session_id, transcript_path, cwd, hook_event_name.
#
# T-1 added turns / assistant_msgs / tool_calls / duration_s to the record. Every field the
# cockpit already reads (apps/web/lib/cockpit/costs.js) keeps its name, position and type:
# the new keys are additive, and an old row still parses.
#
# IMPORTANT — Stop fires once per assistant turn, not once per session. Every record is a
# *cumulative snapshot* of the session so far, so rows and events for one session supersede
# each other: a consumer must reduce to the newest row per `session` before aggregating.
# Summing every row over-counts roughly quadratically (measured 2026-08-23: $56,485 summed
# vs $3,825 actual across 97 sessions). That is why the gate log is accumulated rather than
# consumed — draining it on the first stop would drop every gate from the final snapshot.
set -euo pipefail

# The publisher resolver lives beside this hook. Sourcing it is best-effort by design:
# a hook shell can arrive with a PATH that has neither readlink nor dirname on it, and a
# hook can be copied out of its directory without the helper. Neither may cost the session
# its record, so an unreachable helper degrades to "do not publish", never to a failed hook.
_hook_src="${BASH_SOURCE[0]}"
{ [[ -L "$_hook_src" ]] && command -v readlink >/dev/null 2>&1 &&
  _hook_src="$(readlink -f -- "$_hook_src" 2>/dev/null || printf '%s' "$_hook_src")"; } || true
if [[ -r "${_hook_src%/*}/auditctl-resolve.sh" ]]; then
  # shellcheck source=auditctl-resolve.sh
  . "${_hook_src%/*}/auditctl-resolve.sh"
else
  auditctl_bin() { return 1; }
fi

LOG="${AGENTOPS_COST_LOG:-/projects/dev/.claude/session-costs.jsonl}"
GATE_DIR="${AGENTOPS_GATE_LOG_DIR:-/projects/dev/.claude/state}"

EVENT="$(cat)"
TRANSCRIPT="$(echo "$EVENT" | jq -r '.transcript_path // ""')"
SESSION="$(echo "$EVENT" | jq -r '.session_id // "unknown"')"
RUNTIME_SESSION="$(echo "$EVENT" | jq -r '.runtime_session_id // empty')"
RUNTIME_SESSION="${RUNTIME_SESSION:-${SPRINTCTL_RUNTIME_SESSION_ID:-${CODEX_THREAD_ID:-}}}"
# Last resort: this session itself. Measured 2026-08-29 across 1593 events in 11 stores --
# `runtime_session_id` was populated ZERO times, in the schema field and in metadata alike,
# while the harness session uuid was written 354 times into the untyped `metadata.session`
# beside it. None of the three sources above has a producer for an interactive session:
# the payload field arrives empty, and neither SPRINTCTL_RUNTIME_SESSION_ID nor
# CODEX_THREAD_ID is set by anything in this workspace.
#
# So this hook was writing "" into the one field that ties an event to a running session,
# which is not merely empty -- it is the shape the session-mechanization validators reject
# as blank. For a Claude Code session there is no separate runtime: the harness session id
# IS the identity of the run, which is the same equality actionq's own contract asserts
# when it requires session_id and runtime_session_id to match. `unknown` is excluded
# because a placeholder in a typed field is what the untyped one already suffers from.
if [[ -z "$RUNTIME_SESSION" && -n "$SESSION" && "$SESSION" != "unknown" ]]; then
  RUNTIME_SESSION="$SESSION"
fi
PROJ="$(echo "$EVENT" | jq -r '.cwd // ""' | xargs basename 2>/dev/null || basename "$PWD")"

GATE_FILE="$GATE_DIR/gates-$SESSION.jsonl"

# --- T-4: gate outcomes collected by gate-log.sh during this session -------------------
# rework_rounds = a red gate followed by a later retry of the same command. Rows whose verdict
# could not be attributed (ok null, a compound command) are skipped rather than counted either
# way: `.ok == false` is false for null, which is the behaviour wanted here.
# The log is read, never consumed: each snapshot must carry every gate the session has run.
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
  # Resolution goes through the shared helper because the bare name `auditctl` also belongs
  # to the kernel audit tool -- see hooks/auditctl-resolve.sh for what that cost.
  local auditctl_path
  auditctl_path="$(auditctl_bin)" || return 0
  local summary metadata
  summary="$(printf '%s' "$record" | jq -r '"session \(.project): \(.turns) turns, \(.tool_calls) tool calls, $\(.cost_usd * 100 | round / 100)"')"
  metadata="$(printf '%s' "$record" | jq -c \
      --argjson gates "$GATES" --argjson rework "${REWORK:-0}" \
      '{session, runtime_session_id, turns, assistant_msgs, tool_calls, duration_s, cost_usd,
        model, project, gates: $gates, rework_rounds: $rework}')"
  # No --ref: auditctl allows only wi:/ka:/ad:/sha:/pr:/sprint:/capsule: prefixes, so the
  # session id travels in the metadata instead of being rejected as an invalid ref.
  "$auditctl_path" add --type workflow.session --source claude-hook --actor claude-hook \
    --summary "$summary" --metadata "$metadata" >/dev/null 2>&1 || true
}

# Wait for the turn now ending to reach the transcript before reading it.
#
# Measured 2026-08-30: this hook was registered `async: true`, and an async hook is not
# awaited -- a headless `claude -p` exits before it completes and the row is simply lost.
# Every unattended session on this host recorded nothing for that reason, and it was
# invisible because an interactive session outlives its own hook and always wins the race.
# Registering it synchronously fixes that and exposes the second half: at Stop the
# assistant turn is not on disk yet. The first four synchronous runs wrote
# `assistant_msgs: 0, in: 0, out: 0, cost_usd: 0` -- a row that exists and says nothing,
# which is the same defect wearing the opposite mask.
#
# The record landed 109 ms after Stop in the measured run, so a bounded wait closes it.
# The predicate is that the last conversational record is an assistant message carrying
# usage -- the shape of a *closed* turn. Counting assistant messages instead would be
# satisfied by turn 1 while turn 7 is still in flight.
if [[ -n "$TRANSCRIPT" && -f "$TRANSCRIPT" ]]; then
  # Builtins only for the loop itself: a hook shell can arrive without `seq`, and under
  # `set -e` an empty `$(seq ...)` silently degrades the wait to nothing. `sleep` is
  # external too, so its absence breaks the loop rather than spinning it.
  for ((_i = 0; _i < 30; _i++)); do
    closed="$(tail -n 12 -- "$TRANSCRIPT" 2>/dev/null \
      | jq -s -r '[.[] | select(.type == "assistant" or .type == "user")] | last
                  | if (.type == "assistant" and .message.usage != null) then "yes" else "no" end' \
      2>/dev/null || echo no)"
    [[ "$closed" == "yes" ]] && break
    sleep 0.05 2>/dev/null || break
  done
fi

if [[ -z "$TRANSCRIPT" || ! -f "$TRANSCRIPT" ]]; then
  # No transcript — log a zero entry so the session is still recorded
  RECORD="$(jq -cn \
    --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg proj "$PROJ" \
    --arg session "$SESSION" \
    --arg runtime_session "$RUNTIME_SESSION" \
    '{ts:$ts, project:$proj, session:$session, runtime_session_id:($runtime_session // ""), model:"unknown", in:0, cache_write:0, cache_read:0, out:0, cost_usd:0, turns:0, assistant_msgs:0, tool_calls:0, duration_s:0}')"
  emit_record "$RECORD"
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
  # A turn is a user message the person actually sent. Predicate taken from the
  # L-1 worker implementation of this packet (V5-P1a @ 8b1c8b9): excluding
  # content that carries a tool_result is more robust than requiring a string,
  # which silently drops any future user turn whose content is an array for
  # another reason, an attachment say. Same answer on the transcripts we have,
  # better answer on the ones we do not.
  | ([ $rows[] | select(.type == "user" and (.isMeta != true)
       and ([ .message.content[]? | select(.type == "tool_result") ] | length) == 0) ] | length) as $turns
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

# Gate logs belong to their session for its whole life, so they are swept by age rather than
# consumed. Seven days is longer than any session and short enough to stay tidy.
find "$GATE_DIR" -maxdepth 1 -name 'gates-*.jsonl' -mtime +7 -delete 2>/dev/null || true
