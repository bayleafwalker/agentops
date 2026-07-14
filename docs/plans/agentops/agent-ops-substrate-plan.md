# agent-ops substrate: pg backend, audit log, dispatch service

> **Direction update (2026-07-14):** this plan's framing of separate "local"
> and "remote" sprintctl backend modes — including the core decisions "two
> named modes, not a pluggable backend" and "pg unreachable = clear error, no
> local queue, no replay" — is superseded as *target direction* by
> `sprintctl/docs/plans/adr-outbox-sync-model.md` (doc_id
> `adr-outbox-sync-model`): one producer-side write mechanism (durable local
> outbox), a cached local projection with a visible remote watermark, and an
> observation/command/decision split. The rest of this plan (ownership
> boundaries, auditctl, actionq, cockpit workstreams) remains valid; read the
> backend-mode sections as shipped history, not as the current target.

Plan for the next slice of development workflow tooling: sprintctl gains a pg backend and remote mode for cross-host coordination, auditctl serves as the repo-local audit tool, actionq becomes the queue/service/daemon boundary for dispatched sessions, and the agent-cockpit surface in `agentops` becomes the operator frontend for the substrate that actually exists.

This plan absorbs the earlier `sprintctl-multi-agent-takeup-plan.md` as workstream A; that plan ships unchanged and is the prerequisite for everything else.

## Ownership

This is a cross-repo agent-ops plan, not a `homelab-analytics` implementation plan. The target ownership boundaries follow `/projects/dev/agentops/docs/plans/agentops/agentops-naming-structure-plan.md`:

- Sprint state -> `sprintctl`
- Knowledge artifacts -> `kctl`
- Audit/event ledger -> `auditctl`
- Session lifecycle -> `actionq`
- Operator view -> `agentops` (`agent-cockpit` surface)
- Runtime deployment -> `appservice`

`homelab-analytics` is the first pilot consumer of the substrate. It validates migration, artifact layout, git-hook publishing, and cockpit visibility, but it does not own the substrate implementation.

## Current Workspace Shape

The current `/projects/dev` workspace is a flat set of sibling repositories plus the repo-owned agentops planning surface:

```text
/projects/dev/
  auditctl/             # existing repo-local audit ledger implementation
  actionq/              # existing Postgres-backed queue and actionctl CLI
  actionq-dispatcher/   # existing dispatcher-once implementation
  appservice/           # existing GitOps/deployment source of truth
  homelab-analytics/    # pilot consumer
  kctl/                 # existing knowledge tool
  sprintctl/            # existing sprint/work-item tool
  agentops/             # cross-repo plans and future cockpit/operator surface
```

`auditctl/` now exists as an implementation repo. Workstream D still owns any remaining rollout or contract-alignment work, but the repo-creation step is no longer future work. The agent-cockpit operator surface is planned inside `/projects/dev/agentops`, not as a separate `/projects/dev/agent-cockpit` repo.

Current deployment state in `appservice` includes the actionq Postgres database at:

```text
/projects/dev/appservice/clusters/main/kubernetes/apps/actionq-db/
```

That Flux app creates CNPG cluster `actionq-cnpg-main` in the `vscode` namespace. `sprintctl-postgres` now also exists as a Flux app at `/projects/dev/appservice/clusters/main/kubernetes/apps/sprintctl-postgres/`, while `actionq-server` and `agent-cockpit` remain target deployment units for later workstreams.

## Current Readiness Snapshot

As of 2026-04-28:

- `agentops` is still docs-only; there is no `apps/web/` scaffold yet.
- `auditctl` exists and the planned artifact root is already in use at `/projects/dev/_artifacts/homelab-analytics/audit/`.
- `homelab-analytics` is a clean pilot target rather than an actively blocked implementation repo: sprint `#78` is still marked active, but its items are `5/5` done with no active claims.
- The only stale sprintctl item currently visible in the pilot repo is backlog item `#414` in sprint `#64 cinder-ledger-path`.
- `appservice` carries `actionq-db` and `sprintctl-postgres`; there are still no runtime manifests for `actionq-server` or `agent-cockpit`.
- Cockpit dispatch remains blocked on an actionq API contract that workstream C minimum does not provide.

