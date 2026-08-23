#!/usr/bin/env bash
# Show per-project session cost summary from /projects/dev/.claude/session-costs.jsonl
# Usage: cost-summary [project-name-filter]
set -euo pipefail

LOG="/projects/dev/.claude/session-costs.jsonl"
[[ -f "$LOG" ]] || { echo "No session log yet at $LOG"; exit 0; }

FILTER="${1:-.}"

# The Stop hook fires once per assistant turn and each record is a cumulative snapshot of the
# session so far, so rows for one session supersede each other. Reduce to the newest row per
# session before aggregating: summing every row over-counts roughly quadratically.
jq -rs --arg filter "$FILTER" '
  group_by(.session) | map(sort_by(.ts) | last)
  | [ .[] | select(.project | test($filter)) ]
  | group_by(.project)[]
  | {
      project:     .[0].project,
      sessions:    length,
      total_in:    ([.[].in]          | add // 0),
      total_cw:    ([.[].cache_write] | add // 0),
      total_cr:    ([.[].cache_read]  | add // 0),
      total_out:   ([.[].out]         | add // 0),
      total_cost:  ([.[].cost_usd]    | add // 0 | . * 100 | round / 100),
      avg_cost:    (([.[].cost_usd]   | add // 0) / length | . * 1000 | round / 1000),
      models:      ([.[].model] | unique | join(", "))
    }
  | "\(.project)  sessions=\(.sessions)  in=\(.total_in)  cache_write=\(.total_cw)  cache_read=\(.total_cr)  out=\(.total_out)  total=$\(.total_cost)  avg=$\(.avg_cost)/session  models=\(.models)"
' "$LOG"
