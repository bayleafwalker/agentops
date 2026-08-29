#!/usr/bin/env bash
# Sourced by every hook that publishes to auditctl. Two jobs, both of which every publisher
# needs and each of which has silently dropped telemetry when a hook did it on its own:
#
#   auditctl_bin         -- resolve *our* publisher, not merely something named `auditctl`
#   auditctl_export_root -- default AUDITCTL_ARTIFACTS_ROOT from the single source
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

# Exports AUDITCTL_ARTIFACTS_ROOT if unset or empty.
#
# The root must be the repository the events are being published *for*, because auditctl
# resolves the two halves of a write from different places: `resolve_paths` derives the
# index and the `repo_id` by walking up from the CWD, while `require_artifacts_root` reads
# only this variable. `shard_path` then joins them --
# `<root>/_artifacts/<repo_id>/audit/events-<day>.ndjson` -- so a root that disagrees with
# the CWD writes a correct index and a shard under someone else's repository. The two do not
# reconcile, and `rebuild` reports the events as index-only, i.e. as data loss.
#
# That is not hypothetical. Between 7ae83fb and this change the default below was the literal
# string `/projects/dev/agentops`, so every session in every repo -- the hooks are symlinked
# into `/projects/dev/.claude/hooks/` and shared by all of them -- indexed at its own repo and
# appended under agentops. Measured 2026-08-29: 11 `dev`-scope events in
# `agentops/_artifacts/dev/audit/`, invisible to their own index.
#
# So derive the root by the same rule auditctl uses for the index (auditctl/paths.py:
# `_find_upward` for `.auditctl/` or `.git`) rather than naming any one repository. The data
# file remains the floor for a caller that is under neither marker; a repo-specific root
# belongs in that repo's .envrc, which is per-session and cannot leak into other repos.
#
# $1 is the calling hook's ${BASH_SOURCE[0]}, still resolved through symlinks for the
# fallback lookup, because the link's own directory is the wrong one.
auditctl_export_root() {
  [[ -n "${AUDITCTL_ARTIFACTS_ROOT:-}" ]] && return 0
  local default_root="" line dir

  # Walk up from the publishing session's directory, matching auditctl's own rule.
  dir="${PWD:-}"
  while [[ -n "$dir" && "$dir" != "/" ]]; do
    if [[ -d "$dir/.auditctl" || -e "$dir/.git" ]]; then
      export AUDITCTL_ARTIFACTS_ROOT="$dir"
      return 0
    fi
    dir="${dir%/*}"
  done

  local hook_src="${1:-${BASH_SOURCE[1]}}"
  if [[ -L "$hook_src" ]] && command -v readlink >/dev/null 2>&1; then
    hook_src="$(readlink -f -- "$hook_src" 2>/dev/null || printf '%s' "$hook_src")"
  fi
  local data="${hook_src%/*}/../artifacts-root.default"
  if [[ -r "$data" ]]; then
    read -r line < "$data" 2>/dev/null || line=""
    default_root="$line"
  fi
  export AUDITCTL_ARTIFACTS_ROOT="$default_root"
}
