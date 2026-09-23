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

# Repo root, for the harness_evidence call below (agentops#2445, WP7b) -- best-effort like
# everything else this hook resolves relative to itself. An unresolvable root just means
# that call degrades to a no-op (see emit_harness_evidence). Overridable so a test can point
# it at a fixture root (e.g. one with no scripts/harness_evidence, or a stub that raises)
# without needing to relocate the hook itself -- the same seam AGENTOPS_COST_LOG etc. use.
_HARNESS_EVIDENCE_ROOT="${AGENTOPS_HARNESS_EVIDENCE_ROOT:-}"
if [[ -z "$_HARNESS_EVIDENCE_ROOT" ]]; then
  _HARNESS_EVIDENCE_ROOT="$(cd -- "${_hook_src%/*}/.." 2>/dev/null && pwd -P)" || _HARNESS_EVIDENCE_ROOT=""
fi

LOG="${AGENTOPS_COST_LOG:-/projects/dev/.claude/session-costs.jsonl}"
GATE_DIR="${AGENTOPS_GATE_LOG_DIR:-/projects/dev/.claude/state}"

EVENT="$(cat)"
TRANSCRIPT="$(echo "$EVENT" | jq -r '.transcript_path // ""')"
# Optional passthrough for the harness_evidence rate-limit gauges (agentops#2445, WP7b):
# this hook has no producer of its own for the 5h/7d utilisation windows
# `metrics.build_rate_limit_gauges` expects (`.claude-headroom.json` is documented
# elsewhere as stale with no live writer, and wiring one is out of this item's scope) --
# but a caller (a future harness version, or a test) that already has the shape can hand
# it straight through on the Stop event itself. Absent, this is simply omitted below.
WINDOWS="$(echo "$EVENT" | jq -c '.windows // empty')"
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
# This log has more than one writer -- the workstation and the devbox both wire this
# hook -- and until now nothing recorded which. Rows written before this stay
# host-unknown; they cannot be attributed after the fact.
HOST="${AGENTOPS_HOST:-$(hostname 2>/dev/null || echo unknown)}"

GATE_FILE="$GATE_DIR/gates-$SESSION.jsonl"

# --- T-4: gate outcomes collected by gate-log.sh during this session -------------------
# rework_rounds = a red gate followed by a later retry of the same command. Rows whose verdict
# could not be attributed (ok null, a compound command) are skipped rather than counted either
# way: `.ok == false` is false for null, which is the behaviour wanted here.
# The log is read, never consumed: each snapshot must carry every gate the session has run.
#
# WL-D1: the same file also carries `kind == "decision"` rows -- guard-hook deny/ask
# emits, appended by hooks/lib/emit-decision.sh -- interleaved with the gate rows above.
# Those have no `cmd`/`ok` and must never enter `gates` or the rework count: a decision
# row is not a gate outcome, and letting one in would silently perturb both. This mirrors
# scripts/check_trajectory_flags.py's rework_findings, which already skips kind ==
# "decision" rows (landed 87c7697, PR #197) -- lane.review 3152 recorded the two sides'
# disagreement as the expected state until this item lands.
if [[ -s "$GATE_FILE" ]]; then
  ALL_ROWS="$(jq -cs '.' "$GATE_FILE" 2>/dev/null || echo '[]')"
else
  ALL_ROWS='[]'
fi
GATES="$(printf '%s' "$ALL_ROWS" | jq -c '[ .[] | select(.kind != "decision") ]' 2>/dev/null || echo '[]')"
DECISIONS="$(printf '%s' "$ALL_ROWS" | jq -c '[ .[] | select(.kind == "decision") ]' 2>/dev/null || echo '[]')"
REWORK="$(printf '%s' "$GATES" | jq '
  . as $rows
  | [ range(0; ($rows | length))
      | select($rows[.].ok == false)
      | . as $i
      | select([ $rows[($i + 1):][] | select(.cmd == $rows[$i].cmd) ] | length > 0)
    ] | length' 2>/dev/null || echo 0)"

# --- Transfer: did this session hand its work to a successor? -------------------------
# A handoff under docs/dispatch/handoffs records `predecessor.session_id` at create time and
# gains `successor.session_id` when the successor acks. If the session now stopping is some
# handoff's acked predecessor, the stop is the end of a *transfer*, not the end of the work,
# and the event should say where the work went -- otherwise the successor's session looks
# like an unrelated run that happened to touch the same repos.
#
# `handed_off_to` rides in --metadata, which auditctl documents as "JSON object with
# publisher metadata" and does not schema-restrict; the typed slots are --type/--actor/
# --summary/--detail/--ref, and --ref rejects anything outside its wi:/ka:/ad:/sha:/pr:/
# sprint:/capsule: prefixes, which is already why the session id travels in metadata (below).
# The key is omitted entirely when there is no successor, so an un-handed-off session's
# event is byte-identical to what it was before this change.
#
# Read-only and best-effort: a missing directory, unreadable file or absent jq must not cost
# the session its record. Newest match wins if several -- files sort by <date>-<slug>.v<N>.
HANDOFF_DIR="${AGENTOPS_HANDOFF_DIR:-/projects/dev/agentops/docs/dispatch/handoffs}"
HANDED_OFF_TO=""
if [[ -d "$HANDOFF_DIR" && -n "$SESSION" && "$SESSION" != "unknown" ]]; then
  HANDED_OFF_TO="$(jq -r --arg s "$SESSION" \
    'select(.predecessor.session_id == $s and (.successor.session_id // "") != "")
     | .successor.session_id' "$HANDOFF_DIR"/*.json 2>/dev/null | tail -n 1 || true)"
fi

# --- WP7b (agentops#2445): guarded call into the harness_evidence exporter (#2443) -----
# ENFORCEMENT BOUNDARY: this call must never change this hook's exit code, its stdout, or
# the log/auditctl writes emit_record already performs -- it is purely additive telemetry,
# and every failure mode (python3 absent, the module absent or raising, export() itself
# failing) degrades the same way: silently, to "no telemetry for this row". In production
# OTEL_EXPORTER_OTLP_ENDPOINT stays unset until #2397/#2398 land, and export() performs zero
# network I/O when it is unset (docs/architecture/harness-evidence-policy.md "Fail-open
# posture"), so this call is inert today regardless of what it builds.
#
# `record` is the same cost row emit_record's caller already assembled (the one written to
# $LOG and folded into the auditctl --metadata above); this maps its fields onto the
# harness_evidence payload shape (`schemas/harness-evidence-attributes.schema.json`) rather
# than passing it through verbatim, since the two schemas do not share key names
# (`session` vs `session_id`, `in`/`out` vs `input_tokens`/`output_tokens`, ...) and an
# unrecognised key is silently dropped by the library's own allowlist filter regardless.
emit_harness_evidence() {
  local record="$1"
  command -v python3 >/dev/null 2>&1 || return 0
  [[ -n "$_HARNESS_EVIDENCE_ROOT" && -d "$_HARNESS_EVIDENCE_ROOT/scripts/harness_evidence" ]] || return 0

  local payload
  payload="$(printf '%s' "$record" | jq -c \
    --arg transcript "$TRANSCRIPT" \
    --argjson windows "${WINDOWS:-null}" \
    '{
       schema_version: "harness-evidence-attributes/v1",
       session_id: (.session // "unknown"),
       transcript_path: $transcript,
       runtime: "claude-code",
       harness: "vuoro",
       environment: "prod",
       model: (.model // "unknown"),
       input_tokens: (.in // 0),
       output_tokens: (.out // 0),
       durations: {wall_seconds: (.duration_s // 0)},
       result_class: "success",
       terminal_reason: "completed"
     } + (if (.cost_usd // null) == null then {} else {cost_usd_list: [.cost_usd]} end)
       + (if $windows == null then {} else {windows: $windows} end)' \
    2>/dev/null)" || return 0
  [[ -n "$payload" && "$payload" != "null" ]] || return 0

  # Everything past this point runs with stdout/stderr discarded and its exit status
  # ignored by the caller (`|| true` below): a broken collector, a raised exception while
  # building the batch, or a non-zero interpreter exit must never surface here.
  PYTHONPATH="$_HARNESS_EVIDENCE_ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 - "$payload" \
    >/dev/null 2>&1 <<'PY' || true
import json
import sys

try:
    from scripts.harness_evidence import build_rate_limit_gauges, build_session_span, export_batch

    payload = json.loads(sys.argv[1])
    batch = {"spans": [build_session_span(payload)]}
    if payload.get("windows"):
        batch["metrics"] = [build_rate_limit_gauges(payload)]
    export_batch(batch)
except Exception:
    # Fail-open: this path never raises through to the hook.
    pass
PY
  return 0
}

emit_record() {
  local record="$1"
  printf '%s\n' "$record" >> "$LOG"

  # Best-effort and independent of auditctl below: must run (and must stay inert) whether
  # or not a publisher is on PATH. See emit_harness_evidence's own comment for the guard.
  emit_harness_evidence "$record" || true

  # auditctl is optional: a missing publisher must never cost the session its cost row.
  # Resolution goes through the shared helper because the bare name `auditctl` also belongs
  # to the kernel audit tool -- see hooks/auditctl-resolve.sh for what that cost.
  local auditctl_path
  auditctl_path="$(auditctl_bin)" || return 0
  local summary metadata
  summary="$(printf '%s' "$record" | jq -r '"session \(.project): \(.turns) turns, \(.tool_calls) tool calls, $\(.cost_usd * 100 | round / 100)"')"
  # `gates` and `decisions` travel through FILES, not argv.
  #
  # Linux caps a single argv string at MAX_ARG_STRLEN (32 * page size = 128 KiB),
  # independently of ARG_MAX. `--argjson gates "$GATES"` passes the whole
  # accumulated gate array as one argument, so a long session silently crosses
  # that ceiling and execve fails E2BIG -- "Argument list too long" -- losing the
  # auditctl row while the cost row itself still lands. Measured 2026-09-22:
  # GATES was 169602 bytes against a 131072-byte per-argument cap, on a host
  # whose ARG_MAX is 2 MiB, which is why the total was never the constraint.
  # --slurpfile reads the file and binds an array of the JSON values it holds;
  # each file holds exactly one array, hence the [0].
  local gates_file decisions_file
  gates_file="$(mktemp)" || return 0
  decisions_file="$(mktemp)" || { rm -f "$gates_file"; return 0; }
  printf '%s' "${GATES:-[]}" > "$gates_file"
  printf '%s' "${DECISIONS:-[]}" > "$decisions_file"
  metadata="$(printf '%s' "$record" | jq -c \
      --slurpfile gates "$gates_file" --argjson rework "${REWORK:-0}" \
      --slurpfile decisions "$decisions_file" \
      --arg handed "$HANDED_OFF_TO" \
      '{session, runtime_session_id, turns, assistant_msgs, tool_calls, duration_s, cost_usd,
        model, project, gates: $gates[0], rework_rounds: $rework, decisions: $decisions[0]}
       + (if $handed == "" then {} else {handed_off_to: $handed} end)')"

  # The arrays NEVER travel in the row. OPERATOR DECISION 2026-09-22, delegated.
  #
  # The earlier fix carried gates and decisions inline when they happened to fit
  # and bounded them when they did not. That was the wrong shape, for three
  # reasons, and the threshold it rested on was a number nobody could defend.
  #
  # 1. The "fits" case is the exception, not the rule. Measured across the ten
  #    live gate logs on this host, NINE of ten serialised `gates` arrays exceed
  #    auditctl's whole-event limit of 16384 bytes on their own (largest 169603;
  #    a single `cmd` value reached 15067, because gate rows carry whole shell
  #    commands including heredocs of prose). Optimising for the tenth case
  #    bought nothing and cost a branch.
  # 2. Nothing reads them here. `scripts/check_trajectory_flags.py` recomputes
  #    rework from the gate-log FILE directly (:191, :205, :239-257), and
  #    `scripts/harness_evidence/` drops `gates` and `rework_rounds` as
  #    non-allowlisted, asserted at scripts/tests/test_harness_evidence_export.py
  #    :133-135. The audit row was the only consumer, and it never read them back.
  # 3. A row shape that varies with payload size is its own trap. Two rows of the
  #    same type, one with `gates` populated and one with it empty and a
  #    `truncated` flag, differ in a way that is invisible unless you already know
  #    to look -- so a query written against a short session's row returns wrong
  #    answers on a long one, silently. Uniform beats conditionally-richer.
  #
  # So: every row carries the counts and the derived scalar, and the full arrays
  # always go to a sidecar file beside the cost log. Nothing is lost, every row
  # fits by construction, and there is no threshold to tune or defend. What this
  # gives up is reading a short session's gates straight out of the audit row;
  # that is a real loss and it is accepted, because the alternative lost entire
  # rows -- 1417 of them between 2026-08-23 and 2026-09-22.
  #
  # The sidecar is NOT an auditctl artifact ref: auditctl's own error advertises
  # an `immutableRef kind=artifact under _artifacts/<repo_id>/`, and no such
  # mechanism exists (no `artifact:` prefix in validation.py's
  # VALID_REF_PREFIXES, no command that registers a blob, and that directory is
  # auditctl's NDJSON store root, not a blob store). A plain file is the only
  # mechanism available to this publisher.
  #
  # Every helper is guarded: this hook runs under `set -euo pipefail`, sometimes
  # with a minimal PATH, and a missing `mkdir`, `jq` or `date` must not cost the
  # session its row.
  local overflow_dir overflow_file
  overflow_dir="$(dirname "$LOG")/session-gates"
  overflow_file="$overflow_dir/gates-${SESSION:-unknown}.json"
  # Stable per-session name: the hook republishes a fresh snapshot on every Stop,
  # so the newest write is the complete array for that session.
  if mkdir -p "$overflow_dir" 2>/dev/null && jq -n \
      --slurpfile gates "$gates_file" --slurpfile decisions "$decisions_file" \
      --arg s "${SESSION:-unknown}" --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || true)" \
      '{session: $s, written_at: $ts, gates: $gates[0], decisions: $decisions[0]}' \
      > "$overflow_file" 2>/dev/null; then
    :
  else
    overflow_file=""
  fi
  metadata="$(printf '%s' "$metadata" | jq -c --arg path "$overflow_file" \
    '. as $m
     | del(.gates, .decisions)
     + {gates_count: ($m.gates | length),
        decisions_count: ($m.decisions | length)}
     + (if $path == "" then {gates_unavailable: "sidecar could not be written"}
        else {gates_path: $path} end)')"
  local meta_bytes
  meta_bytes="$(printf '%s' "$metadata" | wc -c 2>/dev/null || true)"
  [[ "$meta_bytes" =~ ^[0-9]+$ ]] || meta_bytes="${#metadata}"
  rm -f "$gates_file" "$decisions_file"
  # No --ref: auditctl allows only wi:/ka:/ad:/sha:/pr:/sprint:/capsule:/baseline:
  # prefixes, so the session id travels in the metadata instead of being rejected
  # as an invalid ref.
  #
  # The publish stays NON-FATAL -- a hook must never cost the session its turn --
  # but it is no longer SILENT. The previous `>/dev/null 2>&1 || true` is exactly
  # how the size rejection above went unnoticed for a month: auditctl printed a
  # precise error and the hook threw it away. stderr and the exit status now land
  # in a durable failure log beside the cost log, so a failed publish is findable
  # after the fact.
  local audit_err audit_rc
  audit_err="$(mktemp)" || audit_err=""
  audit_rc=0
  if [[ -n "$audit_err" ]]; then
    "$auditctl_path" add --type workflow.session --source claude-hook --actor claude-hook \
      --summary "$summary" --metadata "$metadata" >/dev/null 2>"$audit_err" || audit_rc=$?
  else
    "$auditctl_path" add --type workflow.session --source claude-hook --actor claude-hook \
      --summary "$summary" --metadata "$metadata" >/dev/null 2>&1 || audit_rc=$?
  fi
  if (( audit_rc != 0 )); then
    local fail_log
    fail_log="${AGENTOPS_AUDIT_FAILURE_LOG:-$(dirname "$LOG")/auditctl-publish-failures.jsonl}"
    mkdir -p "$(dirname "$fail_log")" 2>/dev/null || true
    local err_text
    err_text=""
    if [[ -n "$audit_err" ]]; then err_text="$(head -c 2000 "$audit_err" 2>/dev/null || true)"; fi
    [[ -n "$err_text" ]] || err_text="stderr not captured"
    jq -cn --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || true)" --arg s "${SESSION:-unknown}" \
      --argjson rc "$audit_rc" --argjson bytes "$meta_bytes" \
      --arg err "$err_text" \
      '{ts:$ts, session:$s, event:"auditctl-publish-failed", exit_status:$rc, metadata_bytes:$bytes, stderr:$err}' \
      >> "$fail_log" 2>/dev/null || true
  fi
  [[ -n "$audit_err" ]] && rm -f "$audit_err"
  return 0
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
    --arg host "$HOST" \
    '{ts:$ts, project:$proj, session:$session, runtime_session_id:($runtime_session // ""), host:$host, model:"unknown", in:0, cache_write:0, cache_read:0, out:0, cost_usd:0, turns:0, assistant_msgs:0, tool_calls:0, duration_s:0}')"
  emit_record "$RECORD"
  exit 0
fi

# Pricing per million tokens, as [input, cache_write, cache_read, output]:
#   opus-5, opus-4-8, opus-4-7, opus-4-6:  5 / 6.25 / 0.50 / 25
#   fable, mythos:                        10 / 12.5 / 1.00 / 50
#   sonnet-5:                              2 / 2.50 / 0.20 / 10
#   sonnet-4-6:                            3 / 3.75 / 0.30 / 15
#   haiku:                                 1 / 1.25 / 0.10 / 5
# An unmatched model prices to null, not to a guess. Silently applying Sonnet
# rates to everything unrecognised is what made the old ladder overstate spend.
RECORD="$(jq -rcs \
  --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg proj "$PROJ" \
  --arg session "$SESSION" \
  --arg runtime_session "$RUNTIME_SESSION" \
  --arg host "$HOST" \
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
  | (if   .model | test("opus-5|opus-4-8|opus-4-7|opus-4-6") then [5,  6.25, 0.50, 25]
     elif .model | test("fable|mythos")                      then [10, 12.5, 1.00, 50]
     elif .model | test("sonnet-5")                          then [2,  2.50, 0.20, 10]
     elif .model | test("sonnet-4-6")                        then [3,  3.75, 0.30, 15]
     elif .model | test("haiku")                             then [1,  1.25, 0.10, 5]
     else null end) as $price
  | . + {
      cost_usd: (
        if $price == null then null else
          (.in          / 1000000 * $price[0]) +
          (.cache_write / 1000000 * $price[1]) +
          (.cache_read  / 1000000 * $price[2]) +
          (.out         / 1000000 * $price[3])
        end
      )
    }
  | {ts: $ts, project: $proj, session: $session, runtime_session_id: $runtime_session, host: $host}
    + . + {turns: $turns, assistant_msgs: $assistant_msgs, tool_calls: $tool_calls, duration_s: $duration_s}
  ' "$TRANSCRIPT")"

emit_record "$RECORD"

# Gate logs belong to their session for its whole life, so they are swept by age rather than
# consumed. Seven days is longer than any session and short enough to stay tidy.
find "$GATE_DIR" -maxdepth 1 -name 'gates-*.jsonl' -mtime +7 -delete 2>/dev/null || true
