# ADR-0001: Revision-Gated Projection Instead of Turn Cadence

- Status: proposed
- Date: 2026-08-17

## Context

Per-turn rendering repeatedly injects identical state and accumulates obsolete snapshots in conversation history. The authoritative task/event substrate already exposes append-only revisions or watermarks.

## Decision

Each provider exposes a cheap opaque revision validator and a bounded renderer. The projector compares the current revision with a disposable per-consumer cursor and renders only on change. Full projections are forced at session start, subagent start, and compaction continuation.

## Consequences

Positive:

- unchanged turns cost zero injected context;
- revision is explicit and usable for optimistic concurrency;
- provider rendering can remain expensive without running every turn;
- cursor loss degrades to duplicate injection.

Negative:

- providers need snapshot-consistent rendering;
- a disposable cursor cache is required;
- external state changes cannot interrupt a model request already in flight.

## Rejected alternatives

- fixed `cadence: turn`: wasteful and accumulative;
- model-maintained context file: stale, racing shadow authority;
- agent discovers commands each session: inconsistent and expensive;
- MCP subscription alone: invalidates resources but does not inject model context.
