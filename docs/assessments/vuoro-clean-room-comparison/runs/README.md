# Clean-Room Run Ledger

This directory contains the completed **gate-stage probes** and is ready for a
future qualifying integration run. The existing probes establish limited
exclusions and one isolated R2 pattern; they are not full lane results or an
adapter-versus-fork comparison. See the
[strategic assessment](../outputs/strategic-assessment.md) and
[final-criteria study](../outputs/final-criteria-study.md) before treating any
result as a disposition threshold pass.

## Run creation

Use one immutable directory per qualifying execution, for example
`runs/2026-07-23-lane-2-beads-restate-integrated/`. It must contain every file
listed in [`contract/experiment-contract.yaml`](../contract/experiment-contract.yaml).
The raw event log uses the shared
[`prevented-recorded` schema](../templates/schema/prevented-recorded-event-log.yaml).
Start from [`run-manifest.template.yaml`](run-manifest.template.yaml) and the
fixture-lock template in `contract/`; do not start from an earlier lane's
partially edited files.

For Lane B, use different run ids for `current` and `reduced`; the accepted
pre-clean-room resume observations can be cited for `S-RESUME`, but do not
replace the rest of the scenario pack or fabricate a comparison clock.

## Next qualifying-run sequencing

1. Reopen only for an integrated planner-to-Restate mutation boundary. Do not
   resume the disqualified whole-product lanes merely to fill matrix cells.
2. Lock the fixture and all candidate/configuration revisions before any
   candidate action.
3. Prove receipt-gated planner mutation, then run the complete R2 sequence and
   authority/reconciliation recovery before broader scenarios.
4. Run S-BATCH, S-SOLO, S-RESUME, and S-SIMPLIFY with the full measurement,
   adaptation, cost, and rollback ledger.
5. Start S-DORMANT at integration setup. A dormant verdict is unavailable
   before fourteen days and must remain `not-run`, not be inferred from a
   short resume.

## Result-sheet discipline

The files in `outputs/` are committed shared sheets, not per-run scratchpads.
Populate them only by linking to complete run-local evidence. Until then, their
`todo` values mean “not observed,” not failure, success, or a prior.
