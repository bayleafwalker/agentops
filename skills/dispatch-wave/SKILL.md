---
name: dispatch-wave
description: Plan, compile, dispatch, observe, review, and integrate a bounded immutable execution wave. Use when several implementation steps share frozen interfaces and acceptance contracts, when work can run independently or as an explicit stack/wave, or when a coordinator should replace per-item polling and repeated full-suite runs with staged verification and terminal resource observation.
---

## Goal

Turn a decision-complete plan into a small number of coherent immutable
candidate actions, followed by independent review and one fresh integration or
repository-full gate where required.

## Preconditions

- Keep authority, compatibility, migration, recovery, schema, interface, and
  test-oracle decisions coordinator-owned.
- Freeze exact repository commits, work revisions, allowed paths, registered
  command IDs, and mutation-sensitive acceptance histories before dispatch.
- Use Actionq for action lifecycle and Sprintctl for development readiness.
  Never infer either from Git branches or surviving worktrees.

## Build the wave

1. Group steps that share one interface, context set, writable boundary, and
   acceptance contract. Prefer one coherent packet over several tiny packets
   when it remains independently reviewable and fits the declared limits.
2. Classify every entry as:
   - `independent`: no candidate input from another entry;
   - `stacked`: consumes the exact approved predecessor candidate;
   - `wave-integrated`: starts from the frozen base and joins through a fresh
     integration action.
3. Declare bounded `max_parallel`. Do not share mutable worktrees. Represent
   deliberate overlap as immutable candidate bundles plus an explicit
   merge-resolution/integration action.
4. Stratify commands:
   - worker attempt: fastest falsifying registered contract gate;
   - candidate verification: focused owner profile in a fresh checkout;
   - integration/repository approval: broad or full profile once per accepted
     independent candidate or integrated wave.
5. For filter/parity behavior, require fixtures where every filter excludes at
   least one record, matching records arrive out of order, ignoring a filter
   fails, the claimed layer is called for real, and empty/list-only assertions
   cannot pass.
6. Give the worker only exact registered command IDs. A worker that cannot run
   its own focused falsifier is not eligible to declare a candidate.
7. Set context-churn limits. Count repeated reads and mutation-free reasoning as
   stall signals, but do not optimize for cheap cache writes alone. Require a
   structured handoff as soon as the candidate and focused gate are ready.

## Observe and advance

1. Dispatch returns one owner-issued resource reference for the wave or action.
2. Issue one bounded `wait(until=terminal)` through the observable-resource
   contract. Do not implement coordinator polling loops.
3. At terminality, require attached execution receipt, candidate bundle,
   verification evidence, and bounded log/output references. Missing required
   attachments make the terminal result incomplete, not successful.
4. Candidate publication enqueues an independent review action through an
   explicit idempotent Actionq transition. Approval enqueues the frozen
   integration or repository-full action. Never synthesize those actions from
   observer-side status guesses.
5. Return the immutable plan reference, terminal resource reference, action
   references, candidate/review/integration refs, commands run, and residual
   blockers.

## Stop conditions

- A worker must decide semantics or alter the oracle.
- A stacked predecessor result is not frozen and approved.
- A command is not in the trusted registry.
- Required terminal attachments are absent or contradictory.
- Repeated context consumption exceeds the packet limits without producing a
  mutation, focused-gate result, blocker, or candidate handoff.