## Why

The cockpit mock (see `Cockpit.html` ideation) implies a topology that the current sprintctl design does not support: cluster-side reads against sqlite over the shared mount (unsafe under WAL), heartbeat/TTL on sprint-level state (rejected by the multi-agent plan), and a single right-pane "outcomes" feed that conflates sprintctl events with what should be per-repo audit history.

Rather than retrofit the mock onto sprintctl, this plan defines the substrate the cockpit can actually sit on: pg-backed sprintctl for cross-host work, sqlite-backed per-repo tools for things that should travel with the repo, and a dispatch service that owns session lifecycle so sprintctl never has to.

## Core decisions (do not relitigate)

- **Sprintctl gets two named modes, not a pluggable backend.** `local` is sqlite-on-disk, single-host, current behavior. `remote` is pg, multi-host, cluster-accessible. Selection is per-repo via env (`SPRINTCTL_BACKEND`, `SPRINTCTL_DB` or `SPRINTCTL_URL`). No backend abstraction layer; the two modes share the CLI surface and event model but are independent storage implementations. Mode mismatch between operator and repo is a hard error, not a fallback.
- **Pg uses single schema with `repo_id` as a column.** No schema-per-repo. Cockpit cross-repo queries become `WHERE repo_id IN (...)` instead of `UNION ALL` across N schemas. Meta-sprints are not architecturally special; they just have a designated `repo_id` (e.g. `_orchestration`).
- **`repo_id` is the repository's directory name.** Path-derived, no separate registry. Operator invariant: repo names across the homelab fleet are unique. If they ever aren't, that's a naming problem to fix at the source, not a schema problem to absorb.
- **Auditctl is sqlite-only, repo-local, with NDJSON as the durable artifact.** Same family as kctl. Sqlite is the fast queryable index; NDJSON is the durable, host-portable artifact that cockpit reads. Either side is reconstructible from the other or from upstream sources (git, sprintctl events). No pg backend for auditctl, ever — the centralization argument that justifies pg for sprintctl does not apply.
- **NDJSON shards daily.** `events-YYYY-MM-DD.ndjson` per repo. Single unbounded files are bad on the read end (cockpit tailing), the rotation end (retention), and the diff end (if ever committed).
- **Audit NDJSON lives sibling under /projects/dev, not in-repo.** Path: `/projects/dev/_artifacts/<repo_id>/audit/`. Same pattern for `<repo_id>/knowledge/` from kctl. Repos stay clean; cockpit gets a read-only mount path; durability is operational (back up `_artifacts/` alongside repos).
- **Heartbeats and TTL belong to actionq, not sprintctl.** Sprintctl tracks takeup as opaque event-pair (taken_up / released). Actionq owns session liveness because actionq owns the session. Cockpit may display both layers but they come from different sources and the UI must not blur them.
- **Actionq owns service and daemon semantics.** The command/service names are `actionq`, `actionq-server`, and `actionq-daemon`; "cluster" is a deployment role, not the repo or binary name. Current code is split between `actionq/` and `actionq-dispatcher/`; workstream C should either absorb dispatcher code into `actionq/` or leave a documented compatibility bridge. No `ssh devbox claude --prompt-file ...`. The daemon enables pause/resume on usage limits, queue replay, and clean session lifecycle tracking.
- **Agentops owns the operator UI.** Do not build the agent-cockpit surface inside `homelab-analytics`; that repo is a pilot data/workflow consumer.
- **Pilot migration: homelab-analytics first, financial-analytics extension second, sprintctl itself third.** Other repos stay local-mode until they earn their way to remote. Some repos may stay local-mode indefinitely.

## Architecture topology

