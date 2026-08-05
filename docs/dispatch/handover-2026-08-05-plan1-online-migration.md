# Handover — Plan 1 / appservice#2080, online v3→v6 migration

**Written** 2026-08-05. Supersedes `handover-2026-08-03-plan1-preflight.md` (ref #656)
for everything after the pre-#2080 preflight.

**Status: #2080-A and #2080-B complete. Migration replanned as ONLINE and
rehearsed. Nothing migrated. Two gates block the cutover — one procedural, one
operational.**

---

## 1. Live production state (verified 2026-08-05 ~05:30Z)

```
work schema            5, plus the staged maintenance bridge
  bridge relations     4
  marker               maintenance-storage v1
  capability ledgers   empty
execution schema       3   (ledger {1,2,3}, checksums exact)
claimed/cancelling     0
vuoro-shared           both containers on the candidate digest
                       sha256:d23387480772a4d6b41f8fdf1c1d0f43a985a1087f76f4c4e80cc4325c53060e
vuoro-execution-migrate-v6   suspended, sentinels all REPLACE_AT_ACTIVATION
vuoro_execution_migration    lock_timeout=5s, statement_timeout=300s
flux vuoro-shared-db         ReconciliationSucceeded
last successful backup       2026-08-05T02:36:06Z
rollback digest              sha256:9c1d0e53… verified still pullable
```

## 2. What was completed

| Step | Outcome | Evidence |
|---|---|---|
| Operator CLI 0.2.13 → 0.2.17 | done, upgrade proven inert | ref #657 |
| **#2080-A** stage schema-5 bridge | PASS | ref #657 (`fe9d9851`) |
| **#2080-B** roll both containers to 0.1.35 | PASS, zero-gap handoff measured | ref #658 |
| appservice Sprintctl marker | committed `7afa6bfd` | note #2322 |
| Close sprintctl#2072 | done on live E2E | note #2323 |
| sprintctl#2096 split | narrowed to 3 scopes | note #2324 |
| Plan 1 gate hardening | merged, probe-proven | appservice #1343 |
| Runbook replanned as online | merged | appservice #1350 |
| Online guardrails | merged | appservice #1350, #1352, #1355 |
| **Online migration rehearsal** | PASS | ref #659 |

## 3. The central change: the outage is not required

The old runbook assumed Vuoro 0.1.31 / ActionQ 0.1.14, for which no
overlap-compatible runtime existed, so it prescribed scale-to-zero. **That
candidate was superseded.** Production runs 0.1.35 / ActionQ 0.1.16.

State the compatibility argument precisely — an earlier loose version of it was
wrong. ActionQ does **not** accept every version from `MIN_SCHEMA_VERSION=1` to
`MAX_SCHEMA_VERSION=6`. Those are range bounds. `require_compatible` tests
set-equality against exactly two ledger shapes:

```
{1,2,3}        complete schema 3 — pre-migration bridge
{1,2,3,4,5,6}  complete schema 6 — steady state
```

Versions 4 and 5 are migration internals, **not serving states**. This is only
safe because `actionq.schema.migrate` applies all DDL and all ledger rows inside
one `conn.transaction()` under `pg_advisory_xact_lock`, so no intermediate shape
is ever externally visible.

The correct claim: **the deployed candidate supports both sides of the atomic
migration boundary.**

## 4. Rehearsal results (ref #659)

Exact `004`–`006` against a production-shaped clone (live `pg_dump` structure +
grants + ownership + data), using the exact migration image digest the Job pins
(`sha256:4877eb4a…`, verified).

```
max blocking on execution.actions   115.7 ms   (median 0.35, p99 2.89)
read errors / 1900 samples          0
existing connection across commit   survived
fresh connection at schema 6        compatible, incl. deployed actionq 0.1.16
applied / retry                     [4,5,6] / []
post ledger + checksums             exact
runtime grants on 5 new tables      present (explicit, inside the transaction)
runtime DDL                         denied
```

**Limitations, do not overstate the result:** only concurrent *readers* were
exercised; the table is small (6 rows / 96 kB — same as production, so the
figure transfers, but not if `actions` grows); full four-domain composition was
not run against the clone (that was proven separately in #2080-B).

## 5. Two findings that change how the cutover must be verified

### 5.1 Readiness is a startup snapshot — and it proved itself in production

`create_composed_app` runs the compatibility check **once**, then hardcodes
`compatibility_state='compatible'` into `ServiceSettings`. `/health/ready`
returns that in-memory value and never queries the database. `/health/live` is
a static dict.

This was then observed live: after the CNPG primary was rescheduled,
`/health/ready` returned **200 for ~9 minutes** while `/api/invoke/v1` returned
**500** (`psycopg.OperationalError: the connection is closed`). A served
`item ref add` failed silently in that window and had to be reissued.

Consequences, all load-bearing for Plan 1:

1. Serving continuity across the migration is **guaranteed by construction** and
   is *not* evidence the runtime works at schema 6.
2. **The cold-start proof is mandatory**, not polish. Until a fresh process is
   proven to start at schema 6, a node eviction could leave the service unable
   to start.
3. Post-migration verification must exercise a **real invocation path**. A green
   probe proves nothing.
4. Recovery from a dead pool is a same-digest rolling restart. This was done and
   restored service immediately — an unplanned cold-start proof at schema 3.

Recorded as note #2326. Worth its own item: a readiness probe that cannot
observe its own dependencies is indistinguishable from one that is always true.

### 5.2 The lock is held for the whole transaction

Because `004`, `005`, `006`, the grants and the compatibility check share one
transaction, the `ACCESS EXCLUSIVE` lock `004` takes on `execution.actions`
persists until the entire transaction commits. **Measure transaction duration,
not statement duration.** This is why `lock_timeout` is mandatory: without it a
migration that cannot take the lock immediately queues, and every later query on
that table queues behind it.

## 6. Two gates block the cutover

1. **Procedural** — no production migration until the rehearsal (ref #659) and
   the online plan receive **independent review**. Not yet done.
2. **Operational** — the cluster is unstable. See §7. Do not migrate into it.

## 7. Open production incident (not caused by this work)

`vuoro-postgres-1` was in a **liveness-kill loop for ~10 hours** on 2026-08-04→05:

```
Liveness probe failed: Get "https://…:8000/healthz": context deadline exceeded   ×17 over 10h
Container postgres failed liveness probe, will be restarted
FATAL: the database system is shutting down (57P03)
```

Triggered by a node reschedule (`k8s-worker-gpu-1` → `k8s-worker-2`, volume
Multi-Attach then detach/reattach), in the same window as another session's SUC
drain-failure investigation
(`docs/training/health-checks/cluster-health-check-2026-08-04-suc-drain-failure.md`).

As of writing it has recovered — postgres 1/1, cluster ready 1/1, backup at
02:36Z succeeded — but `vuoro-shared` shows **6 restarts** and postgres 1, and
`metallb-frr-k8s` on the same node is in **CrashLoopBackOff (59 restarts)**.

Two things to carry forward:

- The CNPG `Cluster` object reported *"Cluster in healthy state"* while
  `readyInstances` was empty. **Its status lies; check `readyInstances` and the
  pod.**
- Ingress to the CNPG pod permits port **8000** only from the `cloudnative-pg`
  namespace; `remote-node` is allowed on **5432 only**. Kubelet probes target
  `:8000`. This may be contributory — but failures were *intermittent*, which
  argues for a slow instance manager over a hard policy denial. **Unconfirmed.
  Do not change policy on a flapping database to test a hypothesis.**

## 8. Next steps, in order

```
1. Stabilise the cluster: postgres liveness loop, metallb-frr-k8s crashloop.
   Coordinate with the SUC drain-failure work; same window, same node.
2. Obtain independent review of ref #659 and the online plan.
3. Establish the producer fence — and only then:
4. Fresh unique CNPG backup; record the recovery-point boundary; replace the
   three sentinels.
5. docs/scripts/vuoro-execution-v6-preflight.sh pre-migrate-online     <- NOT pre-migrate
6. Unsuspend vuoro-execution-migrate-v6; reconcile vuoro-shared-db.
7. Verify via a REAL invocation, not probes. Then the same-digest rolling
   restart cold-start proof.
8. Release the fence only after 7 passes.
```

Do **not** use the `pre-migrate` phase — it requires zero replicas, zero pods,
zero ready endpoints and a succeeded quiescence Job, all false online. Do **not**
scale `vuoro-shared` to zero. Do **not** change the service image; 0.1.35 is
already correct and spans both ledger shapes.

`DRAIN_BOUNDARY_UTC` is a **recovery-point** boundary on this path, not a drain
boundary. It proves the backup is fresh, unique and UID-attested. It does **not**
prove no writes followed. Never present it as evidence of quiescence.

## 9. Rollback posture — inverted from the outage plan

**Forward-fix is primary. Restore is the last resort.** `vuoro-postgres` holds
work, execution, knowledge and audit in one cluster. Because the tracker keeps
running online, restoring to roll back `execution` would also roll back `work`
and discard every tracker write since the recovery point. The outage path did
not carry this cost.

- Before `004` commits: nothing to roll back.
- After ledger v6 commits: 0.1.35 spans 1–6, so v6 is a supported state and is
  **not** by itself a rollback trigger. Prefer forward-fix.
- Never roll to an image whose declared range excludes the current ledger.
  Check the range; do not trust a version number.
- If the migration *stalls* rather than fails, suspect lock queueing. Inspect
  `pg_locks` and `pg_stat_activity` before anything else. Do not blind-cancel
  the runtime's transactions.

## 10. Deferred / open

- sprintctl#2096 Scope A: `_secure_claim_recovery_dir` masks with `0o777`, so it
  cannot see an inherited setgid bit. Live instance:
  `/projects/dev/vuoro/.sprintctl/claim-recovery` is `2700`. Fix: mask `0o7777`.
- sprintctl#2096 Scope B: `authority doctor`. Must **not** by itself block Plan 1.
- sprintctl#2096 Scope C: atomicity — **not reproducible** on 0.2.17. Do not
  implement the presumed rework; keep as a regression assertion.
- sprintctl#2097: enforce the markerless read/write distinction at the command
  layer. No carve-out was created.
- CNPG backup freshness alerting — handed back to the raising session. Note the
  bare `kubectl get backups` resolves to `backups.longhorn.io` and returns an
  empty set; any alert must query `backups.postgresql.cnpg.io`.
- `vuoro-shared-db` Kustomization re-wedges in `Progressing` when a Job it owns
  is deleted mid-reconcile; cleared only by restarting `kustomize-controller`.
  Hit twice this session.
- Readiness-probe blindness (§5.1) deserves its own item.

## 11. Working conventions that earned their keep

- **Run negative controls before believing a proof.** Every gate in this tract
  was proven to fail first: NC-A/NC-B on the execution-v6 backup gate, the
  `lock_timeout` gate, the phase-separation harness cases.
- **Build parity from the live system, not from a reconstruction.** Both the
  bridge rehearsal and this one used `pg_dump` of live structure + grants +
  ownership. The original #2080 defect was exactly a constructed/actual divergence.
- **Check the Kustomization is Ready after merging**, not just that the object
  landed. A `defaultMode` change inside a Job pod template is immutable and
  silently wedged GitOps for hours.
- `kubectl get backups` → Longhorn. Always `backups.postgresql.cnpg.io`.
- Always wrap cluster calls in `direnv exec /projects/dev/appservice`; confirm
  context `admin@main`.
- Sprintctl for appservice runs from the **plain shell** — `direnv` scrubs
  `SPRINTCTL_BACKEND`, which now resolves `invalid` against the committed marker.
- `pg_dump > file 2>&1` captures direnv banners into the SQL. Use `2>/dev/null`.
- Don't `pkill -f <script>` — it matches your own shell.

## 12. Artifacts

```
appservice#2080 ref #657   2080-A bridge-stage receipt (sha256 fe9d9851)
appservice#2080 ref #658   2080-B candidate roll receipt
appservice#2080 ref #659   online-migration rehearsal
appservice#2080 note #2322 marker + ref-provenance repair
appservice#2080 note #2326 readiness startup-snapshot finding
sprintctl#2072  note #2323 live proof-backed activation E2E
sprintctl#2096  note #2324 setgid reproduced / atomicity not reproducible

appservice PRs  #1326 #1331 #1334 #1335 #1337 #1338 #1343 #1350 #1352 #1355
agentops  PRs   #24 #25 #26
runbook         docs/runbooks/vuoro-execution-v6-maintenance.md
preflight       docs/scripts/vuoro-execution-v6-preflight.sh  (3 phases)
```
