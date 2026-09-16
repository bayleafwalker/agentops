#!/usr/bin/env bash
# Every hooks/*.sh is tracked executable in the index, except the sourced-only library.
#
# Ported from templates/dispatch/tests/test_hook_executability.py for the top-level hook
# set. `core.fileMode` is false in this repository, so a working copy can be 755 while
# the index says 644 -- and a clone receives the index mode. A hook registered by bare
# path at 644 exits 126 before reading stdin, which is invisible to `bash <hook>`. So the
# assertion is on the mode git records, which is the thing that travels.
set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
hooks_dir="$(cd -- "$here/.." && pwd -P)"
root="$(git -C "$hooks_dir" rev-parse --show-toplevel)"

# Sourced by its siblings, never executed: 644 is correct for it.
sourced_not_executed=" auditctl-resolve.sh "

fail=0
seen=0
while IFS= read -r line; do
  mode="${line%% *}"
  path="${line#*$'\t'}"
  name="${path##*/}"
  [[ "$path" == hooks/*.sh && "$path" != hooks/*/* ]] || continue
  seen=$((seen + 1))
  if [[ "$sourced_not_executed" == *" $name "* ]]; then
    [[ "$mode" == 100644 ]] || { printf 'FAIL: %s is sourced, expected 100644, index has %s\n' "$path" "$mode" >&2; fail=1; }
  else
    [[ "$mode" == 100755 ]] || { printf 'FAIL: %s is executed, expected 100755, index has %s\n' "$path" "$mode" >&2; fail=1; }
  fi
done < <(git -C "$root" ls-files -s -- hooks)

[[ "$seen" -gt 0 ]] || { printf 'FAIL: no tracked hooks/*.sh found\n' >&2; exit 1; }
[[ "$fail" -eq 0 ]] || exit 1
printf 'hook executability tests passed (%d hooks)\n' "$seen"
