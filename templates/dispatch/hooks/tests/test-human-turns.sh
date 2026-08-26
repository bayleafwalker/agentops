#!/usr/bin/env bash
# V6-K oracle for `human_turns`, and only that field. Written against
# docs/evidence/seeds/V6-K-human-turns.spec.md **revision 2**, with no sight of an
# implementation. The seam is templates/dispatch/hooks/log-session-cost.sh, driven
# end-to-end exactly as Claude Code drives it: a Stop event on stdin, the cost record
# observed through the AGENTOPS_COST_LOG seam that T-1 added, and the auditctl
# metadata blob observed through a stub `auditctl` on PATH.
#
#   REQ-001  human_turns is present in EVERY cost-log record, including the zero record
#   REQ-002  human_turns counts genuine human prompts only, per the three-step rule
#   REQ-003  turns is behaviourally unchanged
#   REQ-004  pre-existing fields keep name/relative order/type; human_turns sits
#            immediately after turns
#   REQ-005  human_turns never exceeds turns
#   REQ-006  the auditctl --metadata key list includes human_turns
#
# Every fixture is built inline below. Nothing here reads a real session transcript
# from ~/.claude/projects or anywhere else, and nothing here writes outside its temp
# directory: AUDITCTL_ARTIFACTS_ROOT is pinned into the temp dir AND a stub auditctl
# shadows the real one on PATH, so the live audit store is never touched.
set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
stop_hook="$(cd -- "$here/.." && pwd -P)/log-session-cost.sh"

[[ -f "$stop_hook" ]] || { printf 'FAIL: seam not found at %s\n' "$stop_hook" >&2; exit 1; }
command -v jq >/dev/null 2>&1 || { printf 'FAIL: jq is required by this test\n' >&2; exit 1; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/gates" "$tmp/audit" "$tmp/bin"

failures=0
note() { printf '  %s\n' "$*"; }
pass() { printf 'ok   %s\n' "$*"; }
fail() { printf 'FAIL %s\n' "$*" >&2; failures=$((failures + 1)); }

assert_eq() { # assert_eq <req+label> <actual> <expected>
  if [[ "$2" == "$3" ]]; then pass "$1"
  else fail "$1: expected '$3', got '$2'"; fi
}

# ---------------------------------------------------------------------------
# REQ-006 observation seam: a stub auditctl.
#
# The metadata blob is only ever visible as an argv of the auditctl call, so the
# blob is captured by shadowing auditctl on PATH rather than by grepping the hook's
# source. Source-grepping would decide the *text* of the key list; this decides the
# *blob actually published*, which is what REQ-006 is about, and it stays correct if
# the worker restructures the jq (which REQ-003's ruling explicitly permits). It also
# means the real auditctl at ~/.local/bin cannot run even by accident.
# ---------------------------------------------------------------------------
cat > "$tmp/bin/auditctl" <<'STUB'
#!/usr/bin/env bash
prev=""
for a in "$@"; do
  [[ "$prev" == "--metadata" ]] && printf '%s\n' "$a" >> "$AUDITCTL_CAPTURE"
  prev="$a"
done
exit 0
STUB
chmod +x "$tmp/bin/auditctl"

# ---------------------------------------------------------------------------
# The frozen `turns` predicate, transcribed independently from the spec's description
# of the CURRENT hook. REQ-003 compares the hook's `turns` against this, so a
# restructured implementation that drifts is caught even if the hard-coded fixture
# counts were themselves wrong.
# ---------------------------------------------------------------------------
frozen_turns() { # frozen_turns <transcript>
  jq -s '[ .[] | select(.type == "user" and (.isMeta != true)
           and ([ .message.content[]? | select(.type == "tool_result") ] | length) == 0) ] | length' "$1"
}

run_stop() { # run_stop <log> <transcript-or-empty> <session>
  local log="$1" transcript="$2" session="$3"
  jq -cn --arg t "$transcript" --arg s "$session" \
    '{session_id:$s, cwd:"/projects/dev/agentops", hook_event_name:"Stop"}
     + (if $t == "" then {} else {transcript_path:$t} end)' \
  | PATH="$tmp/bin:$PATH" \
    AGENTOPS_COST_LOG="$log" \
    AGENTOPS_GATE_LOG_DIR="$tmp/gates" \
    AUDITCTL_ARTIFACTS_ROOT="$tmp/audit" \
    AUDITCTL_CAPTURE="$tmp/meta-$session.json" \
    bash "$stop_hook"
}

