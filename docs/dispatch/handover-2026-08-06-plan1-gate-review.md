# Handover — Plan 1 / appservice#2080, gate-1 review + producer-fence plan

**Written** 2026-08-06. Builds on `handover-2026-08-05-plan1-online-migration.md`
(merged `34c1835`, attached to appservice#2080 as ref #660, superseding
ref #656 for everything after the pre-#2080 preflight). Nothing in that
document is superseded here — this is additive: it closes gate 1 with
conditions, and gives gate-2's residual risk (the producer fence) a concrete
design for the first time.

**Status: neither gate is fully clear yet. Gate 2 (operational) is reported
resolved by the appservice session but not re-verified here. Gate 1
(procedural) is now GO-WITH-CONDITIONS pending two one-sentence doc edits.
A third, previously undocumented gap — the producer fence has no actual
write-blocking mechanism — has a recommended design but is not built.**

---

## 1. What this session did

Picked up mid-conversation after a `/model` switch interrupted a paste of the
appservice stabilization session's notes. Confirmed via `git log`/`git status`
that the 2026-08-05 handover is already merged; found one unrelated untracked
file (`docs/dispatch/handover-2026-07-31-wave2-actionq.md`, a stopped Wave-2
ActionQ handoff, unrelated to this tract — see §6).

Operator confirmed: appservice-side stabilization (postgres liveness-kill
loop, `metallb-frr-k8s` crashloop) is complete, closing what the prior
handover called the operational gate. **Not independently re-verified in this
session** — no live cluster check was run here; see §7 next steps.

Operator confirmed gate 1 (independent review of ref #659 and the online
plan) was **not yet done**. Three fresh-context agents were dispatched in
sequence to do the review and follow-on planning work:

| Agent | Task | Result |
|---|---|---|
| Independent review | GO/NO-GO verdict on ref #659 + the online plan, source-verified | **GO-WITH-CONDITIONS**, no blocking findings |
| Effort/scoping planner | Work breakdown for §8 steps 3–8 of the prior handover | 4 of 6 steps execution-ready; step 3 has a real gap; step 7 works but is unscripted |
| Producer-fence planner | Design a concrete fix for the step-3 gap | Recommends a DB-level REVOKE/GRANT fence, reusing an existing Job idiom |

## 2. Gate 1 (procedural) — GO-WITH-CONDITIONS

A fresh-context reviewer read the deployed serving image's actual source
(`actionq/schema.py` at git tag `v0.1.16`), the `004`–`006` migration SQL, and
`vuoro_service/app.py`, rather than taking the prior handover's claims on
faith. Findings:

**Verified correct, no blocking issues:**
- §3's compatibility argument (`require_compatible` checks set-equality
  against exactly `{1,2,3}` or `{1,2,3,4,5,6}`, all DDL + grants + the
  compatibility check inside one `pg_advisory_xact_lock` transaction) is real
  in the 0.1.16 source, not aspirational.
- `004`–`006` DDL matches the prior handover's description exactly.
- §5.1's readiness-probe claim (`/health/ready` returns a static in-memory
  value, never queries the DB) is confirmed in `vuoro_service/app.py`.
- §8's step ordering (fence before migration, cold-start proof before fence
  release) has no defect.
- Step 4's backup gate: the migration Job's `await-backup-checkpoint` init
  container already hard-verifies backup UID/phase before proceeding, which
  makes the deferred CNPG alerting gap (prior handover §10) non-blocking for
  this specific cutover — the Job checks in-band, an alert isn't load-bearing
  here.

**One nuance not stated in the prior handover:** the atomicity/bridge-safety
guarantee comes from the **serving** image (0.1.16), not the **pinned
migration** image (0.1.14) — 0.1.14's `schema.py` lacks the bridge
special-case and only checks `set(applied) != set(expected)`. This isn't a
bug (the migration Job's own pre-check expects exit code 3 at ledger
`{1,2,3}`, which 0.1.14 correctly produces), but the distinction should be
explicit.

