# Next-Session Handover — Vuoro Clean-Room Comparison

## Current decision

The assessment is **closed at the gate stage** with a no-migration decision:
no tested external composition is eligible for production migration. Continue
operating the existing/reduced Vuoro system by default. This is not a claim
that reduced Vuoro passed the full frozen comparison.

The authoritative decision record is [decision-readout.md](decision-readout.md)
and the normalized gate data is
[hard-gate-r2-r6-verdict.yaml](hard-gate-r2-r6-verdict.yaml).

## Do not reopen for matrix completion

Do not run more probes merely to fill empty scenario rows. Lane 1 fails R2;
Lane 3 fails R5/R6 as executed; Lane 4 is reference-only; td is a negative
control. The required dormant horizon, cost study, and adaptation probes are
intentionally recorded as incomplete rather than estimated.

## Only valid reopening trigger

Reopen only when there is a real **planner-to-Restate mutation boundary** to
test, initially with Beads. The integration must make Restate's claim decision
a prerequisite for every planner execution-state mutation; it must not create a
second write authority.

Before touching a candidate, create a new run ID and lock the candidate
revision/image, configuration hash, and fixture. Keep the frozen R1–R8 and H8
weights unchanged.

## Required next protocol

1. Prove the mutation boundary denies a planner transition without a current
   Restate proof/receipt and accepts it with the current proof.
2. Repeat the complete R2 sequence: concurrent acquire, proofless delegated
   mutation, handoff proof rotation, stale-proof rejection, controlled recovery,
   and stale post-recovery rejection.
3. Record the authority count and an executable reconciliation procedure. A
   Beads/Restate disagreement must have one owner and a tested recovery path.
4. Run comparable S-BATCH, S-SOLO, S-RESUME, and S-SIMPLIFY scenarios. Seed
   S-DORMANT at integration start; do not spend time observing disqualified
   candidates for fourteen days.
5. Capture per-lane/per-scenario operator time, agent tokens/tool calls,
   retries, failures, setup, carrying work, adaptation effort, and rollback.
   Do not average scenario classes or infer costs from this gate-stage work.
6. Re-evaluate R1/R2/R4 only if every hard gate and R6 pass, reconciliation
   decreases, and the candidate has a credible rollback.

## Rollback invariant

Until a candidate qualifies, Vuoro remains the claim and completion authority.
For an experiment, stop the adapter, reject candidate completion callbacks,
and return work to the retained Vuoro proof/revision. Treat planner state as a
projection until reconciliation confirms agreement.

## Useful files

- [Per-lane result sheet](per-lane-result-sheet.yaml)
- [Boundary dispositions](boundary-disposition-sheet.yaml)
- [Authority and reconciliation count](authority-reconciliation-count.yaml)
- [Cost status](segmented-cost-inputs.yaml)
- [Adaptation status](adaptation-probe.yaml)
- [Locked real corpus](../fixtures/sprintctl-real-corpus-v1.yaml)
- [Experiment contract](../contract/experiment-contract.yaml)

## Workspace note

The only expected unrelated worktree entry is `docs/plans/evidence-needed.md`.
Do not stage or alter it while resuming the assessment.