# human_turns as a plain string, "<absent>" when the key is not there at all, so a
# missing field reports as a missing field rather than as jq's `null`.
human_turns_of() { jq -r 'if has("human_turns") then (.human_turns | tostring) else "<absent>" end' <<<"$1"; }

# ===========================================================================
# Fixture A — the mixed transcript. Four genuine human prompts; every excluded
# kind in the revision-2 inventory appears at least once, plus the three content
# shapes that yield no text elements at all.
# ===========================================================================
mixed="$tmp/mixed.jsonl"
cat > "$mixed" <<'JSONL'
{"type":"user","isMeta":true,"timestamp":"2026-08-26T10:00:00.000Z","message":{"role":"user","content":"a meta row is not a turn at all"}}
{"type":"user","timestamp":"2026-08-26T10:00:01.000Z","message":{"role":"user","content":"do the thing"}}
{"type":"assistant","timestamp":"2026-08-26T10:00:02.000Z","message":{"role":"assistant","model":"claude-opus-5","usage":{"input_tokens":100,"cache_creation_input_tokens":200,"cache_read_input_tokens":300,"output_tokens":40},"content":[{"type":"text","text":"ok"},{"type":"tool_use","name":"Bash"}]}}
{"type":"user","timestamp":"2026-08-26T10:00:03.000Z","message":{"role":"user","content":[{"type":"tool_result","content":"out"}]}}
{"type":"user","timestamp":"2026-08-26T10:00:04.000Z","message":{"role":"user","content":[{"type":"text","text":"please continue"}]}}
{"type":"user","timestamp":"2026-08-26T10:00:05.000Z","message":{"role":"user","content":[{"type":"text","text":"<system-reminder>As you answer, remember X</system-reminder>"},{"type":"text","text":"fix the bug in the parser"}]}}
{"type":"user","timestamp":"2026-08-26T10:00:06.000Z","message":{"role":"user","content":[{"type":"text","text":"ship it when green"},{"type":"text","text":"<system-reminder>As you answer, remember X</system-reminder>"}]}}
{"type":"assistant","timestamp":"2026-08-26T10:00:07.000Z","message":{"role":"assistant","model":"claude-opus-5","usage":{"input_tokens":20,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"output_tokens":10},"content":[{"type":"tool_use","name":"Read"}]}}
{"type":"user","timestamp":"2026-08-26T10:00:08.000Z","message":{"role":"user","content":[{"type":"tool_result","content":"out"}]}}
{"type":"user","timestamp":"2026-08-26T10:00:09.000Z","message":{"role":"user","content":[{"type":"text","text":"<system-reminder>be good</system-reminder>"},{"type":"text","text":"\n   <task-notification>Agent general-purpose completed</task-notification>"}]}}
{"type":"user","timestamp":"2026-08-26T10:00:10.000Z","message":{"role":"user","content":"\n  <task-notification>Agent Explore completed</task-notification>"}}
{"type":"user","timestamp":"2026-08-26T10:00:11.000Z","message":{"role":"user","content":[{"type":"image"},{"type":"text","text":"<command-name>/friction</command-name>"}]}}
{"type":"user","timestamp":"2026-08-26T10:00:12.000Z","message":{"role":"user","content":"<command-message>friction is analyzing…</command-message>"}}
{"type":"user","timestamp":"2026-08-26T10:00:13.000Z","message":{"role":"user","content":"<command-args>T-5 gate churn</command-args>"}}
{"type":"user","timestamp":"2026-08-26T10:00:14.000Z","message":{"role":"user","content":"<local-command-stdout>friction note recorded</local-command-stdout>"}}
{"type":"user","timestamp":"2026-08-26T10:00:15.000Z","message":{"role":"user","content":"<local-command-caveat>caveat: not a real prompt</local-command-caveat>"}}
{"type":"user","timestamp":"2026-08-26T10:00:16.000Z","message":{"role":"user","content":[{"type":"text","text":"<system-reminder>lone reminder</system-reminder>"}]}}
{"type":"user","timestamp":"2026-08-26T10:00:17.000Z","message":{"role":"user","content":"[Request interrupted by user for tool use]"}}
{"type":"user","timestamp":"2026-08-26T10:00:18.000Z","message":{"role":"user","content":"This session is being continued from a previous conversation that ran out of context."}}
{"type":"user","timestamp":"2026-08-26T10:00:19.000Z","message":{"role":"user","content":"   \t  "}}
{"type":"user","timestamp":"2026-08-26T10:00:20.000Z","message":{"role":"user","content":""}}
{"type":"user","timestamp":"2026-08-26T10:00:21.000Z","message":{"role":"user","content":[]}}
{"type":"user","timestamp":"2026-08-26T10:00:22.000Z","message":{"role":"user","content":null}}
{"type":"user","timestamp":"2026-08-26T10:00:23.000Z","message":{"role":"user","content":42}}
{"type":"user","timestamp":"2026-08-26T10:00:24.000Z","message":{"role":"user","content":{"note":{"type":"text","text":"an object is not an array"}}}}
{"type":"assistant","timestamp":"2026-08-26T10:01:01.000Z","message":{"role":"assistant","model":"claude-opus-5","usage":{"input_tokens":10,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"output_tokens":5},"content":[{"type":"text","text":"done"}]}}
JSONL
# 20 rows satisfy the frozen `turns` predicate (the isMeta row and the two
# tool_result rows do not). Exactly 4 of those 20 are human under the r2 rule:
#   "do the thing"                               string, plain
#   ["please continue"]                          single text element
#   [<system-reminder>, "fix the bug…"]           marker FIRST, real prompt survives
#   ["ship it when green", <system-reminder>]     marker LAST, real prompt survives
# and, notably, NOT [<system-reminder>, <task-notification>] — every element discarded.
MIXED_TURNS=20
MIXED_HUMAN=4

