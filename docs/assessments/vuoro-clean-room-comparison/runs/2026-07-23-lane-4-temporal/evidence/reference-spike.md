# Lane 4 — Temporal Durable-Execution Reference Spike

An isolated Temporal `1.29.1` auto-setup server backed by a disposable
PostgreSQL container accepted a small Python SDK `1.30.0` workflow over a
loopback-only gRPC port. The workflow used the locked `CR-02` corpus reference
and `BATCH-02` as its workflow ID.

With `WorkflowIDConflictPolicy.FAIL`, the first workflow started and completed
its activity receipt. A second start with the same workflow ID while the first
was still running raised `WorkflowAlreadyStartedError`.

```json
{"duplicate_start_rejected_while_running":true,"result":{"corpus_task":"CR-02","execution_receipt":"temporal-activity-completed"},"workflow_started":true}
```

This calibrates what an industrial durable runtime can provide at the execution
identity boundary. It does not establish R2 proof authority, a work-item state
model, R3 resume presentation, R6 identity or migration controls, operational
cost, or a migration recommendation.
