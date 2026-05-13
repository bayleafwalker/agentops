# cockpit-web frontend (workstream E)

Plan for the cockpit-web frontend: a read-only operator surface over the substrate built by workstreams A–D. Three-pane cockpit, repo strip, command palette, status bar — all carried forward from the mock (`Cockpit.html`, `cockpit.jsx`). Source-of-truth discipline carried in from the substrate plan.

This plan assumes workstreams A–D have shipped through at least the "minimum" tier described in `cluster-cockpit-substrate-plan.md`: sprintctl multi-agent takeup, auditctl with NDJSON dual-write, sprintctl pg backend (homelab-analytics piloted), actionq-daemon on devbox emitting audit events. Cockpit does not ship before that substrate exists.

## Why

The mock's three panes were drawn before the substrate's source boundaries existed. The pg backend, NDJSON audit shards, and actionq's ownership of session liveness are now decided. The cockpit needs to render those boundaries faithfully — pane source labels, no cross-source aggregation that doesn't exist, no UI lies about timing data — without losing the operator surface the mock got right.

## Core decisions (do not relitigate)

- **Three-pane layout, repo strip, command palette, status bar all kept.** Operator muscle memory is worth preserving and the mock validated the layout.
- **Heartbeats and TTL come from actionq-cluster, not sprintctl.** The claims table renders actionq session liveness; sprint takeup is shown as opaque taken_up/released state without timing.
- **Right pane splits.** Primary feed: per-repo audit NDJSON (commits, PRs, decisions, releases). Secondary feed: sprintctl events for the active sprint(s). Two distinct feeds with two distinct source labels, never merged into one stream.
- **Per-pane source-of-truth label.** Small monospace tag indicating the pane's data source: `pg://sprintctl`, `nfs:audit/<repo>`, `actionq://sessions`. Operator-legible; degraded states stay legible.
- **ALL view requires pg connectivity.** Cross-repo aggregation is pg-only. Local-mode repos appear as individual tabs and do not contribute to ALL.
- **Local-mode repo tabs are individual or invisible.** Cockpit running in cluster cannot reach workstation sqlite files. See "local-mode visibility" below.
- **Dispatch composer wires to actionq-cluster API.** No direct sprintctl writes from cockpit. Sprint takeup happens as a side effect of session start.
- **No write paths to pg or NFS.** Cockpit is read-only against both. The single write path is the dispatch composer → actionq-cluster API.
- **Drop the right-pane density sparkline in v1.** Daily NDJSON shards make density-over-time a derived view that's not free; defer until an aggregator exists.
- **TWEAKS panel pattern stays.** Operator preference surface, not a feature flag console.

## Architecture

```
                     COCKPIT-WEB (k8s pod, appservice ns)
                     ┌─────────────────────────────────────┐
                     │  React SPA (static)                 │
                     │  ──────────────────────             │
                     │  cockpit-api (read-only gateway)    │
                     └────┬──────────────┬──────────────┬──┘
                          │              │              │
                  pg://sprintctl   nfs:_artifacts   actionq-cluster
                  (cross-repo,     /audit/*.ndjson   API (read +
                   ts queries)     (per-repo tail)   dispatch)
                          │              │              │
                          ▼              ▼              ▼
                       CNPG            NFS RO         actionq-cluster
                                       mount          k8s service
```

`cockpit-api` is a thin server-side gateway. It is not a database — it owns auth, source-of-truth labels, NDJSON tailing, and pg connection pooling. It is the single thing the SPA talks to. It is the single thing that talks to pg, NFS, and actionq-cluster on the SPA's behalf.

The SPA is a static bundle; the gateway is what makes it a deployable app.

### Why a gateway, not direct connections from the SPA

- NFS mount can't be exposed to a browser. A read API is required.
- Pg credential distribution to browsers is a non-starter. Gateway holds the connection pool.
- Actionq-cluster API is internal; the gateway brokers writes (the dispatch composer) and reads.
- Source-of-truth labels are computed once on the gateway side and stamped onto every payload. The SPA does not assemble them.

The gateway is small. It is not a microservice; it is a façade. If it grows opinions of its own, that is a smell.

## Read patterns

### NDJSON shards (audit, knowledge)

