---
doc_id: live-session-completion-alert-architecture
status: ratified-contract
last_verified: 2026-08-08
tracker_item: agentops#2115
supersedes: null
---

# Live session-completion alert architecture

## Decision summary

Add a separate, observation-only completion stream at the ActionQ/AgentOps
dispatch boundary. ActionQ produces completion observations for every wrapped
session, including direct and OpenCode-backed sessions. A producer-owned
durable outbox retries delivery. AgentOps consumes the stream, applies alert
policy, records idempotent delivery outcomes, and presents alerts through the
operator surface.

This is deliberately separate from post-session reconciliation:

- `session-capsule/v1` remains the rich, immutable input to the fresh
  reconciler and periodic scribe;
- `session.completion-observed/v1` is the small, prompt notification that a
  terminal session fact exists;
- the reconciler does not subscribe, page, or become an alert worker; and
- the cockpit is a consumer, not a session-lifecycle or delivery authority.

The public Vuoro client remains transport-only. `outctl` is not an owner or a
required hop in this design.

## Scope and non-goals

In scope:

- a completion observation contract;
- wrapper emission for direct commands and daemon-launched harnesses,
  explicitly including OpenCode;
- crash-safe local persistence, retry, replay, and dead-letter visibility;
- a served ActionQ ingest/read boundary;
- an AgentOps alert consumer and cockpit read surface; and
- latency, deduplication, privacy, degradation, and verification rules.

Not in scope:

- changing action, claim, lease, or Sprintctl item state;
- treating an alert as proof that reconciliation or acceptance succeeded;
- sending transcripts, prompts, secrets, or raw harness output;
- browser or consumer access to ActionQ tables;
- a cross-tool transaction between ActionQ and AgentOps;
- using Postgres `LISTEN/NOTIFY` as the durable record; or
- requiring SSE for the first correct release.

## Ownership boundary

| Concern | Owner | Rule |
|---|---|---|
| Session terminal fact, wrapper integration, producer stream identity | ActionQ | Session lifecycle state decides ownership. |
| Producer outbox, retry, replay, served ingestion | ActionQ | Delivery is part of publishing ActionQ-owned observations. |
| Cross-domain event schema | AgentOps, reviewed with ActionQ | AgentOps owns shared dispatch/exhaust contracts; ActionQ must be able to implement it without importing AgentOps runtime code. |
| Alert selection, routing, acknowledgement, delivery ledger | AgentOps | These are operator-policy and cross-domain projection concerns. |
| Cockpit alert UX | AgentOps | It reads the AgentOps alert projection and never writes ActionQ lifecycle state. |
| Deployment, credentials, network policy | Appservice | Added only in a separately authorized deployment tranche. |
| Generic served transport | Vuoro | Publishes owner operations without adding completion semantics. |

## Completion observation contract

Contract name: `session.completion-observed/v1`.

It is an **observation**, not an authority command. Delivery is at least once;
all identities required for idempotent consumption are mandatory.

| Field | Requirement |
|---|---|
| `schema_version` | Literal `session.completion-observed/v1`. |
| `event_id` | Stable UUID for this logical completion. Retries retain it. |
| `origin_stream_id` | Durable UUID for one producer installation/outbox stream. It must not be minted per session. |
| `origin_sequence` | Strictly increasing integer allocated transactionally within the producer stream. |
| `runtime_session_id` | Stable ActionQ session identity. |
| `attempt_id`, `action_id` | Nullable dispatch correlation identifiers; required when the session came from ActionQ dispatch. |
| `repo` | Portable `project` plus optional repository UUID. No absolute path. |
| `harness`, `model` | Harness identifier and nullable model descriptor. |
| `terminal` | `kind`, `exit_code`, `reason_code`, and `retryable`. `kind` is one of `succeeded`, `failed`, `cancelled`, `timed-out`, `usage-limited`, or `end-inferred`. |
| `started_at`, `completed_at`, `observed_at` | UTC timestamps. `completed_at` is the session fact; `observed_at` may be later after crash recovery. |
| `duration_ms` | Nullable non-negative duration. |
| `refs` | Non-secret references, including the `session-capsule/v1` artifact ref when it exists and optional ActionQ/Sprintctl/audit identifiers. |
| `evidence` | Bounded summary: dirty flag, commit count, verification pass/fail/error counts. No command output. |
| `privacy` | Explicit assertion that prompt, transcript, and raw output are absent. |