```
                                                 /projects/dev on shared storage
                                                 ├── <repo>/...                 (flat sibling repos)
                                                 └── _artifacts/<repo>/         (planned runtime artifacts)
                                                     ├── audit/events-*.ndjson  (cockpit reads)
                                                     └── knowledge/*.ndjson     (cockpit reads)
  WORKSTATION(S)
  ├── sprintctl (local or remote)
  ├── kctl, auditctl (local sqlite, writes NDJSON to /projects/dev/_artifacts)
  └── manual planning sessions, vscode

  DEVBOX (cluster pod or VM, single instance)
  ├── sprintctl, kctl, auditctl
  ├── actionq-daemon (long-running, owns session lifecycle)
  └── agent harnesses (claude, codex, copilot-cli) — invoked by daemon

  CLUSTER (k8s, appservice GitOps)
  ├── current: actionq-db CNPG at clusters/main/kubernetes/apps/actionq-db/
  ├── current: sprintctl-postgres CNPG at clusters/main/kubernetes/apps/sprintctl-postgres/
  ├── target: actionq-server (queue/service API; talks to daemon over k8s network)
  └── target: agent-cockpit surface from agentops (read-only against pg + /projects/dev/_artifacts/)
```

Single-host repos use sprintctl in local mode; pg never sees them. Multi-host or cockpit-visible repos use sprintctl in remote mode against the cluster pg. Audit/knowledge artifacts are always per-repo NDJSON under the artifact root regardless of sprintctl mode. In this workspace, the planned default artifact root is `/projects/dev`, giving paths such as `/projects/dev/_artifacts/homelab-analytics/audit/events-YYYY-MM-DD.ndjson`.

## Workstream A: sprintctl multi-agent takeup

Ships as written in `sprintctl-multi-agent-takeup-plan.md`. Sqlite-only. No changes from that plan. Prerequisite for everything else because the takeup event model is what the pg schema mirrors.

Open item resolved by this plan: heartbeat events stay deferred indefinitely. Session liveness moves to actionq's domain (workstream C), not sprintctl's. Sprint takeup remains opaque event-pair.

## Workstream B: sprintctl pg backend (remote mode)

### Schema

Single schema. Tables mirror the sqlite schema with `repo_id text not null` added to `Sprint`, `Track`, `WorkItem`, `Event`. Indexes:

- `(repo_id, status, kind, created_at DESC)` on Sprint for cockpit "active sprints across all repos"
- `(repo_id, sprint_id, event_type, created_at)` on Event for the takeup-status query and per-sprint render
- `(repo_id, sprint_id, status)` on WorkItem for claim/state aggregation

Event types are the union of existing sprintctl events plus the takeup events from workstream A. No pg-specific event types.

### CLI delta

`SPRINTCTL_BACKEND={local,remote}` selects mode. `SPRINTCTL_DB=<path>` for local, `SPRINTCTL_URL=<pg-url>` for remote. Direnv per-repo as before.

`repo_id` resolution in remote mode: directory name of the sprintctl marker file's containing repo, no override. Hard-pinned in local mode (the file is the repo).

All existing verbs work in both modes. No verb takes a backend flag; the backend comes from environment.

`sprintctl migrate-to-remote` ships as a first-class verb. Reads a local sqlite, exports as NDJSON, imports into pg under the resolved `repo_id`. Original sqlite is renamed to `.sprintctl.db.frozen-<ts>` as a rollback artifact, kept indefinitely.

### Wire format and clients

NDJSON over HTTP if a thin API is wanted in front of pg, or direct pg connection from clients if not. Recommend direct pg with sqlx-style migrations and CNPG handling auth/TLS — the API daemon is one more thing to operate and the value is unclear. Reconsider only if direct pg connections from workstations turn out to be operationally annoying (firewall, auth distribution).

### Failure mode contract

Pg unreachable in remote mode: sprintctl operations fail with a clear error. No local queue, no replay. Sessions that were holding takeup must be re-acquired by the operator on recovery (`takeup --force` semantics from workstream A). This matches the existing "manual recovery is fine" stance and avoids building a write-buffering subsystem before pain is observed.

### Tests

