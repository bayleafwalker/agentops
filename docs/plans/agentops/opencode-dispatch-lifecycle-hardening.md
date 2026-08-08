---
doc_id: opencode-dispatch-lifecycle-hardening
status: proposed
last_verified: 2026-08-08
tracker_item: agentops#2115
supersedes: null
---

# OpenCode dispatch lifecycle hardening and completion-alert rollout

## Outcome

Coordinate two related but distinct reliability workstreams discovered through
the OpenCode dispatch pilot:

1. ActionQ-owned controller progression and externally verified dispatch
   completion; and
2. an observation-only, replayable live session-completion alert path from
   ActionQ to the AgentOps operator surface.

The first prevents exit, timeout, or a worker's prose from being mistaken for
successful completion. The second promptly tells an operator that a terminal
session fact exists. An alert never proves settlement, validation,
reconciliation, acceptance, or Sprintctl completion.

The governing designs are:

- ActionQ `docs/plans/controller-owned-dispatch-lifecycle.md`;
- [`live-session-completion-alert-architecture.md`](live-session-completion-alert-architecture.md);
- [`live-session-completion-alert-plan.md`](live-session-completion-alert-plan.md); and
- devbox findings in `docs/DISPATCH_OPERATIONS_FINDINGS.md` at commit
  `9f41333`, cited as coordinator-provided evidence until that source is
  available in this project worktree.

## Fixed decisions

- ActionQ owns action/session lifecycle, phase progression, work/finalization
  budgets, authoritative terminal result, producer outbox, and served
  completion log.
- OpenCode is the first qualified verified-completion path. Shared contracts
  remain harness-neutral; other adapters require separate qualification.
- The initial implementation lifecycle is `working -> finalizing -> terminal`
  with 20-minute work, 2-minute finalization, and 25-minute total ceilings.
- OpenCode finalization continues the same JSON-observed session under a
  separately qualified profile with no tools.
- Read-only streaks are collected but do not force transitions in v1.
- `session.completion-observed/v1` reports session/harness exit, not ActionQ
  settlement; settlement may be correlated later as a distinct fact.
- The P0 proposal defaults are SQLite/WAL for the producer outbox, a distinct
  append-only ActionQ completion projection, cockpit-only first delivery, and
  independent retention windows. P0 review must ratify or supersede them
  before runtime implementation.
- AgentOps owns alert policy, durable consumer cursor/inbox, route delivery
  ledger, acknowledgement, and cockpit presentation.
- Vuoro exposes released owner operations without completion semantics.
- outctl is observational only. Auditctl records immutable bounded outcome
  evidence and never decides success.
- Polling is the first correctness path. `LISTEN/NOTIFY` and SSE remain
  evidence-gated optimizations and receive no implementation item yet.
- Appservice runtime enablement is a separate, later authorized tranche. No
  deployment item is created by this planning landing.

## Backlog ledger

### Controller-owned dispatch completion

| Owner | Item | Deliverable | Gate |
|---|---|---|---|
| ActionQ | `actionq#2124` | `dispatch-result/v1` and result-bearing failure settlement | Contract and disposable-Postgres lifecycle tests |
| ActionQ | `actionq#2114` | Bounded work/finalization controller and OpenCode same-session no-tools synthesis | Exit alone can never settle success |
| ActionQ | `actionq#2123` | Progress telemetry and pathological-worker matrix | Every pathological worker terminates deterministically |
| AgentOps | `agentops#2118` | Qualify JSON events, session continuation, and the finalizer profile | Fake plus contained real probes; no finalizer tools |
| Auditctl, tracked in AgentOps | `agentops#2117` | Session-exit result reference/digest publisher alignment | Bounded metadata round-trip without authority broadening |

Wider OpenCode pilot scaling remains blocked until all five records are done,
the ActionQ state-protocol gate passes, and the umbrella records an explicit
resume-or-remain-blocked decision.

### Live completion alerts

