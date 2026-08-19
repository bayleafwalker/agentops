# Implementer Handoff

## Objective

Add revision-gated volatile context projection to the existing agent substrate and wire it into Codex and Claude Code hooks.

A successful implementation provides current task, binding, host, and workspace observations without repeated command pastes or agent-maintained shadow state. Unchanged providers inject zero bytes. Stale authoritative mutations are rejected deterministically.

## Hard constraints

1. **Do not create a new authority.** Binding resolves from the dispatcher-owned queue row. Task state and revisions resolve from sprintctl or the existing authoritative event stream.
2. **Do not create a public `ctx` CLI.** Add projection verbs/endpoints to the existing served substrate. A small local hook adapter is permitted and expected for Codex compatibility.
3. **CAS belongs in the mutation API.** Every relevant mutation requires `if_revision` or an equivalent opaque precondition. Hooks are defense in depth and user/model feedback, not the only enforcement.
4. **Agents never write projections.** They may append attributed claims to the authoritative log, subject to the same revision precondition.
5. **Cursor state is disposable.** It records the last emitted provider revision per consumer. Deleting it may cause duplicate context, never stale authority or data loss.
6. **Do not log raw projected content by default.** Log revisions, byte counts, timing, provider IDs, and result classes.
7. **Budget before the harness.** Produce semantically bounded output below the smaller practical hook limit. Never rely on harness head-and-tail spill behavior.
8. **Treat provider values as untrusted data.** Escape and structure them. A task title is not an instruction merely because somebody put “ignore all previous rules” in Jira with admirable confidence.

## Required architecture

```text
dispatcher env: VUORO_DISPATCH_ID
              │
              ▼
existing binding resolver ──► queue row / repo UUID / task ID
              │
              ▼
provider validator ── cheap revision/watermark/ETag
              │ changed
              ▼
provider renderer ── bounded structured projection at revision
              │
              ▼
disposable consumer cursor ── last emitted revision
              │
              ▼
served projection response
              │
              ▼
local hook adapter ── harness-specific JSON
```

Mutation path:

```text
agent tool call with if_revision
              │
     PreToolUse UX guard
              │
              ▼
authoritative mutation API CAS ── reject stale/missing precondition
              │ success
              ▼
new revision returned in result
              │
     PostToolUse projection
              ▼
new revision injected immediately
```

## Implementation order

1. Add/verify opaque revisions and atomic compare-and-swap at the task mutation authority.
2. Add provider validator and render interfaces with snapshot consistency.
3. Add disposable consumer cursors keyed by dispatch, harness, session, subagent, and provider.
4. Add served projection, mutation-validation, post-mutation, and invalidation endpoints.
5. Package the local hook adapter.
6. Enable non-blocking context hooks first.
7. Observe latency, bytes, render rate, and duplicate rate.
8. Enable mutation blocking only after authoritative CAS is proven independently.
9. Pilot on one repo and one dispatcher route before fleet rollout.

## Definition of done

Use `task/ACCEPTANCE_CRITERIA.md`. Do not mark complete based solely on unit tests or “hook fired” screenshots. The acceptance run must include two sessions sharing a worktree, a subagent, compaction, an external task revision change, a stale mutation, hook bypass, service outage, and rollback.