- Schema migration test: existing sqlite db at any sprintctl version can be migrated to pg without data loss. Round-trip via NDJSON export/import is byte-stable.
- Cross-repo query test: cockpit's "active sprints across all repos" query returns correct results with N repos populated.
- Mode-mismatch test: operator with `SPRINTCTL_BACKEND=local` against a remote-pinned repo (and vice versa) errors clearly rather than silently writing to the wrong place.

## Workstream C: actionq server + devbox daemon

Two components.

### actionq-server (in k8s, target)

- Owns the action queue, scheduler, dispatch policy, retry behavior.
- Uses the existing actionq Postgres-backed queue where available; do not introduce a second scheduling database.
- Exposes API for: queue inspection, action enqueue, session pause/resume, status queries.
- Subscribes to sprintctl events via pg LISTEN/NOTIFY (remote mode only) for sprint-context awareness.
- Publishes audit events into per-repo audit NDJSON via auditctl client library.

### actionq-daemon (on devbox, starts from actionq-dispatcher)

- Long-running. Pulls dispatch instructions from actionq-server or the existing actionq queue.
- Spawns agent sessions (claude, codex, copilot-cli, codestral via opencode) with the right harness, model, and prompt.
- Tracks session PID, heartbeats session liveness, surfaces stale/dead sessions back to actionq-server.
- Handles pause/resume on usage limits: SIGSTOP-equivalent or graceful checkpoint, depending on harness capabilities. Initial cut: pause = signal session to stop at next safe point; resume = re-dispatch with handoff context.
- Issues sprintctl `takeup`/`release` on session start/stop in remote mode.

### Backend harness selection

Per-action: `harness={claude,codex,copilot-cli,codestral}`, `model=<model-id>`. Defaults configurable per-repo and per-action-kind. Routing logic from the multi-model cost analysis already in scope.

### Audit emission

Every dispatch, session start, session pause/resume, session exit lands an audit event into the repo's audit NDJSON via auditctl. PR open, commit landed, PR merged also land audit events (via git hooks emitted by the session, or by actionq-daemon observing the session's commits).

## Workstream D: auditctl

New CLI, same family as sprintctl/kctl. Click + sqlite + stdlib.

### Schema (sqlite, per-repo)

```
audit_event
  id: text (ad:<ulid>, primary)
  ts: timestamp
  type: text                     # commit, pr.open, pr.merge, dispatch, session.start, session.exit, decision, custom
  actor: text                    # operator, agent-id, system
  summary: text                  # one line
  detail: text | null            # markdown
  refs: list[text]               # wi:, ka:, ad:, sha:, pr:, sprint:
  source: text                   # publisher: sprintctl, actionq, git-hook, manual
```

Index: `(ts, type)`, `(type, ts)`. Append-only.

### CLI

```
auditctl add --type <t> --actor <a> --summary <s> [--detail <d>] [--refs <r>...]
auditctl list [--type <t>] [--since <ts>] [--limit <n>]
auditctl render [--since <ts>] [--format ndjson]
auditctl rebuild --from-ndjson <path>
```

### Dual-write contract

Every `auditctl add` writes to sqlite *and* appends to today's NDJSON shard. NDJSON path: `/projects/dev/_artifacts/<repo_id>/audit/events-YYYY-MM-DD.ndjson`. If NDJSON write fails, sqlite write is rolled back; the two are kept in sync at insertion.

`auditctl rebuild --from-ndjson` reconstructs sqlite from the NDJSON shards. This is the disaster-recovery and host-migration path.

### Publishers

- Git hooks: post-commit, post-merge in repo. Tiny shell scripts that call `auditctl add`.
- Sprintctl: emits audit events via `auditctl` client on sprint open, close, takeup, release, knowledge.landed. Configured per-repo; opt-in via marker file.
- Actionq-daemon: emits on session lifecycle and dispatch events as noted in workstream C.

### What auditctl is not

Not a sprint event store. Not a knowledge graph. Not centralized. If two repos need to cross-reference audit events, the cockpit aggregates by reading both NDJSON streams; auditctl itself stays repo-scoped.

## Workstream E: agent-cockpit frontend handover

