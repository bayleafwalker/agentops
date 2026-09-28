# Dispatch Workflow Topology

The stable default is one accountable tract owner with shallow, selective delegation. Neither one
agent per backlog item nor one frontier-model session for an entire tract is a useful invariant.
The delegation boundary is the reasoning unit: one invariant, subsystem contract, or tightly
coupled change whose discoveries need to remain in one implementation context.

## Choose The Reasoning Unit

Keep work with one owner when requirements and implementation are likely to co-evolve, files and
state transitions overlap, or one discovery can invalidate another item's approach. Several
backlog items may therefore share one `unit`. Split units when scopes have independent acceptance
criteria, do not negotiate a shared interface, and can be verified without relying on another
worker's uncommitted state.

Backlog items remain the evidence and closure units. They are not automatically agent boundaries.
Conversely, a large backlog item can need refinement into several implementation units. The build
workflow does that refinement itself when routing finds the decomposition still open; the first
coherent slice builds in the same run and the rest becomes new backlog items.

## Execution Shape

The saved vuoro build workflow routes every unit to the step that adds the most value next.
Routing and readiness never park work on the operator by default. Every lane moves the unit
forward in the same run.

1. Repositories run in parallel when independent.
2. Reasoning units in one repository run sequentially, each in a fresh accountable implementation
   context. Each unit is verified, and repaired if needed, before the next unit builds on top of
   it. This preserves a shared main worktree without forcing unrelated work into the hardest
   unit's model tier.
3. **Route.** A clerical router picks a lane and an implementation tier. A unit whose items all
   carry a caller-supplied tier has been planned and goes straight to build.
   - `build`: the approach is decided and an oracle exists, meaning concrete acceptance criteria
     with a deterministic check.
   - `oracle`: the approach is decided but nothing deterministic pins down "correct".
   - `refine`: architecture, ownership, sequencing, scope or acceptance is still open.
4. **Refine** (frontier model). The refiner decides open questions from the repository's
   documented direction:
   - first, decisions already recorded;
   - then the operator's stated direction;
   - then established patterns;
   - otherwise, the option that is cheapest to change later.

   It records each decision on the item, rewrites the item with acceptance criteria, and splits
   off follow-up items. It never writes code.

   The refiner has genuine oversight: the router's lane and questions are advisory, and it may
   say they are wrong. Before rewriting, it records each item's original intent. It may move
   scope into follow-ups but never drop it, and the verifier checks that the intent survived.

   A unit is retired when the documented direction shows it is obsolete. It is deferred only when
   no agent can progress this run: it depends on unfinished work, or it needs an action only the
   operator can take (operator-held credentials, spending money, irreversible destructive
   operations on production data), or the product intention is entirely missing. An
   operator-only action comes back with exact steps, a verified precondition and the expected
   result. Missing intention comes back as one concrete question in an item note.

   Uncertainty, preference and intention that is merely thin are never deferral reasons. The
   operator shapes product intention through the repository's documents. Where a later change
   of intention diverges from what was built, the work is reworked then. By design, nothing
   tracks or counts escalations as their own category, so there is no escalation metric for agents to optimise.
5. **Oracle** (frontier model, a separate author from the builder). The oracle author writes
   failing-first acceptance checks in the repository's test layout and commits them, or writes a
   concrete review checklist when the work cannot be checked by code. The builder must satisfy
   the oracle and may not modify it. The verifier confirms that the oracle paths are unchanged;
   a modified oracle is never confirmed.
6. **Build.** Items inside one reasoning unit remain with one implementation owner. Smaller
   decisions the items did not settle are decided in line with the recorded direction and noted.
   A builder never narrows an item silently. A part it cannot deliver (another repository, an
   operator-only setting, or moot) becomes a follow-up item: with exact steps for an
   operator-only setting, or cited evidence for a moot part. The verifier treats any part that is
   neither delivered nor moved as an issue, in every lane.
7. **Verify.** Verification uses a fresh context and an isolated worktree once per reasoning unit.
   It inspects every unit commit, runs targeted checks and the oracle first, and runs a broader
   gate once when required.
