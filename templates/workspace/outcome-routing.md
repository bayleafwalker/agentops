# Outcome routing: active dogfood practice

Operator instruction, 2026-11-04. Apply during real work; assess functionality and
fix or retire ineffective patterns. No preliminary policy PR, detailed coordinator
plan or separate benchmark project is required to start using this practice.

- Complete obvious minor tasks directly when delegation would cost more.
- Delegate useful outcomes with acceptance criteria. Select Luna or Terra by
  semantic complexity and uncertainty, not task granularity, file count or size.
- Give workers the outcome, acceptance criteria, constraints, ownership boundaries
  and escalation conditions. Workers own discovery, planning, decomposition,
  implementation, verification and repair within their authorized scope.
- Workers may use authorized native cheaper sessions, including OpenCode Go, for
  granular implementation and suitable suboutcomes. Ordinary engineering decisions
  do not require repeated coordinator approval. Do not create busywork to spend quota.
- Use lightweight deterministic complexity decisions when useful; consult an
  advisory classifier such as Jev for ambiguous cases. Classify once per outcome,
  reconsider when evidence changes, and allow abstention or escalation. This does
  not qualify the historical Jev classifier as an autonomous production router.
- Keep one declared integration owner for overlapping paths and target-branch
  writes. Preserve repository acceptance checks, independent review requirements,
  data restrictions and effect authority. Select required native models explicitly.
- Assess accepted outcomes, coordinator effort, review findings, repairs and elapsed
  time in normal closeouts. Label estimates and unknowns; avoid duplicate reporting.
  Keep guidance aligned with observed results and mark retired patterns with reasons.

## Workflow learning amendment (operator direction, 2026-11-15)

- Requirements and independently maintained acceptance criteria define the outcome;
  implementers own implementation design, decomposition and repair. Resolve real
  product/interface/authority ambiguities; do not default to a more prescriptive spec.
- Do not use line counts or fixed attempt counts as default delivery-quality gates.
  Review brevity and simplification together with correctness and maintainability,
  with concrete findings rather than nits or code compression. Resource deadlines,
  effect boundaries and evidence of progress remain meaningful controls.
- Acceptance authors/reviewers own adversarial scenarios and oracle checks outside
  the implementer's allowance. Strengthen them when evidence reveals a gap; preserve
  criterion revisions, original failures and source bindings. Never weaken the
  outcome to pass, rewrite history, or silently reset an experiment.
- Every project should provide a cheap reproducible setup, focused checks and a
  representative development smoke path that any authorized agent can run. Verify
  the exact entrypoints and prerequisites early; fail promptly with actionable
  environment errors. Use expensive checks when they add evidence for the change.
- Scale concurrent work by dependencies, ownership and actual capacity. Keep the
  coordinator's context small through outcome references, compact checkpoints and
  worker/reviewer ownership; do not impose an arbitrary work-in-progress cap to
  compensate for poor context management.
- Assess, repair, record the chosen strategy and reassess it on subsequent real
  outcomes. Use [workflow-improvement](../../skills/workflow-improvement/SKILL.md)
  for recurring workflow problems. The [strategy record](../../docs/dispatch/assessments/2026-11-15-workflow-feedback.md)
  distinguishes implemented guidance from pending runtime and project rollout.

Details: `/projects/dev/agentops/docs/dispatch/model-routing.md`, section
"Active dogfood practice (2026-11-04)". This instruction does not expand a session's
tool permissions or grant delegation when its runtime instructions prohibit it.
For unattended native workers with coordinator wakeup and a durable local result, use `agentops dispatch run` (see the dispatch-run section in model-routing.md).
