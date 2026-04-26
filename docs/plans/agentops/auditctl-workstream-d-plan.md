# auditctl plan

Workstream D of `/projects/dev/agentops/docs/plans/agentops/agent-ops-substrate-plan.md`. Auditctl is a new repo-local audit event tool in the kctl/sprintctl family: Click CLI, sqlite query index, stdlib implementation beyond Click, per-repo database, and durable daily NDJSON shards for cockpit and migration.

## Goal

Ship a standalone repo-local audit ledger that records human, agent, git, sprintctl, and actionq events into sqlite and daily NDJSON shards with deterministic rebuild.

## Scope

What ships in this workstream:

- New repository at `/projects/dev/auditctl/`; this repo does not exist yet and must be created by the workstream. Auditctl does not live inside kctl.
- Python package `auditctl` with `cli.py`, `db.py`, `ids.py`, `paths.py`, `ndjson.py`, and `render.py`.
- Click CLI with `auditctl add`, `auditctl list`, `auditctl render`, and `auditctl rebuild`.
- Sqlite schema and numbered migrations using the sprintctl `db.py` pattern.
- Per-repo database resolution from `AUDITCTL_DB` or marker-file traversal.
- Dual-write implementation: every `auditctl add` inserts into sqlite and appends one JSON object to today's NDJSON shard.
- Daily NDJSON artifact writer at `<AUDITCTL_ARTIFACTS_ROOT>/_artifacts/<repo_id>/audit/events-YYYY-MM-DD.ndjson`.
- Rebuild path from one shard, a directory of shards, or a glob of shards.
- Example git hook scripts shipped in the auditctl repo, plus a concrete homelab-analytics post-commit hook for the minimum rollout.
- Packaging via setuptools matching kctl's `pyproject.toml` shape.
- Tests for sqlite writes, migrations, dual-write rollback, fcntl locking, rebuild round-trip, CLI output, and id format.

What does not ship in this workstream:

- No pg backend.
- No daemon or long-running service.
- No cockpit reader.
- No publisher implementations inside sprintctl or actionq beyond the invocation contract.
- No automatic NDJSON retention or pruning.

## Repo Structure

Auditctl is a new repo at `/projects/dev/auditctl/` because it is logically separate and will eventually move independently of kctl.

```text
/projects/dev/auditctl/
  AGENTS.md
  README.md
  pyproject.toml
  auditctl/
    __init__.py
    cli.py
    db.py
    ids.py
    ndjson.py
    paths.py
    render.py
  hooks/
    post-commit
    post-merge
  tests/
    conftest.py
    test_cli.py
    test_db.py
    test_dual_write.py
    test_ids.py
    test_rebuild.py
```

`pyproject.toml` follows kctl's packaging pattern:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "auditctl"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["click>=8.1"]

[project.scripts]
auditctl = "auditctl.cli:cli"

