#!/usr/bin/env bash
# Oracle for agentops#2445 (2376-WP7b): the guarded harness_evidence call this item adds to
# hooks/log-session-cost.sh's emit_record().
#
# ENFORCEMENT BOUNDARY: this test proves the call is inert by default and never perturbs the
# hook's own outputs -- it does not turn anything on. `windows` is fed on the Stop event only
# to exercise the metrics path this file's own fixture asks for; the hook has no producer of
# `windows` in production (see log-session-cost.sh's own comment on WINDOWS).
#
#   REQ-001 exits 0 and still writes its cost-log row and auditctl row when the
#           harness_evidence module is absent
#   REQ-002 exits 0 and still writes its cost-log row and auditctl row when every
#           harness_evidence entry point raises
#   REQ-003 with a real endpoint, exactly one /v1/traces POST and one /v1/metrics POST
#           are received, and both bodies pass the #2443 allowlist assertion (only
#           schema-legal keys, and none of the forbidden/dropped ones, ever reach the wire)
#   REQ-004 hook stdout is unchanged (empty) in every case above
set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
hooks_dir="$(cd -- "$here/.." && pwd -P)"
stop_hook="$hooks_dir/log-session-cost.sh"

tmp="$(mktemp -d)"
mkdir -p "$tmp/store/.auditctl" && : > "$tmp/store/.auditctl/auditctl.db"
export AUDITCTL_DB="$tmp/store/.auditctl/auditctl.db"
export AUDITCTL_ARTIFACTS_ROOT="$tmp/store"

server_pid=""
cleanup() {
  [[ -n "$server_pid" ]] && kill "$server_pid" >/dev/null 2>&1 || true
  rm -rf "$tmp"
}
trap cleanup EXIT

fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
assert_eq() { [[ "$2" == "$3" ]] || fail "$1: expected '$3', got '$2'"; }

# A minimal transcript: one real turn, one assistant message with usage, so the hook builds
# a non-trivial record (model/tokens/cost/duration all populated).
transcript="$tmp/transcript.jsonl"
cat > "$transcript" <<'JSONL'
{"type":"user","timestamp":"2026-09-20T10:00:00.000Z","message":{"role":"user","content":"do the thing"}}
{"type":"assistant","timestamp":"2026-09-20T10:00:05.000Z","message":{"role":"assistant","model":"claude-sonnet-5","usage":{"input_tokens":100,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"output_tokens":40},"content":[{"type":"text","text":"ok"}]}}
JSONL

# A stub `auditctl` on PATH, as the other hook suites do -- proves the auditctl write still
# happens (REQ-001/REQ-002) independent of what emit_harness_evidence does.
pubdir="$tmp/pub"; mkdir -p "$pubdir"
cat > "$pubdir/auditctl" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$AUDITCTL_STUB_LOG"
STUB
chmod +x "$pubdir/auditctl"

run_stop() {
  # run_stop <session> <cost-log> <extra-json-merged-into-the-event> <harness-evidence-root>
  local session="$1" log="$2" extra="$3" ee_root="$4"
  local event
  event="$(jq -cn --arg t "$transcript" --arg s "$session" --argjson extra "$extra" \
    '{transcript_path:$t, session_id:$s, cwd:"/projects/dev/agentops", hook_event_name:"Stop"} + $extra')"
  export AUDITCTL_STUB_LOG="$tmp/auditctl-calls-$session.log"
  : > "$AUDITCTL_STUB_LOG"
  printf '%s' "$event" \
    | env PATH="$pubdir:$PATH" AGENTOPS_COST_LOG="$log" AGENTOPS_GATE_LOG_DIR="$tmp/state" \
          AGENTOPS_HARNESS_EVIDENCE_ROOT="$ee_root" \
          AUDITCTL_DB="$AUDITCTL_DB" AUDITCTL_ARTIFACTS_ROOT="$AUDITCTL_ARTIFACTS_ROOT" \
          bash "$stop_hook"
}

# --- REQ-001: the harness_evidence module is absent ------------------------------------
# An empty root has no scripts/harness_evidence directory at all, so emit_harness_evidence's
# own bash-level guard must skip the python call entirely -- never even shelling out.
absent_root="$tmp/no-module-root"; mkdir -p "$absent_root"
log_a="$tmp/costs-a.jsonl"
stdout_a="$(run_stop "sess-absent" "$log_a" '{}' "$absent_root")" \
  || fail "REQ-001: hook exited non-zero with the module absent"
assert_eq "REQ-004 stdout empty (module absent)" "$stdout_a" ""
[[ -s "$log_a" ]] || fail "REQ-001: cost-log row lost with the module absent"
[[ -s "$tmp/auditctl-calls-sess-absent.log" ]] || fail "REQ-001: auditctl row lost with the module absent"
assert_eq "REQ-001 auditctl row session id" \
  "$(jq -r '.session' <<<"$(sed -n 's/.*--metadata //p' "$tmp/auditctl-calls-sess-absent.log")")" "sess-absent"

# --- REQ-002: every harness_evidence entry point raises ---------------------------------
# scripts/harness_evidence exists at this root, but every function the hook calls blows up.
raise_root="$tmp/raises-root"
mkdir -p "$raise_root/scripts/harness_evidence"
cat > "$raise_root/scripts/harness_evidence/__init__.py" <<'PY'
def build_session_span(payload):
    raise RuntimeError("boom: build_session_span")


def build_rate_limit_gauges(payload):
    raise RuntimeError("boom: build_rate_limit_gauges")


