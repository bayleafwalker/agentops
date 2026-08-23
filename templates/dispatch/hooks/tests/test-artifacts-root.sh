#!/usr/bin/env bash
# Gate for M-6a. One outcome, one command: the cost hook takes its AUDITCTL_ARTIFACTS_ROOT
# default from a single source, the data file `templates/dispatch/artifacts-root.default`.
#
#   REQ-006 an explicit AUDITCTL_ARTIFACTS_ROOT still wins, unchanged
#   REQ-007 with it unset the root is the contents of artifacts-root.default
#   REQ-008 that file is resolved relative to the hook, not to $PWD -- symlink included
#   REQ-009 the AUDITCTL_ARTIFACTS_ROOT line no longer hardcodes the default root
#   REQ-010 the cost-log and gate-log defaults are left untouched by that change
#   REQ-011 a missing or empty data file still exits 0 with the cost record written
#
# Subject: templates/dispatch/hooks/log-session-cost.sh and templates/dispatch/
# artifacts-root.default, and nothing else -- running this must not read any other file in
# the repository, and must not write into the checkout. Every fixture stubs `auditctl` on
# PATH, so no real audit write can reach `.auditctl/`.
set -uo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
hooks_dir="$(cd -- "$here/.." && pwd -P)"
dispatch_dir="$(cd -- "$hooks_dir/.." && pwd -P)"
stop_hook="$hooks_dir/log-session-cost.sh"
root_file="$dispatch_dir/artifacts-root.default"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
assert_eq() { [[ "$2" == "$3" ]] || fail "$1: expected '$3', got '$2'"; }

[[ -f "$stop_hook" ]] || fail "subject hook is missing: $stop_hook"

# The single source. These fixtures read the file rather than the value in it -- hardcoding
# '/projects/dev' here would pin the path instead of the single-source property, which is
# the thing actually under test.
[[ -f "$root_file" ]] || fail "REQ-007: the shared default is missing: $root_file"
expected_root="$(head -n1 "$root_file")"
[[ -n "$expected_root" ]] || fail "REQ-007: the shared default is empty: $root_file"

# A minimal but real transcript, so the hook takes its normal path and emits a normal
# record: 2 user turns, 2 assistant messages, 2 tool_use blocks.
transcript="$tmp/transcript.jsonl"
cat > "$transcript" <<'JSONL'
{"type":"user","timestamp":"2026-08-23T10:00:00.000Z","message":{"role":"user","content":"do the thing"}}
{"type":"assistant","timestamp":"2026-08-23T10:00:10.000Z","message":{"role":"assistant","model":"claude-opus-5","usage":{"input_tokens":100,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"output_tokens":40},"content":[{"type":"tool_use","name":"Bash"}]}}
{"type":"user","timestamp":"2026-08-23T10:00:20.000Z","message":{"role":"user","content":"and again"}}
{"type":"assistant","timestamp":"2026-08-23T10:00:30.000Z","message":{"role":"assistant","model":"claude-opus-5","usage":{"input_tokens":10,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"output_tokens":5},"content":[{"type":"tool_use","name":"Bash"}]}}
JSONL

# The root the hook exports is observable only through the publisher it calls, so the stub
# records its environment rather than its arguments. It is also what keeps every fixture
# from reaching a real auditctl and writing into the checkout.
stub_dir="$tmp/bin"; mkdir -p "$stub_dir"
cat > "$stub_dir/auditctl" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "${AUDITCTL_ARTIFACTS_ROOT-<unset>}" >> "$AUDITCTL_ROOT_LOG"
STUB
chmod +x "$stub_dir/auditctl"
export AUDITCTL_ROOT_LOG="$tmp/artifacts-root.log"

gatedir="$tmp/state"; mkdir -p "$gatedir"

# Runs a Stop hook from a chosen working directory and echoes the root it published.
# `env -u` so an AUDITCTL_ARTIFACTS_ROOT inherited from the caller's shell cannot make an
# unset fixture pass for the wrong reason. AGENTOPS_COST_LOG and AGENTOPS_GATE_LOG_DIR keep
# every write inside $tmp.
root_used() {
  local hook="$1" workdir="$2" costlog="$3" explicit="${4-}"
  : > "$AUDITCTL_ROOT_LOG"
  local event
  event="$(jq -cn --arg t "$transcript" \
    '{transcript_path:$t, session_id:"sess-root", cwd:"/projects/dev/agentops", hook_event_name:"Stop"}')"
  if [[ -n "$explicit" ]]; then
    ( cd -- "$workdir" && printf '%s' "$event" | env PATH="$stub_dir:$PATH" \
        AGENTOPS_COST_LOG="$costlog" AGENTOPS_GATE_LOG_DIR="$gatedir" \
        AUDITCTL_ARTIFACTS_ROOT="$explicit" bash "$hook" )
  else
    ( cd -- "$workdir" && printf '%s' "$event" | env -u AUDITCTL_ARTIFACTS_ROOT \
        PATH="$stub_dir:$PATH" \
        AGENTOPS_COST_LOG="$costlog" AGENTOPS_GATE_LOG_DIR="$gatedir" bash "$hook" )
  fi
  tail -n1 "$AUDITCTL_ROOT_LOG"
}

