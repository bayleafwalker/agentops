# Clean-Room Comparison Decision Readout

## Evidence-bounded conclusion

No external composition is eligible to replace Vuoro now. Retain the reduced
Vuoro composition as the operating recommendation and do not start a
production migration from this exercise. This is not a claim that the reduced
baseline won every comparison: full multi-actor scenarios, valid cost data,
adaptation probes, and the fourteen-day dormant scenario were not completed.
It is the only recommendation compatible with the failed hard gates and the
remaining unknowns.

The viable research direction is narrow: Beads may own R1/R4 only if a small
Restate claim adapter is placed in front of every execution-state mutation.
The adapter passed R2 in isolation, but the composed authority count and
reconciliation path are unproven. It is a follow-up hypothesis, not a rollout.

## Hypothesis readout

| Hypothesis | Readout | Why |
| --- | --- | --- |
| H1 external planner owns most work | Not supported as a replacement | Beads lacks R2; the only promising form is an unproven wrapped composition. |
| H2 claims can live in a narrow adapter | Supported in isolation; open in composition | Restate passed proof, rotation, delegation, and recovery litmus. |
| H3 downstream knowledge | Untested | No candidate event-feed/knowledge lane ran. |
| H4 repo-local audit | Unchanged | No audit consumer or substitute was exercised. |
| H5 cockpit uniqueness | Untested | No full supervised batch or projection replacement ran. |
| H6 served substrate removes concurrency defects | Untested | This corpus exercise does not cover the two-month defect window. |
| H7 heartbeat liveness | Unchanged | No new liveness counterexample was collected. |
| H8 model sensitivity | Frozen, unchanged | No candidate result changes the frozen weights. |
| H9 authored notes | Open by instruction | No additional resume observations were collected. |

## Recommended composition and migration order

1. **Now:** operate the reduced Vuoro profile; retain current R2/R3/R5/R6
   authorities. Do not migrate production state.
2. **Only if explicitly authorized:** implement one Beads-to-Restate mutation
   boundary. It must deny a Beads transition without a current adapter receipt,
   and it must create no second write authority.
3. Run the complete locked S-BATCH, S-SOLO, S-RESUME, S-SIMPLIFY, and dormant
   protocol against that integration. Record segmented costs, adaptation probes,
   and authority reconciliation before reconsidering R1/R2/R4.
4. Evaluate an execution runtime independently behind the retained claim-gated
   completion callback. Windmill's tested configuration is excluded; Temporal
   is only a durable-runtime reference.
5. Consider any production cutover only after all hard gates, R2, R6, cost,
   and rollback criteria pass. The current evidence does not meet that bar.

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
the unrun full scenarios, and absent valid cost data are why this readout makes
a conservative no-migration decision rather than declaring a final winner.

Evidence: [per-lane results](per-lane-result-sheet.yaml),
[hard-gate verdicts](hard-gate-r2-r6-verdict.yaml),
[authority count](authority-reconciliation-count.yaml), and
[cost status](segmented-cost-inputs.yaml).
