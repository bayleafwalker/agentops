# Workflow improvement through delivery

Operator direction, 2026-11-15. Assess a workflow against real outcomes, fix the
mechanism causing friction or incorrect results, document the selected strategy,
then reassess and remediate as later evidence arrives. The reusable entrypoint is
[workflow-improvement](../../skills/workflow-improvement/SKILL.md); the first
[strategy record](assessments/2026-11-15-workflow-feedback.md) records this change.

## Ownership and implementation freedom

Requirements establish intended behavior and real constraints. Acceptance criteria
and scenarios independently validate that behavior. Implementers own discovery,
implementation design, decomposition, ordinary regression tests and repair. More
prescriptive specifications are useful only when they resolve a consequential
ambiguity; they are not the default remedy for implementation failure.

Acceptance authors and reviewers own oracle quality, adversarial scenarios and
counterexamples outside implementer allowances. A discovered gap should strengthen
the criteria, with its revision and source-bound rerun recorded. A new scenario
must exercise the intended outcome rather than quietly add a product requirement.
Original failures remain failures. Historical experiments retain their original
policies and denominators; new policy is prospective.

Review correctness, architecture, readability and simplification together. Ask
whether an unnecessary mechanism, duplicate responsibility or avoidable state can
be removed. Code brevity is part of that judgment. Line ceilings, compressed code,
cosmetic nits and fixed retry counts are poor substitutes. Time/cost controls and
progress evidence can still identify stalls; no workflow gets infinite unattended
execution by implication.
Repeated failure without new evidence calls for diagnosis or a different approach,
not another identical attempt. Stop for a real authority/resource boundary or an
operator pause; do not manufacture an approval dependency to avoid making an
ordinary engineering decision.

## Fast environments and forward failure

Projects should expose discoverable commands for setup, focused checks and a
representative development smoke. Any authorized implementation or review agent
should be able to use them without reconstructing the environment from a
conversation. Use the real relevant backend/contract and controlled fixtures;
an unfaithful substitute does not establish integration behavior.

Before an expensive implementation or qualification loop, exercise the exact
entrypoint, installer and prerequisites in a cheap representative environment.
Missing tools, wrong versions, unavailable backends and missing configuration
should fail early with an actionable diagnosis, separately from behavior and
oracle failures. Check a suitable broken-prerequisite case, not just a successful
startup. Keep fixture/port/process ownership and cleanup explicit so parallel
agents can reuse tooling without sharing mutable test state accidentally.

Routine development belongs mostly in these inexpensive feedback loops. Expensive
checks remain appropriate when they establish useful evidence or are required for
integration/release. Repeat them for changed surfaces, failures or unresolved
concerns; do not run every expensive check after every edit, or omit a necessary
one merely because it is expensive. Observe cold/warm setup and check times where
practical; there is no invented universal latency target.

## Context and concurrency

Delegate coherent outcomes and let implementers and reviewers retain the detailed
working context. The coordinator normally needs intent, dependencies, effect
boundaries, ownership, exact candidate/evidence references, decisions and blockers.
Reviewers consume the immutable diff, relevant contracts and focused evidence
rather than a replay of the implementation transcript.

Derive concurrency from dependencies, path ownership, actual compute/service
capacity and integration readiness. Do not reduce useful parallel work simply to
make a context-heavy coordinator easier to operate. Use compact durable
checkpoints and one integration owner where writes overlap. Respect a requested
pause and settle owned processes before handing work on.

## Reassessment, not rule accumulation

Maintain one small strategy record for a recurring mechanism. Record observations,
hypotheses, selected remedies, reasons for rejected alternatives, actual status
and the next meaningful review trigger. Link to existing work/evidence instead of
duplicating it. Revisit at a relevant outcome closeout or when the issue recurs;
no scheduled automation or extra approval round is implied.

Ask whether the remedy improved correctness and feedback time, transferred more
useful context to the owner, or merely moved work into coordination. Keep unknown
measurements unknown. If a rule adds friction, produces false confidence or fails
to improve the observed mechanism, revise or retire it and record why. A completed
documentation change starts observation; it does not establish effectiveness.
