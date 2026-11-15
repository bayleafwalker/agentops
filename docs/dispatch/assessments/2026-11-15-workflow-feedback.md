# Delivery workflow: assessment and remediation

Status: operator-directed strategy adopted; shared guidance implemented;
runtime-policy and project-environment rollout remain pending. Effectiveness has
not yet been measured. This record is intended for subsequent reassessment.

## Evidence and assessment

The operator reviewed roughly two days of lanectl delivery and rejected the
suggestion to solve recurring failures mainly through more scope/budget planning
or an arbitrary concurrency cap. The chosen direction is implementation freedom,
independent acceptance/scenario tightening, substantive brevity/simplification
review, fast representative environments and lower coordinator context retention.

Public examples motivating the changes:

- HLA overview-priority acceptance passed its 53 cases and 55 UI checks, yet
  independent execution exposed Python code-point versus JavaScript UTF-16
  ordering for valid Unicode titles. This demonstrates a scenario gap, not proof
  that a longer implementation specification would have prevented it. See
  lanectl `docs/evidence/2026-11-15-product-contact/overview-priority-closeout/`.
- The first Ubuntu lanectl CI run exposed fake-provider JSON emitted differently
  by shell `echo`. Actual dash red/green evidence supported a portable `printf`
  repair. An exact consumer/environment smoke could expose this earlier. See
  lanectl `docs/evidence/2026-11-15-stream-recovery/ci-preflight.json` and
  `dash-portability.json`.
- Hard line/attempt limits currently shape lanectl implementation eligibility and
  rejection. Their contribution to defects or elapsed time has not been isolated.
  They should not be treated as demonstrated measures of simplicity or quality.
- Coordinator preparation/context cost and total time saved by alternative
  approaches are not separately measured. No comparative productivity claim is
  established by this assessment.

These observations support improving oracle quality and feedback paths. They do
not establish that every defect has one cause, that more concurrency always
helps, or that expensive verification lacks value.

## Chosen actions and status

| Action | Owner/surface | Status and current evidence | Reassessment signal |
|---|---|---|---|
| Give implementers ownership of design/decomposition within real outcome and effect boundaries | Shared dispatch-plan/build guidance | Implemented in canonical skill sources; consumer copies use normal synchronization | Owners can progress without coordinator design micromanagement; contract violations still detected |
| Put independent AC/scenario/oracle strengthening outside implementer allowances | Shared build/review guidance | Implemented as guidance; revisions and original failures must be retained | Counterexamples reject wrong-order, vacuous, partial or inconsistent evidence before acceptance |
| Assess brevity and simplification in the substantive review pass | Shared review guidance | Implemented as guidance, not a new review ceremony | Concrete unnecessary mechanisms/state removed without code compression or cosmetic churn |
| Make cheap setup/focused/dev-smoke paths normal for every project | Shared verification and environment guidance | Expectation implemented; actual per-project entrypoints, timings and broken-prerequisite controls are not yet audited or rolled out | Agents run the same documented entrypoints; prerequisite failures surface before expensive work |
| Reduce coordinator context while retaining useful concurrency | Shared routing and planning guidance | Implemented as guidance; no arbitrary active-task cap introduced | Less transcript replay/context reconstruction; implementers/reviewers own detailed work |
| Replace default delivery LOC/attempt quality gates with review/progress judgment | lanectl runtime/governance owner | Pending explicit prospective implementation and validation; live caps remain enforced | New delivery behavior follows accepted policy without silently resetting old experiments or losing failure history |
| Reassess and repair the strategy itself | workflow-improvement skill and this record | Implemented documentation loop; no efficacy claim or automation | Next relevant closeout records keep/revise/retire decision backed by observed outcomes |
| Reconcile consuming skill copies and conflicting local review rules | Each repository's workflow owner | Pending normal synchronization/review; HLA's local size specialist still has numeric threshold guidance | Concrete simplification findings replace automatic size-only blockers; old findings remain historically attributed |

Resource deadlines, actual capacity, permissions and effect boundaries remain
valid controls. Removing a quality proxy does not authorize unbounded unattended
spending, weaken acceptance or erase an old rejection. Existing paused work is
not resumed by this documentation change.

## Alternatives rejected

- Requiring a more detailed design/size estimate before every implementation:
  this can optimize the constraint instead of the intended outcome and move
  implementation reasoning into the coordinator.
- Splitting or compressing code to fit arbitrary line caps: this can obscure
  quality and hide incomplete behavior.
- Restricting the active queue to a fixed number to ease coordinator memory:
  improve ownership and context transfer first; retain real capacity limits.
- Treating a large passing suite as sufficient acceptance: validate oracle
  sensitivity and the claimed scenarios too.
- Replacing expensive checks indiscriminately: retain checks that establish
  necessary integration, authority or recovery evidence.
- Adding a mandatory retrospective, new dashboard or operator approval round
  for each patch: use normal closeouts and one revisitable strategy record.

## Next review and remaining implementation

Trigger: the next relevant completed implementation/review outcome, or an earlier
recurrence of environment reconstruction, vacuous acceptance or coordinator
context overload. No timed schedule is configured.

The responsible workflow owner should append the observed source/outcome,
feedback/setup latency if available, escaped defects, independent counterexamples,
coordinator intervention/context burden and remaining unknowns. Decide whether
each chosen remedy should be kept, revised or retired, then implement the needed
correction. Link to served work state rather than creating another task history.

Before advertising the lanectl policy change as deployed, implement and validate
the runtime transition separately: optional diagnostic size/attempt accounting,
review/progress-based continuation, preserved historical experiment policies and
failures, and unchanged safety/effect controls. Changing these docs does not
disable existing enforcement or automatically reopen parked attempts.

For environments, prioritize the exact paths that already produced failures;
verify setup/check/dev entrypoints and a broken-prerequisite control with real
dependencies. Record measured results here as they arrive instead of claiming
estate-wide rollout from the shared rule alone.

## Reassessment log

- 2026-11-15: initial assessment and operator-selected remedies recorded.
  Shared guidance and reusable skill authored; subsequent effectiveness,
  runtime-policy implementation and environment rollout are pending.

## Validation of this guidance change

- New skill frontmatter validation passed; a temporary malformed skill missing
  its description was rejected by the same validator.
- Existing skill synchronization and boundary suites: 42 tests passed. The new
  agentops-selected skill resolves through its repository-local skill symlink.
- Public case-study evidence paths resolve in lanectl Git. No private runtime
  traces, credentials or hosting metadata were copied into this public record.
- Whitespace validation passed. No agent forward-test, runtime cap change,
  project-environment rollout or measured productivity improvement is claimed.
- Changes are local source changes until separately published. No paused delivery
  work, provider call, CI run or live service was started for this amendment.