Build the `agent-cockpit` operator surface inside the `agentops` repo. The prior mock direction (`Cockpit.html`, `cockpit.jsx`, `tweaks-panel.jsx`, `cockpit.css`) is conceptually useful but conflates a few sources that the substrate keeps separate.

### Changes vs current mock

1. **Heartbeat/TTL columns in the claims table belong to item-level claims and actionq sessions, not sprint takeup.** The "STALE" pill and `hb_age` come from actionq's session liveness tracking. Display them; just label the source. A separate small panel — "sprint takeup" — shows the opaque taken_up/released state without timing semantics.

2. **Right pane splits into two distinct feeds.** "Outcomes & Review" reads from per-repo audit NDJSON (commits, PRs, decisions, releases). "Sprint event feed" (smaller, secondary) reads from sprintctl events for the active sprint(s). The current single-feed mock blurs these and the resulting UI lies about where the data came from.

3. **Repo strip is remote-mode only in v1.** "ALL" view requires that agent-cockpit has connectivity to pg (cross-repo queries are pg-only). Local-mode repos are not visible in the cluster-hosted cockpit until they migrate to remote mode.

4. **Source-of-truth label per pane.** Small monospace tag indicating where each pane's data came from: `pg://sprintctl`, `artifact:audit/<repo>`, `actionq://sessions`. Demystifies the system for the operator and makes degraded states (one source down, others fine) legible.

5. **Dispatch composer talks to actionq-server, not directly to sprintctl.** The current composer's `KIND` dropdown is fine; the wire path is `agent-cockpit -> actionq-server API -> actionq-daemon on devbox -> session`. Sprint takeup happens as a side effect of session start, not as something the operator initiates from cockpit.

6. **Drop the heartbeat sparkline on the right pane in v1.** Implied by audit NDJSON being daily shards: density-over-time is a derived view that's not free to compute. Add it back when cockpit grows an aggregator service.

### What the mock got right (keep)

Three-pane layout, repo strip, command palette pattern, status bar, the typography and density discipline. The TWEAKS panel pattern is good for operator preferences and should stay.

## Implementation order across workstreams

Each numbered step is independently shippable. Stop after any of them and the system is coherent.

1. **Workstream A complete** (sprintctl multi-agent takeup, sqlite). Per-sprint render, multi-active sprints, takeup events. Single-host. This is the dependency for everything else.

2. **Workstream D minimum**: auditctl as a new CLI with add/list/render/rebuild, dual-write to sqlite + /projects/dev/_artifacts NDJSON. Git-hook publishers in homelab-analytics only. Validates the artifact-path convention before more publishers are wired.

3. **Workstream B**: sprintctl pg backend, remote mode, migrate-to-remote verb. Pilot: homelab-analytics. Original sqlite frozen as rollback. Sprintctl operations work in remote mode for the pilot repo; other repos stay local. This is the longest single chunk.

4. **Workstream C minimum**: actionq-daemon on devbox spawning sessions on demand (no usage-limit pause/resume yet). Wires into auditctl for session-lifecycle events. Wires into sprintctl-remote for takeup/release on session start/stop.

5. **Workstream C full**: actionq-server as k8s service, queue + scheduler + dispatch policy, pause/resume on usage limits, multi-harness routing.

6. **Workstream E**: agent-cockpit surface in `agentops`. Built against the substrate that now actually exists. Read-only against pg + /projects/dev/_artifacts can ship before live dispatch, with `actionq://sessions` satisfied in v1 by a server-side `actionctl sessions` adapter. The dispatch composer still depends on Workstream C full and a real actionq-server API.

7. **Migrate financial-analytics extension to remote mode.** Second pilot of workstream B in real use.

8. **Migrate sprintctl repo itself to remote mode.** Eats own dogfood, exposes any rough edges in the pg path.

9. **Roll remaining repos individually.** Each one is a decision: does it benefit from cockpit visibility? If not, stay local.

Steps 1–4 are the substrate. Step 5–6 are the operator surface. Step 7+ is rollout.

## Dispatch prompts

