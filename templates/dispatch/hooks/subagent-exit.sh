#!/usr/bin/env bash
# Claude Code SubagentStop hook — record that a dispatched unit ended, and why.
#
# Why this exists: before 2026-08-29 nothing in the harness observed a subagent ending.
# On 2026-08-28 three subagents died within 101 seconds against one session-scoped quota
# and the outcome existed only as the last line of each transcript, so nobody looked for
# roughly ten hours. All the state was on disk the whole time. The gap was a durable,
# queryable outcome -- not detection.
#
# The record uses auditctl's existing, already-validated vocabulary:
#   ACTIONQ_TERMINAL_REASON_CODES = completed | process-exit | start-failed | cancelled
#                                 | timeout | usage-limit | crash-inferred
# The validator has been live since its intended writer (actionq-daemon) was retired on
# 2026-08-22, with no producer. This is the producer.
#
# The loss predicate is then a join, not a heuristic: a dispatch with no exit record.
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

EVENT="$(cat)"
SESSION="$(printf '%s' "$EVENT" | jq -r '.session_id // "unknown"')"
TRANSCRIPT="$(printf '%s' "$EVENT" | jq -r '.transcript_path // ""')"
AGENT_ID="$(printf '%s' "$EVENT" | jq -r '.agent_id // .agentId // empty')"
HARNESS_AGENT_TRANSCRIPT="$(printf '%s' "$EVENT" | jq -r '.agent_transcript_path // empty')"
PROJ="$(printf '%s' "$EVENT" | jq -r '.cwd // ""' | xargs basename 2>/dev/null || basename "$PWD")"

# `transcript_path` on a SubagentStop event is the PARENT session's transcript, not the
# subagent's own -- verified 2026-09-14 against agent ae70fc0a294de1cb0, whose event carried
# the parent session file while the agent's own turns live under that session's own
# directory: for parent `.../-projects-dev/279bc82d-....jsonl` the child is
# `.../-projects-dev/279bc82d-.../subagents/agent-<agent_id>.jsonl` -- the parent path with
# `.jsonl` stripped, NOT `dirname` of it (dirname gives `.../-projects-dev/`, which holds no
# `subagents/` of its own; confirmed present on disk at the stripped-suffix location). The
# Claude Code hooks reference (code.claude.com/docs/en/hooks.md, fetched 2026-09-14)
# documents `transcript_path` as one of the common fields shared by every hook event and
# lists no subagent-specific transcript field for SubagentStop, so nothing here can be
# assumed absent a future harness change. `agent_transcript_path` is read defensively above
# in case such a field ever ships; today it is always empty and the path below is derived
# instead.
#
# `transcript_path` in the published metadata is left as-is for compatibility (see below);
# this is purely about which file the terminal-reason parser reads from.
AGENT_TRANSCRIPT=""
if [[ -n "$HARNESS_AGENT_TRANSCRIPT" && -f "$HARNESS_AGENT_TRANSCRIPT" ]]; then
  AGENT_TRANSCRIPT="$HARNESS_AGENT_TRANSCRIPT"
elif [[ -n "$TRANSCRIPT" && -n "$AGENT_ID" ]]; then
  _agent_cand="${TRANSCRIPT%.jsonl}/subagents/agent-${AGENT_ID}.jsonl"
  [[ -f "$_agent_cand" ]] && AGENT_TRANSCRIPT="$_agent_cand"
fi

# The record actually read for terminal-reason parsing: the subagent's own transcript when
# it is resolvable, else the event's transcript_path (old behaviour, preserved as a
# fallback -- e.g. no agent_id on the event, or the subagent's file not yet on disk).
READ_TRANSCRIPT="$TRANSCRIPT"
[[ -n "$AGENT_TRANSCRIPT" ]] && READ_TRANSCRIPT="$AGENT_TRANSCRIPT"

# Resolving the publisher is shared with the Stop hook: `command -v auditctl` can succeed on
# the kernel audit tool of the same name, which is how the missing workflow.session events
# were actually lost. See hooks/auditctl-resolve.sh.
AUDITCTL="$(auditctl_bin)" || exit 0

