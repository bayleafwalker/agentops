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
- `lock.verify_dispatch_lock` to verify vendored source bytes at startup.

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
select a provider or model and does not interpret provider output. It does not
perform automatic provider failover. A future failover policy must wait for a
qualified attempt boundary and be explicit about retries and spend.

The current extraction is the runtime and process-supervision slice. The
V2.1 scheduler and project integration loop remain in their project adapter
until each behavior has an equivalent contract and parity coverage.
