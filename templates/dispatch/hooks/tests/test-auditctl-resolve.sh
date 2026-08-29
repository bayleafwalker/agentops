#!/usr/bin/env bash
# Gate for the publisher-resolution defect measured 2026-08-29: the 08-28 and 08-29 audit
# shards carry zero claude-hook events while the cost log carries 9 and 2 sessions, and
# CLI-sourced writes on the same days succeeded.
#
#   REQ-020 a hook shell whose PATH holds only the *other* auditctl still publishes
#   REQ-021 AUDITCTL_BIN wins over anything on PATH
#   REQ-022 a real publisher on PATH is still used, so a stub or venv install keeps working
#   REQ-023 no publisher anywhere degrades quietly, with the cost row still written
#   REQ-024 both publishing hooks resolve through the shared helper, not `command -v`
#   REQ-025 no caller sets AUDITCTL_ARTIFACTS_ROOT -- the publisher decides its own root
#   REQ-026 two repos publishing with no root set land under their own repositories
#
# The decoy is an ELF, because that is what makes the live collision undetectable: the
# kernel audit tool answers to the name, exits 0, and prints to stderr, so a call ending in
# `|| true` drops the record without a trace. A compiled `true` stands in for it -- same
# shape (compiled, exits 0, writes nothing), no dependency on the `audit` package.
set -uo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
hooks_dir="$(cd -- "$here/.." && pwd -P)"
stop_hook="$hooks_dir/log-session-cost.sh"
subagent_hook="$hooks_dir/subagent-exit.sh"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
assert_eq() { [[ "$2" == "$3" ]] || fail "$1: expected '$3', got '$2'"; }

[[ -f "$stop_hook" ]]     || fail "subject hook is missing: $stop_hook"
[[ -f "$subagent_hook" ]] || fail "subject hook is missing: $subagent_hook"

transcript="$tmp/transcript.jsonl"
cat > "$transcript" <<'JSONL'
{"type":"user","timestamp":"2026-08-29T10:00:00.000Z","message":{"role":"user","content":"do the thing"}}
{"type":"assistant","timestamp":"2026-08-29T10:00:10.000Z","message":{"role":"assistant","model":"claude-opus-5","usage":{"input_tokens":100,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"output_tokens":40},"content":[{"type":"tool_use","name":"Bash"}]}}
JSONL

# A publisher that records the fact it ran. Anything that reaches this file is a real publish.
mk_publisher() { # $1 = dir, $2 = tag
  mkdir -p "$1"
  cat > "$1/auditctl" <<STUB
#!/usr/bin/env bash
printf '%s\n' "$2" >> "\$AUDITCTL_CALL_LOG"
STUB
  chmod +x "$1/auditctl"
}

# The colliding binary: compiled, named auditctl, exits 0, publishes nothing.
# Any ELF that exits 0 will do, and the fixture must find one on a host without /bin/true
# -- devbox is NixOS, where /bin holds only sh. Naming candidates rather than one path
# keeps this test runnable on exactly the hosts a downgrade would hurt most.
decoy_dir="$tmp/decoy"; mkdir -p "$decoy_dir"
decoy_src=""
for candidate in /bin/true /usr/bin/true "$(command -v true 2>/dev/null || true)" \
                 "$(command -v env 2>/dev/null || true)"; do
  [[ -n "$candidate" && -f "$candidate" && -x "$candidate" ]] || continue
  [[ "$(head -c 4 -- "$candidate" 2>/dev/null)" == $'\x7fELF' ]] || continue
  decoy_src="$candidate"; break
done
[[ -n "$decoy_src" ]] \
  || fail "fixture: no compiled executable found to stand in for the kernel audit tool"
cp "$decoy_src" "$decoy_dir/auditctl"
[[ "$(head -c 4 -- "$decoy_dir/auditctl")" == $'\x7fELF' ]] \
  || fail "fixture: the decoy must be a compiled executable, or it tests nothing"

path_dir="$tmp/pathbin"
home_dir="$tmp/home"          # stands in for $HOME, so ~/.local/bin is under our control
export AUDITCTL_CALL_LOG="$tmp/calls.log"

# Runs the Stop hook with a controlled PATH and HOME, echoing what the publisher recorded.
run_stop() { # $1 = PATH, rest = extra env assignments
  local path="$1"; shift
  : > "$AUDITCTL_CALL_LOG"
  jq -cn --arg t "$transcript" \
    '{transcript_path:$t, session_id:"sess-resolve", cwd:"/projects/dev/agentops", hook_event_name:"Stop"}' \
    | env -u AUDITCTL_ARTIFACTS_ROOT -u AUDITCTL_BIN \
        PATH="$path" HOME="$home_dir" \
        AGENTOPS_COST_LOG="$tmp/costs.jsonl" AGENTOPS_GATE_LOG_DIR="$tmp/state" \
        AUDITCTL_CALL_LOG="$AUDITCTL_CALL_LOG" "$@" bash "$stop_hook"
  cat "$AUDITCTL_CALL_LOG"
}

