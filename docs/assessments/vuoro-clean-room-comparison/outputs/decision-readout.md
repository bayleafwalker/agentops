# Clean-Room Comparison Gate-Stage Decision Readout

## Evidence-bounded conclusion

The clean-room comparison has closed its **migration-safety gate**, not the
strategic build-versus-buy decision. No tested external composition is eligible
to replace Vuoro today. Continue operating the existing/reduced Vuoro system by
default and do not start a production migration from this exercise.

This result answers only: “Can a mostly off-the-shelf composition replace Vuoro
immediately, without first implementing the missing Vuoro semantics?” The
answer is no. It does not answer whether an external substrate could replace
most of Vuoro through a small, stable adapter, an upstreamable extension, or a
maintained fork. No source-level adaptation analysis, fork comparison, real
workflow substitution, or residual-bespoke-cost measurement was completed.

The Beads-to-Restate planner mutation boundary has now been tested. The
narrowly scoped claim adapter still passes R2 in isolation, but the real bridge
leaves Beads' native mutation path callable without a receipt. Its authority
count is therefore two, and its repair path does not remove the bypass. This
disqualifies the **tested adapter configuration** from migration; it does not
disqualify a differently structured adapter, a narrow Beads fork, an
upstreamable extension, or a Restate-backed replacement module.

The td minimization control failed the intended R1, R2, R5, and R6 boundaries;
it is evidence about what cannot be removed, not a competing migration path.

## Hypothesis readout

| Hypothesis | Readout | Why |
| --- | --- | --- |
| H1 external planner owns most work | Open after adaptation | Beads-as-is lacks R2; the cost and maintainability of making a planner safely participate are unmeasured. |
| H2 claims can live in a narrow adapter | Supported in isolation; open in a real composition | Restate passed proof, rotation, delegation, and recovery litmus; adapter versus fork is untested. |
| H3 downstream knowledge | Untested | No candidate event-feed/knowledge lane ran. |
| H4 repo-local audit | Unchanged | No audit consumer or substitute was exercised. |
| H5 cockpit uniqueness | Untested | No full supervised batch or projection replacement ran. |
| H6 served substrate removes concurrency defects | Untested | This corpus exercise does not cover the two-month defect window. |
| H7 heartbeat liveness | Unchanged | No new liveness counterexample was collected. |
| H8 model sensitivity | Frozen, unchanged | No candidate result changes the frozen weights. |
| H9 authored notes | Open by instruction | No additional resume observations were collected. |

## Immediate operating decision

1. **Now:** operate the reduced Vuoro profile; retain current R2/R3/R5/R6
   authorities. Do not migrate production state.

2. Keep execution evaluation separate behind the retained claim-gated
   completion callback. Windmill's tested configuration is excluded; Temporal
   is only a durable-runtime reference.

## Open strategic assessment

The next question is: **which external substrate leaves the smallest, cleanest,
and most stable residual Vuoro-specific core?** The primary unfinished
hypothesis is Beads plus Restate, evaluated across adapter, fork, and
replacement-module variants. The required stages and decision criteria are in
[the strategic assessment](strategic-assessment.md). A production cutover
remains unavailable until a variant passes both that residual-ownership
comparison and the frozen hard gates.

## Rollback paths

- **Reduced Vuoro:** re-enable only a previously removed non-authoritative
  surface; no state migration is involved.
- **Beads + Restate experiment:** stop the adapter and direct all work through
  retained Vuoro claims; treat Beads state as a projection until reconciliation
  confirms it agrees with the authoritative claim record.
- **Execution experiment:** disable submission to the new executor, drain or
  cancel jobs without accepting their completion callbacks, and resume only
  from the retained authority's latest proof/revision.
- **Any future cutover:** retain the source authority read-only, export a
  versioned reconciliation report, require an operator-approved reversal, and
  never replay an executor receipt without the current claim proof.

## Remaining evidence

The required fourteen-day S-DORMANT observation cannot be accelerated or
substituted. It should remain explicitly incomplete. The absence of that run,
the unrun full scenarios, absent valid cost data, and absent adaptation/fork
measurement are why this readout does not declare a strategic winner.

Evidence: [per-lane results](per-lane-result-sheet.yaml),
[hard-gate verdicts](hard-gate-r2-r6-verdict.yaml),
[authority count](authority-reconciliation-count.yaml), and
[cost status](segmented-cost-inputs.yaml). See also the
[execution-boundary study](execution-boundary-study.md) and
[reduced-profile sufficiency study](reduced-profile-sufficiency-study.md).