- **v1 read pattern: tail today's shard, optionally include yesterday's.** Shard path: `<nfs-root>/_artifacts/<repo_id>/audit/events-YYYY-MM-DD.ndjson`. Cockpit defaults to today's shard for the right-pane primary feed; "show last 24h" expands to today + yesterday and merges by `ts`.
- **No multi-day aggregation in v1.** "Last 7 days" is a future feature that requires either an aggregator service or per-shard summary files. Out of scope until the operator notices it's missing.
- **No NDJSON parsing in the browser.** Gateway parses, normalizes, and returns JSON to the SPA. NDJSON is a write format and a durable artifact, not a wire format for cockpit.
- **Shard cursor is server-side.** Gateway maintains a tail offset per (repo_id, date) in memory and serves deltas; cold-start re-reads from beginning of today's shard. No client-side cursors.
- **Read mount is a separate NFS mount, mode `ro`.** The cockpit pod cannot write to `_artifacts/`. Filesystem permissions enforce the read-only contract; no application-level "please don't write" trust.
- **Day rollover is a server-side concern.** At 00:00 UTC the gateway closes yesterday's tail handle and opens today's; the SPA sees a continuous feed.

### Pg (sprintctl remote mode)

- **Active sprints across repos:** `SELECT ... FROM sprint WHERE archived_at IS NULL` — the index from workstream B's plan is exactly this query.
- **Per-sprint events for the secondary feed:** `SELECT ... FROM event WHERE repo_id = ? AND sprint_id = ? ORDER BY ts DESC LIMIT n`. Bounded N, no scrolling history in v1.
- **Takeup state:** computed from `event` table by reducing `taken_up`/`released` event pairs per sprint. Gateway computes; SPA renders the reduced state, never the raw events.
- **Read transactions only.** Gateway uses a read-only pg role. Belt and suspenders: even if the gateway code has a bug, the database refuses writes.

### Actionq-cluster

- **Session list:** GET against actionq-cluster API. Includes session id, repo_id, harness, model, claim id (sprintctl item-level claim), heartbeat ts, status (active/paused/stale/dead).
- **Dispatch:** POST against actionq-cluster API. The composer's existing `kind`/`repo`/`body` payload extends with `harness` and `model` fields populated from per-repo defaults.
- **No direct daemon connections.** Cockpit-gateway → actionq-cluster only. The daemon is invisible to cockpit.

## Live-update strategy

- **v1: plain polling, per-pane intervals.** No push, no subscription, no SSE. Polling is honest about the cost of what cockpit is doing and easy to throttle when the operator backgrounds the tab.
  - Action queue: 2s.
  - Claims/sessions: 2s.
  - Sprint hero (rarely changes): 15s.
  - Audit feed: 5s, gateway-side delta cursor avoids re-sending the page each time.
  - Sprint event feed: 10s.
- **`document.visibilityState === 'hidden'`: all intervals × 4.** Backgrounded cockpit is not idle; it is *less urgent*.
- **Pg LISTEN/NOTIFY: deferred.** It is the right end-state but it requires the gateway to multiplex notifications back to N SPA clients (websockets or SSE). v1 ships with polling so the gateway stays simple. Revisit once polling cost is observable.
- **SSE is the candidate upgrade path,** not websockets. One-way data flow matches the read-only model; SSE is supported by k8s ingress without sticky-session gymnastics; the dispatch composer's writes stay POST.

The polling defaults are tuneable per-pane via TWEAKS. Operator who wants 1s claim ticks during an incident gets them; default stays kind to the substrate.

## Local-mode repo visibility

- **Cockpit running in cluster cannot see local-mode repos' sprint state.** Workstation sqlite files are not on NFS, not on pg. A cluster-resident cockpit has no path to them.
- **Auditctl artifacts are visible regardless of sprintctl mode.** A repo that's local-mode for sprintctl but has auditctl writing to `_artifacts/<repo>/audit/` is reachable by cockpit. The repo strip is therefore the union of (pg `repo_id`s with active sprints) and (NFS `_artifacts/` directories with audit shards).
- **Repo strip is grouped, not flat.** Two groups: **REMOTE** (pg-backed; full cockpit) and **LOCAL** (audit-only; right primary feed and audit-derived event feed only). When a LOCAL repo is selected, the center pane shows "no sprint data — local-mode repo" with a one-line nudge toward `sprintctl migrate-to-remote`.
- **ALL means "all REMOTE".** Tooltip on the ALL chip explains the scope. No mixed-mode aggregation, period.
- **Workstation cockpit (future) is the only path for true local-mode sprint visibility.** Same SPA, same gateway code, gateway runs on the workstation, reads local sqlite directly, and federates against the cluster gateway for remote-mode repos. Out of scope for v1; the gateway is built so this is possible later (interfaces over implementations for the three sources).

