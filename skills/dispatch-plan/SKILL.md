---
name: dispatch-plan
description: Resolve consequential product, interface or authority ambiguities and cross-repo sequencing before implementation. Produce an outcome-oriented brief or immutable-wave source while leaving ordinary implementation design with its owner.
---

## Goal

Establish the intended outcome, acceptance evidence and real product, interface
and authority constraints. Give the implementation owner enough context to choose
the design and execution approach without repeating discovery at the coordinator.

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
   derive parallelism from dependencies, ownership and actual capacity; declare worker-focused, candidate-focused, and
   integration/repository-full verification; and identify the owner-issued
   terminal resource reference and required attachments.
8. Produce a compact brief with goal, allowed scope, out-of-scope, relevant
   contracts, independent acceptance responsibilities, cheap setup/focused-check/dev
   entrypoints, verification stages, review expectations and unresolved questions.
   Distinguish required constraints from suggestions. Resolve only consequential
   ambiguities; leave ordinary implementation decisions to the owner. Do not make
   a detailed design or line/attempt estimate a default prerequisite to starting.
9. Stop before implementation. If new sprint/action scope is needed, hand off
   to the repo's sprint or action creation workflow. Route an approved wave to
   `dispatch-wave`.

## Output Contract

- A concise outcome-oriented brief, with consequential decisions separated from
  implementation suggestions and owner-delegated choices.
- Explicit scope boundaries and verification commands.
- No repo edits.
- Open questions separated from decisions.
- In wave mode, a compiler-ready `dispatch-plan-source/v1` outline with exact
  topology and registered command/profile identifiers.

## Do Not

- Do not implement changes in this skill.
- Do not choose a model from AGENTS prose when the manifest or action payload has routing data.
- Do not invent repo-specific rules that belong in an overlay.