run_subagent() { # $1 = PATH, rest = extra env assignments
  local path="$1"; shift
  : > "$AUDITCTL_CALL_LOG"
  jq -cn --arg t "$transcript" \
    '{transcript_path:$t, session_id:"sess-resolve", cwd:"/projects/dev/agentops", hook_event_name:"SubagentStop"}' \
    | env -u AUDITCTL_ARTIFACTS_ROOT -u AUDITCTL_BIN \
        PATH="$path" HOME="$home_dir" \
        AUDITCTL_CALL_LOG="$AUDITCTL_CALL_LOG" "$@" bash "$subagent_hook"
  cat "$AUDITCTL_CALL_LOG"
}

# A PATH that has the ordinary tools (jq, bash, coreutils) and no auditctl of any kind.
#
# It cannot be written as /usr/bin:/bin -- on NixOS those hold almost nothing, and the
# fixture then fails for want of bash instead of testing resolution. It also cannot be the
# caller's PATH with auditctl-holding directories dropped: on this workstation the kernel
# audit tool *is* /usr/bin/auditctl, so dropping that directory takes jq and coreutils with
# it, and REQ-023 ("no publisher anywhere") would pass for the wrong reason.
#
# So shadow it: one directory of symlinks to every executable the caller can reach, minus
# anything named auditctl. Same tools, one name missing, on any host.
shadow="$tmp/shadow"; mkdir -p "$shadow"
while IFS= read -r -d: dir || [[ -n "$dir" ]]; do
  [[ -n "$dir" && -d "$dir" ]] || continue
  for entry in "$dir"/*; do
    [[ -x "$entry" && ! -d "$entry" ]] || continue
    name="${entry##*/}"
    [[ "$name" == "auditctl" ]] && continue
    [[ -e "$shadow/$name" ]] && continue   # first on PATH wins, as it would have
    ln -s "$entry" "$shadow/$name" 2>/dev/null || true
  done
done < <(printf '%s:' "$PATH")
base_path="$shadow"
[[ -e "$shadow/auditctl" ]] \
  && fail "fixture: the auditctl-free PATH still holds an auditctl"
for tool in jq bash; do
  PATH="$base_path" command -v "$tool" >/dev/null 2>&1 \
    || fail "fixture: $tool is not reachable on the auditctl-free PATH"
done

# --- REQ-020: PATH holds only the decoy; ours is at ~/.local/bin ------------------------
mk_publisher "$home_dir/.local/bin" "home"
assert_eq "REQ-020 stop"     "$(run_stop     "$decoy_dir:$base_path")" "home"
assert_eq "REQ-020 subagent" "$(run_subagent "$decoy_dir:$base_path")" "home"

# --- REQ-022: a genuine publisher earlier on PATH is preferred over ~/.local/bin --------
mk_publisher "$path_dir" "path"
assert_eq "REQ-022 stop"     "$(run_stop     "$path_dir:$decoy_dir:$base_path")" "path"
assert_eq "REQ-022 subagent" "$(run_subagent "$path_dir:$decoy_dir:$base_path")" "path"

# ...and the decoy is skipped rather than merely outranked, even when it comes first.
assert_eq "REQ-022 decoy-first" "$(run_stop "$decoy_dir:$path_dir:$base_path")" "path"

# --- REQ-021: an explicit AUDITCTL_BIN wins ---------------------------------------------
mk_publisher "$tmp/explicit" "explicit"
assert_eq "REQ-021 stop" \
  "$(run_stop "$path_dir:$base_path" AUDITCTL_BIN="$tmp/explicit/auditctl")" "explicit"
assert_eq "REQ-021 subagent" \
  "$(run_subagent "$path_dir:$base_path" AUDITCTL_BIN="$tmp/explicit/auditctl")" "explicit"

# --- REQ-023: nothing to publish with is not an error, and costs the row nothing --------
rm -f "$home_dir/.local/bin/auditctl"
: > "$tmp/costs.jsonl"
out="$(run_stop "$decoy_dir:$base_path")"; rc=$?
assert_eq "REQ-023 exit"      "$rc" "0"
assert_eq "REQ-023 published" "$out" ""
assert_eq "REQ-023 cost row"  "$(jq -r '.session' < "$tmp/costs.jsonl" | tail -1)" "sess-resolve"

