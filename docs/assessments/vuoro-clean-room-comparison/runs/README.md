# Clean-Room Run Ledger

There are deliberately no results in this directory yet. A lane result may be
recorded only after its participant lock and fixture lock are complete; this
prevents a changing candidate version, repository branch, or acceptance test
from becoming an untraceable advantage.

## Run creation

Use one immutable directory per execution, for example
`runs/2026-07-23-lane-b-current/`. It must contain every file listed in
[`contract/experiment-contract.yaml`](../contract/experiment-contract.yaml).
The raw event log uses the shared
[`prevented-recorded` schema](../templates/schema/prevented-recorded-event-log.yaml).
Start from [`run-manifest.template.yaml`](run-manifest.template.yaml) and the
fixture-lock template in `contract/`; do not start from an earlier lane's
partially edited files.

For Lane B, use different run ids for `current` and `reduced`; the accepted
pre-clean-room resume observations can be cited for `S-RESUME`, but do not
replace the rest of the scenario pack or fabricate a comparison clock.

## Sequencing

1. Lock the fixture and participants.
2. Run Lane B current and reduced.
3. Run Lane 0, including `S-SIMPLIFY`.
4. Run Lane 1's R2 litmus before its full pack.
5. Run Lane 2 and Lane 3 after their scopes are isolated; they may proceed in
   parallel only after the common fixture is locked.
6. Run Lane 4 last.
7. Start the 14-day dormant clock for every configured lane at setup. A
   dormant verdict is unavailable before that clock matures; it must remain
   `not-run`, not be inferred from a short resume.

## Result-sheet discipline

The files in `outputs/` are committed shared sheets, not per-run scratchpads.
Populate them only by linking to complete run-local evidence. Until then, their
`todo` values mean “not observed,” not failure, success, or a prior.
