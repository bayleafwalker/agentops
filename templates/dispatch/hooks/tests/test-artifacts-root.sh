#!/usr/bin/env bash
# Gate for M-6a, reduced. This oracle used to require the cost hook to default
# AUDITCTL_ARTIFACTS_ROOT from `templates/dispatch/artifacts-root.default`. auditctl 0.1.4
# made that default the publisher's own job -- the root is the repository auditctl resolves,
# and an explicit value may only confirm it -- and 0.1.5 is what runs on every publishing
# host, so the hook now sets nothing at all.
#
#   REQ-006..REQ-009 SUPERSEDED. The property is no longer "the hook defaults the root from
#   the single source" but "no caller decides the root", which is REQ-025 and REQ-026 in
#   test-auditctl-resolve.sh. They are not deleted silently: a reader who finds the old
#   requirement ids in a commit or a packet lands here and is told where the property went.
#
#   REQ-010 the cost-log and gate-log defaults are still nobody else's business
#   REQ-011 the cost record survives a publisher that cannot be configured
#
# Subject: templates/dispatch/hooks/log-session-cost.sh and nothing else -- running this
# must not read any other file in the repository, and must not write into the checkout.
# Every fixture stubs `auditctl` on PATH, so no real audit write can reach `.auditctl/`.
set -uo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
hooks_dir="$(cd -- "$here/.." && pwd -P)"
dispatch_dir="$(cd -- "$hooks_dir/.." && pwd -P)"
stop_hook="$hooks_dir/log-session-cost.sh"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
assert_eq() { [[ "$2" == "$3" ]] || fail "$1: expected '$3', got '$2'"; }

[[ -f "$stop_hook" ]] || fail "subject hook is missing: $stop_hook"

# A minimal but real transcript, so the hook takes its normal path and emits a normal
# record: 2 user turns, 2 assistant messages, 2 tool_use blocks.
transcript="$tmp/transcript.jsonl"
cat > "$transcript" <<'JSONL'
{"type":"user","timestamp":"2026-08-23T10:00:00.000Z","message":{"role":"user","content":"do the thing"}}
{"type":"assistant","timestamp":"2026-08-23T10:00:10.000Z","message":{"role":"assistant","model":"claude-opus-5","usage":{"input_tokens":100,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"output_tokens":40},"content":[{"type":"tool_use","name":"Bash"}]}}
{"type":"user","timestamp":"2026-08-23T10:00:20.000Z","message":{"role":"user","content":"and again"}}
{"type":"assistant","timestamp":"2026-08-23T10:00:30.000Z","message":{"role":"assistant","model":"claude-opus-5","usage":{"input_tokens":10,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"output_tokens":5},"content":[{"type":"tool_use","name":"Bash"}]}}
JSONL

# What the hook does to the publisher's environment is observable only through the publisher
# it calls, so the stub records that environment rather than its arguments -- it should now
# record `<unset>`, and REQ-025 is what asserts so. It is also what keeps every fixture from
# reaching a real auditctl and writing into the checkout.
stub_dir="$tmp/bin"; mkdir -p "$stub_dir"
cat > "$stub_dir/auditctl" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "${AUDITCTL_ARTIFACTS_ROOT-<unset>}" >> "$AUDITCTL_ROOT_LOG"
STUB
chmod +x "$stub_dir/auditctl"
export AUDITCTL_ROOT_LOG="$tmp/artifacts-root.log"

gatedir="$tmp/state"; mkdir -p "$gatedir"

# A working directory that is not the repository and holds nothing of the hook's own.
elsewhere="$tmp/elsewhere"; mkdir -p "$elsewhere"

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

# --- REQ-010: the cost-log and gate-log defaults are still nobody else's business --------
# They were out of scope when the root was defaulted here and they stay out of scope now
# that it is not: deriving them from anything shared would be an unrequested refactor of two
# unrelated defaults with different owners.
grep -qxF -- 'LOG="${AGENTOPS_COST_LOG:-/projects/dev/.claude/session-costs.jsonl}"' "$stop_hook" \
  || fail "REQ-010: the cost-log default was changed by this packet"
grep -qxF -- 'GATE_DIR="${AGENTOPS_GATE_LOG_DIR:-/projects/dev/.claude/state}"' "$stop_hook" \
  || fail "REQ-010: the gate-log default was changed by this packet"

# --- REQ-011: a publisher that cannot be configured must not cost the caller its session -
# The hook still exits 0 and still writes its cost record. Tested on a copy of the hook in a
# tree with nothing beside it, which is also the shape a hook copied out of its directory
# arrives in.
orphan="$tmp/orphan/hooks"; mkdir -p "$orphan"
cp "$stop_hook" "$orphan/log-session-cost.sh"
orphan_log="$tmp/costs-orphan.jsonl"
if ! root_used "$orphan/log-session-cost.sh" "$elsewhere" "$orphan_log" >/dev/null; then
  fail "REQ-011: the Stop hook exited non-zero with nothing beside it"
fi
[[ -s "$orphan_log" ]] || fail "REQ-011: the cost row was lost with nothing beside the hook"
jq -e 'has("cost_usd") and has("turns")' <<<"$(tail -n1 "$orphan_log")" >/dev/null \
  || fail "REQ-011: the record written with nothing beside the hook is not a cost record"

printf 'PASS: artifacts-root oracle (M-6a, reduced): cost/gate defaults untouched, the cost row survives an unconfigurable publisher; REQ-006..REQ-009 superseded by REQ-025/REQ-026 in test-auditctl-resolve.sh\n'