[project.optional-dependencies]
dev = ["pytest>=8"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

## Sqlite Schema

Auditctl uses sqlite only. The local database is the queryable index; NDJSON is the durable artifact. The schema is append-only in v1.

Migration 1:

```sql
CREATE TABLE IF NOT EXISTS audit_event (
    id          TEXT PRIMARY KEY,
    ts          TEXT NOT NULL,
    type        TEXT NOT NULL,
    actor       TEXT NOT NULL,
    summary     TEXT NOT NULL,
    detail      TEXT,
    refs        TEXT NOT NULL DEFAULT '[]',
    source      TEXT NOT NULL,
    metadata    TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_audit_event_ts_type
    ON audit_event(ts, type);

CREATE INDEX IF NOT EXISTS idx_audit_event_type_ts
    ON audit_event(type, ts);

CREATE INDEX IF NOT EXISTS idx_audit_event_source_ts
    ON audit_event(source, ts);
```

Migration structure follows sprintctl's numbered migration list, not kctl's simple loop. `db.py` should define `_MIGRATIONS`, one `_migration_N(conn)` per version when idempotence needs Python checks, `_run_migration(...)`, and `init_db(conn)` that advances `schema_version` one integer at a time inside `BEGIN IMMEDIATE`.

`refs` is JSON text containing an array of strings. Valid prefixes are documented, not constrained in SQL: `wi:`, `ka:`, `ad:`, `sha:`, `pr:`, `sprint:`. `metadata` is JSON text containing source-specific machine metadata. `detail` remains human-readable Markdown or null.

## `ad:<ulid>` Implementation

Event ids are `ad:<ulid>`. The ULID-compatible body is 26 Crockford base32 characters:

- 48 bits: current Unix time in milliseconds.
- 80 bits: randomness from `uuid.uuid4().int & ((1 << 80) - 1)`.
- Encode the resulting 128-bit value with Crockford base32 alphabet `0123456789ABCDEFGHJKMNPQRSTVWXYZ`.
- Left-pad to 26 characters and prefix with `ad:`.

This gives time-sortable ids without adding a ULID dependency. The generator is stdlib-only and should expose `new_event_id(now: datetime | None = None) -> str` for tests.

## Dual-Write Implementation

`auditctl add` writes sqlite and NDJSON in one operation. There is no native transaction across sqlite and file append, so the contract is "sqlite rolls back if NDJSON append fails" plus deterministic rebuild if a host crashes in the narrow post-append window.

Exact algorithm:

1. Resolve repo root, `repo_id`, sqlite database path, and today's NDJSON shard path.
2. Build the complete event object before opening the transaction. Canonical JSON uses sorted keys and compact separators for stable NDJSON.
3. Open sqlite with `PRAGMA foreign_keys = ON` and `PRAGMA journal_mode = WAL`.
4. Start `BEGIN IMMEDIATE`.
5. Insert the event into `audit_event`.
6. Create the shard parent directory with `mkdir(parents=True, exist_ok=True)`.
7. Open the shard with `os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o664)`.
8. Acquire an exclusive advisory lock on the shard file descriptor with `fcntl.flock(fd, fcntl.LOCK_EX)`.
9. Write exactly one UTF-8 line: `json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"`.
10. Flush durability with `os.fsync(fd)`.
11. Release the lock in `finally` with `fcntl.flock(fd, fcntl.LOCK_UN)` and close the descriptor.
12. Commit sqlite.

Failure semantics:

- If sqlite insert fails, no NDJSON append is attempted; exit nonzero.
- If shard open, lock, write, or fsync fails, roll back sqlite and exit nonzero.
- If rollback after an NDJSON failure also fails, write `auditctl: sqlite rollback failed after NDJSON append failure; audit_event <id> may be inconsistent` to stderr and exit nonzero.
- If sqlite commit fails after the NDJSON append has succeeded, write `auditctl: sqlite commit failed after NDJSON append; run auditctl rebuild --from-ndjson` to stderr and exit nonzero.
- If the process crashes after NDJSON fsync and before sqlite commit, NDJSON may contain an event missing from sqlite. `auditctl rebuild --from-ndjson` is the repair path.

Concurrency contract:

- Sqlite allows one writer through `BEGIN IMMEDIATE`.
- NDJSON appends are serialized by `fcntl.flock(..., LOCK_EX)` on the daily shard.
- The lock is acquired after the sqlite insert and before any file write; it is released after fsync or after the failed append attempt.
- Every auditctl writer must use this lock. Operators should not append to audit shards manually.

## `AUDITCTL_ARTIFACTS_ROOT`

`AUDITCTL_ARTIFACTS_ROOT` is set by each repo's `.envrc`, usually to the shared `/projects/dev` root. In the current workspace `/projects/dev` is itself the shared mount; repos are flat siblings under it. The `_artifacts/` directory is a planned sibling artifact tree and may not exist until auditctl creates it.

Write-path behavior:

- `auditctl add` requires `AUDITCTL_ARTIFACTS_ROOT`.
- If unset, `auditctl add` exits 1 before opening sqlite: `Error: AUDITCTL_ARTIFACTS_ROOT is required for audit writes.`
- The command does not silently write sqlite-only records.

Read-path behavior:

- `auditctl list` reads sqlite and does not require `AUDITCTL_ARTIFACTS_ROOT`.
- `auditctl render --format ndjson` can read sqlite and does not require it.
- `auditctl rebuild --from-ndjson <path>` reads the explicit path and does not require it.

## Repo Resolution

Database resolution:

- If `AUDITCTL_DB` is set, use it exactly.
- Otherwise traverse upward from `cwd` looking for `.auditctl/auditctl.db`.
- If no marker is found, use `<repo-root>/.auditctl/auditctl.db` where `<repo-root>` is the nearest parent containing `.git`.
- If neither `.auditctl` nor `.git` is found, error with `Error: not inside an auditctl-enabled repo; set AUDITCTL_DB.`

`repo_id` resolution:

- The `repo_id` is the directory name of the marker file's containing repo.
- For `/projects/dev/homelab-analytics/.auditctl/auditctl.db`, `repo_id` is `homelab-analytics`.
- When `AUDITCTL_DB` is set, derive the repo root by walking upward from the db path until `.auditctl` or `.git` is found; otherwise error and ask for execution inside the repo. There is no `AUDITCTL_REPO_ID` override in v1.

The NDJSON path is:

```text
<AUDITCTL_ARTIFACTS_ROOT>/_artifacts/<repo_id>/audit/events-YYYY-MM-DD.ndjson
```

For the pilot with `AUDITCTL_ARTIFACTS_ROOT=/projects/dev`, this resolves to:

```text
/projects/dev/_artifacts/homelab-analytics/audit/events-YYYY-MM-DD.ndjson
```

## CLI Spec

### `auditctl add`

```text
auditctl add \
  --type <type> \
  --actor <actor> \
  --summary <summary> \
  [--detail <markdown>] \
  [--ref <ref>]... \
  [--source <source>] \
  [--metadata <json>] \
  [--ts <iso-utc>] \
  [--json]
```

Defaults:

- `--source manual`
- `--metadata {}`
- `--ts now in UTC`

Validation:

- `--type`, `--actor`, and `--summary` are required.
- `--metadata` must parse to a JSON object.
- Every `--ref` must start with one of `wi:`, `ka:`, `ad:`, `sha:`, `pr:`, `sprint:`.
- `--ts` must be an ISO UTC timestamp ending in `Z`.

Text output:

```text
Added ad:01HX2YH8R7J9Y8QG6J3S1N6V2K commit git-hook 2026-04-26T10:15:30Z
```

JSON output:

```json
{"id":"ad:01HX2YH8R7J9Y8QG6J3S1N6V2K","ts":"2026-04-26T10:15:30Z","type":"commit","source":"git-hook","repo_id":"homelab-analytics","ndjson_path":"/projects/dev/_artifacts/homelab-analytics/audit/events-2026-04-26.ndjson"}
```

### `auditctl list`

```text
auditctl list [--type <type>] [--source <source>] [--since <ts>] [--until <ts>] [--limit <n>] [--json]
```

Defaults:

- `--limit 50`
- Ordered by `ts DESC, id DESC`.

Text output columns:

```text
TS                    ID                 TYPE           SOURCE       ACTOR        SUMMARY
2026-04-26T10:15:30Z  ad:01HX...6V2K     commit         git-hook     bayleaf      Commit abc1234: update pipeline
```

JSON output is an array of full event objects with parsed `refs` and `metadata`.

### `auditctl render`

```text
auditctl render [--since <ts>] [--until <ts>] [--type <type>] [--source <source>] [--format text|ndjson] [--limit <n>]
```

Defaults:

- `--format text`
- No limit unless `--limit` is supplied.
- Ordered by `ts ASC, id ASC`.

Text render is a compact chronological Markdown-ish log:

```text
## 2026-04-26

- 10:15:30 commit git-hook bayleaf: Commit abc1234: update pipeline
  refs: sha:abc1234
```

`--format ndjson` emits one canonical JSON object per line from sqlite, suitable for comparisons and export. It does not read shard files.

### `auditctl rebuild`

```text
auditctl rebuild --from-ndjson <path> [--replace] [--dry-run]
```

Behavior:

- `<path>` may be a file, a directory, or a glob.
- Directory input reads `events-*.ndjson` sorted lexically.
- Invalid JSON, missing required fields, invalid refs, or invalid ids fail the rebuild with a line-numbered error.
- Default mode imports into the current sqlite db with `INSERT OR IGNORE`, preserving existing rows.
- `--replace` moves the current sqlite file to `.bak-<timestamp>`, creates a fresh db, and imports all events.
- `--dry-run` validates and reports counts without writing.

Text output:

```text
Rebuilt audit db from 12 shard(s): 1842 imported, 0 skipped.
```

## Metadata Column

Use a separate `metadata` column of type `TEXT` containing JSON. Do not overload `detail`.

Rationale:

- `detail` is human-readable Markdown for render output.
- `metadata` is machine-readable publisher context for filters, future cockpit affordances, and rebuild fidelity.
- Keeping them separate avoids forcing humans to read JSON and avoids scraping Markdown for structured values.

Publisher metadata schemas:

```json
{
  "git-hook": {
    "sha": "full commit sha",
    "branch": "current branch name",
    "message": "commit subject"
  },
  "actionq-daemon": {
    "session_id": "actionq session id",
    "harness": "claude|codex|copilot-cli|codestral|opencode",
    "model": "model id",
    "action_id": "action queue id"
  },
  "sprintctl": {
    "sprint_id": "integer or string sprint id",
    "event_type": "sprintctl event type"
  }
}
```

All metadata objects may include an optional `version` integer later. V1 publishers should omit keys they do not know rather than writing nulls.

## Git Hook Answer

Auditctl will ship example hook scripts in `/projects/dev/auditctl/hooks/` after the new repo exists. Repos may symlink or copy them, but auditctl does not manage hook installation in v1.

"Git hook publishers in homelab-analytics only" means the minimum rollout installs hook scripts only in `/projects/dev/homelab-analytics/.git/hooks/`. Other repos may run auditctl manually, but they do not get automatic commit/merge audit events until later rollout.

Exact homelab-analytics post-commit hook:

```sh
#!/bin/sh
set -eu

if ! command -v auditctl >/dev/null 2>&1; then
  echo "auditctl post-commit hook: auditctl not found on PATH" >&2
  exit 0
fi

sha="$(git rev-parse HEAD)"
branch="$(git rev-parse --abbrev-ref HEAD)"
subject="$(git log -1 --pretty=%s)"
actor="${USER:-git}"
metadata="$(SHA="$sha" BRANCH="$branch" SUBJECT="$subject" python3 -c \
  'import json, os; print(json.dumps({"sha": os.environ["SHA"], "branch": os.environ["BRANCH"], "message": os.environ["SUBJECT"]}, separators=(",", ":")))')"

auditctl add \
  --type commit \
  --source git-hook \
  --actor "$actor" \
  --summary "Commit ${sha}: ${subject}" \
  --ref "sha:${sha}" \
  --metadata "$metadata" >/dev/null
```

The shipped auditctl example can use a small helper style if desired, but the minimum hook above is intentionally plain shell and python3, both available in the devbox and workstation environments.

## Publisher Integration Spec

Publishers call the `auditctl` binary as a subprocess. They do not import auditctl Python modules.

### Sprintctl

Sprintctl emits audit events only after its own event write succeeds. Example invocation for a sprint event:

```sh
auditctl add \
  --type "sprint.${SPRINTCTL_EVENT_TYPE}" \
  --source sprintctl \
  --actor "$ACTOR" \
  --summary "$SUMMARY" \
  --detail "$DETAIL" \
  --ref "sprint:${SPRINT_ID}" \
  --metadata "{\"sprint_id\":${SPRINT_ID},\"event_type\":\"${SPRINTCTL_EVENT_TYPE}\"}"
```

Initial event mapping:

- `sprint-opened` -> `type=sprint.opened`
- `sprint-closed` -> `type=sprint.closed`
- `sprint-taken-up` -> `type=sprint.taken_up`
- `sprint-released` -> `type=sprint.released`
- `knowledge.landed` -> `type=knowledge.landed`, with `ka:<id>` refs when known

If auditctl fails, sprintctl should warn on stderr and keep the sprintctl operation successful in v1. Audit is an integration side effect for sprintctl, not the source transaction.

### Actionq-Daemon

Actionq-daemon emits one event per lifecycle transition:

```sh
auditctl add \
  --type "session.start" \
  --source actionq-daemon \
  --actor "$HARNESS" \
  --summary "Session ${SESSION_ID} started for action ${ACTION_ID}" \
  --ref "wi:${WORK_ITEM_ID}" \
  --metadata "{\"session_id\":\"${SESSION_ID}\",\"harness\":\"${HARNESS}\",\"model\":\"${MODEL}\",\"action_id\":\"${ACTION_ID}\"}"
```

Initial event types:

- `dispatch.queued`
- `dispatch.started`
- `session.start`
- `session.pause`
- `session.resume`
- `session.exit`
- `pr.open`
- `pr.merge`

Actionq owns retry policy. If auditctl fails, actionq should mark the audit emission failure in its own logs and continue session lifecycle handling.

## Retention Answer

No automatic deletion in v1. NDJSON shards are small, append-only, and useful as the disaster-recovery source. Storage is cheap relative to the operational risk of deleting audit history too early.

Retention is the operator's responsibility for now. A follow-up may add:

```text
auditctl prune --before <YYYY-MM-DD> [--archive-to <path>]
```

That command is out of scope for this workstream.

## Client Library Answer

Sprintctl, actionq-daemon, and git hooks consume auditctl by subprocess calls to the `auditctl` binary.

No vendored Python module and no shared pip package in v1. Subprocess calls keep publishers decoupled, work across language boundaries, avoid import/version conflicts between repos, and match the operational model where `/home/dev/.local/bin` is on PATH in the devbox.

Publisher requirement: `auditctl` must be installed on PATH, normally via:

```sh
uv tool install /projects/dev/auditctl --python python3
```

## Test Plan

Unit and CLI tests:

- `test_db.py`: init creates `schema_version`, `audit_event`, and indexes; migrations are idempotent; insert/list round-trips parsed `refs` and `metadata`.
- `test_ids.py`: ids match `^ad:[0-9A-HJKMNP-TV-Z]{26}$`, preserve timestamp ordering for increasing injected times, and use no external dependency.
- `test_dual_write.py`: successful `add` writes one sqlite row and one NDJSON line; NDJSON open/write/fsync failure rolls back sqlite; sqlite insert failure does not create a shard line.
- `test_dual_write.py`: concurrent writers produce valid complete NDJSON lines using `fcntl` locking. Use multiple processes, not only threads.
- `test_rebuild.py`: rebuild from a shard directory recreates sqlite rows exactly; duplicate lines are ignored in default mode; `--replace` backs up and recreates the db.
- `test_cli.py`: `add`, `list`, `render`, and `rebuild` text/JSON outputs match expected contracts.
- `test_paths.py`: `AUDITCTL_DB` and marker traversal resolve the db path and `repo_id`; write commands fail clearly when `AUDITCTL_ARTIFACTS_ROOT` is unset.
- `test_validation.py`: invalid refs, invalid metadata JSON, invalid timestamps, and malformed NDJSON fail with actionable messages.

Use temporary directories for both repo roots and artifact roots. Do not require the real `/projects/dev/_artifacts` path in tests.

## Out of Scope

- Cockpit reading NDJSON; that is workstream E.
- Pg, central service, remote mode, or any shared server.
- Specific sprintctl and actionq publisher implementations beyond the invocation contract.
- Automatic hook installation across all repos.
- Retention deletion or archive tooling.
- A Python client library with stable import API.

## Implementation Order

Each step is shippable on its own. Step 1 must land before any publisher integration.

1. Standalone auditctl repository with packaging, sqlite migrations, id generation, path resolution, and `add/list/render/rebuild` working against sqlite and NDJSON.
2. Dual-write hardening: fcntl lock tests, rollback tests, fsync behavior, and rebuild round-trip from daily shards.
3. Documentation and examples: README, `.envrc` example, hook examples in `hooks/`, and operator notes for `AUDITCTL_ARTIFACTS_ROOT`.
4. Homelab-analytics git hook minimum: install post-commit and post-merge hooks only in `/projects/dev/homelab-analytics`, validate events land in sqlite and `_artifacts/homelab-analytics/audit/`.
5. Sprintctl publisher integration: emit subprocess calls for selected sprint lifecycle events, warning only on audit failure.
6. Actionq-daemon publisher integration: emit subprocess calls for dispatch and session lifecycle events.
7. Follow-up planning for retention: design `auditctl prune --before <date>` after real shard volume is known.
