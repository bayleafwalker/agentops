# auditctl publisher handover

Reference for actionq and sprintctl integrators implementing Step 4/5 of the agent-ops substrate plan.

auditctl is **already shipped** at `/projects/dev/auditctl`. Install it:

```bash
uv tool install /projects/dev/auditctl --python python3
```

---

## Interface contract

### Invocation

Publishers call the `auditctl` binary as a subprocess. No Python import, no shared package.

```bash
auditctl add \
  --type <type> \
  --source <source> \
  --actor <actor> \
  --summary "<one-line description>" \
  [--refs "wi:123,sprint:2"]          # comma-separated, or use --ref repeatedly
  [--ref sha:abc123]                  # repeatable; combines with --refs
  [--metadata '{"key":"value"}']      # JSON object, publisher-specific
  [--detail "<markdown>"]             # human-readable body, optional
  [--ts 2026-04-28T09:00:00Z]        # defaults to now
  [--json]                            # emit JSON to stdout on success
```

### Exit codes

| Code | Meaning |
|------|---------|
| 0    | Event written to sqlite and NDJSON shard |
| 1    | Validation error, I/O failure, or missing env var |

On failure, `Error: <message>` is written to stderr. The publisher should capture stderr and
treat it as `audit_error`. **Audit failure must not block the primary operation.**

### `--json` output (exit 0)

```json
{
  "id": "ad:01JSVK3H7...",
  "ndjson_path": "/projects/dev/_artifacts/homelab-analytics/audit/events-2026-04-28.ndjson",
  "repo_id": "homelab-analytics",
  "source": "actionq-daemon",
  "ts": "2026-04-28T09:00:00Z",
  "type": "session.start"
}
```

Capture `id` for use as `ad:<id>` ref in downstream events (e.g., reference the start event
from the exit event).

### Required env vars

| Variable | Required for | Notes |
|----------|-------------|-------|
| `AUDITCTL_ARTIFACTS_ROOT` | `auditctl add` | Set to `/projects/dev` in the devbox/workstation envrc |
| `AUDITCTL_DB` | Optional | Auto-resolved from git root; set explicitly if calling outside the repo |

**When calling from outside the project directory** (e.g., actionq-daemon running in a
different working directory), use `direnv exec` to load the project's envrc:

```bash
direnv exec /projects/dev/homelab-analytics auditctl add \
  --type session.start --source actionq-daemon --actor claude \
  --summary "Session ${SESSION_ID} started for wi:${WI_ID}" \
  --refs "wi:${WI_ID},sprint:${SPRINT_ID}" \
  --json
```

This sets `AUDITCTL_DB` and `AUDITCTL_ARTIFACTS_ROOT` from the project's `.envrc` without
changing the daemon's working directory.

---

## actionq integration (Step 4)

### AuditctlClient shape

```python
# clients.py
import json
import subprocess
from pathlib import Path
from dataclasses import dataclass

@dataclass
class AuditResult:
    ok: bool
    event_id: str | None     # ad:<ulid> on success
    error: str | None        # stderr text on failure

class AuditctlClient:
    def __init__(self, project_path: Path, fail_on_error: bool = False):
        self._project_path = project_path
        self._fail_on_error = fail_on_error

    def emit(
        self,
        type_: str,
        actor: str,
        summary: str,
        refs: list[str] | None = None,
        metadata: dict | None = None,
        source: str = "actionq-daemon",
    ) -> AuditResult:
        cmd = [
            "direnv", "exec", str(self._project_path),
            "auditctl", "add",
            "--type", type_,
            "--source", source,
            "--actor", actor,
            "--summary", summary,
            "--json",
        ]
        if refs:
            cmd += ["--refs", ",".join(refs)]
        if metadata:
            cmd += ["--metadata", json.dumps(metadata, separators=(",", ":"))]

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        except Exception as exc:
            result = AuditResult(ok=False, event_id=None, error=str(exc))
        else:
            if proc.returncode == 0:
                payload = json.loads(proc.stdout)
                result = AuditResult(ok=True, event_id=payload["id"], error=None)
            else:
                result = AuditResult(ok=False, event_id=None, error=proc.stderr.strip())

        if not result.ok and self._fail_on_error:
            raise RuntimeError(f"auditctl emit failed: {result.error}")
        return result
```

