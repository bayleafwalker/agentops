#!/usr/bin/env bash
# Claude Code UserPromptSubmit hook — one line of warning when the context
# window is filling, so a handoff gets written while there is still room to
# write it.
#
# Not a stop and deliberately not a stop: the plan's threshold (60% of a 1M
# window) is where the measured corpus's long sessions sat when quality visibly
# dropped, not a limit. It is a guess to calibrate, so blocking on it would
# convert a guess into an outage. One line, on stdout, which Claude Code adds to
# the turn as context.
#
# Reads the same field the status line does, from the transcript's last
# assistant `usage` block rather than from any harness API: the transcript is
# the one source a hook can always reach.
#
# Env:
#   HANDOFF_THRESHOLD_PCT   integer percent, default 60
#   HANDOFF_CONTEXT_WINDOW  override the assumed window in tokens
set -uo pipefail

EVENT="$(cat)"
command -v jq >/dev/null 2>&1 || exit 0

TRANSCRIPT="$(printf '%s' "$EVENT" | jq -r '.transcript_path // ""')"
[[ -n "$TRANSCRIPT" && -r "$TRANSCRIPT" ]] || exit 0

THRESHOLD="${HANDOFF_THRESHOLD_PCT:-60}"

# The last assistant message that carries a usage block. Cache reads and cache
# writes are part of the prompt that was sent, so they count toward the window;
# leaving them out understates a cached session by most of its context.
read -r USED MODEL <<<"$(
  jq -rs '
    [ .[]
      | select(.type == "assistant" and .message.usage != null)
    ] | last
    | if . == null then "0 unknown"
      else
        ( (.message.usage.input_tokens                // 0)
        + (.message.usage.cache_read_input_tokens     // 0)
        + (.message.usage.cache_creation_input_tokens // 0)
        + (.message.usage.output_tokens               // 0)
        | tostring )
        + " " + (.message.model // "unknown")
      end
  ' "$TRANSCRIPT" 2>/dev/null || echo "0 unknown"
)"
[[ "$USED" =~ ^[0-9]+$ ]] || exit 0
(( USED > 0 )) || exit 0

# 1M is the assumption; the model name is the only thing that may override it.
WINDOW=1000000
case "${MODEL,,}" in
  *"[1m]"*|*1m*)   WINDOW=1000000 ;;
  *haiku*)         WINDOW=200000 ;;
  *200k*)          WINDOW=200000 ;;
esac
WINDOW="${HANDOFF_CONTEXT_WINDOW:-$WINDOW}"
(( WINDOW > 0 )) || exit 0

PCT=$(( USED * 100 / WINDOW ))
if (( PCT >= THRESHOLD )); then
  printf 'context at %d%%: prepare a handoff (/handoff) before new changes\n' "$PCT"
fi
exit 0
