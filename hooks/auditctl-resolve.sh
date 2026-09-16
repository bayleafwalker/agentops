#!/usr/bin/env bash
# Sourced by every hook that publishes to auditctl. One job, which has silently dropped
# telemetry when a hook did it on its own:
#
#   auditctl_bin -- resolve *our* publisher, not merely something named `auditctl`
#
# It used to have a second, `auditctl_export_root`, which mirrored auditctl's own walk in
# bash to default AUDITCTL_ARTIFACTS_ROOT. auditctl 0.1.4 made the root default to the
# repository it resolves, and 0.1.5 is what runs on every host that publishes (workstation,
# devbox, vuoro-shared), so that export can no longer change an outcome -- it can only fail
# closed when the two walks drift apart. Three resolvers is worse than two: retired here,
# and the publisher is now the only thing that decides where its own writes land.
#
# Why resolution is not `command -v auditctl`:
#   `auditctl` is also the Linux kernel audit control tool, /usr/bin/auditctl, owned by the
#   `audit` package (installed on this host 2026-07-31). Ours is a uv-installed Python
#   console script in ~/.local/bin. A hook shell without ~/.local/bin on PATH -- Stop and
#   SubagentStop inherit neither a login shell nor direnv -- resolves the name to the kernel
#   tool, which answers "You must be root to run this program." and exits 0. With the
#   publisher call ending in `|| true`, the record is dropped without a trace. Measured
#   2026-08-29: the 08-28 and 08-29 shards carry zero claude-hook events while the cost log
#   carries 9 and 2 sessions, and CLI-sourced writes on the same days succeeded.
#
#   This is also why an `[[ -x $HOME/.local/bin/auditctl ]]` fallback placed *behind*
#   `command -v` does not help: `command -v` succeeds, on the wrong binary, so the fallback
#   never runs.
#
# The guard is written against the class -- "a different program answers to this name" --
# rather than against the one colliding package: a candidate is rejected when it is
# demonstrably not ours (a compiled executable; our publisher is and has always been a
# script), never accepted only when it matches a shape we recognise. If our own auditctl is
# ever rewritten as a compiled binary it is still reached through AUDITCTL_BIN or its known
# install location, and the failure direction of a wrong guess stays "publish anyway"
# rather than "silently stop publishing".
#
# Everything here is written with shell builtins where it can be. A hook shell's PATH is
# exactly the thing that cannot be trusted -- that is the defect above -- and a caller whose
# PATH lacks `head` or `readlink` must still get an answer.

# Echoes the path to our auditctl and returns 0, or returns 1 if there is none to use.
# AUDITCTL_BIN is authoritative when *set*, empty included: that is how a test says "no
# publisher exists" now that an absent one can no longer be expressed by emptying PATH.
auditctl_bin() {
  if [[ -n "${AUDITCTL_BIN+set}" ]]; then
    [[ -n "$AUDITCTL_BIN" && -x "$AUDITCTL_BIN" ]] || return 1
    printf '%s\n' "$AUDITCTL_BIN"; return 0
  fi
  local candidate magic
  # PATH order first, so a test stub or a virtualenv install still wins, skipping any
  # candidate that is a compiled executable.
  while IFS= read -r candidate; do
    [[ -x "$candidate" && -r "$candidate" ]] || continue
    magic=""
    LC_ALL=C read -r -N 4 magic < "$candidate" 2>/dev/null || true
    [[ "$magic" == $'\x7fELF' ]] && continue
    printf '%s\n' "$candidate"; return 0
  done < <(type -a -P auditctl 2>/dev/null || true)
  # The known install location, reached when PATH held only the colliding binary, or nothing.
  if [[ -x "$HOME/.local/bin/auditctl" ]]; then
    printf '%s\n' "$HOME/.local/bin/auditctl"; return 0
  fi
  return 1
}
