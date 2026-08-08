---
doc_id: live-session-completion-alert-plan
status: proposed
last_verified: 2026-08-08
tracker_item: agentops#2115
supersedes: null
---

# Live session-completion alert implementation plan

## Outcome

Deliver prompt, replayable session-completion alerts without coupling live
notification to the fresh reconciler, periodic scribe, `outctl`, or browser
database access. The governing design is
[`live-session-completion-alert-architecture.md`](live-session-completion-alert-architecture.md).

This is cross-repository work. AgentOps owns sequencing and shared contracts;
ActionQ owns the producer and served completion stream; AgentOps owns alert
consumption and cockpit presentation; Appservice owns any runtime enablement.

## Backlog registration

The canonical cross-repository ledger is
[`opencode-dispatch-lifecycle-hardening.md`](opencode-dispatch-lifecycle-hardening.md).
This implementation plan maps to the following Sprintctl records:

| Package | Item |
|---|---|
| P0 contract and semantics | `agentops#2119` |
| P1 producer outbox | `actionq#2122` |
| P2 direct/daemon/OpenCode parity | `actionq#2121` |
| P3 durable observable session log | existing `actionq#2027` |
| P3 generic served transport | existing `vuoro#2028` |
| P4 consumer and delivery ledger | `agentops#2116` |
| P5 cockpit surface | `agentops#2120` |
| P6 optional wakeups/SSE | no item until its measurement entry gate passes |
| P7 runtime enablement | separate future Appservice/operator tranche |

The umbrella `agentops#2115` closes only after the source gates and a separately
authorized live pilot produce the required durable evidence. Existing ActionQ
and Vuoro observable-resource items are reused rather than duplicated.

## Baseline and gap

Already present:

- ActionQ's harness-neutral wrapper writes `session-capsule/v1`, supports clean
  and inferred ends, and preserves the wrapped command's outcome on recorder
  failure.
- ActionQ's daemon has one coordinator launch seam for harness adapters,
  including OpenCode.
- AgentOps has capsule/proposal schemas, a fresh post-session reconciler, a
  periodic scribe, and cockpit reconciliation views.
- Cockpit v1 deliberately uses polling and defers PostgreSQL notification and
  SSE.

Missing:

- a small completion-event contract distinct from the capsule;
- a persistent producer stream identity and durable wrapper outbox;
- daemon/direct/OpenCode integration with one completion primitive;
- idempotent served ingest and replay reads;
- an always-on consumer, alert policy, delivery ledger, and operator alert
  surface; and
- end-to-end outage/replay evidence.

## Work packages

### P0 — ratify semantics and ownership

Owner: AgentOps, with ActionQ review.

Deliverables:

1. Add `session.completion-observed/v1` JSON schema, example, and dependency-free
   semantic validation beside the session-mechanization contracts.
2. Add the event to the state/event/command matrix as an ActionQ-owned
   observation and distinguish it from capsule reconciliation.
3. Resolve the five open questions in the architecture outline, especially
   alert timing and the first delivery route.
4. Freeze privacy rules, reason codes, additive-versioning behavior, and
   idempotency invariants.

Gate:

- schema rejects secrets/raw content, invalid terminal combinations, duplicate
  or non-positive stream positions, and unstable identity examples;
- ActionQ and AgentOps docs agree on ownership and event timing; and
- no runtime implementation begins while the event means both harness exit and
  action settlement.

Rollback: documentation/schema only; supersede the proposed contract before a
producer ships.

### P1 — ActionQ durable producer outbox

Owner: ActionQ. This touches session lifecycle/retry/recovery risk surfaces and
requires focused state-protocol review.

Deliverables:

1. Add a host-persistent outbox with one durable `origin_stream_id`, atomic
   monotonic sequence allocation, stable event IDs, payload digests, retry
   state, acknowledgements, and quarantine.
2. Refactor wrapper completion into one internal record primitive that places
   the capsule first and queues its completion pointer second.
3. Recover stale markers and completed capsules missing an outbox row without
   creating duplicate logical events.
