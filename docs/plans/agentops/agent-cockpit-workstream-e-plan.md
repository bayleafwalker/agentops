# agent-cockpit frontend workstream E plan

Workstream E of `/projects/dev/agentops/docs/plans/agentops/agent-ops-substrate-plan.md`. Builds the `agent-cockpit` operator frontend inside the `agentops` repo, aligned to the substrate owned by workstreams A-D: pg-backed sprintctl remote mode, actionq session liveness and dispatch, and repo-local audit NDJSON artifacts under /projects/dev/_artifacts.

## Goal

Ship a cluster-hosted agent-cockpit frontend that gives the operator a read-only, source-labeled view of remote-mode sprint state, actionq session liveness, and per-repo audit outcomes, with one write path only: dispatching new work through actionq.

## Scope

What ships in this workstream:

- Next.js app under `/projects/dev/agentops/apps/web/`.
- New route: `apps/web/app/cockpit/page.js`.
- New API routes under `apps/web/app/cockpit/api/`:
  - `repos/route.js` for remote-mode repository inventory and active sprint summaries.
  - `sprints/route.js` for selected repo or ALL sprint state from `pg://sprintctl`.
  - `takeup/route.js` for current sprint takeup state from `pg://sprintctl`.
  - `claims/route.js` for item claims joined with actionq session liveness from `actionq://sessions`.
  - `events/route.js` for sprintctl event feed reads from `pg://sprintctl`.
  - `audit/route.js` for paginated reads from `artifact:audit/<repo>`.
  - `dispatch/route.js` for submitting dispatch requests to actionq-server.
- New cockpit component directory: `apps/web/components/cockpit/`.
- New server-side data access helpers: `apps/web/lib/cockpit/`.
- New Storybook stories and Playwright coverage for the cockpit layout using mock API data.
- Route-level CSS or component CSS that follows the existing `app/globals.css` and generated token setup.

Agent-cockpit is a surface in the architecture sense: it does not own business state, storage, or sprint/audit/actionq semantics. The owning repo is `agentops`; deployment still belongs to `appservice`.

Current workspace note: `homelab-analytics` already has a Next.js app at `/projects/dev/homelab-analytics/apps/web/frontend/`, but agent-cockpit should not be added there. That app remains the household analytics frontend. The `apps/web/` paths in this document are relative to `/projects/dev/agentops/`.

What does not ship:

- No substrate changes to sprintctl, actionq, auditctl, pg schema, CNPG deployment, or /projects/dev/_artifacts artifact layout.
- No frontend write path to pg or /projects/dev/_artifacts.
- No local sqlite reader in the cluster-hosted cockpit.
- No auth layer beyond cluster-internal reachability in v1.

## No-Mockup Acknowledgment

The master plan references `Cockpit.html`, `cockpit.jsx`, `tweaks-panel.jsx`, and `cockpit.css` as prior ideation. Those files do not exist in the repositories and are not implementation inputs. This plan defines agent-cockpit from scratch using the master plan decisions and workstream A's takeup event model.

## Mock Feature Decisions

Features that survive:

- Three-pane layout:
  - left pane: repo strip and navigation
  - center pane: selected repo sprint state, sprint tabs, takeup, work items, and claims
  - right pane: split feeds for audit outcomes and sprintctl events
- Repo strip with an `ALL` option for cross-repo remote-mode views.
- Dense operator-oriented typography and status-bar style footer.
- Command palette pattern for navigation and quick actions.
- TWEAKS-style preferences panel for local UI density, sorting, and feed filters.

Features that change:

- Claims heartbeat and TTL columns come from actionq session liveness, not sprintctl. The claims table must label this with `actionq://sessions`.
- Sprint takeup is a small opaque state panel per active sprint. It shows `taken_up` and `released` state derived from sprintctl events and carries no TTL, heartbeat, or stale semantics.
- Right pane becomes two feeds:
  - `Outcomes & Review` from audit NDJSON daily shards.
  - `Sprint event feed` from sprintctl pg events.
- Dispatch composer sends to actionq-server, which then coordinates the actionq-daemon and any sprintctl takeup/release side effects.
- Repo strip is remote-mode only in v1. Local-mode repos are not shown in the cluster-hosted cockpit.

Features dropped in v1:

- Right-pane density sparkline.
- Browser-side file tailing of audit NDJSON.
- Mixed ALL aggregation that combines remote-mode pg data with local-mode sqlite data.
- Any direct cockpit mutation of sprintctl pg, audit NDJSON, or repo-local `_artifacts/`.

## Component Inventory