Contract invariants:

1. One logical terminal transition produces one `event_id`. A retry, replay,
   process restart, or consumer reconnect must not create a new identity.
2. The same `(origin_stream_id, origin_sequence)` always denotes the same
   payload digest. A mismatch is corruption and is quarantined.
3. A clean or inferred capsule may be referenced but is not embedded. Alert
   delivery must not wait for reconciliation.
4. The event reports what the wrapper observed. It does not claim that the
   action was settled, the Sprintctl item was completed, or verification was
   accepted unless a separate durable ref says so.
5. Unknown additive fields are tolerated within v1; changing meanings or
   required fields needs a new schema version.

## Producer and outbox architecture

ActionQ exposes one internal completion-recording primitive used by every
launch path. The CLI wrapper and daemon call the same primitive; harness
adapters do not publish independently.

```text
direct command ---- actionq-session-wrap --+
                                           |
daemon -> harness adapter -> child exit ---+-> finish session
                                                |
                                                +-> atomically write capsule
                                                +-> enqueue completion pointer
                                                        |
                                                        v
                                                ActionQ local outbox
                                                        |
                                                  served ingest/retry
```

The outbox is producer-owned, host-persistent state under the ActionQ state
directory. The implementation may use SQLite/WAL or an equivalently tested
transactional store. It must provide:

- a durable, installation-scoped `origin_stream_id` and transactional sequence
  allocation;
- payload plus digest, creation time, attempt count, next-attempt time, last
  error class, and acknowledgement state;
- atomic enqueue before a completion is reported as recorded;
- at-least-once retry with bounded exponential backoff and jitter;
- stable event identity across retries;
- explicit retention and compaction only after durable acknowledgement;
- a queryable dead-letter/quarantine state, never silent discard; and
- bounded disk behavior with visible health signals.

The wrapper's existing fail-open rule remains: recorder failure cannot replace
the wrapped command's exit code. Fail-open does not mean fail-invisible. It
must leave a local diagnostic, a health counter, and—when possible—a recovery
marker. Startup recovery scans stale markers and completed capsules and
backfills any missing deterministic completion event before normal delivery.

Ordering is guaranteed only within one origin stream. Consumers must not infer
global order across hosts.

## Direct and OpenCode emission

### Direct sessions

`actionq-session-wrap` records completion after the child exits and after its
capsule has been atomically placed. The CLI returns the child's result even if
enqueue or delivery fails. A direct invocation receives a stable local runtime
session ID and uses the installation's persistent stream identity.

### Daemon and OpenCode sessions

The daemon wraps its coordinator-owned child lifecycle, not each harness
adapter. This gives Claude, Codex, OpenCode, and future adapters identical
completion semantics and covers process-start failure, timeout, cancellation,
usage-limit classification, and crash inference.

OpenCode's positional-prompt invocation and contained worker identity do not
change the contract. Publication happens in the ActionQ coordinator after
`waitpid` and terminal classification; the worker never receives event-ingest
credentials. A direct `opencode` command is covered only when launched through
`actionq-session-wrap`, which should be the documented entry point.

## Served boundary

ActionQ should publish owner operations through the existing served operation
catalog rather than expose tables:

- `actionq.session-completion.ingest` — idempotently accept one producer event
  by `event_id` and stream position; return a durable acknowledgement;
- `actionq.session-completion.list` — cursor-based read for authorized
  consumers, ordered by the server's ingest cursor; and
- `actionq.session-completion.health` — stream lag, retry age, quarantine
  count, and last acknowledgement.

The durable server record is the source for replay. PostgreSQL notification
may later wake readers, but notification payloads are hints containing only a
cursor or event ID. Missed notifications must be repaired by cursor reads.

