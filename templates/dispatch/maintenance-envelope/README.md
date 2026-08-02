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
  templates/dispatch/maintenance-envelope/example.json
```

The structural JSON Schema assists editors. Cross-field semantics are enforced
by the Python validator: exact repository bases and candidate commits,
contiguous steps, earlier-only dependencies, same-repository commit chaining,
closed path/command allowlists, independent passing reviews, bounded expiry,
forward-only abort policy, complete audit reconciliation, and the plan-1 zero
dependent-session/zero-normal-claim start gate.

Only `backup_name`, `backup_uid`, and `drain_boundary_utc` are just-in-time in
v1. Their definitions are required, source-specific, anchored, and bound before
an exact step. A JIT value cannot select a commit, operation, path, command,
review, actor, authority, image, schema, or rollback policy.

Recovery records remain separate. `observation` and `requested-command` may be
retained and reconciled later, but have `authority: none`; they cannot grant,
claim, approve, publish, reconcile, advance, or bind JIT state.