# Fixture B — nothing but genuine human prompts, including one carrying an
# appended reminder. Pins the REQ-005 upper boundary: human_turns == turns.
allhuman="$tmp/all-human.jsonl"
cat > "$allhuman" <<'JSONL'
{"type":"user","timestamp":"2026-08-26T11:00:00.000Z","message":{"role":"user","content":"first prompt"}}
{"type":"user","timestamp":"2026-08-26T11:00:01.000Z","message":{"role":"user","content":[{"type":"text","text":"second prompt"}]}}
{"type":"user","timestamp":"2026-08-26T11:00:02.000Z","message":{"role":"user","content":"  third prompt, leading space is not a marker"}}
{"type":"user","timestamp":"2026-08-26T11:00:03.000Z","message":{"role":"user","content":[{"type":"text","text":"fourth prompt"},{"type":"text","text":"<system-reminder>appended by the harness</system-reminder>"}]}}
{"type":"assistant","timestamp":"2026-08-26T11:00:04.000Z","message":{"role":"assistant","model":"claude-sonnet-4","usage":{"input_tokens":5,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"output_tokens":5},"content":[{"type":"text","text":"ok"}]}}
JSONL
ALLHUMAN_TURNS=4
ALLHUMAN_HUMAN=4

# Fixture C — nothing but harness noise, including all three r2 tags. Pins the
# REQ-005 lower boundary: human_turns == 0 while turns stays positive.
allnoise="$tmp/all-noise.jsonl"
cat > "$allnoise" <<'JSONL'
{"type":"user","timestamp":"2026-08-26T12:00:00.000Z","message":{"role":"user","content":"<task-notification>done</task-notification>"}}
{"type":"user","timestamp":"2026-08-26T12:00:01.000Z","message":{"role":"user","content":"<command-message>running</command-message>"}}
{"type":"user","timestamp":"2026-08-26T12:00:02.000Z","message":{"role":"user","content":"<command-args>--now</command-args>"}}
{"type":"user","timestamp":"2026-08-26T12:00:03.000Z","message":{"role":"user","content":"<local-command-caveat>caveat</local-command-caveat>"}}
{"type":"user","timestamp":"2026-08-26T12:00:04.000Z","message":{"role":"user","content":"  [Request interrupted by user]"}}
{"type":"user","timestamp":"2026-08-26T12:00:05.000Z","message":{"role":"user","content":"    "}}
{"type":"assistant","timestamp":"2026-08-26T12:00:06.000Z","message":{"role":"assistant","model":"claude-haiku-4","usage":{"input_tokens":5,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"output_tokens":5},"content":[{"type":"text","text":"ok"}]}}
JSONL
ALLNOISE_TURNS=6
ALLNOISE_HUMAN=0

# ---------------------------------------------------------------------------
# Drive the hook once per fixture, plus once with no transcript at all.
# ---------------------------------------------------------------------------
log="$tmp/costs.jsonl"
run_stop "$log" "$mixed"    "sess-mixed";     row_mixed="$(tail -1 "$log")"
run_stop "$log" "$allhuman" "sess-all-human"; row_allhuman="$(tail -1 "$log")"
run_stop "$log" "$allnoise" "sess-all-noise"; row_allnoise="$(tail -1 "$log")"
run_stop "$log" ""          "sess-zero";      row_zero="$(tail -1 "$log")"

