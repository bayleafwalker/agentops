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
Conversely, a large backlog item can require planning to create several implementation units before
dispatch. If that decomposition is still uncertain, the item is not build-ready.

## Execution Shape

The saved vuoro build workflow uses these rules:

1. Repositories run in parallel when independent.
2. Reasoning units in one repository run sequentially, each in a fresh accountable implementation
   context. This preserves a shared main worktree without forcing unrelated work into the hardest
   unit's model tier.
3. Items inside one reasoning unit remain with one implementation owner.
4. Verification uses a fresh context and an isolated worktree once per reasoning unit. It inspects
   every item diff, runs targeted checks first, and runs a broader gate once when required.
5. A separate clerical stage applies sprintctl state transitions from the verifier's verdict.
6. Publication is optional and occurs only after every built unit in that repository clears the
   gate. The workflow never force-pushes or repairs unexpected Git state.

Claim proof never enters workflow results or verifier prompts. A build worker captures it in an
exact mode-0600 workflow credential record for the authorized close stage, which validates the
record identity and removes only that file after a successful close or release. This is necessary
for remote sprintctl backends, where sprintctl's built-in local recovery record is unavailable.

This is deliberately flat. Build workers do not recursively create planners, coders, reviewers, or
summarizers. If a worker discovers an unresolved shared architecture, ownership boundary,
cross-repository dependency, or interface negotiation, it reports the constraint and trips the
same-repository circuit breaker. The tract owner then consolidates or replans the remaining wave.

## Routing And Escalation

- `bounded`: concrete acceptance criteria, known or discoverable local pattern, and deterministic
  rejection checks. Size alone does not disqualify a bounded change.
- `standard`: repository discovery, inferred contracts, multiple plausible implementations, or
  interpretation of failures.
- `hard`: subtle lifecycle, authority, migration, parity, or state-machine implementation after the
  relevant decisions are settled.
- planning/frontier: unresolved architecture, ownership, compatibility policy, cross-repository
  sequencing, or tract/backlog realignment.

Escalate from observed uncertainty rather than prestige. A failed deterministic check usually
returns to the same build tier with a precise defect packet. Escalate when the attempt reveals an
unknown contract, unexpected coupling, or a decision the worker lacks authority to make.

Provider ladders remain asymmetric. Codex can use Luna for bounded implementation, Terra for
uncertain and semantically hard implementation, and Sol for decisions. Claude uses Sonnet at
different effort levels for code-bearing work; Haiku is reserved for read-only triage and
deterministic bookkeeping. The same topology does not require pretending the providers have the
same worker economics.

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
reopens, duplicated discovery, integration repairs, and human interventions. Include the unit's
coupling classification; without it, aggregate one-owner versus dispatched results are not
actionable.