# terminal_reason from the transcript's own terminal *record*, not from its prose.
#
# The first version of this matched the localized wall-clock string a usage limit shows the
# agent ("You've hit your session limit - resets 12:30am (Europe/Helsinki)") on the last
# three assistant text blocks, on the stated grounds that no machine-readable form arrives.
# That is false at the artifact. The terminating record carries `isApiErrorMessage: true`,
# `apiErrorStatus: 429`, `error: "rate_limit"` and, since ~2026-08, a `quotaLimits` object
# whose `resetsAt` is the exact epoch second the localized string renders. Verified against
# ~/.claude/projects/-projects-dev/5f65b838-.../subagents/agent-a5d642b86112f09ec.jsonl:
# resetsAt 1787952600 == 2026-08-29T00:30:00 Europe/Helsinki == the string it printed.
#
# Measured over all 353 subagent transcripts on this host, the text match produced 76
# non-`completed` verdicts where the records carry 19: every one of its 38 `timeout` and 5
# `cancelled` verdicts was spurious, and 14 of 33 `usage-limit`. The failure mode is
# structural, not a tuning problem -- a research subagent that *completes* and reports on
# rate limiting says "rate limits" in its final block, and prose about a failure is
# indistinguishable from the failure. Zero false negatives either way, so nothing is lost
# by reading the record instead.
REASON="completed"
RAW=""
RESET_AT=""
RESET_SOURCE=""
if [[ -n "$READ_TRANSCRIPT" && -f "$READ_TRANSCRIPT" ]]; then
  # Kept for the record, never for the verdict: the operator-visible text of the ending.
  RAW="$(tail -n 40 -- "$READ_TRANSCRIPT" 2>/dev/null \
    | jq -r 'select(.type == "assistant") | .message.content[]? | select(.type == "text") | .text' 2>/dev/null \
    | tail -n 3 || true)"

  # The last conversational record is the terminal one. Harness bookkeeping records
  # (file-history-snapshot, queue-operation, turn_duration summaries) can follow it, so
  # select by type rather than taking the literal last line.
  TERM="$(tail -n 12 -- "$READ_TRANSCRIPT" 2>/dev/null \
    | jq -s -c '[.[] | select(.type == "assistant" or .type == "user")] | last // {}' 2>/dev/null || echo '{}')"

  if [[ "$(printf '%s' "$TERM" | jq -r '.isApiErrorMessage // false')" == "true" ]]; then
    STATUS="$(printf '%s' "$TERM" | jq -r '.apiErrorStatus // empty')"
    ERRKIND="$(printf '%s' "$TERM" | jq -r '.error // empty')"
    QSTATUS="$(printf '%s' "$TERM" | jq -r '.quotaLimits.status // empty')"
    if [[ "$STATUS" == "429" || "$ERRKIND" == "rate_limit" || "$QSTATUS" == "rejected" ]]; then
      REASON="usage-limit"
      # The reset instant is derivable after all, when the field is present. Older
      # transcripts (pre-2026-08) carry the 429 with no quotaLimits, and those keep the
      # honest answer: the string was never parsed.
      EPOCH="$(printf '%s' "$TERM" | jq -r '.quotaLimits.resetsAt // empty')"
      if [[ -n "$EPOCH" ]]; then
        RESET_AT="$(date -u -d "@$EPOCH" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || true)"
        RESET_SOURCE="quotaLimits.resetsAt"
      else
        RESET_SOURCE="unparsed-local-string"
      fi
    elif [[ "$STATUS" == "408" || "$STATUS" == "504" || "$ERRKIND" == *timeout* ]]; then
      REASON="timeout"
    else
      REASON="process-exit"
    fi
  else
    # A user interrupt is written as its own record whose text is the marker, so this is
    # still the record and not the prose. No subagent transcript on this host ends this
    # way, so unlike the three reasons above it has never been observed -- it is here
    # because the marker is structural, not because a corpus demanded it.
    TERM_TEXT="$(printf '%s' "$TERM" \
      | jq -r '.message.content | if type == "string" then . else (.[]? | select(.type == "text") | .text) end' 2>/dev/null \
      | head -n 1 || true)"
    if [[ "$TERM_TEXT" == "[Request interrupted by user"* ]]; then REASON="cancelled"; fi
  fi
else
  # No transcript at all: the unit ended without producing one.
  REASON="crash-inferred"
fi

# Cascade harvest. A dying parent orphans children that already finished -- measured on
# 2026-08-28: four completed depth-2 children, 249 lines, lost with their parent. Their
# transcripts are siblings on disk, so name them here and the work stays recoverable.
#
# Siblings live at `${TRANSCRIPT%.jsonl}/subagents/agent-*.jsonl` (the same session
# directory derived for AGENT_TRANSCRIPT above), not `dirname(TRANSCRIPT)/agent-*.jsonl`.
# That was the same dirname-vs-stripped-suffix mistake as AGENT_TRANSCRIPT's original
# derivation: verified 2026-09-14 on this host, `dirname "$TRANSCRIPT"` (the shared
# `-projects-dev` sessions directory) holds zero `agent-*.jsonl` files directly, while 60
# exist under `*/subagents/agent-*.jsonl` -- so this block always published an empty
# sibling list in production, never actually harvesting anything.
CHILDREN="[]"
if [[ -n "$TRANSCRIPT" ]]; then
  subdir="${TRANSCRIPT%.jsonl}/subagents"
  if [[ -d "$subdir" ]]; then
    CHILDREN="$(find "$subdir" -maxdepth 1 -name 'agent-*.jsonl' -newermt '-6 hours' 2>/dev/null \
      | head -n 50 | jq -R -s -c 'split("\n") | map(select(length > 0))' 2>/dev/null || echo '[]')"
  fi
fi

METADATA="$(jq -cn \
  --arg session "$SESSION" --arg agent "$AGENT_ID" --arg project "$PROJ" \
  --arg reason "$REASON" --arg transcript "$TRANSCRIPT" --arg agent_transcript "$AGENT_TRANSCRIPT" \
  --arg raw "$(printf '%s' "$RAW" | tail -c 400)" \
  --arg reset_at "$RESET_AT" --arg reset_source "$RESET_SOURCE" \
  --argjson children "$CHILDREN" \
  '{session: $session, agent_id: $agent, project: $project, terminal_reason: $reason,
    transcript_path: $transcript,
    agent_transcript_path: (if $agent_transcript == "" then null else $agent_transcript end),
    raw_tail: $raw, sibling_transcripts: $children,
    reset_at: (if $reset_at == "" then null else $reset_at end),
    reset_source: (if $reset_source == "" then null else $reset_source end)}')"

"$AUDITCTL" add --type dispatch.exit --source claude-hook --actor claude-hook \
  --summary "subagent ended in $PROJ: $REASON" --metadata "$METADATA" >/dev/null 2>&1 || true