run_subagent "$decoy_dir:$base_path" >/dev/null
assert_eq "REQ-023 subagent exit" "$?" "0"

# --- REQ-024: neither hook resolves the publisher on its own ----------------------------
# A hook that grows its own `command -v auditctl` back is the exact regression this gate
# exists for, and it would pass every fixture above while failing in a real hook shell.
# Comment lines are stripped first: both hooks name the broken idiom in prose, explaining
# what it cost, and that prose is the reason the regression stays fixed.
for hook in "$stop_hook" "$subagent_hook"; do
  code="$(grep -v '^[[:space:]]*#' "$hook")"
  grep -q 'command -v auditctl' <<<"$code" \
    && fail "REQ-024: $(basename "$hook") resolves auditctl itself; use auditctl_bin"
  grep -q 'auditctl_bin' <<<"$code" \
    || fail "REQ-024: $(basename "$hook") does not resolve through auditctl_bin"
done

# --- REQ-025: no caller sets the artifacts root; the publisher decides it ---------------
# auditctl <= 0.1.3 read the shard root only from AUDITCTL_ARTIFACTS_ROOT while deriving the
# index and repo_id by walking up from the CWD, so a caller that named one repository sent
# every session's shards there while each indexed at its own root -- `rebuild` then reported
# the events as index-only, which reads as data loss. Measured 2026-08-29: 11 dev-scope
# events written into agentops/_artifacts/dev/audit/, invisible to their own index.
#
# auditctl 0.1.4 removed the precondition: the root defaults to the repository auditctl
# itself resolves, and an explicit value may only confirm that resolution, never redirect it.
# So the fix here is not a better walk in bash -- it is no walk in bash. This guard is
# written against the class rather than against the one hook that had the bug: *any*
# publishing hook that assigns this variable has taken a decision that is not its to take,
# whatever value it assigns and however it derived it.
resolve_sh="$hooks_dir/auditctl-resolve.sh"

for hook in "$resolve_sh" "$stop_hook" "$subagent_hook"; do
  code="$(grep -v '^[[:space:]]*#' "$hook")"
  grep -qE '(export|setdefault)?[[:space:]]*AUDITCTL_ARTIFACTS_ROOT=' <<<"$code" \
    && fail "REQ-025: $(basename "$hook") sets AUDITCTL_ARTIFACTS_ROOT; the publisher decides its own root"
  grep -q 'auditctl_export_root' <<<"$code" \
    && fail "REQ-025: $(basename "$hook") still calls the retired auditctl_export_root"
done
grep -v '^[[:space:]]*#' "$resolve_sh" | grep -q '/projects/dev/[a-z]' \
  && fail "REQ-025: auditctl-resolve.sh names a specific repository in code"

# --- REQ-026: two repos publishing with no root set land in their own repositories -------
# The falsifier for the whole arrangement, measured against the installed publisher rather
# than asserted about it: with AUDITCTL_ARTIFACTS_ROOT unset, an event added from repo A
# must appear under A and an event added from repo B under B. If auditctl is ever downgraded
# below 0.1.4 on a host, this is what catches it -- the version that needs the export back
# fails here rather than silently misrouting a day of shards.
publisher="$( unset AUDITCTL_BIN; . "$resolve_sh"; auditctl_bin || true )"
if [[ -n "$publisher" && -x "$publisher" ]]; then
  for name in alpha beta; do
    repo="$tmp/scoped-$name"; mkdir -p "$repo/.git" "$repo/sub"
    ( cd "$repo/sub" && unset AUDITCTL_ARTIFACTS_ROOT AUDITCTL_DB \
      && "$publisher" add --type workflow.friction --source resolve-test --actor resolve-test \
         --summary "scope probe $name" >/dev/null 2>&1 ) \
      || fail "REQ-026: publishing from $repo/sub failed with no artifacts root set"
    shard="$(find "$repo/_artifacts" -name 'events-*.ndjson' 2>/dev/null | head -1)"
    [[ -n "$shard" ]] \
      || fail "REQ-026: no shard under $repo after publishing from it -- the root did not follow the session"
    grep -q "scope probe $name" "$shard" \
      || fail "REQ-026: $repo shard does not carry its own event"
  done
  [[ -z "$(find "$tmp/scoped-alpha/_artifacts" -name 'events-*.ndjson' -exec grep -l 'scope probe beta' {} + 2>/dev/null)" ]] \
    || fail "REQ-026: beta's event landed under alpha -- shards are crossing repositories"
else
  printf 'skip: REQ-026 needs the auditctl publisher installed\n' >&2
fi

printf 'ok: test-auditctl-resolve (REQ-020..REQ-026)\n'
