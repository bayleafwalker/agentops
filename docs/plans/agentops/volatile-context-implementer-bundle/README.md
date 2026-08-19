# Revision-Gated Volatile Context — Implementer Bundle

This bundle turns the design discussion into a repository-ready implementation handoff for Codex and Claude Code.

The target is **volatile context without model-maintained memory**:

- the dispatcher supplies a stable binding identifier;
- authoritative stores expose cheap revision validators;
- a projector renders only providers whose revision changed;
- mutation APIs enforce optimistic concurrency at the authority;
- harness hooks inject changed observations and improve failure feedback;
- agents may append attributed claims, but never write projections.

## Recommendation

Implement this as a module on the existing served substrate, not as a new `ctx` product, database, or user-facing CLI. Install one small local **hook adapter** because Codex currently runs command hooks only. The adapter posts hook events to the served projection API and translates the response into each harness's hook JSON.

The hook is not the final correctness boundary. Every authoritative mutation must itself require an expected revision and reject stale writes. Shell hooks are useful guardrails; shell parsing is not a lock manager, however much regex may wish otherwise.

## What is included

- architecture and ADRs;
- API and projection contracts;
- current Claude Code and Codex hook maps;
- sample harness configurations;
- JSON Schemas;
- a dependency-free Python reference implementation;
- unit and integration-oriented tests;
- implementation backlog, acceptance criteria, rollout, rollback, and metrics.

## Explicit non-goals

- no new durable memory store;
- no agent-written “current context” file;
- no polling renderer that pastes the same snapshot every turn;
- no new public `ctx` CLI;
- no reliance on hooks as the sole concurrency control;
- no raw secrets, credentials, or unbounded logs in injected context;
- no automatic MCP rollout merely to transport one projection.

## Important compatibility corrections

The supplied design was directionally right, but current harness behavior changes four implementation details:

1. Current Codex supports `additionalContext` on `PreToolUse` as well as `PostToolUse`.
2. `PostCompact` is not the portable reinjection hook. Both harnesses still expose `SessionStart` with `source=compact`; use that for context reinjection. `PostCompact` is useful for side effects and observability.
3. Claude Code's `WorktreeCreate` hook replaces default worktree creation and must return the worktree path. Do not install it merely to invalidate workspace context.
4. Claude Code can call HTTP and MCP handlers directly, but Codex currently executes command handlers only. A tiny local adapter remains the cross-harness denominator.

See `docs/source-verification.md` for the checked behavior and sources.

## Start here

1. Read `IMPLEMENTER_HANDOFF.md`.
2. Adopt the contracts in `docs/contracts.md` and `schemas/`.
3. Implement CAS in the authoritative mutation path before enabling blocking hooks.
4. Run the reference tests:

```bash
cd reference
python -m unittest discover -s tests -v
```

5. Validate the full bundle:

```bash
./scripts/validate-bundle.sh
```

## Bundle status

The reference code is intentionally substrate-neutral. The implementer must replace the fake task provider and HTTP paths with the existing sprintctl/Vuoro served interfaces and cursor cache. The bundle does not guess private table names or undocumented command shapes.
