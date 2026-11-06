# Measure acceptance, correctness and use separately

Status: reusable experiment procedure with a read-only preflight, 5 November
2026. No cohort has been run or accepted by this artifact. Use one
[companion](outcome-observations.template.json) for each software, household or
creative cohort to retain observations beside the existing experiment records;
it is not an import payload, schema migration, acceptance writer or production
data set.

## Reuse the current owners

[`vuoro-evidence.ExperimentRecord`](https://github.com/bayleafwalker/vuoro/blob/1eae8ace228af39bd224565bac5be0a1fb7c4f25/packages/vuoro-evidence/src/vuoro_evidence/experiment.py)
already binds the named population and revision arm, preserves missing cases,
records capture and run composition, and summarizes review, rework, recovery
and costs. Its references do not authenticate themselves. The existing
[`cost_per_release.py`](../../../../scripts/cost_per_release.py) joins offline
session/tick/event exports without becoming a settlement writer. Its wall-time
apportionment remains an allocation assumption, not exact per-task billing.

Use the current owner Decision as the internal acceptance observation. Bind
the companion's independent check and use evidence through existing evidence
references. Do not overwrite owner disposition when an external check disagrees;
retain both observations and let the existing owner review the disagreement.

## Freeze the question before executing

Record the task population and excluded cases, immutable requirements and
oracle references, source/release and model/harness/recipe revisions, observation
window, capture method and comparison rule. Select those before seeing outcomes.
For a before/after comparison preserve workload mix and report sample size,
variance and relevant changes in the environment. If the intended comparison
cannot be supported, report a bounded observation rather than a causal effect.

An independent requirement or oracle is defined outside the implementation's
own success signal. Examples are owner-approved requirements, a reviewed mapping
fixture, a known reconciliation total or a user task observed to succeed. Merely
using a second component or model does not establish independence.

## Keep these columns separate

| Observation | States and required basis | What it establishes |
| --- | --- | --- |
| Internal acceptance | accepted / rejected / pending / unknown; exact owner Decision and artifact revision | The owner's recorded process disposition. |
| Requirement check | pass / fail / unknown / not-applicable; frozen criterion, oracle origin, evaluated revision, result and evidence | Correctness within those independently specified criteria. |
| Actual use | observed / not-observed / unknown / not-applicable; consumer, observation window and evidence | Whether a named consumer used the artifact during that scope. Use alone does not establish correctness. |
| Escaped defects | observed count or unknown; detection method, observation window and coverage | Defects found after acceptance. Zero under an observed method is bounded evidence, not proof of no defects. |
| Burden and cost | review/rework/recovery time, direct cost by currency, capture coverage, unknown components | The measured resource burden of the whole population. |

No revert and survival into a later sprint can be recorded as observations.
They do not upgrade unknown correctness or unknown use to a pass. A comparison
with no capture of defects must not report zero escaped defects.

## Derived measures

- **Cost per internally accepted case:** whole-population cost divided by
  internally accepted cases. Retain failed/rejected attempts and retries in the
  numerator. Label it a process metric; acceptance leniency can change it.
- **Cost per independently verified case:** whole-population cost divided by
  cases passing the predeclared independent requirement set. Report which
  required checks were unknown; incomplete checks cannot create a pass.
- **Useful verified outcomes:** count the intersection of independently passed
  cases and observed use, when use is an applicable predeclared requirement.
  Present the other categories and missing cases alongside this count.
- **Reviewer burden:** report observed review/rework/recovery distributions and
  unknown observations across every disposition, not only accepted work.

With zero successful cases, the relevant ratio is undefined, not zero. With
missing costs, report the known partial numerator and coverage; do not present
a precise total-cost ratio. Never sum currencies without an explicitly sourced
conversion basis. A token count is not a monetary cost. Repeated runs of one
case do not manufacture extra successful cases.

## Preregistering and using the companion

Copy it into the owner's private evidence location. Bind the planned population,
independent requirements, evaluation policy and observation window before runs.
Record the same frozen expected case IDs for both arms, and reference the
baseline and candidate `ExperimentRecord` and revision under `comparison.arms`.
Set `comparison.registered_at`, the named threshold owner, the claim rule, a
positive useful-verified-rate threshold, and thresholds for maintenance,
re-explanation, review, failed attempts, escaped defects and direct cost before
recording observations. Each threshold carries its own owner reference and
registration time. Duplicate `case_template` once per case per arm into `cases`;
preserve absent cases with no positive observation instead of dropping them.
Record the arm revision and first observation time. Null means unknown, not zero.
An empty observation array means no observations were supplied; it does not mean
a check passed.

The companion records case-level maintenance, re-explanation and review minutes,
failed attempts, direct cost with currency, and escaped defects alongside
independent requirement checks, actual use and internal acceptance. Link those
values to their source evidence. Keep owner acceptance, independently checked
requirements, actual use and escaped defects distinct. A pass requires its
criterion, independent oracle, evaluator, evaluated revision and evidence refs;
observed use and zero escaped defects also require their observation basis and
coverage.

Run the read-only guard before discussing an outcome:

```sh
python scripts/outcome_measurement.py path/to/outcome-observations.json --json
```

The report gives each arm's expected denominator and known-case coverage for
useful verified outcomes, independent passes, burden, failed attempts, defects
and cost. `not-preregistered` means the population, revisions, dates, owner or
threshold is missing or not frozen in time, including when a whole expected
case/arm pair has no observation; `incomplete` means an observed case lacks a
required value (for example a null cost or burden, an unknown required check, or
mixed currencies); both states exit 2 and neither allows a benefit claim; `thresholds-not-met` is a valid no-improvement or
guardrail failure; and `thresholds-met` means only that the configured
descriptive comparison passed. In all states, owner review remains necessary.
An outcome-improvement claim requires a positive useful-verified-rate threshold.
A benefit claim also requires preregistered thresholds and complete source
coverage for maintenance, re-explanation, review, failed attempts, escaped
defects and direct cost; each configured threshold must pass. `no_worse` sets a
maximum permitted increase, while `increase` and `decrease` require at least the
stated change. Rate changes use a 0-to-1 fraction; burden and cost use minutes,
attempt counts, defect counts and the recorded currency. Missing cost, effort,
use, defects or independent evidence stay unknown and block the corresponding
claim. Mixed currencies cannot be compared; this companion does not convert
them or claim causal effects.

The companion preserves semantic detail absent from the base observation's
disposition/evidence-class fields. Store its immutable reference among the
owner evidence, and use the existing ExperimentRecord for run/population/cost
accounting. The preflight reads the authored companion only; it does not verify
that referenced owner records exist or write a result back to them. If
consumption requires a new service operation, implement it under the TypeSpec
contract process rather than turning this authoring file into an ABI.

## Why compliance is a separate diagnostic

In [Harness Policy Distillation, table 1](https://arxiv.org/html/2610.20261v1),
the SFT condition improves runtime compliance from 19.90% to 55.92% while task
success falls from 3.09% to 2.06%. That bounded study motivates preserving both
dimensions. It does not establish an effect size for this estate or justify a
model-training programme.
