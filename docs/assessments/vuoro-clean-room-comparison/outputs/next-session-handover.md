# Next-Session Handover — Vuoro Clean-Room Comparison

## Current decision

The migration-safety gate is **closed** with a no-migration decision: no tested
external composition is eligible for production migration. Continue operating
the existing/reduced Vuoro system by default. The strategic buy/adapt/fork
assessment is still open; this is not a claim that reduced Vuoro passed the
full frozen comparison or is the cheapest maintainable design.

The authoritative decision record is [decision-readout.md](decision-readout.md)
and the normalized gate data is
[hard-gate-r2-r6-verdict.yaml](hard-gate-r2-r6-verdict.yaml).

## Do not reopen the safety gate for matrix completion

Do not run more probes merely to fill empty scenario rows. Lane 1 fails R2;
Lane 3 fails R5/R6 as executed; Lane 4 is reference-only; td is a negative
control. The required dormant horizon, cost study, and adaptation probes are
intentionally recorded as incomplete rather than estimated.

## Tested integration result

The real **Beads-to-Restate mutation boundary** was run after this handover.
The bridge made Restate's claim decision a prerequisite on its own path, but
native Beads mutation remained callable and created a second authority. It is
therefore disqualified; do not repeat it merely to fill scenario rows.

Do not repeat that configuration merely to fill scenario rows. A new safety-gate
candidate must materially eliminate or deny the native planner mutation path
before it reaches authoritative execution state.

## Strategic work that remains authorized by this record

The missing substantive question is whether a candidate can meet the gate with
less total bespoke and operational surface than Vuoro. Begin with the
[strategic assessment](strategic-assessment.md): source-map Beads mutations,
identify supported interception points and direct-write prevention, and compare
a thin adapter, maintained fork, upstreamable extension, Restate-backed module,
and Beads-as-projection variants. This analysis does not itself grant a
candidate production authority.

Before touching a candidate, create a new run ID and lock the candidate
revision/image, configuration hash, and fixture. Keep the frozen R1–R8 and H8
weights unchanged.

## Required next protocol

1. Lock the selected adapter/fork/replacement variant and prove its materially
   changed mutation boundary denies a planner transition without a current
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
   decreases, the candidate has a credible rollback, and the residual
   ownership comparison is favorable.

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
- [Final-criteria study](final-criteria-study.md)
- [Strategic assessment](strategic-assessment.md)
- [Adaptation status](adaptation-probe.yaml)
- [Locked real corpus](../fixtures/sprintctl-real-corpus-v1.yaml)
- [Experiment contract](../contract/experiment-contract.yaml)

## Workspace note

The only expected unrelated worktree entry is `docs/plans/evidence-needed.md`.
Do not stage or alter it while resuming the assessment.
