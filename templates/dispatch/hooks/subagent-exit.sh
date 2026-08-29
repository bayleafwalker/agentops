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
  auditctl_export_root() { :; }
fi

EVENT="$(cat)"
SESSION="$(printf '%s' "$EVENT" | jq -r '.session_id // "unknown"')"
TRANSCRIPT="$(printf '%s' "$EVENT" | jq -r '.transcript_path // ""')"
AGENT_ID="$(printf '%s' "$EVENT" | jq -r '.agent_id // .agentId // empty')"
PROJ="$(printf '%s' "$EVENT" | jq -r '.cwd // ""' | xargs basename 2>/dev/null || basename "$PWD")"

# Resolving the publisher is shared with the Stop hook: `command -v auditctl` can succeed on
# the kernel audit tool of the same name, which is how the missing workflow.session events
# were actually lost. See hooks/auditctl-resolve.sh.
AUDITCTL="$(auditctl_bin)" || exit 0
auditctl_export_root "${BASH_SOURCE[0]}"

# terminal_reason from the transcript's own tail. A usage limit is reported to the agent as a
# localized wall-clock string ("resets 12:30am (Europe/Helsinki)"), never as Retry-After, so
# match the text and keep the raw line -- a derived reset instant must record how it was
# derived, and here it cannot be derived at all.
REASON="completed"
RAW=""
if [[ -n "$TRANSCRIPT" && -f "$TRANSCRIPT" ]]; then
  RAW="$(tail -n 40 "$TRANSCRIPT" 2>/dev/null \
    | jq -r 'select(.type == "assistant") | .message.content[]? | select(.type == "text") | .text' 2>/dev/null \
    | tail -n 3 || true)"
  shopt -s nocasematch
  if   [[ "$RAW" == *"session limit"* || "$RAW" == *"rate limit"* || "$RAW" == *"usage limit"* ]]; then REASON="usage-limit"
  elif [[ "$RAW" == *"timed out"* || "$RAW" == *"timeout"*   ]]; then REASON="timeout"
  elif [[ "$RAW" == *"cancelled"*  || "$RAW" == *"canceled"* ]]; then REASON="cancelled"
  fi
  shopt -u nocasematch
else
  # No transcript at all: the unit ended without producing one.
  REASON="crash-inferred"
fi

# Cascade harvest. A dying parent orphans children that already finished -- measured on
# 2026-08-28: four completed depth-2 children, 249 lines, lost with their parent. Their
# transcripts are siblings on disk, so name them here and the work stays recoverable.
CHILDREN="[]"
if [[ -n "$TRANSCRIPT" ]]; then
  subdir="$(dirname -- "$TRANSCRIPT")"
  if [[ -d "$subdir" ]]; then
    CHILDREN="$(find "$subdir" -maxdepth 1 -name 'agent-*.jsonl' -newermt '-6 hours' 2>/dev/null \
      | head -n 50 | jq -R -s -c 'split("\n") | map(select(length > 0))' 2>/dev/null || echo '[]')"
  fi
fi

METADATA="$(jq -cn \
  --arg session "$SESSION" --arg agent "$AGENT_ID" --arg project "$PROJ" \
  --arg reason "$REASON" --arg transcript "$TRANSCRIPT" \
  --arg raw "$(printf '%s' "$RAW" | tail -c 400)" \
  --argjson children "$CHILDREN" \
  '{session: $session, agent_id: $agent, project: $project, terminal_reason: $reason,
    transcript_path: $transcript, raw_tail: $raw, sibling_transcripts: $children,
    reset_source: (if $reason == "usage-limit" then "unparsed-local-string" else null end)}')"

"$AUDITCTL" add --type dispatch.exit --source claude-hook --actor claude-hook \
  --summary "subagent ended in $PROJ: $REASON" --metadata "$METADATA" >/dev/null 2>&1 || true