- `CockpitPage`: route entrypoint that lays out the cockpit and wires initial server-rendered shell state.
- `CockpitShell`: owns the three-pane layout, status bar, refresh timers, selected repo, selected sprint, and degraded-source state.
- `RepoStrip`: left-side repo selector with `ALL`, remote-mode repo tabs, source health, and "Remote mode only" note.
- `CockpitNav`: compact left-pane navigation for overview, active sprints, claims, outcomes, and settings anchors.
- `SourceTruthTag`: monospace source label component used in every pane header.
- `SprintOverviewPane`: center-pane container for the selected repo or ALL view.
- `ActiveSprintTabs`: tab row rendered when the selected repo has N active sprints.
- `SprintTakeupPanel`: per-sprint opaque takeup panel showing active and released actors from `sprint-taken-up` and `sprint-released` events.
- `WorkItemBoard`: grouped active sprint work items and state summaries from `pg://sprintctl`.
- `ClaimsTable`: item claim table with heartbeat age, TTL, stale state, and session actor from `actionq://sessions`.
- `RightFeedPane`: right-column split container.
- `OutcomesReviewFeed`: primary audit feed reading `audit_event` records from NDJSON shards.
- `SprintEventFeed`: secondary sprintctl event feed for selected active sprint(s).
- `DispatchComposer`: operator form for enqueuing actionq work.
- `CommandPalette`: keyboard-driven navigation and dispatch shortcut surface.
- `TweaksPanel`: UI-only preferences for density, sort order, and feed filters.
- `DegradedSourceBanner`: per-pane unavailable or stale data message with last-known timestamp.
- `CockpitStatusBar`: footer showing selected repo, refresh status, and source health.

## Data Access Layer

All browser-facing data access goes through Next.js API routes. The client never opens pg, actionq, or the artifact mount directly.

### Active Sprints Across Repos

Route: `GET /cockpit/api/repos`

Source: `pg://sprintctl`

Returns remote-mode repositories that have pg sprintctl data, active sprint counts, latest sprint update time, and source health. `ALL` is a virtual client option and exists only when pg connectivity is healthy.

Route: `GET /cockpit/api/sprints?repo_id=<repo|ALL>`

Source: `pg://sprintctl`

For `repo_id=ALL`, returns active sprints across all remote-mode repos. For a concrete repo, returns that repo's active sprint(s), tracks, work items, claim records that are stored in sprintctl, and sprint-level metadata.

### Current Takeup State

Route: `GET /cockpit/api/takeup?repo_id=<repo>&sprint_id=<id>`

Source: `pg://sprintctl`

Reads sprintctl events with event types `sprint-taken-up` and `sprint-released`, using the workstream A pairing rules. The response groups by `(actor, instance_id)` and returns active and released takeups. It does not compute heartbeat, TTL, elapsed stale state, or ownership rights.

### Claims And Actionq Session State

Route: `GET /cockpit/api/claims?repo_id=<repo|ALL>&sprint_id=<id?>`

Sources: `pg://sprintctl` for work item and claim records, `actionq://sessions` for heartbeat and TTL.

The route joins sprintctl claim/work-item state with actionq session state by the stable runtime session id when available, otherwise by actionq's claim/session association. The API response keeps the fields source-labeled:

```json
{
  "claim": { "source": "pg://sprintctl" },
  "session": { "source": "actionq://sessions" }
}
```

If actionq is unavailable, the route still returns sprintctl claim rows with `session=null` and a degraded-source marker.

Required upstream actionq read contract before implementation starts:

- A list/read surface that returns `session_id`, `runtime_session_id` when present, heartbeat timestamp or age, TTL or deadline, harness, model, and the action/claim association used to map a session back onto sprintctl claims.
- Stable semantics for the fallback join path when `runtime_session_id` is absent. The cockpit should not invent this join from event payload guesses.

### Sprint Event Feed

Route: `GET /cockpit/api/events?repo_id=<repo|ALL>&sprint_id=<id?>&limit=100&cursor=<cursor>`

Source: `pg://sprintctl`

Returns sprintctl event rows for the active sprint(s), newest first, cursor-paginated. This feed is secondary to audit outcomes and should be visually smaller.

### Audit NDJSON Shards

Route: `GET /cockpit/api/audit?repo_id=<repo>&days=3&limit=100&cursor=<cursor>`

Source: `artifact:audit/<repo>`

Reads from `/projects/dev/_artifacts/<repo_id>/audit/events-YYYY-MM-DD.ndjson` on the server. Returns parsed audit events, newest first, cursor-paginated, with shard metadata and last-read offset.

No browser component reads, tails, or receives a file handle for an NDJSON shard.

## Read Pattern Answer

The v1 audit read pattern is server-side paginated reads over the latest N daily shards.

Implementation contract:

- The API route reads the latest `N` daily shards for the selected repo, default `N=3`, bounded by `COCKPIT_AUDIT_LOOKBACK_DAYS`.
- The route parses NDJSON server-side, drops invalid lines into a route-local warning list, sorts by event timestamp descending, and returns a page plus cursor.
- Cursor shape is opaque to the client. It may encode shard date, byte offset, and event timestamp.
- A background client poll every 30 seconds calls the same route with the newest known cursor or `since_ts`.
- The server checks file size and mtime before rereading a shard and may keep a short in-process cache keyed by `(repo_id, shard_date, mtime, size)`.