**The one real gap, not blocking:** §9's "forward-fix is primary" currently
means *no rollback plan exists*, not a rehearsed alternative. Mitigating
detail absent from the prior handover: Postgres's transactional DDL
auto-rolls-back a failed migration transaction with no orphaned state — so
mid-transaction failure self-heals. There is still no drill for the harder
case: a successful commit followed by a runtime-observed defect at schema 6.

**Conditions attached to the GO** (apply before treating gate 1 as fully
closed):
1. Add one sentence to §3 of the prior handover naming which image (0.1.16,
   not 0.1.14) the bridge-safety guarantee depends on.
2. Add one sentence to §9 noting Postgres auto-rolls-back failed migration
   transactions.
3. Re-confirm the operational gate (cluster stability) immediately before
   step 3 of the cutover — the prior handover's §1 snapshot will be hours old
   by execution time, and this session did not re-verify it.

None of these edits have been applied yet — they're recommendations, not
completed work.

## 3. Effort/scoping review of the remaining steps (prior handover §8, steps 3–8)

| Step | Status | Note |
|---|---|---|
| 3. Producer fence | **Gap** — see §4 | Currently a checklist, not a control; see below |
| 4. Fresh backup + sentinels | Ready | Two reviewed GitOps commits, mechanism confirmed working |
| 5. `pre-migrate-online` preflight | Ready | Script's phase distinction verified to match the handover exactly — no discrepancy |
| 6. Unsuspend Job + reconcile | Ready | Single commit + Flux reconcile; watch the known Kustomization re-wedge bug (prior handover §11) |
| 7. Real-invocation + cold-start proof | Ready but unscripted | Mechanically possible via kubectl/E2E harness today, but manual multi-signal observation — no packaged script, easy to miss a signal under time pressure |
| 8. Release fence | Trivial | Safety depends entirely on step 7 being done rigorously first |

## 4. The producer-fence gap (step 3) and its recommended resolution

