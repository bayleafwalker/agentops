# Agent-Ops Ecosystem

A reference for the `/projects/dev` agent-ops substrate: what each tool does, how they relate, how the cockpit reads them, how to deploy the system, and how to get started.

> **Current target architecture, realigned 2026-08-20:** native harnesses and
> runtimes execute agent work; Sprintctl uses advisory reservations plus
> expected-revision CAS; ActionQ contracts toward a federation layer that
> records work/execution references, relations, assurance, acceptance, and
> reconciliation without owning a worker daemon, queue, leases, or fan-out;
> Outctl is retired from active Vuoro scope. See
> [`native-runtime-federation-realignment-2026-08-20.md`](plans/agentops/native-runtime-federation-realignment-2026-08-20.md)
> and [`vuoro-system-shape.md`](architecture/vuoro-system-shape.md). Sections
> explicitly labelled **deployed compatibility** describe migration residue,
> not a surface to extend.

---

## What This Is

The agent-ops substrate is a set of small, composable tools that give one developer (with optional agent sessions) structured execution state, durable history, and an operator view over their work. Each tool owns exactly one domain. None of them replaces the others.

The core rule: **state ownership decides repo ownership.**

The companion target rule is: **a Vuoro client may understand transport and
presentation, but it does not carry the authoritative implementation of
substrate policy.** Domain ownership remains split even when one deployed
Vuoro process composes all domain adapters.