This avoids browser-side tailing, avoids an always-on aggregator service, and keeps the cockpit read-only against /projects/dev/_artifacts.

## Polling And Subscription Answer

Use polling in v1. Do not add pg LISTEN/NOTIFY proxying or SSE until the basic surface has real operator usage.

Per-source mechanism:

- `pg://sprintctl`: poll every 30 seconds for repo inventory, active sprint state, takeup state, and sprint events. Trigger immediate refetch on selected repo or sprint tab changes.
- `actionq://sessions`: poll every 10 seconds for session liveness and claims enrichment. This is the only data source with heartbeat/TTL semantics, so it refreshes more frequently.
- `artifact:audit/<repo>`: poll every 30 seconds for new audit shard lines and use paginated on-demand fetches for older history.
- Dispatch submission: after a successful dispatch POST, immediately refetch actionq session state, sprint state, and audit feed once.

SSE is a v2 candidate for actionq session events. Pg LISTEN/NOTIFY is a v2 candidate if sprint event freshness becomes a real problem. Neither is required for v1.

## Local-Mode Answer

The cluster-hosted cockpit is remote-mode only in v1.

Local-mode repos are not visible in the repo strip because the in-cluster frontend cannot safely or consistently reach sqlite files on workstations. The UI must state this plainly in the left pane:

`Remote mode only`

The `ALL` view requires pg connectivity and includes only repos present in `pg://sprintctl`. No mixed-mode aggregation exists in v1.

## Auth Answer

V1 is cluster-internal only with no cockpit-specific auth layer.

Access paths:

- `kubectl port-forward` to the agent-cockpit service.
- Tailscale peer-to-peer access from the operator workstation to the cluster-hosted service.

The service should not be exposed as a public ingress in v1. Runtime manifests belong in `/projects/dev/appservice`, likely under `clusters/main/kubernetes/apps/agent-cockpit/` once the app exists in `agentops`. OIDC, mTLS, and role-based cockpit permissions are v2 work once the operator surface proves useful.

## Multi-Sprint Tab Answer

The left pane selects a repo or `ALL`. The center pane renders the selected repo's active sprint(s).

When a selected repo has N active sprints:

- Render `ActiveSprintTabs` at the top of the center pane.
- Each tab label uses `#<sprint_id> <short title>`.
- Selecting a tab scopes the takeup panel, work item board, claims table, and sprint event feed to that sprint.
- The takeup panel sits below the tab row and shows only the selected sprint's opaque takeup state.

For `ALL`, render a cross-repo active sprint list first. Selecting a sprint from that list focuses the same center-pane sprint detail view and preserves repo context in the tab label.

## Degraded State Answer

Each pane degrades independently. A source failure must not blank the whole cockpit.

Required degraded messages:

- Pg unreachable: center pane shows `Sprint data unavailable — pg://sprintctl unreachable` with `last_known_at` if cached data exists. The `ALL` tab is disabled because cross-repo state requires pg.
- Artifact audit unavailable: right pane audit feed shows `Audit data unavailable — artifact:audit/<repo> unreachable` with `last_known_at` if cached data exists.
- Actionq unreachable: claims table shows `Session data unavailable — actionq://sessions unreachable`. Sprintctl claim rows may still render, but heartbeat, TTL, and stale pills are suppressed or marked unknown.

Source health should also be summarized in `CockpitStatusBar`. The UI must never imply that stale session state came from sprintctl.

## Dispatch Composer

`DispatchComposer` is the only v1 write path. It sends work to actionq-server through the Next.js API route:

Route: `POST /cockpit/api/dispatch`

Source target: actionq-server API

The route validates the request, attaches operator context, forwards to actionq-server, and returns the action id or validation errors. It does not write to sprintctl or /projects/dev/_artifacts.

This is a hard dependency, not a convenience layer. Workstream C minimum does not create `actionq-server`; it keeps the public interface on `actionctl` and daemon-side integration. A live cockpit dispatch path therefore requires Workstream C full or an explicitly documented interim API bridge.

Wire format from cockpit to Next.js route:

```json
{
  "repo_id": "homelab-analytics",
  "sprint_id": 12,
  "work_item_id": "wi:abc123",
  "kind": "implement|review|test|investigate|document|custom",
  "title": "Short operator title",
  "prompt": "Operator-authored task prompt",
  "harness": "claude|codex|copilot-cli|codestral",
  "model": "optional model id",
  "priority": "normal|high",
  "refs": ["wi:abc123", "sprint:12"],
  "requested_by": "operator id from cockpit environment"
}
```

