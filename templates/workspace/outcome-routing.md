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

Details: `/projects/dev/agentops/docs/dispatch/model-routing.md`, section
"Active dogfood practice (2026-11-04)". This instruction does not expand a session's
tool permissions or grant delegation when its runtime instructions prohibit it.
For unattended native workers with coordinator wakeup and a durable local result, use `agentops dispatch run` (see the dispatch-run section in model-routing.md).