Rejected: a registry file that lists local-mode repos cockpit should also peek at. Adds a config surface that contradicts "directory name is repo_id, no separate registry" from workstream B and produces a class of bug where the registry and pg disagree.

## Sprint takeup panel — N>1 active sprints

- **Per-repo takeup row, not a global one.** When N repos each have an active sprint, the panel renders one row per (repo_id, sprint_id) showing taken_up/released opaque state.
- **No global takeup aggregation.** The substrate plan rejects timing semantics on takeup; an aggregate count of "3 sprints taken up" is a count of states, not of activity. Show the rows; let the operator read them.
- **Sort: most-recent state change first.** The takeup event ts is what drives ordering. The panel is short (≤10 rows in practice); pagination is not a concern.
- **Center-pane sprint hero shows ONE sprint at a time.** When N>1 active sprints exist in the current filter, compact switcher tabs render above the hero, defaulting to the most-recently-updated sprint. Center pane is single-sprint focused; the takeup panel is the multi-sprint surface.
- **The takeup panel sits beside the claims table**, not below it — the two answer different questions ("who has taken up which sprint" vs "what's actively claimed inside the active sprint") and putting them on the same vertical axis collapses the distinction.

## Source-of-truth labels

Every pane carries a small label. Format: monospace, secondary text color, top-right of the pane header.

- Action queue: `actionq://queue`
- Claims/sessions table: `actionq://sessions` (heartbeats here) + `pg://sprintctl/items` (item titles, refs)
- Sprint hero: `pg://sprintctl/sprint`
- Sprint takeup panel: `pg://sprintctl/events#takeup`
- Outcomes & Review (right primary): `nfs:_artifacts/<repo>/audit/`
- Sprint event feed (right secondary): `pg://sprintctl/events`
- Status bar connection chips: each substrate's reachability, with the same identifiers.

When two sources contribute to one pane (claims table), both labels render, comma-separated. The operator can always answer "where did this number come from".

## Degraded states

Substrates fail independently. Cockpit must remain useful when one or two are down.

| Degraded condition | Cockpit behavior |
| --- | --- |
| **pg unreachable** | Repo strip collapses to LOCAL only. Center pane shows "sprint data unavailable — pg unreachable" with the source label highlighted in `--bad`. Right primary (audit NDJSON) still works. Dispatch composer disabled if it requires pg-derived defaults; enabled in degraded form (no per-repo harness defaults) otherwise. |
| **NFS unmounted** | Right primary feed shows "audit unavailable — NFS unmounted". Other panes unaffected. Dispatch and sprint state work normally. |
| **actionq-cluster down** | Claims table hides heartbeat/TTL columns; shows item-level claim data from pg only with a banner: "session liveness unavailable". Dispatch composer disabled with explanatory tooltip. Action queue pane shows last-known state with a "stale" overlay timestamped to last successful poll. |
| **all three down** | Cockpit shows the connection-status grid, full-window, with last-success timestamps and the gateway's own health. No phantom data, no spinners forever. |
| **gateway down** | Browser shows a single "cockpit-api unreachable" screen. SPA does not attempt to reach pg/NFS/actionq directly even in degraded mode — the architectural boundary is held. |

Status bar's existing per-substrate dots become the canonical degraded-state indicator. Dot states formalized: `live` (green), `slow` (amber, last poll >2× expected interval), `down` (red), `unknown` (grey, before first poll). Hovering a dot reveals last-success ts and the most recent error string.

## Auth and access

- **v1: cluster-internal only.** Cockpit-web pod is exposed via a ClusterIP service. Operator reaches it via `kubectl port-forward` or by being on the cluster network (Tailscale node attached to the cluster). No public ingress, no per-user auth.
- **No login screen in v1.** Single-operator, single-trust-domain homelab. If anyone is on the cluster network, they're authorized.
- **Tailscale exposure is the next step, not v1.** When the operator wants cockpit from a phone or laptop off the cluster network, expose via tailscale serve / magicdns. Still no per-user auth; Tailscale's identity is the auth.
- **Per-user auth is a future workstream**, not part of E. When multiple operators exist, OIDC against an existing IdP is the right shape; out of scope here.
- **Dispatch composer's write path is gated by gateway-side allow-list.** Only requests originating from the cockpit pod's network identity reach actionq-cluster. The composer is read-only-cockpit's one privilege; not free.