Expected actionq-server response:

```json
{
  "action_id": "aq:01J...",
  "status": "queued",
  "queue_position": 3,
  "session_id": null
}
```

Feedback shown in the UI:

- On success: queued action id, queue position when present, and a link/filter to the matching session once actionq reports it.
- On validation error: inline field errors from actionq.
- On actionq unavailable: `Dispatch unavailable — actionq://sessions unreachable`.
- After success: immediate one-shot refresh of claims/session state and audit outcomes.

Sprint takeup is not initiated by the composer. It appears later as a side effect of actionq-daemon starting a session and recording sprintctl takeup.

## Source-Of-Truth Labels

Every major pane header must include an exact source label:

- Left repo strip: `pg://sprintctl`
- Center sprint pane: `pg://sprintctl`
- Sprint takeup panel: `pg://sprintctl`
- Claims table sprint claim columns: `pg://sprintctl`
- Claims table heartbeat/TTL columns: `actionq://sessions`
- Right pane `Outcomes & Review`: `artifact:audit/<repo>`
- Right pane `Sprint event feed`: `pg://sprintctl`
- Dispatch composer: `actionq://sessions`

For `ALL`, labels stay the same. The visible repo value may be `ALL`, but the data source remains `pg://sprintctl`.

## Test Plan

Can be tested with mock data:

- Three-pane responsive layout at desktop and narrow widths.
- Repo strip behavior, including disabled `ALL` when pg health is degraded.
- N active sprint tabs for one repo.
- Takeup panel rendering active and released actors without TTL or heartbeat language.
- Claims table rendering session liveness from actionq and unknown liveness when actionq is degraded.
- Right-pane split feed with audit primary and sprint event secondary.
- Dispatch composer validation, optimistic feedback, and error states.
- Source-of-truth labels and degraded messages.
- Keyboard command palette and tweaks panel.

Requires real pg plus NDJSON/actionq setup:

- `GET /cockpit/api/repos` and `GET /cockpit/api/sprints` against sprintctl remote-mode pg.
- Takeup state derivation from real `sprint-taken-up` and `sprint-released` events.
- Cross-repo `ALL` active sprint query.
- Claims enrichment against actionq session liveness.
- Audit shard pagination over real `_artifacts/<repo_id>/audit/events-YYYY-MM-DD.ndjson`.
- Dispatch composer end-to-end enqueue against actionq-server.

Frontend verification commands:

- `npm run typecheck` in `apps/web`.
- `npm run storybook:build` for cockpit stories.
- `npm run playwright:test` for visual and interaction coverage.
- Route-level API tests can use mocked pg/actionq/artifact-root adapters in `lib/cockpit/`.

## Out Of Scope

- Workstream A-D implementation or schema changes.
- Pg migrations, CNPG deployment, sprintctl remote-mode migration, or actionq service deployment.
- Local-mode sqlite reads from cockpit.
- Writes to sprintctl pg from cockpit.
- Writes, edits, compaction, or retention management for `/projects/dev/_artifacts/`.
- Audit aggregation service, density sparkline, or historical analytics over audit shards.
- Public ingress, OIDC, mTLS, or multi-user authorization.
- Operator write paths beyond dispatch composer.

## Implementation Order

1. Static cockpit shell with hardcoded data.
   - Add `/cockpit`.
   - Build the three-pane layout, repo strip, center sprint tabs, takeup panel, claims table, dual right feed, dispatch composer shell, source labels, degraded banners, status bar, command palette, and tweaks panel.
   - Add Storybook stories and Playwright coverage using hardcoded fixtures.

2. Live pg integration.
   - Add `lib/cockpit/sprintctl-pg` helpers.
   - Implement `repos`, `sprints`, `takeup`, and `events` API routes against `pg://sprintctl`.
   - Enable `ALL` only when pg health is good.
   - Render real active sprints, takeup state, work items, and sprint events.

3. NDJSON audit feed.
   - Add `lib/cockpit/audit-shards` helpers.
   - Implement paginated server-side reads of latest N daily shards.
   - Add 30-second audit polling and independent artifact-root degraded state.

4. Actionq session liveness.
   - Add `lib/cockpit/actionq` client helpers.
   - Enrich claims with actionq heartbeat/TTL via 10-second polling.
   - If actionq only exposes read-side session data at this stage, ship cockpit as read-only and keep dispatch disabled.

5. Dispatch composer after actionq-server exists.
   - Implement `POST /cockpit/api/dispatch`.
   - Show queued/failed feedback and immediate post-dispatch refresh.
   - Document the exact actionq-server request/response contract used by the route.

6. Operator hardening.
   - Add route-level mock adapter tests.
   - Add degraded-source regression tests.
   - Tune density and keyboard navigation from real use.
   - Document cluster-internal access and remote-mode-only behavior near cockpit deployment docs.
