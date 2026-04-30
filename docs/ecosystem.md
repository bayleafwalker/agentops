# Agent-Ops Ecosystem

A reference for the `/projects/dev` agent-ops substrate: what each tool does, how they relate, how the cockpit reads them, how to deploy the system, and how to get started.

---

## What This Is

The agent-ops substrate is a set of small, composable tools that give one developer (with optional agent sessions) structured execution state, durable history, and an operator view over their work. Each tool owns exactly one domain. None of them replaces the others.

The core rule: **state ownership decides repo ownership.**

| Domain | Tool | Repo |
|---|---|---|
| Sprint and work-item state | `sprintctl` | [bayleafwalker/sprintctl](https://github.com/bayleafwalker/sprintctl) |
| Knowledge extraction and review | `kctl` | [bayleafwalker/kctl](https://github.com/bayleafwalker/kctl) |
| Repo-local audit and event ledger | `auditctl` | [bayleafwalker/auditctl](https://github.com/bayleafwalker/auditctl) |
| Action queue and session lifecycle | `actionq` | [bayleafwalker/actionq](https://github.com/bayleafwalker/actionq) |
| Operator UI and cross-repo plans | `agentops` | [bayleafwalker/agentops](https://github.com/bayleafwalker/agentops) |
| Kubernetes deployment | `appservice` | private — internal operations only |

These are siblings under `/projects/dev/`, not nested inside each other. `_artifacts/` is their shared output directory.

```
/projects/dev/
  sprintctl/
  kctl/
  auditctl/
  actionq/
  actionq-dispatcher/
  agentops/
  appservice/
  <consumer-repos>/
  _artifacts/
    <repo-id>/
      audit/
        events-YYYY-MM-DD.ndjson
      knowledge/
        knowledge-YYYY-MM-DD.ndjson
```

---

## Tools

### sprintctl

**What it does.** Tracks sprints, work items, claims, decisions, dependencies, and handoffs in SQLite (local mode) or PostgreSQL (remote mode). It is the system of record for active sprint execution.

**When to use it.** Any time you want to know what is active, what is blocked, what has been decided, or what to work on next. Use it at the start and end of every session.

**Modes.** `local` uses a per-repo SQLite file; suited for single-host, single-operator repos. `remote` uses a shared PostgreSQL cluster; suited for repos where cockpit visibility or multi-host coordination is needed. Mode is selected via environment: `SPRINTCTL_BACKEND=local` with `SPRINTCTL_DB=<path>`, or `SPRINTCTL_BACKEND=remote` with `SPRINTCTL_URL=<pg-url>`. Mode mismatch against a repo's declared mode is a hard error, not a silent fallback.

**Install.**
```bash
uv tool install /projects/dev/sprintctl --python python3
```

**Key commands.**
```bash
# Create and populate a sprint
sprintctl sprint create --name "Sprint 42" --status active
sprintctl item add --sprint-id 1 --track cli --title "Implement foo"

# Read live context (primary resume surface)
sprintctl usage --context --json
sprintctl session resume --json

# Claim and complete work
sprintctl claim start --item-id 1 --actor claude-session-1 --json
sprintctl item done-from-claim --claim-id <id> --claim-token <token> --actor claude-session-1

# Record durable notes during work
sprintctl item note --id 1 --type decision --summary "Chose X over Y because Z"

# Render a committed snapshot
sprintctl render > docs/sprint-snapshots/sprint-current.txt

# Migrate a repo from local to remote mode
sprintctl migrate-to-remote
```

**Key env vars.**

| Variable | Purpose |
|---|---|
| `SPRINTCTL_BACKEND` | `local` or `remote` |
| `SPRINTCTL_DB` | Path to SQLite file (local mode) |
| `SPRINTCTL_URL` | PostgreSQL connection string (remote mode) |

---

### kctl

**What it does.** Reads sprintctl event streams and extracts two separate artifact types: durable knowledge (decisions, patterns, lessons, blockers resolved) and coordination knowledge (claim handoffs, ownership corrections, workflow improvements). It drives a review pipeline: `candidate → approved → published → rendered markdown`.

**When to use it.** At the end of a sprint or working session to capture what mattered. Not during active work — `kctl` is a read-only consumer of sprintctl; it never writes back into sprint state.

**Install.**
```bash
uv tool install /projects/dev/kctl --python python3
```

**Key commands.**
```bash
# Extract candidates from recent sprint events
kctl extract --sprint-id 42

# Review pipeline
kctl review list --status pending --json
kctl review approve --id 7
kctl publish --id 7

# Render committed knowledge markdown
kctl render > docs/knowledge-base.md

# Machine-readable status for agents deciding sprint actions
kctl status --json
kctl review list --status approved --json
```

**Artifact output.** Published knowledge writes to `<artifacts-root>/_artifacts/<repo-id>/knowledge/`. This path is read by the agent cockpit's right pane.

---

### auditctl

**What it does.** Records human, agent, git, sprintctl, and actionq events into a repo-local SQLite index and a durable daily NDJSON shard. The SQLite database is the fast query index; the NDJSON shards are the portable artifact the cockpit reads.

**When to use it.** Transparently, via git hooks and publisher integrations. Directly for manual decisions, custom events, or recovery (`rebuild`). Repos opt in by installing the hooks and setting `AUDITCTL_ARTIFACTS_ROOT`.

**Install.**
```bash
uv tool install /projects/dev/auditctl --python python3
```

**Artifact layout.**
```
<AUDITCTL_ARTIFACTS_ROOT>/_artifacts/<repo-id>/audit/events-YYYY-MM-DD.ndjson
```
Each `auditctl add` writes atomically to both SQLite and the current day's NDJSON shard. If the NDJSON write fails, the SQLite write is rolled back. Either side is fully reconstructible from the other.

**Configure a repo.**
```bash
export AUDITCTL_DB="$PWD/.auditctl/auditctl.db"   # auto-detected from git root if unset
export AUDITCTL_ARTIFACTS_ROOT="/projects/dev"
```

**Key commands.**
```bash
# Add events
auditctl add --type decision  --actor bayleaf  --summary "Chose SQLite for audit store"
auditctl add --type commit    --source git-hook --actor bayleaf --summary "Commit abc123" --ref sha:abc123

# Query
auditctl list --limit 20
auditctl list --type session.start --since 2026-01-01

# Export and recover
auditctl render --format ndjson
auditctl rebuild --from-ndjson /projects/dev/_artifacts/homelab-analytics/audit
```

**Valid event types.** `commit`, `merge`, `pr.open`, `pr.merge`, `session.start`, `session.exit`, `dispatch`, `decision`, `custom`.

**Valid ref prefixes.** `wi:`, `ka:`, `ad:`, `sha:`, `pr:`, `sprint:`.

**Git hook setup.** Copy the hook templates from `auditctl/hooks/` into a repo's `.git/hooks/` directory:
```bash
cp /projects/dev/auditctl/hooks/post-commit  .git/hooks/post-commit
cp /projects/dev/auditctl/hooks/post-merge   .git/hooks/post-merge
chmod +x .git/hooks/post-commit .git/hooks/post-merge
```
The hooks self-silence if `auditctl` is not on `PATH`, so they are safe to install on machines without the tool.

**Key env vars.**

| Variable | Purpose |
|---|---|
| `AUDITCTL_DB` | SQLite database path (defaults to `<git-root>/.auditctl/auditctl.db`) |
| `AUDITCTL_ARTIFACTS_ROOT` | Parent of `_artifacts/`; required for writes |

---

### actionq

**What it does.** A PostgreSQL-backed action queue with a strict lifecycle (`pending → claimed → completed / failed / rejected / cancelled`) and an append-only event log. `actionctl` is the public contract. Consumers do not import the package or write SQL directly.

**When to use it.** To enqueue, dispatch, and track discrete units of agent work. The queue provides concurrency-safe claiming (via `SELECT … FOR UPDATE SKIP LOCKED`), rate limiting for automated producers, chain-depth enforcement for parent-child actions, and a coordinator event surface for daemon session tracking.

**Install.**
```bash
uv tool install /projects/dev/actionq --python python3
```

**Queue setup.**
```bash
export ACTIONQ_URL='postgresql://user:password@host:5432/db'
actionctl migrate
```

**Key commands.**
```bash
# Enqueue
actionctl add \
  --type scope-iterate \
  --project sprintctl \
  --target 42 \
  --source doc:plan \
  --created-by human:cli

# Dispatch loop (exits with code 2 when queue is empty)
actionctl claim --worker worker:dispatcher-1
actionctl complete 1 --result branch=agent/scope-iterate/1

# Inspect
actionctl ls --status pending
actionctl show 1
actionctl events

# Session state (daemon sessions, derived from coordinator events)
actionctl sessions --active
actionctl sessions --project homelab-analytics

# Coordinator events from daemon
actionctl emit --type session.heartbeat --actor daemon:devbox \
  --payload '{"session_id": "aqs:abc", "pid": 12345}'

# Maintenance
actionctl sweep   # requeue timed-out claims
```

**Session read contract.** `actionctl sessions` returns a JSON array where each row summarizes a session by reducing `session.*` coordinator events. The cockpit consumes this through a gateway adapter; it is the stable interface regardless of whether a dedicated `actionq-server` API sits in front.

**Key env vars.**

| Variable | Default | Purpose |
|---|---|---|
| `ACTIONQ_URL` | required | PostgreSQL connection string |
| `ACTIONQ_SCHEMA` | `actionq` | Schema name |
| `ACTIONQ_MAX_CHAIN_DEPTH` | `3` | Max parent-child action depth |
| `ACTIONQ_RATE_LIMIT_PER_HOUR` | `20` | Hourly enqueue cap for `agent:` and `script:` producers |

---

### actionq-dispatcher

**What it does.** A one-shot coordinator that claims a single pending action, prepares an isolated git worktree, invokes an agent worker (Claude via CLI, or a fake worker for smoke testing), validates the resulting diff against configured ACLs and gates, and records the outcome through `actionctl` and `sprintctl`.

**When to use it.** When running agent sessions from a cron job, systemd timer, or manual invocation. Each `dispatcher-once` call handles exactly one action cycle. Scheduling frequency is an operator decision external to the tool.

**Install.**
```bash
uv tool install /projects/dev/actionq-dispatcher --python python3
```

**One cycle.**
```bash
dispatcher-once --config /path/to/config.toml
```
If `DISPATCHER_CONFIG` is set, the flag can be omitted. Returns `{"result": "completed", "action_id": N}` or similar on success.

**Runners.** `local` invokes the Claude CLI with ACL-scoped tool permissions. `fake` or `fake-commit` writes a deterministic file and commits without calling a model — use this to validate queue, worktree, and gate flow before enabling real sessions.

**Pause without changing service wiring.**
```bash
touch ~/.local/state/actionq-dispatcher/PAUSED
# Invocations exit cleanly, emit coordinator_paused, claim nothing
rm ~/.local/state/actionq-dispatcher/PAUSED
```

**Config shape (TOML).**
```toml
[global]
worktree_root      = "~/.local/state/actionq-dispatcher/worktrees"
pause_file         = "~/.local/state/actionq-dispatcher/PAUSED"
actionctl_bin      = "actionctl"
claude_bin         = "claude"

[projects.sprintctl]
path               = "/projects/dev/sprintctl"
base_ref           = "HEAD"

[actions.scope-iterate]
model              = "claude-sonnet-4-6"
runner             = "local"
prompt_template    = "/projects/dev/actionq-dispatcher/prompts/scope-iterate.md"
tool_acl           = "/projects/dev/actionq-dispatcher/acls/scope-iterate.json"
test_command       = "pytest"
```

---

## The Agent Cockpit

The agent cockpit (`agentops/apps/web`) is a read-only operator surface. It displays sprint state, active sessions, and audit history from three independent data sources in a single UI. It does not own any state itself.

### Architecture

```
                   COCKPIT-WEB (k8s pod)
                   ┌──────────────────────────────────────┐
                   │  React SPA (static bundle)           │
                   │  cockpit-api (read-only gateway)     │
                   └────┬────────────────┬───────────────┬┘
                        │                │               │
                pg://sprintctl   nfs:_artifacts      actionq://sessions
                (sprint/items/   /<repo>/audit/      (session liveness,
                 takeup events)   *.ndjson)            heartbeats, TTL)
```

`cockpit-api` is the single façade the SPA talks to. It owns PostgreSQL connection pooling, NFS shard parsing, actionq session reads, source-of-truth label stamping, and the dispatch write path. The SPA never connects to pg, NFS, or actionq directly.

### Three-Pane Layout

**Left / center pane.** Sprint hero (active sprint progress, burn bar), claims table (work items with item-level claims from pg joined to session liveness from actionq), sprint takeup panel (per-repo opaque taken-up / released state), action queue.

**Right pane.** Two stacked feeds:
- *Outcomes & Review* — audit NDJSON parsed and normalized per repo (commits, PRs, decisions, releases). Source label: `nfs:_artifacts/<repo>/audit/`.
- *Sprint event feed* — sprintctl events for the active sprint. Source label: `pg://sprintctl/events`.

**Repo strip.** Tabs for each repo in the workspace. Repos with sprintctl remote-mode data appear under **REMOTE** and support the full cockpit. Repos with only audit shards appear under **LOCAL** with audit feeds only. **ALL** means all REMOTE repos.

### Source Labels

Every pane carries a small monospace label identifying where its data came from:

| Pane | Source label |
|---|---|
| Action queue | `actionq://queue` |
| Claims / sessions table | `actionq://sessions` + `pg://sprintctl/items` |
| Sprint hero | `pg://sprintctl/sprint` |
| Sprint takeup panel | `pg://sprintctl/events#takeup` |
| Outcomes & Review | `nfs:_artifacts/<repo>/audit/` |
| Sprint event feed | `pg://sprintctl/events` |

When a source is unreachable, its pane shows a labeled banner rather than phantom data. Substrates fail independently; the cockpit remains partial rather than entirely broken.

### Session Join Contract

The cockpit joins sprintctl claim records to actionq sessions in this order:

1. `claim.runtime_session_id == session.runtime_session_id`
2. Fallback: `claim.claim_id == session.claim.claim_id` within the same repo

No joins on branch names, worktree paths, or other payload fragments.

### Dispatch

The dispatch composer POSTs to `cockpit-api → actionq-server`. Sprint takeup happens as a side effect of session start, not as a direct write from cockpit. The cockpit has no other write paths to pg or NFS.

### Live Update

Panes poll at independent intervals via the gateway. Intervals scale up when the browser tab is hidden (`document.visibilityState === 'hidden'`). The TWEAKS panel exposes per-pane interval overrides.

Default intervals: action queue 2 s, sessions 2 s, audit feed 5 s (gateway-side delta cursor), sprint events 10 s, sprint hero 15 s.

---

## Deployment

All live Kubernetes manifests live in `appservice/clusters/main/kubernetes/apps/`. The tool repos may include example manifests in `deploy/examples/` but `appservice` is the deployment source of truth. `appservice` is a private, internal-operations-only repo and is not published under `bayleafwalker`.

### PostgreSQL Clusters (CNPG)

Two CNPG clusters serve the substrate:

- `actionq-cnpg-main` (namespace `vscode`) — action queue tables.
- `sprintctl-cnpg-main` — sprintctl remote-mode tables, `repo_id` as a column on Sprint / Track / WorkItem / Event, single schema across all repos.

The `vscode-shell` pod has `SPRINTCTL_URL` injected from the sprintctl CNPG app secret so remote-mode tools work in the devbox without manual configuration.

### Devbox Pattern

`actionq-daemon` runs on the devbox (the `vscode-shell` pod) as a long-running process. It:

- Pulls dispatch instructions from the action queue.
- Spawns agent sessions (`claude`, `codex`, `opencode`) with ACL-scoped tool permissions.
- Tracks session PID and emits `session.*` coordinator events via `actionctl emit`.
- Calls `sprintctl claim start / done-from-claim` on session boundaries.
- Calls `auditctl add --type session.start / session.exit` for each session.

Scheduling the daemon (systemd unit, cron, or k8s init container restart loop) is an operator choice. Example unit files live under `actionq-dispatcher/ops/`.

### Cockpit Pod

The cockpit pod runs in the `appservice` namespace. It requires:

- A read-only PostgreSQL role scoped to sprintctl tables.
- A read-only mount of the `_artifacts/` PVC at the NFS root path.
- Network access to the actionq-server service.

Auth is network-identity-based (cluster-internal or Tailscale). No per-user login in the single-operator homelab configuration.

### Artifact Root

`_artifacts/` is a sibling directory of the project repos under `/projects/dev`. It is not committed inside any repo. Back it up alongside the repos.

```
/projects/dev/_artifacts/
  homelab-analytics/
    audit/
      events-2026-04-26.ndjson
      events-2026-04-27.ndjson
    knowledge/
      knowledge-2026-04-26.ndjson
  sprintctl/
    audit/
    knowledge/
```

The cockpit pod mounts this as a read-only NFS volume.

---

## Quickstart

### Track A: Sprint workflow only

Suitable for any repo that wants structured execution state without queue dispatch or audit publishing.

```bash
# 1. Install
uv tool install /projects/dev/sprintctl --python python3
uv tool install /projects/dev/kctl     --python python3

# 2. Configure (add to repo .envrc, or direnv allow after editing)
export SPRINTCTL_BACKEND=local
export SPRINTCTL_DB="$PWD/.sprintctl/sprintctl.db"

# 3. Create a sprint
sprintctl sprint create --name "Sprint 1" --status active
sprintctl item add --sprint-id 1 --track cli --title "Bootstrap tooling"

# 4. Work loop
sprintctl usage --context --json      # check context at session start
sprintctl claim start --item-id 1 --actor me --json
# ... do work ...
sprintctl item note --id 1 --type decision --summary "Decided on X"
sprintctl item done-from-claim --claim-id <id> --claim-token <token> --actor me

# 5. Extract and publish knowledge at sprint end
kctl extract --sprint-id 1
kctl review list --status pending --json
kctl review approve --id 1
kctl publish --id 1
kctl render > docs/knowledge-base.md
```

---

### Track B: Add audit publishing

Extend Track A with `auditctl` to capture commits, merges, decisions, and session events as NDJSON artifacts the cockpit reads.

```bash
# 1. Install
uv tool install /projects/dev/auditctl --python python3

# 2. Configure (add to .envrc)
export AUDITCTL_DB="$PWD/.auditctl/auditctl.db"
export AUDITCTL_ARTIFACTS_ROOT="/projects/dev"   # writes under /projects/dev/_artifacts/<repo-id>/

# 3. Install git hooks
cp /projects/dev/auditctl/hooks/post-commit .git/hooks/post-commit
cp /projects/dev/auditctl/hooks/post-merge  .git/hooks/post-merge
chmod +x .git/hooks/post-commit .git/hooks/post-merge

# 4. Add manual events
auditctl add --type decision --actor me --summary "Chose X over Y"

# 5. Verify artifacts
auditctl list --limit 10
ls /projects/dev/_artifacts/<repo-id>/audit/
```

Commits and merges now land in the daily NDJSON shard automatically. The cockpit's right-pane Outcomes feed reads from these shards.

---

### Track C: Queue-dispatched agent sessions

Extend Track B with `actionq` and `actionq-dispatcher` to run agent sessions as discrete claimed actions with full lifecycle tracking.

```bash
# 1. Install
uv tool install /projects/dev/actionq            --python python3
uv tool install /projects/dev/actionq-dispatcher --python python3

# 2. Configure (add to .envrc)
export ACTIONQ_URL='postgresql://user:password@host:5432/db'
export ACTIONQ_SCHEMA='actionq'

# 3. Initialize queue schema
actionctl migrate

# 4. Enqueue work
actionctl add \
  --type scope-iterate \
  --project homelab-analytics \
  --target 42 \
  --source doc:plan \
  --created-by human:cli

# 5. Smoke-test the dispatcher (fake worker, no model call)
dispatcher-once --config /projects/dev/actionq-dispatcher/examples/config.smoke.toml

# 6. Run a real session
dispatcher-once --config /path/to/config.toml

# 7. Observe session state
actionctl sessions --active
actionctl events --limit 20
```

For continuous dispatch, schedule `dispatcher-once` via cron or a systemd timer. The tool exits with code `2` when the queue is empty, making it safe to poll:

```bash
# cron: run every 5 minutes
*/5 * * * * dispatcher-once --config /path/to/config.toml || true
```

The dispatcher emits `session.*` coordinator events into actionq and calls `auditctl add` on session boundaries. Both event streams flow through to the cockpit without additional wiring.

---

## Repo Boundaries (Reference)

| Repo | Owns | Does not own |
|---|---|---|
| `sprintctl` | Sprint state, work items, claims, decisions, takeup events | Session liveness, heartbeats, audit events |
| `kctl` | Knowledge review pipeline, durable artifact rendering | Sprint writes, audit events |
| `auditctl` | Repo-local audit index, NDJSON shards, git hook templates | Sprint state, knowledge graph, centralized storage |
| `actionq` | Action queue, session lifecycle, heartbeat / TTL semantics, dispatch daemon | Sprint state, knowledge, audit internals |
| `agentops` | Operator UI, cross-repo substrate plans | Substrate state (reads only) |
| `appservice` | Live Kubernetes manifests, CNPG clusters, secrets (private repo) | Application logic |

The boundary rule: if data travels with a repo (is per-repo, local-first, recoverable from the repo's own history), it belongs in `auditctl` or `kctl`. If data is cluster-wide coordination (active sessions, dispatch policy, sprint state across hosts), it belongs in `actionq` or `sprintctl remote`. The cockpit reads all of these; it writes to none of them except through the dispatch composer → actionq path.