Hand to dispatch-plan (Opus) when initiating each planning session. Each prompt assumes the planner reads this document and the referenced prior plans before producing a sprint plan.

### Planning prompt: sprintctl pg backend (workstream B)

```
Plan workstream B from /projects/dev/agentops/docs/plans/agentops/agent-ops-substrate-plan.md: sprintctl pg backend
and remote mode.

Context to read first:
- /projects/dev/agentops/docs/plans/agentops/agent-ops-substrate-plan.md (this plan)
- sprintctl-multi-agent-takeup-plan.md (workstream A; assumed shipped)
- existing sprintctl source for current sqlite schema and CLI surface

Decisions already made (do not relitigate):
- Two named modes: local (sqlite) and remote (pg). No abstraction layer.
- Single pg schema, repo_id as column on Sprint/Track/WorkItem/Event.
- repo_id = repo directory name. Path-derived, no registry.
- Mode selection via SPRINTCTL_BACKEND env. Mode mismatch is a hard error.
- migrate-to-remote ships as a verb. NDJSON is the export format.
- Original sqlite frozen as .sprintctl.db.frozen-<ts> on migration.
- Pg-unreachable in remote mode = clear error, no local queue, no replay.
- Direct pg connections from clients; no API daemon in front (revisit if pain).

Open items the planning session must resolve:
- CNPG cluster deployment shape (single instance, replica count, backup)
- Connection auth distribution to workstations and cluster pods
- Migration test fixtures: which existing sqlite states must round-trip
- Whether sprintctl ships CNPG manifests or assumes one already exists
- Backward compatibility: does old sprintctl on a remote-pinned repo fail
  gracefully or silently corrupt? (Should be the former; verify how.)

Out of scope:
- Auditctl integration (workstream D plans that)
- Actionq integration (workstream C plans that)
- Cockpit (workstream E plans that)

Output: planning doc following sprintctl-multi-agent-takeup-plan.md style.
Implementation order should produce independently shippable steps.
```

### Planning prompt: auditctl new tool (workstream D)

```
Plan workstream D from /projects/dev/agentops/docs/plans/agentops/agent-ops-substrate-plan.md: auditctl, a new
repo-local audit event tool in the sprintctl/kctl family.

Context to read first:
- /projects/dev/agentops/docs/plans/agentops/agent-ops-substrate-plan.md
- existing kctl source for the family pattern (Click, sqlite, stdlib-only,
  per-repo db, NDJSON render)

Decisions already made (do not relitigate):
- Sqlite-only. No pg backend ever.
- Per-repo db, located via AUDITCTL_DB env or marker-file traversal.
- Dual-write: every add lands in sqlite AND appends to today's NDJSON shard.
- NDJSON path: /projects/dev/_artifacts/<repo_id>/audit/events-YYYY-MM-DD.ndjson
- ad:<ulid> for event ids. refs use prefix convention from sprintctl plan.
- Publishers: git hooks, sprintctl, actionq-daemon. All via auditctl CLI.
- rebuild --from-ndjson is the recovery and host-migration path.

Open items the planning session must resolve:
- Atomic dual-write semantics: how to keep sqlite + NDJSON consistent under
  concurrent appends. Filesystem locking? Single-writer constraint?
- Schema for source-specific event detail (commit sha, PR number, session id)
- Whether auditctl ships the git hook scripts or just the spec for them
- Retention policy: NDJSON shards forever vs archived after N months
- How auditctl client library is consumed by sprintctl and actionq publishers
  (vendored, separate package, subprocess call to CLI)

Out of scope:
- Cockpit reading NDJSON (workstream E plans that)
- Specific publisher implementations beyond git hooks (those plan themselves)

Output: planning doc, sprintctl-multi-agent-takeup-plan.md style.
```

### Planning prompt: actionq server + daemon (workstream C)