| Package | Owner | Item | Deliverable |
|---|---|---|---|
| P0 | AgentOps with ActionQ review | `agentops#2119` | Ratified `session.completion-observed/v1`, schema/validator, ownership and timing |
| P1 | ActionQ | `actionq#2122` | Durable producer stream and outbox |
| P2 | ActionQ | `actionq#2121` | Direct, daemon, and OpenCode emission parity |
| P3 | ActionQ | existing `actionq#2027` | Durable observable session snapshot/change, cursor, replay, and recovery semantics |
| P3 transport consumer | Vuoro | existing `vuoro#2028` | Generic resource/cursor transport without domain semantics |
| P4 | AgentOps | `agentops#2116` | Consumer cursor, policy, inbox, delivery ledger, polling, and route health |
| P5 | AgentOps | `agentops#2120` | Cockpit alert read surface and operator panel |
| P6 | ActionQ/AgentOps | no item until entry gate | Optional wake hints and SSE only if polling misses measured latency/load targets |
| P7 | Appservice/operator | separate future tranche | Credentials, persistence, network policy, enablement, outage/replay drills |

ActionQ `#2027` and Vuoro `#2028` predate this plan and already own the
required observable-resource and transport seams. They are referenced and
constrained here instead of duplicated.

## Dependency order

```text
verified dispatch:
  actionq#2124 -> actionq#2114 -> actionq#2123
                                  \
  agentops#2118 ------------------+--> agentops#2115 pilot decision
  agentops#2117 ------------------/

completion alerts:
  agentops#2119 -> actionq#2122 -> actionq#2121 -> actionq#2027
                                                   |
                                                   +-> vuoro#2028
                                                   |
                                                   +-> agentops#2116
                                                          |
                                                          v
                                                   agentops#2120
                                                          |
                                                          v
                                                   agentops#2115
```

Sprintctl native dependency records are used within one repository. This
ledger and the item descriptions carry cross-repository ordering; no fake
same-repository dependency is created to imply a cross-system transaction.

## Circuit breakers

Stop the implementation wave and return to the owning coordinator when:

- `dispatch-result/v1` meaning or settlement mapping is unresolved;
- finalization can still access investigation or mutation tools;
- work and finalization can overlap;
- a worker exit can settle without a valid immutable result;
- session-completion timing is ambiguous between harness exit and settlement;
- an alert or consumer gains ActionQ/Sprintctl mutation authority;
- raw prompt, transcript, output, credentials, claim proof, environment, or
  absolute worktree paths enter a result, completion event, or alert;
- producer/consumer restart loses a logical event or duplicates operator
  delivery;
- ActionQ `#2027` or Vuoro `#2028` would need domain semantics widened; or
- deployment is required without a separately authorized Appservice tranche.

One rejected contained-worker attempt returns to the coordinator. Do not make
the prompt more aggressive as a substitute for closing a lifecycle defect.

## Verification and evidence

Source gates:

- ActionQ targeted contracts, daemon, runner, harness, state-protocol, and
  disposable-Postgres lifecycle tests;
- AgentOps schema/harness-profile tests and the dependency-free dispatch
  artifact validator;
- Auditctl publisher contract fixtures and repository gate;
- AgentOps cockpit `npm test` and `npm run build`; and
- Vuoro transport/client/service tests only when `#2028` consumes the released
  owner operation.

Operational gates:

- dispatch workers: reads forever, edits forever, exits without result, claims
  completion with no diff, edits without summary, blocks legitimately, and
  completes normally;
- alert paths: direct success/failure, daemon/OpenCode, producer offline,
  server response loss, consumer offline, route offline, duplicate replay,
  and privacy inspection;
- healthy alert projection p95 within five seconds of server ingestion; and
- explicit metrics for producer backlog age, ingest lag, consumer cursor lag,
  oldest pending route delivery, duplicate suppression, and dead letters.

Runtime receipts name immutable Git commits plus Sprintctl, ActionQ, and
Auditctl durable references. Large logs retained under `_artifacts` are
host-persistent evidence only and must record source host, absolute path,
hashes, and retention; they are not durable-authoritative closure.

## Rollout and rollback

1. Ratify contracts and ownership.
2. Land ActionQ verified completion and qualify the OpenCode finalizer.
3. Pass the pathological-worker matrix before resuming wider dispatch.
4. Land the completion producer/outbox and launch-path parity.
5. Reuse the ActionQ observable log and Vuoro transport only after their
   existing owner gates pass.
6. Land AgentOps consumer and cockpit polling surfaces against fixtures, then
   real replay.
7. Request a separate Appservice pilot tranche for one producer host and one
   non-critical project.

Rollback disables new verified profiles, completion delivery, consumers, or
cockpit presentation independently. Immutable ActionQ results, completion
events, outbox rows, server records, and delivery receipts are retained for
their configured periods and are never reinterpreted by rollback.
