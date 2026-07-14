---
doc_id: ops-upgrade-reconciliation-2026-07
status: ratified
supersedes: null
---

# Ops-upgrade source-of-truth reconciliation — 2026-07-14

Pre-edit reconciliation for the agent-ops substrate refinement described in
`sprintctl/docs/ops-upgrade-plan.md`. Every claim below was checked against
current HEAD, live remote sprint state, and the workstation environment on
2026-07-14 before any documentation or backlog mutation. Classification
vocabulary: **verified current fact**, **GitOps intent / runtime unverified**,
**stale documentation**, **unresolved question**.

## Verified current facts

1. **Capability receipts are shipped.** sprintctl `main` commit
   `a5aef844a8ea9c9776b31ebd7028c0d161d3d0fa` (2026-07-14) lands atomic
   sprint-close boundary events, receipt pointers, and SQLite/PostgreSQL
   parity tests. Treat as shipped, not pending.
2. **PostgreSQL integration tests can target any URL.**
   `sprintctl/tests/test_pg_integration.py` gates only on
   `SPRINTCTL_TEST_PG_URL`, creates `itest-<uuid>` repo scopes, and relies on
   fixture teardown for cleanup. There is no server-side guard and no
   dedicated test role.
3. **No `itest-*` scopes currently exist in production PostgreSQL.**
   `sprintctl repo list` (remote backend, 2026-07-14) returns exactly:
   `_orchestration, actionq, agentops, aligned-equity, appservice, auditctl,
   box, homelab-analytics, kctl, scribectl, sprintctl`. The leaked-scope
   cleanup described in the ops-upgrade plan is **already satisfied or never
   persisted**; the remaining work is prevention (guard + test role), not
   cleanup.
4. **The workspace backup exists in GitOps.**
   `appservice/clusters/main/kubernetes/apps/vscode/app/workspace-backup.yaml`
   defines a daily Restic backup (03:55 UTC, retention policy, excludes
   ConfigMap) and a monthly restore drill with dedicated PVCs. Do not create
   an item to build this.
5. **The cockpit has a direct SQL write path.**
   `agentops/apps/web/lib/cockpit/sprintctl.js` (~lines 371–393) implements a
   sprint-activation transaction (`BEGIN` / `SELECT … FOR UPDATE` /
   `UPDATE sprint …` / `INSERT INTO event …`) in JavaScript against the
   sprintctl database. `write-surface-policy.md` (adopted 2026-07-10) permits
   mediated Tier-2a writes, so this is a policy-visible but domain-boundary
   exception: sprint-transition invariants are re-implemented outside
   sprintctl.
6. **ADR-001 is contradicted by shipped code.**
   `sprintctl-orchestrator/ADR-001-orchestration-boundary.md` (status
   Proposed, 2026-03-27) rules that sprintctl never becomes network-native
   and never adopts PostgreSQL. sprintctl now ships `pg.py`, a remote
   backend, `migrate-to-remote`, and a CNPG-backed production database.
   Formal supersession is required; the analysis of orchestration-layer
   responsibilities (P1–P5) remains historically valuable.
7. **Sprint state has drifted in both active scopes.**
   - sprintctl scope: sprint 379 "Phase 25: Remote Mode Foundations"
     (2026-04-28 → 2026-05-12) is still `active` two months past its end
     date, 11/14 done, 3 blocked `dispatch-smoke` items (942–944). Work such
     as capability receipts shipped without a corresponding active-sprint
     record.
   - homelab-analytics scope: sprint 354 (2026-05-10 → 2026-05-23) is
     `active` with 5/5 items done.
   - agentops, actionq, auditctl, kctl, appservice scopes have no active
     sprint; each holds one planned tool-backlog sprint (380–384).
8. **sprintctl's "Architecture Backlog" (sprint 374) is heavily stale.**
   Items 832–875 describe features that are shipped in current `main`
   (`usage --context`, `item ref add/list/remove`, `item dep`, `next-work`,
   handoff bundles, fzf output). Items 876–895 describe kctl-owned knowledge
   model work parked in the sprintctl scope. Refinement must reconcile these
   with evidence, not duplicate them.
