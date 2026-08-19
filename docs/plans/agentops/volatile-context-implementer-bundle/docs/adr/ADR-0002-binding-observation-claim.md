# ADR-0002: Separate Binding, Observation, Claim, and Cursor

- Status: proposed
- Date: 2026-08-17

## Decision

Use four explicit categories:

- binding is written by the dispatcher and resolved from the queue row;
- observation is rendered by the projector and injected as current data;
- claim is appended by an attributed actor to the authoritative event log;
- cursor is disposable projector bookkeeping.

Agents may append claims. Agents may not write projections or binding records.

## Rationale

A two-way binding-versus-memory distinction incorrectly implies that agents never write state and conflicts with scribe/claim workflows. The four-way taxonomy makes authority and lifetime explicit.

## Consequences

- projections can be freely rebuilt;
- claims remain auditable;
- deleting cursors cannot delete work;
- hand-start fallback files remain identifiers-only.
