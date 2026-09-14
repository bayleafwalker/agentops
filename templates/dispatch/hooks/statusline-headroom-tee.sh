#!/usr/bin/env bash
# Statusline stdin tee: captures Claude Code's statusline JSON for
# headroom_writer.py to read later, without disturbing the statusline itself.
#
# Intended use (not wired here): prepend this to the existing statusline
# command, e.g.
#   statusline-headroom-tee.sh | <existing statusline jq pipeline>
# It reads all of stdin, writes it atomically to
# ${HEADROOM_STATE_DIR:-$HOME/.local/state/headroom}/claude-statusline.json,
# then prints stdin back out to stdout BYTE-EXACT (trailing newlines and all)
# so the downstream statusline command sees exactly what it would have seen
# without this hook in the pipeline. `input="$(cat)"` + `printf '%s'` would
# silently strip trailing newlines via command substitution -- this captures
# stdin into a file with a plain `cat` redirect instead, which is
# byte-transparent, and plays that file back with `cat`.
#
# Must never break the statusline: any failure to write the tee file is
# swallowed, stdin is still passed through, and the script always exits 0.

set -u

state_dir="${HEADROOM_STATE_DIR:-$HOME/.local/state/headroom}"
target="$state_dir/claude-statusline.json"

# Capture stdin exactly, once, into a temp file -- preferably inside
# state_dir, falling back to $TMPDIR/tmp if that directory can't be created
# or written to (e.g. an unwritable state dir). This capture file is the
# single source of truth for both the tee write and the passthrough, so a
# failure publishing to `target` can never affect what reaches stdout.
capture=""
if mkdir -p "$state_dir" 2>/dev/null; then
  capture="$(mktemp "$state_dir/.claude-statusline.stdin.XXXXXX" 2>/dev/null)" || capture=""
fi
if [ -z "$capture" ]; then
  capture="$(mktemp "${TMPDIR:-/tmp}/statusline-headroom-tee.XXXXXX" 2>/dev/null)" || capture=""
fi

if [ -n "$capture" ]; then
  cat > "$capture"

  # Best-effort atomic publish to the target, from a copy of the capture so
  # `capture` still holds the exact bytes to pass through even if this fails.
  {
    tmp_target="$(mktemp "$state_dir/.claude-statusline.json.XXXXXX" 2>/dev/null)" &&
    cp "$capture" "$tmp_target" 2>/dev/null &&
    mv -f "$tmp_target" "$target" 2>/dev/null
  } || true

  cat "$capture"
  rm -f "$capture" 2>/dev/null
else
  # No temp file could be created anywhere (state dir and $TMPDIR both
  # unwritable): tee is impossible, but the statusline must still see its
  # input unchanged, so stream it straight through.
  cat
fi

exit 0
