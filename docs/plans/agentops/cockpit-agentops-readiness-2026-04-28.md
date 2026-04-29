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
- Workstream B now has concrete implementation in `/projects/dev/sprintctl`: backend selection, pg storage, and `migrate-to-remote` are present, with remote-mode operator guidance under `docs/guides/remote-mode.md`.
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

- `actionq-db` is live under `/projects/dev/appservice/clusters/main/kubernetes/apps/actionq-db/`.
- `sprintctl-postgres` now exists under `/projects/dev/appservice/clusters/main/kubernetes/apps/sprintctl-postgres/`.
- `vscode-shell` now depends on `sprintctl-postgres` and injects `SPRINTCTL_URL` from `sprintctl-cnpg-main-app`.
- There are still no runtime app definitions for `actionq-server` or `agent-cockpit`.

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
- `sprintctl` remote backend and migration path.
- `sprintctl-postgres` appservice deployment slice.
- Actionq session read contract for cockpit claims/session enrichment, with a viable v1 adapter path through `actionctl sessions`.
- Pilot repo documentation target and real artifact location.

### Not ready yet

- Appservice manifests for `actionq-server` and `agent-cockpit`.
- A live actionq API target for cockpit dispatch.
- Any in-repo `agentops/apps/web` scaffold.

## Plan Corrections Needed

1. Treat `auditctl` as an existing implementation repo.
   The remaining workstream D work is integration, rollout, and any delta between the shipped implementation and the plan, not repo creation.

2. Treat cockpit dispatch as blocked on workstream C full, not merely C minimum.
   A read-only cockpit or a cockpit with mocked dispatch can start earlier, but the live `POST /cockpit/api/dispatch` path needs an actual actionq API contract.

3. Normalize the sprintctl pg query contract to the companion plan.
   The master plan should use the same active-sprint index/query language as `pg-backend-remote-mode-plan.md`.

4. Point cockpit implementation at the shipped actionq session contract.
   The read-side contract now exists in `/projects/dev/actionq/docs/session-read-contract.md`, including runtime-session join semantics, TTL/deadline fields, and the fallback claim association. In v1, consume it through a cockpit server adapter that invokes `actionctl sessions`; do not invent a second session summarizer in the cockpit codebase.

## Recommended Sequencing

1. Close the planning drift first.
   Update the master/cockpit/pilot docs so the current repos and dependencies are described accurately.

2. Use the pilot repo as a rollout target, not as a source of new substrate work.
   `homelab-analytics` is ready for migration rehearsal once the rollout sequence is scheduled; there is no repo-local sprint work to unblock first.

3. Sequence cockpit implementation in two slices.
   Slice 1: shell plus read-only panes backed by pg/audit plus the shipped actionq session contract, consumed through a server-side `actionctl sessions` adapter with short caching.
   Slice 2: live dispatch only after actionq exposes the required write API, and session reads can later move to a thin actionq read route if that service surface proves worth operating.

4. Keep remaining appservice work explicit.
   No plan should imply full cluster readiness until `actionq-server` and `agent-cockpit` manifests exist beside `actionq-db` and `sprintctl-postgres`.

## Immediate Follow-Up

- Start the next execution sprint against cockpit or actionq-server work rather than continuing to describe workstream B as planning-only.
- Reconcile the shipped `auditctl` repo against the workstream D plan and capture any delta in a focused follow-up doc instead of leaving contradictory repo-exists / repo-does-not-exist statements in the main plan set.
