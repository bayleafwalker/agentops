---
name: dispatch-plan
description: Use when a request needs architecture decisions, scope shaping, cross-repo sequencing, or a batch/wave execution design before implementation. Produces a decision-complete brief or immutable-wave source without repo mutations.
---

## Goal

Produce an implementation brief that is complete enough for a build worker to execute without making new product, architecture, or routing decisions.

## Inputs

- The user request or accepted scope description.
- The repo dispatch manifest and any selected overlay.
- Relevant sprint, actionq, docs, and architecture context.
- The repo's planning guide, when one exists.

## Steps

1. Confirm the request needs planning: unclear boundaries, new architecture, ambiguous verification, cross-repo sequencing, or missing acceptance criteria.
2. Load the repo environment before reading sprint, cluster, or queue state.
3. Read the dispatch manifest first. Treat model and harness assignment as structured routing data, not prose.
4. Read the repo overlay for domain constraints, affected paths, verification commands, and gated operations (`.claude/gates.json`; absence of a declaration means routine).
5. Gather only the sprint/action/doc context needed to decide the scope.
6. Choose `single` or `wave` mode. Use wave mode only when interfaces and
   acceptance histories are frozen and multiple coherent units can amortize
   context, preparation, review, and broad verification.
7. In wave mode, classify entries as independent, stacked, or wave-integrated;
   set bounded parallelism; declare worker-focused, candidate-focused, and
   integration/repository-full verification; and identify the owner-issued
   terminal resource reference and required attachments.
8. Produce a brief with goal, allowed scope, out-of-scope, expected file areas,
   adversarial acceptance checks, verification stages, audit/review
   expectations, context-churn limits, and unresolved questions.
9. Stop before implementation. If new sprint/action scope is needed, hand off
   to the repo's sprint or action creation workflow. Route an approved wave to
   `dispatch-wave`.

## Output Contract

- A concise, decision-complete implementation brief.
- Explicit scope boundaries and verification commands.
- No repo edits.
- Open questions separated from decisions.
- In wave mode, a compiler-ready `dispatch-plan-source/v1` outline with exact
  topology and registered command/profile identifiers.

## Do Not

- Do not implement changes in this skill.
- Do not choose a model from AGENTS prose when the manifest or action payload has routing data.
- Do not invent repo-specific rules that belong in an overlay.