8. **Repair.** A unit with concrete findings (`issues_found`) gets up to two repair rounds. The
   first round runs at the same tier and the second escalates one tier. Each round is re-verified
   from scratch. A unit without a verdict (missing evidence, timeouts, no verifier answer) is
   re-verified once instead, because there is nothing concrete to repair.
9. **Park.** Every unit records its base commit, and everything committed after it (the oracle,
   the build, repairs, and anything unreported) is the unit's range. The workflow tracks main's
   head itself: a unit's base must be the head the previous unit left, or the repository halts.
   So no agent-reported base can reach back into an earlier unit. The verifier works at the tip
   the builder or last repair left, and rejects unlisted commits in the range.

   A unit that still has issues is parked: its whole range is reverted with `git revert`, never
   a history rewrite. Its claims are released with a note that hands the findings to the next
   refinement pass, and later units continue. An item is closed only when its whole unit is
   confirmed.

   A unit that ends without a verdict is left **unverified**. It is not reverted, because the
   work may be good, but its claims are released and the repository's push is withheld.

   The repository stops only when a unit's base is unknown or a revert does not apply cleanly,
   because later units would then build on commits nobody can account for.
10. A separate clerical stage applies sprintctl state transitions from the verifier's verdict.
11. **Publish.** Publication is optional. It pushes the verified work together with the reverts
    of parked units, and refuses if `origin/main..HEAD` holds any commit it did not expect. So main
    gains only verified net changes. It is withheld while any unit is unverified or the repository
    halted. The workflow never force-pushes or repairs unexpected Git state.

Items are held with sprintctl's advisory reservations (`sprintctl agent-protocol`). A reservation
carries no secret, so nothing sensitive travels between stages. The builder reserves each item
and marks it active. The clerical close stage then either marks it done, against the item's
current status revision, and releases the reservation, or returns it to pending and releases the
reservation.

This is deliberately flat. Workers do not recursively create planners, coders, reviewers, or
summarizers. Each stage is one agent with one job, and the workflow script owns sequencing.

## Routing And Escalation

- `bounded`: concrete acceptance criteria, known or discoverable local pattern, and deterministic
  rejection checks. Size alone does not disqualify a bounded change.
- `standard`: repository discovery, inferred contracts, multiple plausible implementations, or
  interpretation of failures.
- `hard`: subtle lifecycle, authority, migration, parity, or state-machine implementation after the
  relevant decisions are settled.
- Refinement (frontier): unresolved architecture, ownership, compatibility policy,
  cross-repository sequencing, or tract/backlog realignment. The workflow resolves these itself;
  they are a lane, not a stop.

Escalate from observed uncertainty rather than prestige. A failed deterministic check first
returns to the same build tier with a precise defect packet; a second failure escalates one tier.
A routing mistake is cheap by design: routing a ready unit to refinement costs one refinement pass
that sharpens the item, and building an under-specified unit meets its oracle and the verifier.

Provider ladders remain asymmetric. Codex can use Luna for bounded implementation, Terra for
uncertain and semantically hard implementation, and Sol for decisions. Claude uses Sonnet at
different effort levels for code-bearing work, Opus for refinement and oracle authorship, and Haiku
for routing and deterministic bookkeeping. The same topology does not require pretending the
providers have the same worker economics.

## Independent Verification

A verifier need not always be a more expensive model. Independence requires fresh context, direct
diff inspection, cold execution of relevant checks, explicit command evidence, authority to
reject, and no trust in the implementer's self-report. Use a frontier validator only when the
consequence of a subtle semantic miss warrants it.

All gating commands run foreground and blocking with a bounded timeout. A timeout or unavailable
required gate is `inconclusive`; it is never converted into a pass and never handled by detached
execution plus polling. Audit mode records findings but does not repair already shipped work.

## Measure The Shape

Compare topology by accepted scope per capacity consumed, not by agent count or generated lines.
For comparable units, record wall time, model/capacity use, accepted closures, verifier defects,
reopens, duplicated discovery, integration repairs, and human interventions. The build workflow's
`dispatch.route.decision` events already carry each unit's lane, refinement outcome, oracle kind,
repair rounds, and final outcome. Include the unit's
coupling classification; without it, aggregate one-owner versus dispatched results are not
actionable.