## Mock features: keep / change / drop

| Feature | Disposition | Notes |
| --- | --- | --- |
| Three-pane layout | **Keep** | Layout validated. |
| Repo strip with per-repo dots and counts | **Keep, modified** | Sourced from gateway (pg + NFS), not hard-coded. Repos grouped REMOTE / LOCAL. |
| Command palette (⌘K) | **Keep** | Search payload sourced from gateway, not the JSX literal. |
| Status bar with per-substrate dots | **Keep, modified** | Now four substrates: pg, nfs, actionq-cluster, gateway-self. Dot states formalized. |
| Top bar brand, breadcrumb, UTC clock | **Keep** | UTC clock now ticks against gateway-server time, not browser time, to keep heartbeats honest. |
| Sprint hero with burn bar | **Keep** | Single-sprint focus; switcher tabs added when N>1. |
| Sprint takeup panel (NEW) | **Add** | Per-repo opaque takeup rows; replaces the implicit "active claims" framing in the mock. |
| Claims table | **Keep, modified** | Item title/refs from pg; agent/heartbeat/TTL from actionq. Two source labels rendered on the pane header. |
| Live agent log tail | **Keep, modified** | Sourced from actionq-cluster session log streaming endpoint, not synthesized. Filter tabs (all/agents/tests/system) survive. |
| Right pane: single "Outcomes & Review" feed | **Change** | Splits into two stacked sections with distinct source labels. |
| Right pane: 60-min density sparkline | **Drop** | Derived view, not free under daily NDJSON shards. Reconsider when an aggregator service exists. |
| Dispatch composer | **Keep, rewired** | Same UI; payload includes `harness` and `model`; POST goes to actionq-cluster API via gateway. |
| TWEAKS panel | **Keep, extended** | Theme, density, accent, telemetry-on/off, live-log-on/off all stay. Add: poll-interval override per pane; source-label-always-visible toggle. |
| Heartbeat sparkline bar in claims table | **Keep, relabeled** | Source: actionq, not sprintctl. Visual unchanged. |
| Mock data baked into JSX | **Drop** | Replaced by gateway endpoints. |
| ALL view aggregating across all repos | **Keep, scoped** | "ALL" = all REMOTE repos only. Tooltip in the strip explains the scope. |
| Selected-row state (qitem.selected, review.selected) | **Keep** | Detail-pane (future) consumes selection; v1 uses selection only for visual emphasis. |
| Live ticking clock + claim TTL countdown | **Keep, retargeted** | Drives off gateway server-time and actionq-reported heartbeat ages, not browser-side fake clocks. |
| `act-NNNN` synthetic action ids in queue | **Drop** | Replaced with actionq-cluster's actual action ids. |

## Gateway shape

Single Go or Python service, picked by whatever the substrate already standardizes on. Endpoints, all GET except dispatch:

```
GET  /api/health                               → gateway + downstream reachability
GET  /api/repos                                → [{repo_id, mode, sources_available}]
GET  /api/sprints/active                       → all active sprints across REMOTE repos
GET  /api/sprints/:sprint_id                   → sprint hero + items + takeup state
GET  /api/sessions                             → actionq sessions (cross-repo)
GET  /api/sessions?repo_id=...                 → filtered
GET  /api/dispatches                           → actionq dispatch lifecycle rows
GET  /api/audit?repo_id=...&since=...          → audit NDJSON, parsed + normalized
GET  /api/costs/summary                        → workspace session cost summary
GET  /api/headroom                             → cached Codex/Claude quota headroom snapshot
POST /api/headroom                             → force-refresh configured headroom commands
GET  /api/audit/stream?repo_id=...             → SSE upgrade path (deferred to v1.1)
GET  /api/sprint-events?repo_id=...&sprint_id  → secondary right-pane feed
POST /api/dispatch                             → forwards to actionq-cluster
GET  /api/log/stream?session_id=...            → agent log tail (SSE in v1.1; poll in v1)
```

Gateway responsibilities, exhaustive:

1. Source-of-truth label stamping on every response.
2. Pg connection pooling (read-only role).
3. NFS shard parsing and tail cursor management.
4. Auth (network-allowlist v1; OIDC-shaped later).
5. Polling-cost throttling (per-client rate limits if cockpit ever multiplies).

What it explicitly does not do: cache, denormalize, schema-rewrite, or aggregate across days. Gateway as façade, not as data layer.

