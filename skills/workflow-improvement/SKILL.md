---
name: workflow-improvement
description: Assess recurring delivery or agent-workflow problems, implement authorized remedies, record the strategy and revisit it against later outcomes. Use for requested retrospectives or demonstrated recurring friction, not as a mandatory ceremony for every patch.
---

## Purpose

Improve the working system while delivering real outcomes. Keep a small,
revisitable account of what was observed, what changed, and what would cause the
chosen remedy to be revised or retired. A written rule is not evidence that a
tool or environment implements it.

## Working loop

1. Find the relevant existing strategy/decision record and current workflow.
   Start from a concrete failure or friction report. Separate observed facts,
   hypotheses, estimates and unknowns; cite the source/evidence when available.
2. Identify the mechanism behind the issue and a proportionate remedy. Prefer
   better context, independently owned acceptance, useful feedback environments
   and tooling over more prescriptive specs, arbitrary line/retry limits,
   concurrency restrictions or additional approval rituals. These are diagnostic
   choices, not a requirement to prescribe the same remedy for every project.
3. Implement the authorized change and validate the actual path. Use a cheap
   representative check and a failure control appropriate to the defect, then
   run required broader checks. Keep implementation design with the implementer
   and scenario/oracle tightening with independent acceptance/review ownership.
4. Update the existing record with the chosen action, rationale, owner/surface,
   actual implementation status, verification and remaining gaps. Distinguish
   authored guidance, deployed tooling, observed behavior and proven improvement.
   Preserve superseded decisions and failed attempts. Do not rewrite history,
   reset budgets, resume paused work or widen effect authority through a lesson.
5. Reassess at the next relevant outcome closeout, recurrence, environment failure
   or material workflow change. Compare observed results with the remedy's
   hypothesis; keep, revise or retire it and implement necessary corrections
   within authority. Reuse the same record rather than duplicating the history.

## Record the useful minimum

- Issue and evidence; suspected mechanism and confidence.
- Selected remedy and alternatives rejected, with reasons.
- Status per action: proposed, implemented, observing, revise or retired; include
  the responsible owner/surface and any runtime or rollout gap.
- Actual verification and observable reassessment signals: escaped defects,
  false passes, feedback/setup latency, agent environment-repair time,
  coordinator context/intervention effort and outcome completion where available.
  Mark unavailable measurements unknown; do not manufacture metrics infrastructure.
- Next review trigger, latest observation, resulting decision and next action.

Use the repository's existing decision format when it fits. Link to served work
state and source-bound evidence rather than copying transcripts or creating a
parallel task tracker. Keep private evidence in its permitted destination.

## Boundaries

Do not turn a local example into a universal checklist, add a new ceremony before
ordinary work, or claim a change reduced failures before subsequent evidence
exists. Simplify or remove a remedy that adds friction without value. Existing
cost, time, safety and authority controls still apply; revise enforced policy
explicitly and prospectively rather than bypassing it or erasing prior failures.