**The gap.** The appservice runbook's "Settle producers" step treats the
fence as a checklist: stop/suspend known producers (workstation, devbox-vm,
legacy vscode `actionq-daemon`/`dispatcher-once`/tmux loops), wait for
settlement, verify via `pre-scale`. The runbook itself flags, unresolved:
whether the still-live `vuoro-shared` endpoint can itself admit execution
writes during the window. No execution-write fence and no proof of
unreachability exists in either `agentops` or `appservice` — confirmed by
grep; only the warning text itself matches. This matters because the
migration takes an `ACCESS EXCLUSIVE` lock on `execution.actions` for the
whole transaction, and the "online, no outage" design assumes no writer races
it. Confirmed writer surface (from the quiescence Job's own SQL):
`execution.actions` and `execution.events`, both written through
`vuoro_execution_runtime`.

**Recommended fix: a DB-level REVOKE/GRANT fence**, not an application-level
maintenance-mode flag. The app-level option was ruled out: `vuoro-shared`
ships purely as a pinned OCI digest with no maintenance-mode mechanism in the
deployed manifests, and no app source is vendored in either repo — building
it would mean changing and rebuilding the upstream image, which directly
violates the runbook's own invariant that the service image doesn't change
during this migration.

The DB-level option reuses an already-proven Job idiom already present in
the repo (`vuoro-schema-grants-v1.yaml`,
`vuoro-execution-migration-session-limits-v1.yaml`: connect as a role,
mutate, read back and assert):

1. **`vuoro-execution-write-fence-apply.yaml`** — Job that `REVOKE`s
   INSERT/UPDATE/DELETE on `execution.actions` and `execution.events` from
   `vuoro_execution_runtime`, then reads back
   `information_schema.role_table_grants` to prove the revoke actually took.
2. **A write-probe smoke test** — attempt a real INSERT/rollback as the
   runtime role and assert `InsufficientPrivilege`; run as part of step 3
   before trusting `pre-scale`.
3. **A release step** (reuse the idempotent grants Job, or a dedicated
   `vuoro-execution-write-fence-release.yaml`) restoring privileges after
   step 7 passes, gated on its own read-back proof — this becomes the actual
   precondition for step 8.

Failure modes are clean: a failed REVOKE just fails the preflight write-probe
(REVOKE isn't inside the migration transaction, nothing to unwind); a failed
*restore* fails closed (writes stay blocked, surfaces as 500s) rather than
failing open.

**Documentation follow-on**, not yet applied: add this apply/verify/release
triple as explicit checks in the runbook's step 3 and step 8, and add the
write-probe assertion as a new check inside `pre-migrate-online`, which
today only proves queue emptiness, not write-denial.

None of this has been built. It is a design, reviewed against the actual
manifests and lock semantics, not yet implemented as YAML.

## 5. Updated view of the full cutover sequence

Supersedes prior handover §8 step 3's description only; steps 1, 2, 4–8
unchanged from the prior handover.

```
1. Stabilise the cluster.                                    [reported done, not re-verified here]
2. Independent review of ref #659 and the online plan.       [GO-WITH-CONDITIONS, see §2]
3. Establish the producer fence:
   a. Settle known producers (workstation/devbox-vm/legacy loops) per runbook.
   b. Apply the DB-level write-fence (§4) and pass its read-back verification.
   c. Run the write-probe smoke test; only then trust pre-scale.
4. Fresh unique CNPG backup; record the recovery-point boundary; replace sentinels.
5. docs/scripts/vuoro-execution-v6-preflight.sh pre-migrate-online     <- NOT pre-migrate
6. Unsuspend vuoro-execution-migrate-v6; reconcile vuoro-shared-db.
7. Verify via a REAL invocation, not probes. Then the same-digest rolling
   restart cold-start proof.
8. Release the write-fence (own read-back proof), then release the producer
   fence, only after 7 passes.
```

## 6. Stray item, not part of this tract

`docs/dispatch/handover-2026-07-31-wave2-actionq.md` is untracked in the
working tree — a stopped Wave-2 ActionQ handoff (ActionQ #2033/#2034 done,
#2035 unclaimed), unrelated to Plan 1. It predates this session and was not
touched. Flagging so it isn't mistaken for part of this handoff or lost.

## 7. Next steps, in order

1. Apply the two one-sentence doc edits to
   `handover-2026-08-05-plan1-online-migration.md` (§2 conditions 1–2).
2. Re-verify cluster stability live, immediately before proceeding (§2
   condition 3) — do not rely on the appservice session's report alone given
   time elapsed.
3. Build and rehearse the write-fence apply/probe/release Jobs (§4) against
   the same production-shaped clone used for ref #659, before trusting it in
   production.
4. Update the appservice runbook and `pre-migrate-online` preflight per §4's
   documentation follow-on.
5. Resume the prior handover's §8 sequence at step 3 using the updated
   sub-steps in §5 above.
6. Decide on `docs/dispatch/handover-2026-07-31-wave2-actionq.md` (§6) —
   commit, finish, or discard — independently of this tract.

Nothing in this session touched production or the appservice cluster. All
three review passes were read-only (file/source reads); no manifests,
scripts, or runbooks were modified.

## 8. Artifacts

```
agentops   docs/dispatch/handover-2026-08-05-plan1-online-migration.md   (34c1835, ref #660)
agentops   docs/dispatch/handover-2026-08-06-plan1-gate-review.md        (this document)
appservice#2080  ref #659   online-migration rehearsal (reviewed here, GO-WITH-CONDITIONS)
appservice        docs/runbooks/vuoro-execution-v6-maintenance.md        (producer-fence gap lives here)
appservice        docs/scripts/vuoro-execution-v6-preflight.sh           (pre-migrate-online phase confirmed correct)
appservice         clusters/main/kubernetes/apps/vuoro-shared-db/app/vuoro-schema-grants-v1.yaml
appservice         clusters/main/kubernetes/apps/vuoro-shared-db/app/vuoro-execution-migration-session-limits-v1.yaml
appservice         clusters/main/kubernetes/apps/vuoro-shared-db/app/vuoro-execution-migrate-v6.yaml
```