## Consumer and alert path

AgentOps runs a small completion-alert consumer with its own durable inbox
cursor and delivery ledger.

```text
ActionQ completion log -> cursor reader -> idempotent AgentOps inbox
                                           |
                                      policy evaluation
                                      /              \
                              alert delivery      suppressed record
                                      |
                              cockpit alert projection
```

The first correct version polls the served cursor at a short bounded interval.
This is a subscription-shaped consumer without pretending that the existing
post-completion reconciler is one. A later `LISTEN/NOTIFY` wakeup may reduce
latency while preserving polling as gap repair. Cockpit may continue polling
the AgentOps alert projection initially; SSE is a later one-way delivery
optimization.

Alert policy is configuration, not producer semantics. The initial policy
should support:

- alert on every terminal session, or only non-success terminal kinds;
- project, harness, actor, and dispatch/direct filters;
- severity mapping (`info`, `warning`, `critical`);
- coalescing repeated failures without losing individual event records;
- quiet hours and route selection; and
- acknowledgement as AgentOps operator state, never an ActionQ mutation.

Every evaluated event receives a terminal consumer outcome: delivered,
suppressed by named rule, delivery-pending, or dead-lettered. Delivery retries
reuse `(event_id, route_id)` as the idempotency key.

## Latency and degradation targets

- Target: p95 alert projection within 5 seconds of server ingestion for a
  healthy v1 deployment.
- Producer backlog age, server ingest lag, consumer cursor lag, oldest pending
  alert, and dead-letter counts are first-class metrics.
- If ActionQ ingest is unavailable, the producer outbox grows visibly and
  retries without blocking session exit.
- If AgentOps is unavailable, the ActionQ completion log retains replayable
  events and the consumer resumes from its last durable cursor.
- If an alert route is unavailable, only that delivery ledger backs up; the
  inbox cursor and other routes continue according to explicit fan-out rules.
- No component may equate an empty poll response with proof that no sessions
  completed while it was disconnected.

## Security and privacy

- Use a narrow producer credential that can ingest completion observations but
  cannot claim, settle, or enqueue actions.
- Use a read-only AgentOps consumer credential scoped to completion reads.
- Store no prompt, transcript, raw output, environment, token, secret, absolute
  worktree path, or claim proof in an event or alert.
- Treat operator routes as potentially external: message templates use the
  bounded event fields and links, never artifact contents.
- Record actor and delivery audit facts without broadening auditctl or cockpit
  into a queue authority.

## Ratified implementation decisions (AgentOps #2119)

1. The producer store is ActionQ-owned SQLite/WAL with `synchronous=FULL`.
   Sequence allocation and enqueue are one transaction. Compaction is allowed
   only for durably acknowledged rows; unacknowledged and quarantined rows are
   not age-pruned.
2. The durable server completion log is a distinct append-only ActionQ
   projection keyed by `event_id`, not the action terminal-event ledger.
3. The first operator route is cockpit-only. Delivery acknowledgement means
   durable insertion into the AgentOps cockpit projection, not browser receipt.
4. Producer acknowledgements, ActionQ server events, AgentOps inbox entries,
   and delivery receipts have independent, explicitly configured finite
   retention policies. Runtime owners choose values and expose health before
   enablement; the wire contract does not couple or encode them.
5. The completion observation fires at harness/session exit. Action settlement
   is a later, separate correlated fact and never delays the completion alert.

These decisions freeze contract semantics only. They authorize no runtime
producer, served operation, consumer, cockpit implementation, or deployment.

## Related contracts

- `docs/plans/agentops/session-mechanization-plan.md`
- `docs/dispatch/session-mechanization-contracts.md`
- `docs/plans/agentops/state-event-command-matrix.md`
- `docs/plans/agentops/cockpit-web-frontend-plan.md`
- `docs/plans/agentops/live-session-completion-alert-plan.md`
- `sprintctl/docs/plans/adr-outbox-sync-model.md`