```
Plan workstream C from /projects/dev/agentops/docs/plans/agentops/agent-ops-substrate-plan.md: actionq becomes
a server-backed queue with a daemon on devbox handling session lifecycle.

Context to read first:
- /projects/dev/agentops/docs/plans/agentops/agent-ops-substrate-plan.md
- `/projects/dev/actionq` for the current Postgres-backed queue and `actionctl`
- `/projects/dev/actionq-dispatcher` for the current `dispatcher-once` implementation
- multi-model routing notes from prior cost analysis sessions

Decisions already made (do not relitigate):
- Two components: actionq-server (k8s) and actionq-daemon (devbox, single
  long-running process).
- Current deployment already has actionq CNPG in appservice at
  `clusters/main/kubernetes/apps/actionq-db/`; do not plan a second queue DB.
- Daemon-mediated dispatch. No ssh-and-fire-prompt path.
- Daemon owns session liveness, heartbeats, pause/resume on usage limits.
- Sprintctl takeup/release happens as side effect of session start/stop in
  remote mode.
- Audit events emitted via auditctl client on session lifecycle and dispatch.
- Per-action backend harness selection (claude, codex, copilot-cli, codestral)
  with per-repo and per-action-kind defaults.
- Heartbeats and TTL semantics live HERE, not in sprintctl.

Open items the planning session must resolve:
- Wire protocol between actionq-server and actionq-daemon (HTTP poll? gRPC
  streaming? k8s service mesh assumptions?)
- Pause/resume mechanism per harness (SIGSTOP feasibility, harness checkpoint
  APIs, fallback to "stop at next safe point")
- Daemon failure mode: when daemon dies mid-session, who notices and how
- actionq-server storage: use the existing actionq pg queue; identify only
  additional tables or API endpoints needed for session lifecycle.
- How handoff context flows from paused session to resumed session
- Retry and backoff policy for failed sessions
- Multi-model routing decision logic: per-action explicit, or smart routing

Out of scope:
- Auditctl internals (workstream D)
- Cockpit dispatch UI (workstream E)
- sprintctl protocol changes (none expected; daemon uses existing remote-mode
  CLI/API)

Output: planning doc, sprintctl-multi-agent-takeup-plan.md style. Implementation
order MUST allow daemon-only-on-devbox as a shippable intermediate step before
actionq-server exists.
```

### Planning prompt: agent-cockpit frontend handover (workstream E)

```
Plan workstream E from /projects/dev/agentops/docs/plans/agentops/agent-ops-substrate-plan.md: agent-cockpit frontend inside the agentops repo,
read-only operator surface for the substrate built by workstreams A-D.

Context to read first:
- /projects/dev/agentops/docs/plans/agentops/agent-ops-substrate-plan.md (especially "agent-cockpit frontend handover")
- Cockpit.html, cockpit.jsx, tweaks-panel.jsx, cockpit.css from prior ideation

Decisions already made (do not relitigate):
- Three-pane layout, repo strip, command palette, status bar all kept.
- Heartbeats/TTL come from actionq, not sprintctl. Label the source.
- Right pane splits: audit NDJSON (primary) + sprintctl events (secondary).
- Per-pane source-of-truth label.
- ALL view requires pg connectivity (cross-repo). Local-mode repos are not
  visible in the cluster-hosted v1 cockpit.
- Dispatch composer wires to actionq-server API. No direct sprintctl writes.
- Drop the right-pane density sparkline in v1.
- Read-only against pg and /projects/dev/_artifacts/. No write paths to pg or /projects/dev/_artifacts.

Open items the planning session must resolve:
- Read pattern for NDJSON shards: tail latest day? aggregate last N days?
- Polling vs subscription for live updates (pg LISTEN/NOTIFY? SSE? plain poll?)
- How local-mode repo tabs work when cockpit runs in cluster (does cockpit
  even see local-mode repos, or are they invisible to it?)
- Auth and access (cluster-internal only? Tailscale-exposed?)
- How "sprint takeup" panel renders when N>1 active sprints across N repos
- Degraded state UX (pg unreachable, artifact root unavailable, actionq down)

Out of scope:
- Substrate changes (workstreams A-D own those)
- Operator write paths beyond the dispatch composer

Output: planning doc, sprintctl-multi-agent-takeup-plan.md style. Should
explicitly enumerate which mock features survive, which change, which drop.
```