4. Add CLI health/status/replay inspection that does not expose credentials or
   payload secrets.
5. Bound retention and disk growth; acknowledged compaction must be explicit
   and testable.

Verification histories:

- crash before and after capsule rename;
- crash before, during, and after outbox commit;
- restart after send but before acknowledgement persistence;
- duplicate recovery scan;
- sequence allocation under concurrent wrapper completions;
- payload digest mismatch quarantine;
- disk-full/permission failure preserves wrapped exit code and emits a visible
  recorder-health failure; and
- retention never removes unacknowledged or quarantined records.

Gate: all histories pass on a disposable state directory, and a generated
event validates with the canonical AgentOps validator.

Rollback: disable delivery while retaining the local outbox and capsules.

### P2 — direct, daemon, and OpenCode emission parity

Owner: ActionQ.

Deliverables:

1. Wire `actionq-session-wrap` to P1 for direct sessions.
2. Wire the daemon's coordinator child-lifecycle seam to the same primitive;
   do not add publishers to individual harness adapters.
3. Map child start failure, ordinary failure, timeout, cancellation,
   usage-limit, success, and inferred crash to the frozen terminal vocabulary.
4. Prove OpenCode uses coordinator publication after child exit and that the
   contained worker receives no ingest credential.
5. Document the wrapper as the supported entry point for a human launching
   OpenCode directly.

Verification matrix:

| Path | Success | Non-zero | Timeout/cancel | Crash recovery | Duplicate replay |
|---|---:|---:|---:|---:|---:|
| Direct wrapped command | required | required | required | required | required |
| Daemon fake harness | required | required | required | required | required |
| Daemon OpenCode adapter | required | required | required | required | required |

The OpenCode row first uses a fake executable that captures argv/environment.
A real disposable OpenCode invocation is a separate operational gate because
the existing adapter documentation records that its local CLI shape was not
previously smoke-verified.

Gate: each logical session produces exactly one stable completion event and at
most one capsule ref, while the child/session outcome remains unchanged by
recorder or network failure.

Rollback: per-launch-path feature flags leave capsule production intact and
stop new outbox enqueue.

### P3 — served ActionQ completion log

Owner: ActionQ for semantics and storage; Vuoro only exposes catalog transport.

Deliverables:

1. Implement idempotent completion ingest with a credential narrower than
   queue claim/settlement authority.
2. Persist server events append-only with uniqueness on `event_id` and stream
   position plus digest-consistency checks.
3. Return durable acknowledgements that the producer can persist before
   compaction.
4. Implement cursor-based list/replay and health operations in the served
   operation catalog.
5. Define retention, pagination bounds, authorization, and cursor invalidation
   behavior.

Verification histories:

- same event retried many times;
- same stream position with a different digest;
- out-of-order and gapped stream positions;
- producer timeout after server commit;
- consumer disconnect across page boundaries;
- retention boundary and stale cursor response; and
- read/ingest credentials cannot enqueue, claim, renew, settle, or cancel an
  action.

Gate: producer outage/recovery drill drains a backlog without loss or duplicate
server facts; replay reconstructs the accepted ordered stream.

Rollback: stop ingestion, preserve server records and producer backlog.

### P4 — AgentOps consumer and alert ledger

Owner: AgentOps.

Deliverables:

1. Add a cursor reader with a durable inbox and server-cursor checkpoint.
2. Implement explicit policy evaluation and terminal outcomes: delivered,
   suppressed, pending, or dead-lettered.
3. Add per-route delivery receipts keyed by `(event_id, route_id)` and retry
   without re-evaluating immutable event facts.
4. Start with bounded short polling; expose lag and route health.
5. Implement the ratified first route. If the first route is cockpit-only,
   "delivered" means durably projected for cockpit, not that a browser tab was
   open.

Verification histories:

- duplicate pages and consumer restart;
- server gap repaired by replay;
- policy change applies prospectively unless an explicit replay is requested;
- one route fails while another succeeds;
- quiet-hours suppression and later release if configured;
- poison event isolation; and
- no alert template renders prohibited fields.

