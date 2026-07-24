# Vuoro Clean-Room Comparison — Evidence Package

Status: **migration-safety gate closed; strategic buy/adapt/fork assessment
open** (`2026-07-23`). No tested external composition is eligible for
migration. That supports retaining Vuoro's existing/reduced authority by
default; it does not establish that an external substrate cannot replace most
of Vuoro after measured adaptation or a maintained fork. See the
[decision readout](outputs/decision-readout.md),
[strategic assessment](outputs/strategic-assessment.md), and
[final-criteria study](outputs/final-criteria-study.md).

This package is the reusable evidence framework for **item #1217**. It creates
stable recording schemas for all planned capture formats before any external lane
study begins.

The package is anchored to the frozen artifacts and does not modify requirements:

- `docs/plans/Vuoro-Clean-Room-Comparison-Plan.md`
- `docs/assessments/vuoro-pre-clean-room/06-reduced-workflow-specification.md`
- `docs/assessments/vuoro-pre-clean-room/07-open-hypotheses.md`
- `docs/assessments/vuoro-pre-clean-room/08-resume-observations.md`

## Package layout

- `templates/schema/`
  - scenario-specific recording schemas for `S-BATCH`, `S-SOLO`, `S-DORMANT`,
    `S-RESUME`, and `S-SIMPLIFY`
  - a shared prevented-versus-recorded event log schema
- `outputs/`
  - reusable data sheets for lane results, gate verdicts, measurements, adaptation
    probe, authority/reconciliation count, cost inputs, and boundary disposition
- `references/`
  - frozen threshold and H8 model-sensitivity capture
  - canonical raw evidence links
- `contract/`
  - the immutable scenario/control package and the candidate-version lock
- `runs/`
  - run-local gate probes and future qualifying runs; the recorded probes are
    intentionally narrower than the complete scenario contract

## Usage pattern

1. Treat the existing lane records as gate-stage evidence only. They exclude
   drop-in migration and the tested configurations; they do not estimate the
   residual bespoke core of an adapted or forked candidate.
2. Run the source-level adaptation and fork analysis described in
   `outputs/strategic-assessment.md` before declaring any candidate
   economically unfit.
3. Before an authoritative vertical slice, create a new run ID and the
   complete run-local evidence set described in `runs/README.md`; do not
   overwrite the shared output sheets.
4. Populate a final boundary disposition only after a qualified integrated
   candidate satisfies the frozen safety criteria *and* the residual-ownership
   comparison supports the proposed migration shape.

The intent is to keep candidate evidence comparable by forcing one scenario
pack, one failure schedule, and one capture set across all lanes. The frozen
requirements and H8 weights are inputs to the experiment, never candidate-tuned
outputs.
