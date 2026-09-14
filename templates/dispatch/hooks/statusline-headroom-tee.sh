#!/usr/bin/env bash
# Statusline stdin tee: captures Claude Code's statusline JSON for
# headroom_writer.py to read later, without disturbing the statusline itself.
#
# Intended use (not wired here): prepend this to the existing statusline
# command, e.g.
#   statusline-headroom-tee.sh | <existing statusline jq pipeline>
# It reads all of stdin, writes it atomically to
# ${HEADROOM_STATE_DIR:-$HOME/.local/state/headroom}/claude-statusline.json,
# then prints stdin back out unchanged so the downstream statusline command
# sees exactly what it would have seen without this hook in the pipeline.
#
# Must never break the statusline: any failure to write the tee file is
# swallowed, stdin is still passed through, and the script always exits 0.

set -u

state_dir="${HEADROOM_STATE_DIR:-$HOME/.local/state/headroom}"
target="$state_dir/claude-statusline.json"

input="$(cat)"

{
  mkdir -p "$state_dir" 2>/dev/null &&
  tmp="$(mktemp "$state_dir/.claude-statusline.json.XXXXXX" 2>/dev/null)" &&
  printf '%s' "$input" > "$tmp" 2>/dev/null &&
  mv -f "$tmp" "$target" 2>/dev/null
} || true

printf '%s' "$input"
exit 0