def export_batch(batch):
    raise RuntimeError("boom: export_batch")
PY
log_b="$tmp/costs-b.jsonl"
stdout_b="$(run_stop "sess-raises" "$log_b" '{}' "$raise_root")" \
  || fail "REQ-002: hook exited non-zero when the module raises"
assert_eq "REQ-004 stdout empty (module raises)" "$stdout_b" ""
[[ -s "$log_b" ]] || fail "REQ-002: cost-log row lost when the module raises"
[[ -s "$tmp/auditctl-calls-sess-raises.log" ]] || fail "REQ-002: auditctl row lost when the module raises"
assert_eq "REQ-002 auditctl row session id" \
  "$(jq -r '.session' <<<"$(sed -n 's/.*--metadata //p' "$tmp/auditctl-calls-sess-raises.log")")" "sess-raises"

# --- REQ-003: a real endpoint receives exactly one traces POST and one metrics POST -----
capture="$tmp/capture"; mkdir -p "$capture"
server_script="$tmp/fake_collector.py"
cat > "$server_script" <<'PY'
import http.server
import sys
import threading

capture_dir = sys.argv[1]
port = int(sys.argv[2])
counters = {"n": 0}
lock = threading.Lock()


class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        with lock:
            counters["n"] += 1
            n = counters["n"]
        name = self.path.strip("/").replace("/", "_") or "root"
        with open(f"{capture_dir}/{n:02d}-{name}.json", "wb") as fh:
            fh.write(body)
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):  # noqa: D401 - silence default request logging
        pass


httpd = http.server.HTTPServer(("127.0.0.1", port), Handler)
httpd.serve_forever()
PY

port=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')
python3 "$server_script" "$capture" "$port" &
server_pid=$!

# Bounded wait for the fixture server's socket, not a fixed sleep.
for ((_i = 0; _i < 50; _i++)); do
  python3 -c "import socket,sys; s=socket.socket(); s.settimeout(0.1); sys.exit(0 if s.connect_ex(('127.0.0.1', $port)) == 0 else 1)" \
    && break
  sleep 0.05
done

windows='{"5h":{"used_percent":42.5,"resets_at":"2026-09-20T18:00:00Z"}}'
log_c="$tmp/costs-c.jsonl"
stdout_c="$(printf '%s' "$(jq -cn --arg t "$transcript" --arg s "sess-endpoint" --argjson w "$windows" \
    '{transcript_path:$t, session_id:$s, cwd:"/projects/dev/agentops", hook_event_name:"Stop", windows:$w}')" \
  | env PATH="$pubdir:$PATH" AGENTOPS_COST_LOG="$log_c" AGENTOPS_GATE_LOG_DIR="$tmp/state" \
        AUDITCTL_DB="$AUDITCTL_DB" AUDITCTL_ARTIFACTS_ROOT="$AUDITCTL_ARTIFACTS_ROOT" \
        AUDITCTL_STUB_LOG="$tmp/auditctl-calls-sess-endpoint.log" \
        OTEL_EXPORTER_OTLP_ENDPOINT="http://127.0.0.1:$port" \
        bash "$stop_hook")" || fail "REQ-003: hook exited non-zero with a real endpoint"
assert_eq "REQ-004 stdout empty (real endpoint)" "$stdout_c" ""

# Bounded wait for the two POSTs to land (the hook call itself is synchronous, so this is
# almost always immediate; bounded rather than fixed in case the loopback round-trip is
# slow under load).
for ((_i = 0; _i < 50; _i++)); do
  [[ "$(find "$capture" -type f | wc -l)" -ge 2 ]] && break
  sleep 0.05
done

assert_eq "REQ-003 exactly two POSTs received" "$(find "$capture" -type f | wc -l)" "2"
traces_file="$(grep -l . "$capture"/*traces.json 2>/dev/null || true)"
metrics_file="$(grep -l . "$capture"/*metrics.json 2>/dev/null || true)"
[[ -n "$traces_file" ]] || fail "REQ-003: no /v1/traces POST was received"
[[ -n "$metrics_file" ]] || fail "REQ-003: no /v1/metrics POST was received"

# --- allowlist assertion (from #2443): only the OTLP envelope, never the drop summary or
# any forbidden key, reaches the wire.
for f in "$traces_file" "$metrics_file"; do
  jq -e 'has("resourceSpans") or has("resourceMetrics")' "$f" >/dev/null \
    || fail "REQ-003: $f is not a bare OTLP envelope"
  jq -e 'has("dropped_attribute_count") or has("dropped_attribute_keys") | not' "$f" >/dev/null \
    || fail "REQ-003: $f leaked the library's own drop-summary fields onto the wire"
  raw="$(cat "$f")"
  for forbidden in prompt tool_output authorization raw_tail raw_header raw_quota_message; do
    [[ "$raw" != *"\"$forbidden\""* ]] || fail "REQ-003: forbidden key '$forbidden' reached the wire in $f"
  done
done
jq -e '.resourceSpans[0].scopeSpans[0].spans[0].attributes[] | select(.key == "session_id") | .value.stringValue == "sess-endpoint"' \
  "$traces_file" >/dev/null || fail "REQ-003: the traces body does not carry this session's identity"
jq -e '[.resourceMetrics[0].scopeMetrics[0].metrics[0].gauge.dataPoints[]] | length == 1' \
  "$metrics_file" >/dev/null || fail "REQ-003: the metrics body does not carry the one window supplied"

printf 'harness-evidence call hook tests passed\n'