## Implementation order

This section records the original phased plan. As of the current cockpit build,
steps 1-5 are shipped as a co-located Next.js SPA plus API gateway, step 6 is
partially shipped, and a new dispatch lifecycle slice has been added on top of
the original claims/dispatch composer split.

1. **Gateway skeleton + health endpoint.** Read-only pg connection from a pod, NFS read mount, actionq-cluster client. Serves `/api/health` only. Deployable as the cockpit-web pod with a placeholder SPA. Validates connectivity, mount permissions, and the gateway pattern itself.

2. **Repo strip and sprint hero, pg-only.** SPA fetches `/api/repos` and `/api/sprints/active`. Single-sprint hero, no claims table yet, no audit feed. The center-pane skeleton with real data.

3. **Claims table with item-level claims from pg.** No actionq integration yet — heartbeat/TTL columns hidden behind a "session liveness unavailable" banner. Source label `pg://sprintctl/items`. The substrate piloted this far is sufficient to ship cockpit through this step.

4. **Audit feed in right primary.** Gateway parses NDJSON shards, returns normalized events. Polling at 5s. Source label `nfs:_artifacts/<repo>/audit/`. Sprint event feed (right secondary) ships in the same step — both right-pane feeds together so the split is visible from day one.

5. **Actionq integration.** Sessions endpoint, claims table gets heartbeat/TTL columns, dispatch lifecycle rows come from `GET /dispatches`, and the dispatch composer is wired through `/api/dispatch`. Status bar's actionq dot goes live. The log-tail panel remains deferred.

6. **Sprint takeup panel.** Multi-sprint surface; sprint switcher in the hero when N>1. The reduce-events-to-takeup-state computation lives in the gateway.

7. **Degraded state UX hardening.** Each substrate's down-state path implemented and tested. Status bar dot states formalized. Per-pane source labels go red when their source fails.

8. **TWEAKS additions.** Poll-interval overrides, source-label-always-visible toggle, theme/density already from mock.

9. **Command palette gateway-sourced.** Replaces the mock's hard-coded payload. Repos and sprints are searchable today; items, sessions, audit events, and dispatches are later expansions.

10. **v1 cut.** Tailscale exposure decision (in or deferred). Gateway containerized, pod manifest reviewed, NFS mount confirmed `ro`.

Stop after step 4 and cockpit is a useful read-only sprint+audit dashboard. Stop after step 5 and it's the operator surface the substrate plan envisioned. Steps 6–10 are polish.

## Tests

- **Gateway has no write paths to pg or NFS.** Verified by connection role and mount mode at boot; cockpit pod refuses to start if either is wrong.
- **Source label correctness.** Every endpoint response includes the substrate it sourced from; integration test asserts the label matches the actual substrate touched.
- **Degraded-state matrix.** For each (substrate down, substrate slow) combination listed in "Degraded states", a test asserts the cockpit renders the documented banner/disable state and does not crash, hang, or surface phantom data.
- **NDJSON shard rollover.** At 00:00 UTC simulated, gateway closes yesterday's handle and opens today's; SPA's right-primary feed sees a continuous, monotonic stream.
- **Local-mode repo visibility.** Repo with audit shards but no pg presence renders as a LOCAL-group tab; selecting it shows the documented "no sprint data" center-pane state, not a crash.
- **ALL filter scope.** ALL excludes LOCAL repos in cross-repo aggregations; tooltip on the chip matches the scope.
- **Polling backoff on visibility change.** Tab hidden ⇒ all intervals 4×; tab visible ⇒ intervals restored. Verified in browser test.

## Out of scope (in this plan)

- **SSE / pg LISTEN/NOTIFY.** Polling for v1; SSE upgrade path defined but not built.
- **Detail panes for selected items.** Selection state is preserved, click-to-detail is not. Add when the operator notices a missing drill-down.
- **Multi-operator auth.** Single-trust-domain cockpit only.
- **Aggregator service** for multi-day audit summaries, density sparklines, takeup-rate-over-time.
- **Workstation cockpit** for true local-mode visibility. Architecture allows it; v1 doesn't ship it.
- **Mobile layout.** Cockpit is a desktop operator console. Phone screens get a "use a real screen" splash.
- **Substrate changes.** Workstreams A–D own those; cockpit consumes whatever they expose.
- **Dispatcher-meta cockpit UI.** The cockpit only renders `dispatch_group_id` grouping until a coordinator exists.
- **Billing dashboard.** The status bar and dispatch row show lightweight cost facts; period reports can live in command-palette or tweaks-adjacent surfaces later.
- **Private usage API coupling.** Model headroom is consumed from configured JSON-producing commands, not hard-coded Codex or Claude auth scraping. The cockpit shows staleness age inline so dispatch warnings are proportional to how fresh the quota signal is.
- **Log-tail pane.** Session id visibility plus operator CLI/tmux hints are enough until log-tail pain is proven.