rows="row_mixed row_allhuman row_allnoise row_zero"
for label in $rows; do
  jq -e . >/dev/null 2>&1 <<<"${!label}" \
    || { printf 'FAIL: the hook emitted a record that is not valid JSON (%s)\n' "$label" >&2; exit 1; }
done

printf '\n--- REQ-001  human_turns is present in every cost-log record ---------------\n'
for label in $rows; do
  if jq -e 'has("human_turns")' >/dev/null 2>&1 <<<"${!label}"; then
    pass "REQ-001 $label carries the 'human_turns' field"
  else
    fail "REQ-001 $label is MISSING the 'human_turns' field — the hook does not emit it"
  fi
done
note "(row_zero is the no-transcript record, which REQ-001 covers explicitly)"

printf '\n--- REQ-002  human_turns counts genuine human prompts only -----------------\n'
assert_eq "REQ-002 mixed: $MIXED_HUMAN human prompts among $MIXED_TURNS turns" \
  "$(human_turns_of "$row_mixed")" "$MIXED_HUMAN"
assert_eq "REQ-002 all-human transcript" \
  "$(human_turns_of "$row_allhuman")" "$ALLHUMAN_HUMAN"
assert_eq "REQ-002 all-noise transcript counts nothing" \
  "$(human_turns_of "$row_allnoise")" "$ALLNOISE_HUMAN"
assert_eq "REQ-002 no-transcript zero record" \
  "$(human_turns_of "$row_zero")" "0"
note "discard-then-check cases in the mixed fixture:"
note "  [marker, prompt] -> human      [prompt, marker] -> human"
note "  [marker, marker] -> NOT human  (every element discarded)"
note "excluded tags exercised: <task-notification> (leading whitespace), <command-name>,"
note "  <command-message>, <command-args>, <local-command-stdout>, <local-command-caveat>,"
note "  <system-reminder>, [Request interrupted, the compaction notice"
note "no-text-element shapes exercised: \"\", whitespace-only, [], null, a number, an object"

printf '\n--- REQ-003  turns is behaviourally unchanged ------------------------------\n'
assert_eq "REQ-003 mixed: turns matches the independently re-derived predicate" \
  "$(jq -r '.turns' <<<"$row_mixed")" "$(frozen_turns "$mixed")"
assert_eq "REQ-003 mixed: turns is still $MIXED_TURNS" \
  "$(jq -r '.turns' <<<"$row_mixed")" "$MIXED_TURNS"
assert_eq "REQ-003 all-human: turns matches the re-derived predicate" \
  "$(jq -r '.turns' <<<"$row_allhuman")" "$(frozen_turns "$allhuman")"
assert_eq "REQ-003 all-human: turns is still $ALLHUMAN_TURNS" \
  "$(jq -r '.turns' <<<"$row_allhuman")" "$ALLHUMAN_TURNS"
assert_eq "REQ-003 all-noise: turns matches the re-derived predicate" \
  "$(jq -r '.turns' <<<"$row_allnoise")" "$(frozen_turns "$allnoise")"
assert_eq "REQ-003 all-noise: turns is still $ALLNOISE_TURNS (noise rows stay in turns)" \
  "$(jq -r '.turns' <<<"$row_allnoise")" "$ALLNOISE_TURNS"
assert_eq "REQ-003 zero record: turns is still 0" \
  "$(jq -r '.turns' <<<"$row_zero")" "0"

printf '\n--- REQ-004  pre-existing fields intact; human_turns immediately after turns \n'
legacy='["ts","project","session","runtime_session_id","model","in","cache_write","cache_read","out","cost_usd","turns","assistant_msgs","tool_calls","duration_s"]'
for label in row_mixed row_zero; do
  actual="$(jq -c 'keys_unsorted | map(select(. != "human_turns"))' <<<"${!label}")"
  assert_eq "REQ-004 $label legacy key order" "$actual" "$(jq -c . <<<"$legacy")"
