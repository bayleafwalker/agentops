# Plan Acceptance Lattice (target architecture)

Status: proposed, 2026-09-28. The value-routing build workflow
(`workflow-topology.md`) is the migration step toward this design. Its implementation details are
evidence for this design, not constraints on it.

## Shape

**Plan → acceptance lattice → frontier resolution → frozen contract → oracle → build → verify**

| Component | Responsibility |
|---|---|
| Deterministic controller | Structure, dependency graph, authority boundaries, state transitions, thresholds |
| Jev (System One) | Many narrow semantic judgments per plan node and parent–child edge |
| Frontier planner | Writes and revises the plan; resolves failed or uncertain dimensions; may overrule the lattice |
| Oracle author | Turns the frozen contract into falsifiable checks, independently of the builder |
| Builder | Implements one frozen unit |
| Verifier | Establishes evidence, including whether the original intent survived decomposition |
| Operator | Shapes product intention through the repository's documents |

1. A planner produces a hierarchical work graph: objectives, decisions, dependencies, acceptance
   criteria, and traceability to parent intent.
2. Deterministic checks validate structure, cycles, identifiers and authority boundaries.
3. Jev scores every node and parent–child edge with atomic questions:
   - does the child preserve a named part of the parent's intent;
   - is the decomposition complete;
   - are sibling units too coupled to run independently;
   - is a decision still open;
   - is the acceptance observable;
   - can the proposed oracle reject wrong work;
   - does the unit fit one reasoning context;
   - is information missing;
   - does it cross an authority boundary.
4. Code combines the probabilities under a versioned policy. Nodes that clear it proceed.
5. Deficient or uncertain nodes go to the frontier planner with only the failed dimensions.
6. The revised graph is reassessed, for a bounded number of rounds.
7. The accepted contract is frozen and digested, in line with digest-bound acceptance
   (agentops #255).
8. An independent oracle author writes executable checks or a durable review contract.
9. Builders work only against frozen units.
10. Verification checks both correctness and that the original intent survived.

"Accepted" is a conjunction of separately measured properties:

`structurally_valid ∧ intent_covered ∧ decisions_closed ∧ acceptance_observable ∧ oracle_viable ∧ authority_permitted`

Jev supplies the semantic terms. Code owns the conjunction and its thresholds.

## Principles

**The planner keeps genuine oversight.**
- The lattice advises; it does not command. The planner may disagree with a lattice judgment, a
  rule or a deterministic step, and records why. It does not revise until Jev is satisfied.
- Revision rounds are capped. A disagreement the planner stands by is accepted with its
  rationale, not looped.
- Goodhart guard: whether the plan got better, or only narrower and easier, is never judged by
  the model the planner is optimising against. The original intent is recorded before
  refinement. Scope may move into follow-ups but is never dropped. The verifier checks the
  delivered work against the recorded intent.

**The operator shapes intention; the process does not wait on them.**
- Product shape and intention live in the repository's documents: direction docs, plans,
  decisions. Agents decide within them, preferring the option that is easiest to reverse, and
  record the decision in the frozen contract.
- When a later change of intention diverges from what was built, the work is reworked. That is
  cheaper than pausing now.
- Work goes to the operator only when product intention is entirely missing, or when an action
  needs the operator's own authority (their credentials, spending, irreversible production
  changes).
- Nothing tracks, counts or scores escalations. That is deliberate: a metric would become
  something agents optimise toward.

## Evidence so far

See `jev/eval/agentops-2026-09-28/README.md`.

- **On flat sprintctl items, narrow questions detect planning need about as well as a single
  Haiku triage call** (AUC around 0.7), not better. Their advantage is diagnostic: they name the
  dimension that failed, which is what the planner's packet needs.
- **A naive OR of failed dimensions over-flags** (77 of 100 items at 0.7). Each threshold needs
  calibrating against outcome labels before a combined rule decides anything. Otherwise the
  lattice sends nearly everything to the frontier planner, the opposite of its purpose.
- **The relational questions are untested.** Parent intent, completeness and sibling coupling
  need a plan graph, which sprintctl's flat items do not provide.

## Migration path

1. **Now.** Value-routing build workflow. Haiku lanes; the refiner records original intent;
   oracle, verify and repair; `dispatch.route.decision` records. Those records give outcome
   labels: repairs, parks, confirmations.
2. **Score lattice probes offline against recorded outcomes** (`jev_shadow.py score`) and
   calibrate per-dimension thresholds.
3. **Give the refiner the failed dimensions** instead of generic open questions.
4. **Introduce the plan graph and frozen contract.** Where the graph lives (Vuoro's
   digest-bound acceptance, or sprintctl dependencies plus a contract document) is the open
   design decision. The relational lattice questions become testable at this step.
