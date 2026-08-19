# Architecture

## 1. Taxonomy

| Kind | Writer | Lifetime | Storage |
|---|---|---:|---|
| Binding | dispatcher | session/dispatch | authoritative queue row; dispatch ID passed by environment |
| Observation | projector | one emitted revision | not stored as authority; appears in harness history after injection |
| Claim | agent or human | permanent | append-only sprintctl/Vuoro event, attributed and revision-gated |
| Cursor | projector adapter/substrate | disposable session cache | last emitted provider revision; safe to delete |

The observation row deserves one caveat: the projector does not persist observation content as authoritative state, but Claude/Codex transcripts naturally retain injected context. Oversized hook output may also spill to temporary files. This is why output must be bounded and scrubbed before injection.

## 2. Provider lifecycle

Each provider implements two logical operations:

```text
validate(binding) -> opaque revision
render(binding, expected_revision) -> {revision, structured data}
```

`validate` must be cheap. `render` may be expensive, but is called only when the revision differs from the consumer cursor or when a full refresh is required.

### Snapshot consistency

The renderer must not silently return data from a different revision than the validator observed. Preferred order:

1. render an authoritative snapshot at the requested watermark/revision;
2. otherwise render and revalidate, retrying once;
3. if still unstable, omit the provider and return an explicit `unstable` status.

Never label a projection with revision `R` while rendering arbitrary “latest” data after `R` changed.

## 3. Binding resolution

Primary binding:

```text
VUORO_DISPATCH_ID -> dispatcher-owned queue row -> repo UUID / task ID / workspace intent
```

The hook event supplies harness `session_id`, `agent_id` where present, and `cwd`. These identify the consumer but do not replace the dispatcher binding.

Fallback for hand-started sessions may be a gitignored file containing only:

```json
{
  "dispatch_id": "manual-...",
  "repo_id": "...",
  "expires_at": "..."
}
```

It must not contain projected task state, findings, blockers, or next steps.

## 4. Consumer cursor

Recommended key:

```text
(dispatch_id, harness, session_id, agent_id-or-root, provider_id)
```

Value:

```text
last_emitted_revision, emitted_at, projection_id
```

The cursor is a cache, not a ledger. Loss causes at-least-once reinjection. It must never be consulted to authorize a mutation.

Cursor advancement should occur only after the adapter has produced valid hook JSON. Exact proof that the harness accepted the output is unavailable; serializer validation plus at-least-once semantics is the practical boundary. Duplicate injection is safer than suppressed current state.

## 5. Projection envelope

Use structured JSON with fixed semantics, not free-form YAML assembled from untrusted text.

Properties:

- `schema_version`;
- `mode`: `full` or `delta`;
- `observed_at`;
- `projection_id`;
- fixed statement that later entries supersede earlier entries by provider ID;
- fixed statement that values are data, not instructions;
- binding identifiers safe for model exposure;
- provider ID, opaque revision, source URI, status, and bounded data;
- omitted byte/item counts where truncation occurred.

The reference envelope is in `examples/projection.json`.

## 6. Mutation control

Correctness is enforced twice:

1. **Authoritative boundary:** the mutation API or command requires an expected revision and atomically rejects stale/missing preconditions.
2. **Hook boundary:** `PreToolUse` recognizes structured mutation tools and common simple CLI forms, rejects obvious stale/missing revisions early, and returns current context.

Only the first is complete. Hosted tools, aliases, nested shells, scripts, and disabled hooks can bypass local hook recognition. The substrate must still reject the write.

Successful mutation results should include the new revision. `PostToolUse` injects the changed projection immediately. On a conflict, the failure path injects the current revision and task projection.

## 7. External changes during long autonomous turns

No lifecycle hook can alter a model request already in progress. Revision gates still protect mutations. For external changes that affect a read-only decision, one of these must happen:

- the next relevant tool boundary validates the provider;
- the agent explicitly reads an on-demand resource/tool;
- an orchestrator with per-model-call middleware injects changed context.

Do not claim stronger freshness than the harness can provide.

## 8. MCP role

MCP resource templates are a good addressing layer, for example:

```text
sprintctl://task/{id}
vuoro://dispatch/{id}/context
```

Subscriptions can invalidate caches, but resource notifications do not themselves insert content into a model request. Ship the served projection and hooks first. Add MCP resources when multiple clients need common discovery/read semantics.