done
# Position: human_turns must sit at index(turns)+1 in every record.
for label in $rows; do
  pos="$(jq -r 'keys_unsorted as $k
                | ($k | index("human_turns")) as $h
                | ($k | index("turns")) as $t
                | if $h == null then "<absent>"
                  elif $t == null then "<no-turns-field>"
                  else ($k[$t+1] // "<end-of-object>") end' <<<"${!label}")"
  assert_eq "REQ-004 $label: the key immediately after 'turns'" "$pos" "human_turns"
done
type_check() { # type_check <row-label> <field> <jq type>
  local got; got="$(jq -r --arg f "$2" '.[$f] | type' <<<"${!1}")"
  assert_eq "REQ-004 $1 .$2 is $3" "$got" "$3"
}
for f in ts project session runtime_session_id model; do type_check row_mixed "$f" string; done
for f in in cache_write cache_read out cost_usd turns assistant_msgs tool_calls duration_s; do
  type_check row_mixed "$f" number
done
assert_eq "REQ-004 mixed .model is still the last model seen" \
  "$(jq -r '.model' <<<"$row_mixed")" "claude-opus-5"
assert_eq "REQ-004 mixed .in is still summed from the transcript" \
  "$(jq -r '.in' <<<"$row_mixed")" "130"
assert_eq "REQ-004 mixed .assistant_msgs unchanged" \
  "$(jq -r '.assistant_msgs' <<<"$row_mixed")" "3"
assert_eq "REQ-004 mixed .tool_calls unchanged" \
  "$(jq -r '.tool_calls' <<<"$row_mixed")" "2"
assert_eq "REQ-004 mixed .duration_s unchanged" \
  "$(jq -r '.duration_s' <<<"$row_mixed")" "61"
jq -e '.cost_usd > 0' >/dev/null <<<"$row_mixed" \
  && pass "REQ-004 mixed .cost_usd is still computed" \
  || fail "REQ-004 mixed .cost_usd is no longer computed"
grep -q 'AGENTOPS_COST_LOG:-/projects/dev/.claude/session-costs.jsonl' "$stop_hook" \
  && pass "REQ-004 the default cost-log path is preserved" \
  || fail "REQ-004 the default cost-log path was changed"

printf '\n--- REQ-005  human_turns never exceeds turns -------------------------------\n'
for label in $rows; do
  if ! jq -e 'has("human_turns")' >/dev/null 2>&1 <<<"${!label}"; then
    fail "REQ-005 $label: cannot compare, 'human_turns' is absent"
  elif jq -e '(.human_turns | type) != "number"' >/dev/null 2>&1 <<<"${!label}"; then
    fail "REQ-005 $label: 'human_turns' is not a number, got $(jq -c '.human_turns' <<<"${!label}")"
  elif jq -e '.human_turns <= .turns and .human_turns >= 0' >/dev/null 2>&1 <<<"${!label}"; then
    pass "REQ-005 $label: 0 <= human_turns ($(jq -r '.human_turns' <<<"${!label}")) <= turns ($(jq -r '.turns' <<<"${!label}"))"
  else
    fail "REQ-005 $label: human_turns=$(jq -r '.human_turns' <<<"${!label}") exceeds turns=$(jq -r '.turns' <<<"${!label}")"
  fi
done

printf '\n--- REQ-006  the auditctl --metadata key list includes human_turns ---------\n'
# Observed through the stub auditctl, not by grepping the hook, so a restructured
# implementation is judged on the blob it actually publishes.
check_metadata() { # check_metadata <session> <row-label>
  local capture="$tmp/meta-$1.json" label="$2" blob
  if [[ ! -s "$capture" ]]; then
    fail "REQ-006 $1: the hook published no auditctl --metadata blob at all"
    return
  fi
  blob="$(tail -1 "$capture")"
  if ! jq -e . >/dev/null 2>&1 <<<"$blob"; then
    fail "REQ-006 $1: the --metadata argument is not valid JSON"
    return
  fi
  if jq -e 'has("human_turns")' >/dev/null 2>&1 <<<"$blob"; then
    pass "REQ-006 $1: metadata carries 'human_turns'"
    assert_eq "REQ-006 $1: metadata human_turns agrees with the cost row" \
      "$(jq -r '.human_turns | tostring' <<<"$blob")" "$(human_turns_of "${!label}")"
  else
    fail "REQ-006 $1: the auditctl --metadata key list OMITS 'human_turns' (keys: $(jq -c 'keys_unsorted' <<<"$blob"))"
  fi
  # The key list is in scope only for the addition; nothing may drop out of it.
  local missing=""
  for k in session runtime_session_id turns assistant_msgs tool_calls duration_s \
           cost_usd model project gates rework_rounds; do
    jq -e --arg k "$k" 'has($k)' >/dev/null 2>&1 <<<"$blob" || missing="$missing $k"
  done
  [[ -z "$missing" ]] \
    && pass "REQ-006 $1: every pre-existing metadata key survives" \
    || fail "REQ-006 $1: metadata key(s) dropped:$missing"
}
check_metadata sess-mixed row_mixed
check_metadata sess-zero  row_zero
note "(the stub auditctl also guarantees the real audit store is never written)"

printf '\n'
if (( failures > 0 )); then
  printf '%d assertion(s) failed — human_turns is not implemented to spec revision 2\n' "$failures" >&2
  exit 1
fi
printf 'human_turns tests passed\n'
