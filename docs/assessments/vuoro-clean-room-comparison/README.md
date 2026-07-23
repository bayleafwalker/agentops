# Vuoro Clean-Room Comparison — Evidence Package (Setup)

Status: **candidate-neutral setup only** (no candidate execution data added).

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

## Usage pattern

1. For each lane run, fill scenario templates under `templates/schema/*`.
2. Copy event rows into the shared `prevented-recorded` log template.
3. Populate gate and measurement sheets under `outputs/`.
4. Populate boundary disposition after all lanes complete and compare against
   frozen thresholds.

The intent is to keep candidate evidence comparable by forcing one schema and one
capture set across all lanes.