# --- REQ-006: an explicit root in the environment is still the one that wins ------------
assert_eq "REQ-006 explicit root wins" \
  "$(root_used "$stop_hook" "$tmp" "$tmp/costs-explicit.jsonl" "$tmp/explicit-root")" \
  "$tmp/explicit-root"

# --- REQ-007: unset -> the root is whatever the shared data file says --------------------
assert_eq "REQ-007 unset root comes from artifacts-root.default" \
  "$(root_used "$stop_hook" "$tmp" "$tmp/costs-unset.jsonl")" \
  "$expected_root"

# --- REQ-008: resolution is relative to the hook's own location, not to $PWD -------------
# Run from a working directory that is not the repository root and has no data file of its
# own -- resolving against $PWD would find nothing here.
elsewhere="$tmp/elsewhere"; mkdir -p "$elsewhere"
assert_eq "REQ-008 resolved from a foreign cwd" \
  "$(root_used "$stop_hook" "$elsewhere" "$tmp/costs-cwd.jsonl")" \
  "$expected_root"

# ...and through a symlink, which is how the hook is actually invoked: /projects/dev/.claude/
# hooks/ holds symlinks into this repo, so ${BASH_SOURCE[0]} is the symlink's path and
# `dirname` alone lands in a directory with no data file next to it.
linkdir="$tmp/linked-hooks"; mkdir -p "$linkdir"
ln -sf "$stop_hook" "$linkdir/log-session-cost.sh"
assert_eq "REQ-008 resolved through a symlinked hook" \
  "$(root_used "$linkdir/log-session-cost.sh" "$elsewhere" "$tmp/costs-link.jsonl")" \
  "$expected_root"

# --- REQ-009: the root is no longer written into the hook as a literal -------------------
# One source means one source; a copy left behind here is a copy that drifts, whichever one
# gets edited next. Scoped to the lines that establish AUDITCTL_ARTIFACTS_ROOT -- the
# cost-log and gate-log defaults are different defaults, with different owners, not
# duplicated anywhere, and none of this packet's business.
offender="$(grep -nF -- 'AUDITCTL_ARTIFACTS_ROOT' "$stop_hook" | grep -F -- "$expected_root" | head -n1)"
if [[ -n "$offender" ]]; then
  fail "REQ-009: the AUDITCTL_ARTIFACTS_ROOT line still hardcodes '$expected_root' -- $offender"
fi

# --- REQ-010: the converse, now that REQ-009 is scoped -----------------------------------
# The cost-log and gate-log defaults are out of scope for this packet and must survive it
# untouched -- deriving them from the same data file would be a second, unrequested
# refactor of two unrelated defaults.
grep -qxF -- 'LOG="${AGENTOPS_COST_LOG:-/projects/dev/.claude/session-costs.jsonl}"' "$stop_hook" \
  || fail "REQ-010: the cost-log default was changed by this packet"
grep -qxF -- 'GATE_DIR="${AGENTOPS_GATE_LOG_DIR:-/projects/dev/.claude/state}"' "$stop_hook" \
  || fail "REQ-010: the gate-log default was changed by this packet"

# --- REQ-011: a data file that is gone must not cost the caller its session --------------
# The hook still exits 0 and still writes its record. What it puts in the root then is the
# implementer's call. Tested on a copy of the hook in a tree with no data file above it,
# because the real one must keep its own.
orphan="$tmp/orphan/hooks"; mkdir -p "$orphan"
cp "$stop_hook" "$orphan/log-session-cost.sh"
if [[ -e "$tmp/orphan/artifacts-root.default" ]]; then
  fail "fixture: the orphan tree must have no data file"
fi
orphan_log="$tmp/costs-orphan.jsonl"
if ! root_used "$orphan/log-session-cost.sh" "$elsewhere" "$orphan_log" >/dev/null; then
  fail "REQ-011: the Stop hook exited non-zero with the data file missing"
fi
[[ -s "$orphan_log" ]] || fail "REQ-011: the cost row was lost with the data file missing"
jq -e 'has("cost_usd") and has("turns")' <<<"$(tail -n1 "$orphan_log")" >/dev/null \
  || fail "REQ-011: the record written with the data file missing is not a cost record"

# An empty data file is the same class of accident as a missing one.
empty="$tmp/empty/hooks"; mkdir -p "$empty"
cp "$stop_hook" "$empty/log-session-cost.sh"
: > "$tmp/empty/artifacts-root.default"
empty_log="$tmp/costs-empty.jsonl"
if ! root_used "$empty/log-session-cost.sh" "$elsewhere" "$empty_log" >/dev/null; then
  fail "REQ-011: the Stop hook exited non-zero with an empty data file"
fi
[[ -s "$empty_log" ]] || fail "REQ-011: the cost row was lost with an empty data file"

printf 'PASS: artifacts-root oracle (M-6a): explicit root wins, unset reads artifacts-root.default from the hook'\''s own location through a symlink, no literal left in the hook, cost/gate defaults untouched, missing and empty data files still exit 0 with the record written\n'
