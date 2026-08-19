# Implementation Plan

## Wave 0 — Compatibility and inventory

- Pin minimum supported Claude Code and Codex versions.
- Capture current hook event schemas in compatibility tests.
- Locate the existing queue-row binding resolver, repo UUID, cursor cache, served API module, and mutation paths.
- Inventory all sprintctl/Vuoro mutation entry points: CLI, HTTP, MCP, worker internals, maintenance jobs.

**Gate:** no unknown write path remains that can silently omit revision preconditions.

## Wave 1 — Authority revisions and CAS

- Define opaque revision token format per resource.
- Add atomic `if_revision` enforcement to task/claim mutations.
- Return typed missing-precondition and conflict errors.
- Return previous/new revision and event ID on success.
- Add idempotency key handling where absent.

**Gate:** an integration test bypassing all hooks cannot commit a stale mutation.

## Wave 2 — Provider substrate

- Add provider registry in code/config owned by the served substrate.
- Implement binding, task, host, and workspace validators.
- Implement bounded structured renderers.
- Add snapshot-at-revision or validate/render/revalidate consistency.
- Add disposable cursor access through the existing cursor cache.

**Gate:** unchanged validation performs no renderer call; cursor deletion causes duplicate output only.

## Wave 3 — Served contracts

- Implement projection endpoint.
- Implement mutation precheck endpoint.
- Implement post-mutation observation endpoint.
- Implement cursor invalidation endpoint.
- Add authz binding dispatch identity to provider/resource access.
- Add hard output budgeting and field allowlists.

**Gate:** contract tests validate all JSON Schemas and failure modes.

## Wave 4 — Hook adapter and harness wiring

- Package the local command adapter under a stable libexec path.
- Add Claude and Codex hook configurations.
- Pass dispatcher binding via environment.
- Add `SubagentStart` and compact-session coverage.
- Add Claude-only cwd/fallback-file invalidation without configuring a context-only `WorktreeCreate` hook.

**Gate:** both harnesses pass the same acceptance sequence with no manual context paste.

## Wave 5 — Non-blocking pilot

- Enable session/subagent/prompt/post-mutation projection.
- Keep mutation precheck advisory while authority CAS already rejects conflicts.
- Measure latency, bytes, unchanged rate, duplicate rate, and renderer frequency.
- Tune provider budgets and semantic fields.

**Gate:** zero spill events, acceptable latency, and no binding collisions.

## Wave 6 — Enforced precheck

- Enable fail-closed precheck for recognized mutations.
- Verify conflict feedback includes current revision and projection.
- Add dashboards/alerts for service availability and rejection anomalies.

**Gate:** stale mutations are blocked at both hook and authority boundaries; service outage behavior matches policy.

## Wave 7 — Optional MCP resources

Only after the hooks are stable:

- expose read-only resource templates for task/dispatch context;
- add update subscriptions for cache invalidation where clients support the 2026-07-28 protocol;
- do not assume subscriptions inject context automatically.