### [global.audit] config fields

```toml
[global.audit]
enabled = true
fail_action_on_emit_error = false   # true only for debugging; audit is a side effect
```

`fail_action_on_emit_error = false` is the correct default — audit failures must not block
session lifecycle. Set to `true` only when debugging the integration.

### Event types and call sites in `_dispatch_and_run`

Emit in this order; each call is best-effort (log on failure, continue):

| Event | When | Refs | Metadata keys |
|-------|------|------|---------------|
| `dispatch.queued` | action dequeued, before session start | `wi:<id>` | `action_id`, `harness`, `model` |
| `session.start`   | harness process spawned | `wi:<id>`, `sprint:<id>` | `session_id`, `action_id`, `harness`, `model` |
| `session.pause`   | usage limit pause, if implemented | `wi:<id>` | `session_id`, `reason` |
| `session.resume`  | resume after pause | `wi:<id>` | `session_id` |
| `session.exit`    | harness process exits | `wi:<id>`, `sprint:<id>`, `sha:<head>`, `ad:<start_event_id>` | `session_id`, `exit_code`, `action_id` |

`ad:<start_event_id>` in session.exit references the session.start event — capture the `id`
from the AuditResult returned by the start emit.

### Mirroring audit status into session.exited payload

```python
audit_result = client.emit("session.exit", ...)
payload = {
    "session_id": session_id,
    "exit_code": exit_code,
    # ...
    "audit_status": "ok" if audit_result.ok else "error",
    "audit_error": audit_result.error,   # None on success
}
```

### Test surface

- Command construction: assert `direnv exec <path> auditctl add ...` args are built correctly
  for each event type. Use `unittest.mock.patch("subprocess.run")`.
- Success path: mock returns exit 0 with valid JSON; assert AuditResult.ok and event_id set.
- Failure degradation: mock returns exit 1; assert AuditResult.ok=False, error captured,
  primary operation continues (no exception raised when fail_on_error=False).
- fail_on_error=True: mock returns exit 1; assert RuntimeError raised.
- Timeout: mock raises subprocess.TimeoutExpired; assert graceful degradation.

---

## sprintctl integration (Step 5)

### Call sites

After each successful sprintctl operation, emit via subprocess (not AuditctlClient — sprintctl
is a Python package but should keep the subprocess boundary to stay decoupled):

```bash
auditctl add \
  --type sprint.opened \
  --source sprintctl \
  --actor "$USER" \
  --summary "Sprint ${SPRINT_ID} opened" \
  --ref "sprint:${SPRINT_ID}" \
  --metadata "{\"sprint_id\":${SPRINT_ID},\"event_type\":\"sprint-opened\"}" \
  || echo "auditctl emit failed (non-fatal)" >&2
```

Event type mapping:

| sprintctl operation | auditctl type | Required refs |
|--------------------|---------------|---------------|
| sprint-opened      | `sprint.opened`     | `sprint:<id>` |
| sprint-closed      | `sprint.closed`     | `sprint:<id>` |
| sprint-taken-up    | `sprint.taken_up`   | `sprint:<id>`, `wi:<id>` |
| sprint-released    | `sprint.released`   | `sprint:<id>`, `wi:<id>` |
| knowledge.landed   | `knowledge.landed`  | `sprint:<id>`, `ka:<id>` |

### Failure contract

If auditctl fails, sprintctl writes a warning to stderr and returns success. Audit is a side
effect; the sprintctl operation is the primary transaction.

```python
result = subprocess.run(["auditctl", "add", ...], capture_output=True)
if result.returncode != 0:
    click.echo(f"warning: auditctl emit failed: {result.stderr.decode().strip()}", err=True)
```

---

## Valid ref prefixes (for both integrators)

`wi:`, `ka:`, `ad:`, `sha:`, `pr:`, `sprint:`

Any value after the prefix is accepted by the validator. Use the actual ID, not a placeholder
like `sprint:current` — resolve sprint/work-item IDs before calling auditctl.
