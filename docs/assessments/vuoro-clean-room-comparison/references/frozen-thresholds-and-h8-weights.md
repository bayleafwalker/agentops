# Frozen thresholds and H8 model-sensitivity weights

Do not alter for candidate convenience. These values are frozen in the baseline
plan prior to external comparison.

## Pre-registered decision thresholds

From the comparison plan:

- **Remove** — Lane 0 / S-SIMPLIFY passes relevant hard gates, succeeds in
  at least 90% of relevant scenarios, adds at most 20% operator time versus
  baseline, and causes no recovery or trust-boundary regression.
- **Buy (external replacement)** — pass hard gates, match or improve Lane B
  outcome quality, reduce expected carrying cost by at least 30%, avoid
  adapters/forks greater than roughly one-third of displaced logic, and have a
  credible rollback path.
- **Wrap (external + thin adapter)** — commodity functionality is externalized,
  adapter is stable and materially smaller than displaced component, authority is
  unambiguous, reconciliation decreases.
- **Keep bespoke (reduced)** — reduced Vuoro materially outperforms Lane B at the
  boundary, or candidate fails hard gates or broad adaptation.
- **Keep bespoke (current)** — only when reduced-vs-current comparison is
  unfavorable for replacements and migration cost does not justify change.

## H8 weights (frozen)

From `06-reduced-workflow-specification.md`:

- R1 lifecycle: Low
- R2 claims: Medium
- R3 resume: High
- R4 decision log: Medium
- R5 unattended execution safety: Low
- R6 cross-machine authority: Low
- R7 durable knowledge transfer: Medium-high
- R8 composed operator view: Medium

## Baseline source references

- `docs/assessments/vuoro-pre-clean-room/06-reduced-workflow-specification.md`
- `docs/assessments/vuoro-pre-clean-room/07-open-hypotheses.md`
- `docs/assessments/vuoro-pre-clean-room/08-resume-observations.md`
- `docs/assessments/vuoro-pre-clean-room/README.md`
- `docs/plans/Vuoro-Clean-Room-Comparison-Plan.md`
