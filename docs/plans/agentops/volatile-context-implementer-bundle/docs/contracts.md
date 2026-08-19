# Contracts

The JSON Schemas in `schemas/` are normative for the reference bundle. Field names may be adapted to existing service conventions, but the semantics should remain.

## 1. Projection request

`POST /v1/agent-context/project`

```json
{
  "schema_version": "1",
  "harness": "codex",
  "event": "UserPromptSubmit",
  "mode": "delta",
  "dispatch_id": "dispatch-123",
  "repo_id": "repo-uuid",
  "session_id": "harness-session",
  "agent_id": null,
  "cwd": "/projects/dev/repo",
  "provider_ids": ["binding", "task", "host", "workspace"]
}
```

The service resolves binding from `dispatch_id`. Client-supplied `repo_id` and `cwd` are validation hints, not authority.

### Modes

- `full`: render selected providers regardless of cursor; used at session/subagent start and after compaction.
- `delta`: run validators and render only changed providers; used at user prompt and post-mutation boundaries.

A successful unchanged delta returns HTTP 200 with `context: null` and an empty `providers` array. The hook prints nothing.

## 2. Projection response

```json
{
  "schema_version": "1",
  "projection_id": "019...",
  "mode": "delta",
  "observed_at": "2026-08-17T18:00:00Z",
  "context": "{...bounded projection envelope...}",
  "providers": [
    {
      "id": "task",
      "revision": "task:18422",
      "status": "ok",
      "bytes": 1320,
      "truncated": false
    }
  ],
  "total_bytes": 1648
}
```

`context` is already formatted and bounded by the service. The adapter must not append raw command output.

## 3. Mutation validation

`POST /v1/agent-context/mutations/validate`

```json
{
  "schema_version": "1",
  "harness": "claude-code",
  "dispatch_id": "dispatch-123",
  "session_id": "session-123",
  "agent_id": null,
  "provider_id": "task",
  "resource_id": "TASK-42",
  "expected_revision": "task:18421",
  "tool_name": "mcp__sprintctl__append_claim",
  "tool_input": {
    "task_id": "TASK-42",
    "if_revision": "task:18421"
  }
}
```

Response on stale precondition:

```json
{
  "schema_version": "1",
  "allowed": false,
  "reason": "Task revision changed: expected task:18421, current task:18422",
  "current_revision": "task:18422",
  "context": "{...current bounded task projection...}"
}
```

The hook response improves feedback. The actual mutation endpoint must independently perform the same atomic compare-and-swap.

## 4. Post-mutation observation

`POST /v1/agent-context/mutations/observe`

The request carries the same binding/session/tool identity and, where available, the mutation result's `new_revision`. The service renders the affected provider and advances only that provider cursor.

If the mutation output does not expose a revision, the service validates the provider and renders on change. Prefer adding `new_revision` to the mutation result rather than re-querying.

## 5. Invalidation

`POST /v1/agent-context/invalidate`

Used for Claude-only lifecycle events such as `CwdChanged` or a watched fallback binding file. Invalidation clears relevant disposable cursors; it does not alter task/binding state.

```json
{
  "dispatch_id": "dispatch-123",
  "harness": "claude-code",
  "session_id": "session-123",
  "agent_id": null,
  "provider_ids": ["workspace"]
}
```

## 6. Authoritative mutation contract

Every mutation to a revisioned resource must support:

```text
resource identity + expected revision + attributed actor + idempotency key
```

Recommended response:

```json
{
  "result": "applied",
  "previous_revision": "task:18422",
  "new_revision": "task:18423",
  "event_id": "..."
}
```

Recommended conflict response: HTTP 409 or an equivalent typed CLI failure with the current revision. Missing preconditions should be HTTP 428 where suitable, or a typed CLI usage error. Do not silently interpret an omitted revision as “latest”.
