# Observability

## Metrics

Recommended Prometheus-style metrics:

```text
agent_context_requests_total{event,harness,mode,result}
agent_context_provider_validations_total{provider,result}
agent_context_provider_renders_total{provider,result}
agent_context_provider_validation_seconds{provider}
agent_context_provider_render_seconds{provider}
agent_context_projection_bytes{event,harness}
agent_context_projection_providers{event,harness}
agent_context_cursor_hits_total{provider}
agent_context_cursor_misses_total{provider}
agent_context_cursor_duplicates_total{provider}
agent_context_truncations_total{provider,reason}
agent_context_mutation_precondition_rejections_total{provider,reason}
agent_context_hook_adapter_seconds{event,harness}
agent_context_hook_adapter_errors_total{event,harness,class}
```

## Structured events

Record metadata such as:

```json
{
  "projection_id": "...",
  "dispatch_id_hash": "...",
  "harness": "codex",
  "event": "UserPromptSubmit",
  "providers": [{"id": "task", "revision": "task:18422", "bytes": 1320}],
  "total_bytes": 1648,
  "duration_ms": 41,
  "result": "emitted"
}
```

Do not log raw projected content by default. Hash or otherwise pseudonymize identifiers where central telemetry does not need direct joinability.

## Pilot questions

The pilot should answer:

1. What percentage of user turns emit zero context?
2. How often does a validator change without a render-worthy semantic change?
3. What is the byte/token overhead per session compared with static task pastes?
4. How often are mutations rejected for missing versus stale revisions?
5. Are stale conflicts genuine concurrent updates or cursor/adapter bugs?
6. Do subagents receive the intended binding and task revision?
7. Does compaction restore current context without duplicate accumulation becoming material?
8. What happens during served endpoint outage?

## Initial targets

- unchanged delta rate: greater than 80% after session start;
- p95 delta hook latency: under 150 ms locally;
- hard projection size: at or below 7,500 bytes;
- harness spill events: zero;
- stale mutation accepted when hooks bypassed: zero;
- binding collision across sessions/worktrees: zero.
