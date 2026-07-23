# Vuoro Clean-Room Comparison — Evidence Package

Status: **experiment contract frozen in Git; no lane outcome is recorded yet**
(`2026-07-23`).

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
  - run-local evidence, created only after the contract and candidate lock are
    committed

## Usage pattern

1. Commit `contract/experiment-contract.yaml` and a resolved
   `contract/candidate-lock.yaml` before the first hands-on run.
2. For each lane run, create the required run-local files described in
   `runs/README.md`; do not overwrite the shared output schemas.
3. Copy event rows into the shared `prevented-recorded` log template, then
   populate the result sheets under `outputs/` with links to that raw evidence.
4. Populate boundary disposition only after all lanes that can affect that
   boundary have completed, and compare against the frozen thresholds.

The intent is to keep candidate evidence comparable by forcing one scenario
pack, one failure schedule, and one capture set across all lanes. The frozen
requirements and H8 weights are inputs to the experiment, never candidate-tuned
outputs.