## Rejected paths (do not re-propose)

- **Pluggable sprintctl backend (sqlite → pg toggle as abstraction).** Already rejected in workstream A's plan. Re-confirmed: two named modes is honest, an abstraction layer over both is a bug farm. The cost of the duplication is paid once at the storage layer; the alternative pays it forever in every query.
- **Sprintctl daemon shim (sprintctld) wrapping sqlite over HTTP.** Considered as an alternative to going straight to pg. Rejected: the daemon adds operational complexity to preserve a storage choice that the cluster topology has already outgrown.
- **Schema-per-repo in pg.** Cross-repo cockpit queries become unions, migrations multiply, meta-sprints become structurally special. Single schema with `repo_id` is what pg is good at.
- **Auditctl with pg backend.** Centralization argument doesn't apply: audit events are derived from upstream primary sources (git, sprintctl events) and are repo-scoped by definition. NDJSON under /projects/dev/_artifacts is the durable artifact, not the index.
- **Audit NDJSON committed in-repo.** Pollutes diffs, mixes runtime facts with code history. Sibling under /projects/dev keeps the boundary clean.
- **Actionq dispatching via `ssh devbox claude --prompt-file ...`.** Throwaway intermediate that doesn't enable pause/resume, makes session lifecycle tracking fragile, and is just barely cheaper than building the daemon properly.
- **Heartbeat/TTL semantics in sprintctl.** Already rejected for sprint takeup. Re-confirmed: actionq owns session liveness because actionq owns the session.
- **Cockpit reading sqlite directly over the shared mount.** What this whole plan exists to avoid. Cockpit reads pg (sprint state) + NDJSON under /projects/dev/_artifacts (audit/knowledge). Never sqlite over the shared mount.
- **Single ALL-repos view that mixes local and remote mode repos.** Not in v1. Reconsider only if the operator UX of switching tabs is actually painful.

## Open items

- **CNPG cluster shape.** Single-instance is fine for the homelab; backup story (WAL archiving to NAS? pgbackrest?) needs a decision before homelab-analytics migrates.
- **Audit event schema for harness-specific detail.** Claude/codex/copilot-cli session metadata differs. Extensible `detail` field vs typed sub-tables. Defer until first publisher beyond git hooks.
- **Cockpit auth.** Cluster-internal-only is the simplest start; Tailscale exposure is the obvious next step. Out of scope for the substrate; in scope for workstream E.
- **Pause/resume on usage limits per harness.** Genuine research question; what each harness exposes is unclear. Workstream C minimum ships without this; full version researches and implements.
- **kctl integration with the audit log.** Should kctl also dual-write NDJSON to `_artifacts/<repo>/knowledge/`? Probably yes, for symmetry and cockpit access. Plan as a small follow-up to workstream D.
- **What happens when a repo's sqlite-mode sprintctl history needs to become visible to cockpit later.** Implied path: migrate to remote mode (via `sprintctl migrate-to-remote`). Validate on a non-pilot repo before rolling.
- **Does `homelab-analytics` migration to remote-mode happen mid-sprint or between sprints?** Operationally easier between sprints; technically possible mid-sprint. Decide when scheduling.

## Things to verify before starting

- WAL mode confirmed on existing sprintctl dbs (assumed yes).
- `/projects/dev/_artifacts/` is either absent or unused and can be created for agent-ops artifacts.
- Devbox can run a long-running daemon process (systemd unit, or k8s pod with hostPath access to repos — pick one before workstream C).
- CNPG operator is or can be installed in the appservice namespace.
- Git hook conventions across repos are consistent enough that one auditctl hook script template works for all (or that per-repo customization is a small layer on top).
- Existing actionq code (if any) and what of it survives into the cluster-service shape.
- Naming: pick three-word codenames for each workstream's first sprint before dispatch. Suggested seed words: `pg-cutover`, `audit-ledger`, `daemon-bridge`, `cockpit-realign`.