Gate: a recorded server completion reaches its configured alert route within
the healthy latency target, and every input has a queryable consumer outcome.

Rollback: stop the consumer; its cursor and ActionQ replay log permit restart.

### P5 — cockpit alert surface

Owner: AgentOps.

Deliverables:

1. Add a read endpoint for recent alerts, pending deliveries, acknowledgement
   state, and source lag.
2. Add a compact operator alert panel with terminal kind, project, harness,
   completion age, and safe links to existing detail surfaces.
3. Poll the AgentOps projection for v1, respecting background-tab throttling.
4. If acknowledgement is included, persist it as AgentOps operator state; it
   must not mutate ActionQ or Sprintctl.
5. Show explicit degraded states for producer backlog, server unavailability,
   consumer lag, and route failure.

Gate: frontend tests cover deduplication, ordering, acknowledgement,
degradation, and redaction; `npm test` and `npm run build` pass.

Rollback: hide the panel/route without stopping the producer or consumer.

### P6 — optional wakeups and SSE

Owners: ActionQ for database wake hints; AgentOps for consumer/cockpit stream.

Entry gate: measure that polling latency or load violates the agreed target.
Do not implement this package merely to call the system event-driven.

Possible upgrades:

1. PostgreSQL `LISTEN/NOTIFY` wakes the ActionQ cursor reader. The durable log
   and cursor replay remain the correctness path.
2. AgentOps SSE carries one-way alert projection updates to browsers. Reconnect
   uses a durable cursor or a normal list refresh.

Gate: deliberately drop notifications and SSE connections; all events still
appear exactly once in the projection after cursor repair.

Rollback: disable wakeups/SSE and return to polling without a data migration.

### P7 — runtime enablement and evidence

Owner: Appservice/operator under separate mutation authority.

Deliverables:

1. Provision narrow ingest/read/route credentials, persistent state, network
   policy, and resource limits.
2. Enable one producer host and one non-critical project first.
3. Run a success, failure, OpenCode, producer-offline, consumer-offline, and
   route-offline drill.
4. Record p50/p95 completion-to-alert latency, backlog recovery time, duplicate
   suppression, and privacy inspection results.
5. Expand only after the pilot's retention and alert-volume assumptions are
   observed rather than guessed.

Gate: pilot evidence meets the latency target, no event is lost, duplicates do
not cause duplicate operator deliveries, and credentials fail closed outside
their narrow operations.

Rollback: disable runtime flags and consumers; retain replayable records for
the documented retention period.

## Dependency sequence

```text
P0 contract
   |
   v
P1 producer outbox -> P2 launch-path parity -> P3 served log
                                                |
                                                v
                                      P4 consumer/alerts -> P5 cockpit
                                                |              |
                                                +------v-------+
                                                       P6 optional push
                                                |
                                                v
                                           P7 runtime pilot
```

P1 and P4 may prototype against the frozen P0 fixtures, but neither may claim
end-to-end completion before P3. P5 may use fixture data while P4 is built.
Runtime deployment is not implied by completing source work.

## Acceptance criteria

The feature is complete only when:

1. direct and daemon/OpenCode sessions emit the same validated contract;
2. a producer or consumer restart loses no acknowledged logical event;
3. duplicate delivery produces one server fact and one receipt per alert route;
4. the alert path meets the agreed latency target in the healthy pilot;
5. producer, server, consumer, and route backlogs are separately visible;
6. notification loss is repaired through durable cursors;
7. alerts contain no prohibited content or authority credentials;
8. session completion, action settlement, reconciliation proposal, proposal
   acceptance, and Sprintctl completion remain distinct facts in UI and docs;
9. disabling alerts does not disable capsule/scribe correctness; and
10. no implementation adds completion semantics to `outctl` or the generic
    Vuoro client.

## Required durable evidence

Source tests and fixture packets live in the owning repositories. Runtime
receipts should record immutable Git commits plus auditctl evidence IDs and
Sprintctl work-item refs. Large outage/replay logs may remain host-persistent
under `_artifacts`, but closure must name the source host and path and must not
describe those files as durable-authoritative.
