# Maintenance envelope v1

`maintenance-envelope/v1` freezes the exact, independently reviewed plan that
may be used during a bounded authority outage. It is an allowlist and evidence
contract, not a credential, claim, lease, approval, recovery grant, or command
executor. AgentOps owns this schema and validator only. Sprintctl owns any
future lifecycle capability, Vuoro owns released transport/composition, and
the deployment repository owns every operational mutation.

Validate an envelope with the dependency-free normative validator:

```bash
python templates/dispatch/scripts/validate_maintenance_envelope.py \
  --at 2026-08-02T20:00:00Z --step attest-backup \
  templates/dispatch/maintenance-envelope/example.json
```

Activation validation requires an explicit trusted evaluation time and exact
next step. It rejects evaluation before `not_before`, at or after `expires_at`,
stale start-gate evidence, late JIT observations, or bindings aimed at another
step. `--structural` is available for editor/CI checks, but makes no activation
readiness assertion and must never authorize execution.

The structural JSON Schema assists editors. Cross-field semantics are enforced
by the Python validator: exact repository bases and candidate commits,
contiguous steps, earlier-only dependencies, same-repository commit chaining,
closed path/command allowlists bound to canonical registry bytes and exact
argument vectors, independent passing reviews and publication receipts,
activation-time expiry,
forward-only abort policy, complete audit reconciliation, and the plan-1 zero
dependent-session/zero-normal-claim start gate.

Only `backup_name`, `backup_uid`, and `drain_boundary_utc` are just-in-time in
v1. Their definitions are required, source-specific, anchored, and each value
has an in-window observation, immutable evidence reference, and receipt. A
binding may be absent before its declared step, is mandatory at that step, and
remains mandatory for every later step; observations can never be later than
the activation evaluation. A JIT value cannot select a commit, operation, path, command,
review, actor, authority, image, schema, or rollback policy.

Recovery records remain separate. `observation` and `requested-command` may be
retained and reconciled later, but have `authority: none`; they cannot grant,
claim, approve, publish, reconcile, advance, or bind JIT state.