9. **Per-repo dispatch manifests already exist** (`sprintctl.dispatch.json`,
   `appservice.dispatch.json`, `scribectl.dispatch.json`, …). The proposed
   `agentops.toml` appears nowhere outside the ops-upgrade plan text. Any new
   manifest role must consolidate with the dispatch manifest format via an
   explicit migration decision, not add a second format.
10. **`scribectl` is an unrelated tool.** It is a fiction-writing contract
    runner (Obsidian vault pipeline). The "canonical periodic scribe" in the
    session-mechanization design is a different component and must not be
    assigned to the `scribectl` repository. Naming collision only.
11. **Remote access contract.** The workstation reaches remote sprintctl
    state via `SPRINTCTL_URL` (injected from a local env file, not committed)
    plus `SPRINTCTL_BACKEND=remote`; the sprintctl repo carries a marker that
    rejects local-backend use. Existing backlog items 947/987 already track
    the injected-secret contract.

## Runtime-verified backup state (appservice cluster, 2026-07-14)

Checked via the appservice repo kubeconfig (`clusters/.kube/config`),
namespace `vscode`:

- **Deployed and current:** CronJobs `workspace-backup` (daily 03:55),
  `workspace-restore-drill` (monthly), `actionq-cnpg-restore-drill`,
  `sprintctl-cnpg-restore-drill` all exist and are not suspended.
- **Last successful workspace backup:** job `workspace-backup-29733355`
  completed 2026-07-14T03:56:19Z (same day). Verified green.
- **Restore drills are NOT durably observable.** All three drill CronJobs
  last scheduled 2026-07-01, but no drill job history survives from that
  date. The only surviving drill evidence is `actionq-cnpg-restore-drill`
  success from 2026-06-01 and a manual
  `sprintctl-cnpg-restore-drill-remediation-20260712` job (completed
  2026-07-12T07:42Z) — indicating the July sprintctl drill required manual
  remediation and that drill outcomes are lost to job garbage collection.
  This confirms the true gap is drill observability/alerting and semantic
  restore validation, not backup existence.

## GitOps intent / runtime unverified

- **Cockpit/daemon runtime state** (agent-cockpit deployment, actionq
  daemon) — inferred from GitOps and repo docs only; not runtime-verified in
  this pass.

## Stale documentation (corrected in this pass)

- `agentops/docs/plans/agentops/substrate-resilience-plan.md` claims the
  workspace PVC has "no VolSync ReplicationSource or other cluster-managed
  backup". A cluster-managed Restic backup + restore drill now exists in
  GitOps (fact 4). The remaining true gap is semantic/runtime verification
  and observability, not existence.
- `sprintctl-orchestrator/ADR-001-orchestration-boundary.md` (fact 6) —
  superseded by the sprintctl outbox/sync ADR.
- Sprint 374 item bodies describing already-shipped CLI features (fact 8).

## Unresolved questions

1. Who owns the Tier-0 harness-neutral session wrapper mechanism: actionq
   (session lifecycle authority) with agentops owning the capsule contract,
   or agentops end-to-end? Proposed default: actionq owns the mechanism,
   agentops owns the cross-domain contract and projection. To be settled in
   the state/event/command matrix.
2. Should sprints 379 (sprintctl) and 354 (homelab-analytics) be closed now?
   Sprint close is an authority operation that now emits a capability
   boundary and invokes operator receipt judgment — deliberately left to the
   operator; drift-detection backlog items cover recurrence.
3. Did the 2026-07-01 workspace and CNPG restore drills succeed? Job history
   is garbage-collected and only a manual sprintctl-cnpg remediation job
   (2026-07-12) survives. Needs operator confirmation and a durable
   drill-outcome record going forward.

## Governing documents produced in this pass

- `sprintctl/docs/plans/adr-outbox-sync-model.md` — canonical decision:
  outbox model, observation/command/decision split, identity and cursor
  model, migration.
- `agentops/docs/plans/agentops/session-mechanization-plan.md` — Tier 0/1/2
  session bookkeeping, capsule, reconciler, periodic scribe, cockpit metrics.
- `agentops/docs/plans/agentops/state-event-command-matrix.md` — per-event
  ownership, offline eligibility, validation, projection behaviour.
- Updates to `substrate-resilience-plan.md` and `write-surface-policy.md`.
- Supersession notice in `sprintctl-orchestrator/ADR-001-orchestration-boundary.md`.