## Rejected paths (do not re-propose)

- **SPA talks to pg / NFS / actionq directly.** Browser cannot mount NFS. Pg credential distribution to browsers is a security nonstarter. Gateway is the architectural boundary.
- **Gateway as a data layer with its own store.** It is a façade. If it grows a cache that's a smell; if it grows a schema that's a bug. The substrate is the data layer.
- **Cross-source aggregation in v1 across local- and remote-mode repos.** Substrate plan already rejects mixed-mode ALL; reconfirmed here for cockpit specifically.
- **Multi-day NDJSON aggregation in v1.** Today + optional yesterday only. Multi-day is an aggregator-service problem, not a gateway problem.
- **Websockets for live updates.** SSE is the upgrade path; websockets bring sticky-session and write-channel concerns the read-only model doesn't justify.
- **Pg LISTEN/NOTIFY in cockpit gateway.** Actionq-cluster is already the LISTEN consumer (per workstream C). Two consumers multiply the surface area where a missed notification produces a stale UI. Cockpit polls.
- **Local-mode-repo registry file.** Contradicts "no registry" from workstream B; produces drift bugs. The directory layout is the registry.
- **OIDC / SSO / per-user auth in v1.** Single-operator homelab. Network identity is sufficient.
- **Detail-pane click-throughs in v1.** The mock's `selected` state stays for visual emphasis only. Drill-downs are a v2 surface.
- **In-cockpit retry / backoff buttons for failed sessions.** Cockpit is read-only-plus-dispatch. Retry is an actionq-cluster operator concern; cockpit surfaces the failure, doesn't act on it.
- **A "lite" or "audit-only" repo entry type.** LOCAL-group tabs already cover the audit-only case. A third type adds taxonomy without adding utility.

## Open items

- **Gateway framework.** Resolved: cockpit uses Next.js API routes as the gateway, not a separate Go/Python service.
- **NFS read-only mount mechanism in the cockpit pod.** Resolved in deployment: the cockpit reads the workspace PVC read-only and serves audit shards from `/projects/dev/_artifacts`.
- **Server time source for the UTC clock.** Gateway-served, but if the gateway is restarted mid-tick, the SPA needs a graceful resync. Trivial; flag here so it isn't forgotten.
- **Per-pane poll-interval TWEAKS persistence.** TWEAKS already persists via the host protocol in the mock; verify it still does once cockpit is hosted as a real SPA outside the design environment.
- **First-load latency budget.** Initial fetch of repos + active sprints + today's audit shards across all REMOTE repos must complete in under 2s on the cluster network. Establish the budget before step 4 so step 5+ can defend it.
- **Gateway log shipping.** Cockpit-gateway's own logs go where? auditctl is for repo-scoped events; the gateway is infra. Probably stdout into whatever the cluster uses for pod logs. Decide before v1 cut.
- **Tailscale-or-not for v1 cut.** Substrate plan leaves it open; cockpit's v1 ships cluster-internal regardless, but the decision affects whether step 10 includes a tailscale-serve manifest.

## Things to verify before starting

- Workstreams A–D minimum tier shipped (sprintctl pg pilot, auditctl NDJSON, actionq-daemon, actionq-cluster API at least readable).
- Read-only pg role exists on the CNPG cluster and grants are scoped to the sprintctl tables only.
- `_artifacts/` NFS path is mountable read-only by an `appservice` namespace pod.
- Actionq API coverage is documented for `/sessions`, `/dispatches`, and `/dispatch`; `/dispatches` is the lifecycle row surface that ties queued actions, sessions, result refs, optional grouping, and lightweight cost attribution together.
- A staging cockpit pod can be deployed without disrupting any in-flight sprint or actionq session — the cockpit is read-only but the gateway pod still occupies cluster resources and an `appservice` namespace slot.
- Naming: pick the v1 cut's three-word codename. Substrate plan suggested seed words including `cockpit-realign`; that fits.