| Domain | Tool | Repo |
|---|---|---|
| Sprint and work-item state | `sprintctl` | [bayleafwalker/sprintctl](https://github.com/bayleafwalker/sprintctl) |
| Knowledge extraction and review | `kctl` | [bayleafwalker/kctl](https://github.com/bayleafwalker/kctl) |
| Repo-local audit and event ledger | `auditctl` | [bayleafwalker/auditctl](https://github.com/bayleafwalker/auditctl) |
| Federated work/execution references, relations, assurance, acceptance and reconciliation (target) | `actionq` | [bayleafwalker/actionq](https://github.com/bayleafwalker/actionq) |
| Native agent execution and session lifecycle | selected first-party harness/runtime | external integration boundary |
| Native harness telemetry and raw evidence | OpenTelemetry plus selected Langfuse or Phoenix/object storage | deployment-selected, non-authoritative |
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
  outctl/                  # frozen discovery artifact; not a project member
  agentops/
  appservice/
  <consumer-repos>/
  _artifacts/              # host-local unless explicitly replicated
    <repo-id>/
      audit/
        events-YYYY-MM-DD.ndjson
      knowledge/
        knowledge-YYYY-MM-DD.ndjson
```

## Cockpit Architecture (staged rollout boundary)

The cockpit is a Next.js app in `agentops/apps/web`. The browser talks only to
`/cockpit/api/*` routes served by the same pod; those routes are the gateway for
PostgreSQL, actionq-server, workspace artifacts, and the shared cost log.

The table below describes the pre-retirement deployment shape. It may remain
observable until the operator lands appservice phase 1, proves namespace and
database health, and then lands phase 2. Repository source does not prove those
runtime steps have happened.

Pre-retirement data paths:

| Cockpit surface | Source |
|---|---|
| Repos, sprints, work items, historical claims/current reservations, takeup, sprint events | Sprintctl owner adapter (legacy deployment may still label this `pg://sprintctl`) |
| Sessions and dispatch lifecycle rows | `actionq-server` (`/sessions`, `/dispatches`, `/dispatch`) |
| Audit outcome feed | `/projects/dev/_artifacts/<repo-id>/audit/*.ndjson` read-only |
| Dispatch manifest summary | `agentops/templates/dispatch/examples/*.dispatch.json` by default |
| Status-bar cost token | `/projects/dev/.claude/session-costs.jsonl` |
| Model headroom | Configured JSON refresh commands cached by `/cockpit/api/headroom` |

The pre-retirement cockpit write path, `POST /cockpit/api/dispatch`, forwards
to `actionq-server` only when `COCKPIT_ACTIONQ_SERVER_URL` and
`COCKPIT_ACTIONQ_DISPATCH_CONTRACT=v1` are set. Appservice phase 2 removes that
binding; it is intentionally not replaced by a queue worker. Sprintctl and the
workspace artifact mount remain read-only from the cockpit.

New repository adoption starts from
`agentops/templates/dispatch/repository-baseline/`. The baseline keeps shared
skills and schemas in agentops while the consumer owns its overlay, semantic
document, context packets, executable tests, and evidence. Run the shared
dependency-free validator from the consumer root before dispatch or publication.

`outctl` was retired from active Vuoro scope on 2026-08-16. Its repository is a
frozen discovery artifact, not an adjacent live component or project member.
New harness-evidence work belongs at the native runtime boundary and targets
standard OpenTelemetry plus the operator-selected Langfuse or Phoenix and
object-storage path. Those observations remain non-authoritative and require
explicit redaction and retention policy.

The deployed Dispatches pane still renders historical/current compatibility
ActionQ queue rows. The target cockpit instead shows federated native execution
references and their assurance/acceptance/reconciliation state. There is no
dispatcher-meta UI backlog: the underlying fan-out engine is retired, not
deferred.

Model headroom is intentionally a soft signal. Codex `/status` and Claude Code
`/usage` are slash-command/TUI surfaces today, so the cockpit does not scrape
them or assume private auth endpoints. Operators can provide
`COCKPIT_CODEX_HEADROOM_COMMAND` and `COCKPIT_CLAUDE_HEADROOM_COMMAND` that emit
JSON shaped like the upstream usage data. The gateway keeps reset timestamps,
Codex credits and review limits, and Claude's Opus/non-Opus weekly split, caches
the last successful value, and marks stale data when refresh fails.

---

## Tools

### sprintctl

**What it does.** Tracks sprints, work items, revisions, decisions,
dependencies, handoffs, and advisory reservations. A reservation makes
overlapping work visible; it is not a capability and does not prevent a second
reservation. Expected-revision CAS protects work mutation.

**When to use it.** Any time you want to know what is active, what is blocked, what has been decided, or what to work on next. Use it at the start and end of every session.

**Modes.** `local` uses the repository SQLite authority. Normal shared access
uses the served Vuoro adapter selected by the repository backend record;
normal-client direct PostgreSQL/`remote` mode is retired. Backend mismatch is a
hard error, not a silent fallback.

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

# Reserve and complete work
sprintctl reservation reserve --item-id 1 --actor codex-session-1 \
  --role execution --session-id "$SPRINTCTL_RUNTIME_SESSION_ID" --json
sprintctl item show --id 1 --json   # read status_revision
sprintctl item status --id 1 --status done --actor codex-session-1 \
  --expected-revision 'item:<uuid>@status:active'

# Record durable notes during work
sprintctl item note --id 1 --type decision --summary "Chose X over Y because Z"

# Render a committed snapshot
sprintctl render > docs/sprint-snapshots/sprint-current.txt

# Inspect overlapping advisory reservations
sprintctl reservation list --item-id 1 --json
```

**Key client settings.**

| Setting | Purpose |
|---|---|
| repository `.sprintctl/backend.json` | `local` or `served` normal-client selection |
| `SPRINTCTL_DB` | Path to SQLite file (local mode) |
| served endpoint/profile variables | Vuoro transport configuration; clients do not receive PostgreSQL authority credentials |

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
`auditctl add` is an ordered, recoverable dual-write: SQLite insertion is held
uncommitted while the locked NDJSON append is fsynced, then SQLite commits. It
is not a fictional cross-store atomic transaction. A successful response means
both writes completed; a crash or lost response can leave an unknown outcome
that must be resolved by the audit repository's rebuild/recovery procedure.

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

**Target responsibility.** ActionQ is contracting from its PostgreSQL queue and
execution plane into the federation owner for work identity/relations/revisions,
authority and evidence requirements, references to external native executions,
acceptance, reconciliation, and backend qualification. Each execution
reference records the binding assurance the selected runtime can actually
prove.

**Current owner source.** ActionQ 0.1.26 (`9dccf4e`) removed
`actionq-daemon`, all harness adapters, worktree/session execution, and the
standalone HTTP server. The retained package is a PostgreSQL action-lifecycle
owner with `actionctl`, its Vuoro execution adapter, completion outbox, and
supporting persistence. Lease/claim persistence remains in that retained
surface and is the next extraction boundary; source deletion is not a claim
that the federation target is complete.

**When to use it.** New integrations use only reviewed federation contracts as
they land. They do not enqueue work for an ActionQ worker, create a worker
loop, or make ActionQ supervise a native runtime. Native sessions start and are
controlled at their own runtime boundary. Current queue commands are retained
for owner-local inspection, migration, compatibility, and extraction work, not
as a new execution adoption path.

**Install.**
```bash
uv tool install /projects/dev/actionq --python python3
```

**Owner-local inspection commands.**
```bash
actionctl check-compatibility
actionctl ls --status pending
actionctl show 1
actionctl events
```

Do not infer a current session or worker API from historical `session.*`
events. The session wrapper and server projection that produced those rows were
removed from owner source.

**Key env vars.**

| Variable | Default | Purpose |
|---|---|---|
| `ACTIONQ_URL` | required | PostgreSQL connection string |
| `ACTIONQ_SCHEMA` | `actionq` | Schema name |
| `ACTIONQ_MAX_CHAIN_DEPTH` | `3` | Max parent-child action depth |
| `ACTIONQ_RATE_LIMIT_PER_HOUR` | `20` | Hourly enqueue cap for `agent:` and `script:` producers |

---

### actionq-dispatcher

**Status: inactive retirement tombstone.** Release 0.2.0 (`510822a`, tag
`actionq-dispatcher-v0.2.0`) retains the `dispatcher-once` console-script name
only. Every invocation exits nonzero with an actionable retirement message; it
does not resolve an executable, spawn a process, read configuration, or access
a queue.

Do not install or schedule this package for new work. On a host that still has
the pre-retirement launcher, an operator may upgrade once to 0.2.0 so stale
callers fail clearly, then uninstall it after the callers and services are
removed. This is a migration operation, not a functioning compatibility mode.
Historical implementation remains in Git history and the
`actionq-dispatcher-v0.1.2` tag.

---

## The Agent Cockpit (deployed compatibility and migration target)

The agent cockpit (`agentops/apps/web`) is a read-only operator surface. It displays sprint state, active sessions, and audit history from three independent data sources in a single UI. It does not own any state itself.

The diagram and field names below describe the deployed queue-era UI. Migration
replaces claim/session joins and queue dispatch writes with Sprintctl advisory
reservations and read-only ActionQ federation references. A historical queue
row may remain visible, but the cockpit must not launch or supervise a native
runtime.

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

The deployed cockpit joins historical Sprintctl claim records to ActionQ
sessions in this order:

1. `claim.runtime_session_id == session.runtime_session_id`
2. Fallback: `claim.claim_id == session.claim.claim_id` within the same repo

No joins on branch names, worktree paths, or other payload fragments.

### Dispatch (pre-retirement deployment shape)

Before appservice phase 2, the dispatch composer may still POST to
`cockpit-api → actionq-server`. That path has no current owner-source server or
worker behind it and is removed, not replaced, by the gated rollout. The
cockpit has no other write paths to Sprintctl or the artifact mount.

### Live Update

Panes poll at independent intervals via the gateway. Intervals scale up when the browser tab is hidden (`document.visibilityState === 'hidden'`). The TWEAKS panel exposes per-pane interval overrides.

Default intervals: action queue 2 s, sessions 2 s, audit feed 5 s (gateway-side delta cursor), sprint events 10 s, sprint hero 15 s.

---

## Deployment (current compatibility inventory)

All live Kubernetes manifests live in `appservice/clusters/main/kubernetes/apps/`. The tool repos may include example manifests in `deploy/examples/` but `appservice` is the deployment source of truth. `appservice` is a private, internal-operations-only repo and is not published under `bayleafwalker`.

### PostgreSQL Clusters (pre-retirement inventory)

The staged deployment inventory includes two CNPG clusters; verify their
actual state through the operator-owned appservice rollout evidence:

- `actionq-cnpg-main` (namespace `vscode`) — action queue tables.
- `sprintctl-cnpg-main` — sprintctl remote-mode tables, `repo_id` as a column on Sprint / Track / WorkItem / Event, single schema across all repos.

The `vscode-shell` pod has `SPRINTCTL_URL` injected from the sprintctl CNPG app secret so remote-mode tools work in the devbox without manual configuration.

### Devbox retirement gate

The devbox unit and its pinned checkout are running-system residue, not a
current ActionQ package surface. Do not start, reinstall, refresh, or repin
`actionq-dispatch.service`: ActionQ 0.1.26 has no matching daemon entry point.
Runtime retirement is complete only after operator evidence shows the unit was
disabled and stopped and the separately reviewed NixOS module retirement was
deployed. Repository merge state alone is insufficient.

### Cockpit Pod (pre-retirement requirements)

The cockpit pod runs in the `appservice` namespace. It requires:

- A read-only PostgreSQL role scoped to sprintctl tables.
- A read-only mount of the `_artifacts/` PVC at the NFS root path.
- Network access to the actionq-server service until appservice phase 2 removes
  the retired binding.

Auth is network-identity-based (cluster-internal or Tailscale). No per-user login in the single-operator homelab configuration.

### Artifact Root

`_artifacts/` is a sibling directory of the project repos under `/projects/dev`.
It is semi-ephemeral and host-local unless explicitly copied and hash-verified;
its path is not evidence of cross-host durability. Durable references belong in
the owning served systems.

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
sprintctl reservation reserve --item-id 1 --actor me --role execution \
  --session-id "$SPRINTCTL_RUNTIME_SESSION_ID" --json
# ... do work ...
sprintctl item note --id 1 --type decision --summary "Decided on X"
sprintctl item show --id 1 --json  # read status_revision
sprintctl item status --id 1 --status done --actor me \
  --expected-revision 'item:<uuid>@status:active'

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

### Historical Track C: queue-dispatched agent sessions (superseded)

This was the queue-era adoption track. Its implementation is preserved in Git
history, not as executable current guidance. Remove old schedules and units;
do not install, invoke, or smoke-test `dispatcher-once`, and do not replace it
with `actionq-daemon --once`. New work starts through the selected native
runtime and, once reviewed contracts exist, records or reconciles an external
execution reference through ActionQ federation.

---

## Repo Boundaries (Reference)

| Repo | Owns | Does not own |
|---|---|---|
| `sprintctl` | Sprint state, work items, revisions, decisions, dependencies, advisory reservations | Native session lifecycle, telemetry, audit events |
| `kctl` | Knowledge review pipeline, durable artifact rendering | Sprint writes, audit events |
| `auditctl` | Repo-local audit index, NDJSON shards, git hook templates | Sprint state, knowledge graph, centralized storage |
| `actionq` | Target federation domain; currently retained queue lifecycle, Vuoro adapter, and persistence extraction boundary after daemon/server/harness source deletion | Native runtime execution, Sprint state, knowledge, audit internals |
| `actionq-dispatcher` | Inactive fail-closed retirement tombstone | Dispatch, queue access, process launch, federation, or workflow policy |
| `agentops` | Operator UI, cross-repo substrate plans | Substrate state (reads only) |
| `appservice` | Live Kubernetes manifests, CNPG clusters, secrets (private repo) | Application logic |

The boundary rule: work state and its mutation revisions belong to Sprintctl;
native execution belongs to the selected runtime; cross-runtime identity,
relations, assurance, evidence requirements, acceptance, and reconciliation
belong to ActionQ's target federation layer. Auditctl and Kctl retain their own
audit and knowledge records. The cockpit composes owner APIs and does not gain
raw database or native-runtime execution authority.
