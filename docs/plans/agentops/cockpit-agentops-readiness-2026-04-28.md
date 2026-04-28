# cockpit / agentops readiness assessment - 2026-04-28

Cross-cutting planning snapshot for the current cockpit and agent-ops workplans.

## Purpose

Document current substrate readiness, identify the places where the plan set drifted from the current repos, and pin the next sequencing decisions before more implementation starts.

## Observed State

### agentops

- `agentops` is still a planning-only repo in practice: `/projects/dev/agentops` has `docs/` only and no `apps/web/` scaffold yet.
- The plan set is the coordination source of truth, but parts of it still assume `auditctl` is not created and that cockpit dispatch can speak to an actionq API that does not exist yet.

### sprintctl

- Workstream A is represented as shipped planning input: takeup is the event-model contract for the rest of the substrate.
- Workstream B is still planning-only. There is no active sprint in `/projects/dev/sprintctl/.sprintctl/`, and the repo currently has no active sprint state driving a pg cutover.
- The pg backend plan already corrected one schema assumption from the master plan: the sprint table has no `archived_at`, so the active-sprint read path is based on `(repo_id, status, kind, created_at)`.

### actionq / actionq-dispatcher

- `actionq` already provides the queue and `actionctl`.
- `actionq-dispatcher` already contains both `dispatcher-once` and an `actionq-daemon` entrypoint, so workstream C is an integration and ownership consolidation problem more than a greenfield daemon build.
- The minimum workstream C plan explicitly keeps the public interface on `actionctl`; it does not create a new `actionq-server` API in the minimum step.

### auditctl

- `/projects/dev/auditctl` now exists and has an implementation, README, tests, and hook examples.
- `/projects/dev/_artifacts/homelab-analytics/audit/events-2026-04-26.ndjson` exists, so the planned artifact root and shard layout are already proven in the pilot repo.
- This means the older "auditctl repo does not exist yet" wording is stale and should no longer drive sequencing decisions.

### appservice

- Current GitOps state only includes `actionq-db` under `/projects/dev/appservice/clusters/main/kubernetes/apps/actionq-db/`.
- There are still no runtime app definitions for `sprintctl-postgres`, `actionq-server`, or `agent-cockpit`.

### homelab-analytics pilot

- The pilot repo's active sprint is `#78 semantic-seam-forge`.
- Live sprint state on 2026-04-28 shows `5/5` items done, `0` active claims, and no ready, stale, or blocked items in the active sprint.
- The only stale sprintctl state in the repo is backlog sprint `#64 cinder-ledger-path`, where item `#414` remains `active` with no claim.
- The pilot is therefore not blocked by unfinished repo work. It is waiting on substrate rollout and on a decision about when to migrate the repo to remote mode.

## Readiness Summary

### Ready now

- Audit shard path and repo-local audit publishing shape.
- Queue foundation in `actionq`.
- Dispatcher and daemon implementation base in `actionq-dispatcher`.
- Pilot repo documentation target and real artifact location.

### Not ready yet

- `sprintctl` remote mode implementation and migration path.
- Appservice manifests for sprintctl Postgres, actionq-server, and agent-cockpit.
- A canonical read contract for cockpit claims/session enrichment from actionq.
- A live actionq API target for cockpit dispatch.
- Any in-repo `agentops/apps/web` scaffold.

## Plan Corrections Needed

1. Treat `auditctl` as an existing implementation repo.
   The remaining workstream D work is integration, rollout, and any delta between the shipped implementation and the plan, not repo creation.

2. Treat cockpit dispatch as blocked on workstream C full, not merely C minimum.
   A read-only cockpit or a cockpit with mocked dispatch can start earlier, but the live `POST /cockpit/api/dispatch` path needs an actual actionq API contract.

3. Normalize the sprintctl pg query contract to the companion plan.
   The master plan should use the same active-sprint index/query language as `pg-backend-remote-mode-plan.md`.

4. Pin the cockpit claims/session join contract before implementation.
   Cockpit needs a stable actionq read shape that exposes at least `session_id`, `runtime_session_id` where present, `heartbeat_at`, `ttl_seconds`, and the claim/session association used to enrich sprintctl claims.

## Recommended Sequencing

1. Close the planning drift first.
   Update the master/cockpit/pilot docs so the current repos and dependencies are described accurately.

2. Use the pilot repo as a rollout target, not as a source of new substrate work.
   `homelab-analytics` is ready for migration rehearsal once workstream B exists; there is no repo-local sprint work to unblock first.

3. Sequence cockpit implementation in two slices.
   Slice 1: shell plus read-only panes backed by pg/audit once workstream B is available.
   Slice 2: claims/session enrichment and dispatch only after actionq exposes the required read/write API.

4. Keep appservice work explicit.
   No plan should imply cluster readiness until `sprintctl-postgres`, `actionq-server`, and `agent-cockpit` manifests exist beside `actionq-db`.

## Immediate Follow-Up

- Start the next sprint in `sprintctl` for workstream B or workstream C rather than continuing to hold `homelab-analytics` sprint `#78` open as a placeholder.
- Reconcile the shipped `auditctl` repo against the workstream D plan and capture any delta in a focused follow-up doc instead of leaving contradictory repo-exists / repo-does-not-exist statements in the main plan set.
