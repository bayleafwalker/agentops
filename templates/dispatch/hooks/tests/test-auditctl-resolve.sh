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
#
# The decoy is an ELF, because that is what makes the live collision undetectable: the
# kernel audit tool answers to the name, exits 0, and prints to stderr, so a call ending in
# `|| true` drops the record without a trace. /bin/true stands in for it -- same shape
# (compiled, exits 0, writes nothing), no dependency on the `audit` package being installed.
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
decoy_dir="$tmp/decoy"; mkdir -p "$decoy_dir"
cp /bin/true "$decoy_dir/auditctl"
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

base_path="/usr/bin:/bin"     # jq, bash, coreutils -- but no auditctl of any kind

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

printf 'ok: test-auditctl-resolve (REQ-020..REQ-024)\n'
