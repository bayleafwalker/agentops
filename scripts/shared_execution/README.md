# Shared execution mechanics

This package extracts the V2.1 local runtime and child-process supervision
used by project dispatch adapters. Consumers vendor the package and record its
source digest in a project `dispatch.lock`. The lock is verified before a
consumer starts its dispatcher.

The main imports are:

- `runtime.Store` for the V2.1 SQLite task/event/meta tables, transitions,
  journaling, and single-driver lock;
- `runtime.atomic`, `runtime.read`, `runtime.git`, and `runtime.alive` for the
  existing durability and process identity behavior;
- `process.run_child` and `process.stop_attempt` for child process groups,
  timeout cleanup, and restart cleanup;
- `protocol.RunEnvelope`, `AttemptEnvelope`, `EventEnvelope`, and `EvidenceRef`
  for versioned JSON identities and evidence references;
- `lock.verify_dispatch_lock` to verify vendored source bytes at startup;
- `provider.decide_failover` to check a caller-supplied ordered binding snapshot
  against explicit role, harness-command, data-class, quota-reset, usage, and
  cost constraints.
- `governance.InterpretationGovernance` to append immutable result and
  interpretation revisions, disposition attestations, and dispute-driven
  reconciliation intents to the existing event log.

## Authority and policy boundary

The local SQLite journal, process receipts, and `dispatch.lock` are host-local
execution state. They are a recoverable cache; they do not grant permission to
run, cancel, integrate, accept, or publish work. Sovite remains the authority
for execution leases, fencing, cancellation, and authoritative attempt
journaling. Run and attempt identities are supplied by that owner or by the
project adapter; this package validates and records them without minting
authority.

Project adapters retain task eligibility, requirements, acceptance tests,
scorecards, repo scope, and integration policy. Sovite owns eligible providers,
role/model bindings, data rules, and cost constraints. This package does not
select a provider or model and does not interpret provider output. Failover
checks are disabled when the feature flag is absent or false. When enabled by
the consumer, the helper checks only the next binding in the operator-provided
order. It requires explicit eligibility, role, harness-command and data-policy
references, explicit subscription/API billing mode, billing and budget
enforcement references, known coordinator/owner attempt usage, and a known
remaining budget. Paid overage must be explicitly false. Quota exhaustion also
requires a known future reset. Those references remain caller-supplied claims;
the helper validates a prequalified snapshot's shape and bounds but does not
mint or verify Sovite authority or qualification.

The consumer must reconcile the previous attempt receipt and preserve the
contract and workspace before creating a new attempt. It must record the
provider change durably and link the new attempt to its predecessor. Paid
upgrades are refused unless the next attempt's explicit ceiling is no higher
than the current binding's ceiling and fits the remaining budget. The helper
does not enable an unqualified binding or authorize fallback by itself.

The current extraction is the runtime and process-supervision slice. The
V2.1 scheduler and project integration loop remain in their project adapter
until each behavior has an equivalent contract and parity coverage.

Retrospective interpretation governance is separate from execution state.
`record_result_revision` and `record_interpretation_revision` bind immutable
source and evidence references, digests, provenance, and revision dependencies.
`attest_disposition` appends `pending`, `acknowledged`, `ratified`, `disputed`,
or `superseded` observations without replacing earlier attestations; superseded
observations name an existing replacement revision of the same kind. The actor
reference is attribution, not an authorization check; the caller's owner
contract remains responsible for identity and authority. A dispute
appends an advisory reconciliation intent listing the transitive revisions to
reevaluate and their original evidence references. The intent is an immutable
snapshot; `downstream_impacts` computes the current dependency closure, including
revisions added later. It does not create an owner work item, change a task
state, block unrelated work, or gate integration.
Project adapters retain risk meaning and external-effect authorization.
