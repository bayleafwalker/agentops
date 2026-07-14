---
doc_id: state-event-command-matrix
status: ratified
supersedes: null
---

# State / event / command matrix

Per-event classification and ownership for the agent-ops substrate, per
`sprintctl/docs/ops-upgrade-plan.md` (sections 2 and 4). Protocol semantics —
outbox, ingestion, cursors, watermarks — are specified in
`sprintctl/docs/plans/adr-outbox-sync-model.md` (doc_id
`adr-outbox-sync-model`); this matrix assigns each event/command type to a
class and an owner and states its offline/validation/projection behaviour.

> **Ownership rule: state ownership decides repository ownership.**
> Cross-domain projection and operator UX belong to `agentops`.

## Type classes

| Class | Meaning |
|---|---|
| **observation** | Appendable offline; remains true even when the referenced aggregate has advanced remotely; synchronizes by union + deduplication; may be classified concurrent or anachronistic; never silently discarded for a stale basis revision. |
| **authority command** | Requires remote arbitration. A local producer may record `command.requested`, but must not project the transition as effective until the remote authority emits an accepted decision. No optimistic offline exclusive claims. |
| **remote decision** | Authored only by the owning remote domain authority. A stale or invalid command remains visible as an immutable request plus rejection; it never mutates authoritative state. |

Column key: **Offline** = may be appended to the local outbox while
disconnected. **Remote validation** = remote authority must validate before
the effect is real. **Local projection** = how the cached local projection
treats the record before/after sync.

## sprintctl (sprint execution memory and work claims)

| Event / command | Class | Offline | Remote validation | Local projection | Authoritative result event |
|---|---|---|---|---|---|
| note / decision recorded | observation | yes | no (union + dedup) | applied immediately; flagged anachronistic if basis revision is stale | the observation itself, once ingested |
| `work.completed` (progress fact) | observation | yes | no | applied immediately as a progress fact; does **not** change item status | the observation itself, once ingested |
| `item.done` | authority command | no (record `command.requested` only) | yes — evidence gates, claim proof | pending intent; status unchanged until decision | `item.transitioned` (accepted) or command rejection |
| item status transition (any) | authority command | no | yes — `VALID_TRANSITIONS` against current shared state | pending intent until decision | `item.transitioned` decision |
| sprint activation | authority command | no | yes — `SPRINT_TRANSITIONS` (`planned -> active`) | pending intent until decision | sprint boundary event (`sprint-activated`) decision |
| sprint close | authority command | no | yes — boundary/receipt gates | pending intent until decision | sprint boundary event (`sprint-closed`) decision |
| claim acquire / renew / handoff / release | authority command | no — offline claim acquisition is not supported | yes — claim table arbitration | claim shown valid only while backed by an unexpired remote grant | claim `granted` / `renewed` / `expired` / `denied` decision |
| doc-ref addition (`item ref add`) | observation | yes | no (union + dedup) | applied immediately | the observation itself, once ingested |
| capability-receipt pointer acceptance | authority command (validation-bearing) | no | yes — canonical artifact availability + validation | pending intent until decision | pointer-accepted decision or rejection |

`work.completed` vs `item.done` is the canonical example of the split: the
former is a bufferable fact about work, the latter is a state transition whose
validity depends on shared state and gates.

## actionq (queue and dispatcher leases, session lifecycle)

| Event / command | Class | Offline | Remote validation | Local projection | Authoritative result event |
|---|---|---|---|---|---|
| queue claim | authority command | no | yes — lease arbitration | claim shown valid only under an unexpired grant | lease granted / denied decision |
| lease renewal | authority command | no | yes | renewed lease visible only after decision | lease renewed / expired decision |
| lease timeout / conflict determination | remote decision | n/a (remote-authored) | n/a | applied to projection on ingest | the decision itself |
| session lifecycle exhaust (dispatch, start, exit) | observation | yes | no (union + dedup) | applied immediately | the observation itself, once ingested |

## auditctl (durable local capture / outbox)

| Event / command | Class | Offline | Remote validation | Local projection | Authoritative result event |
|---|---|---|---|---|---|
| audit event (commit, pr, decision, custom, …) | observation | yes — auditctl **is** durable local capture/outbox | no; synchronization optional for observations | local index (sqlite) + NDJSON shard immediately | the observation itself, once ingested (if synced) |

## kctl (knowledge review lifecycle)

| Event / command | Class | Offline | Remote validation | Local projection | Authoritative result event |
|---|---|---|---|---|---|
| knowledge candidate extracted | observation | yes | no | applied immediately | the observation itself, once ingested |
| review lifecycle transition (accept / reject / supersede) | authority command (kctl-owned) | no | yes — kctl review authority | pending until kctl decision | kctl review-transition decision |

## Session mechanization (see [`session-mechanization-plan.md`](session-mechanization-plan.md))

Artifact schemas and field contracts for the two rows below marked
`(artifact + pointer)` / `(proposal artifact)`:
[`session-mechanization-contracts.md`](../../dispatch/session-mechanization-contracts.md).

| Event / command | Class | Offline | Remote validation | Local projection | Authoritative result event |
|---|---|---|---|---|---|
| `session.started` | observation | yes | no | applied immediately | the observation itself, once ingested |
| `session.ended` / `session.end-inferred` | observation | yes | no | applied immediately | the observation itself, once ingested |
| `session-capsule/v1` | observation (artifact + pointer) | yes | no (pointer is non-validation-bearing) | capsule pointer visible immediately | the observation itself, once ingested |
| `reconciliation-proposal/v1` created | observation (proposal artifact) | yes (scribe-authored, cursor-tracked) | no — proposals never mutate authoritative state | appears in review queue | the proposal artifact itself |
| proposal accepted | authority command(s) | no | yes — acceptance **executes as normal sprintctl authority commands** (see sprintctl rows above) | pending intents until sprintctl decisions | the corresponding sprintctl decisions; proposal lifecycle → `accepted` |
| proposal rejected / superseded | observation (durable lifecycle record) | yes | no | proposal leaves review queue; rejection durable for dedup | the lifecycle record itself |

## Ownership assignments

| Concern | Owner | Basis |
|---|---|---|
| Sprint execution memory, work claims, item/sprint transitions | `sprintctl` | domain authority (ops-upgrade-plan §4) |
| Queue and dispatcher leases, session lifecycle authority | `actionq` | domain authority |
| Durable local audit capture/outbox | `auditctl` | domain authority |
| Knowledge review lifecycle | `kctl` | domain authority |
| Cross-domain projection, gateway, operator UX, review queue, metrics panels | `agentops` | cross-domain projection/operator UX → agentops |
| Deployment truth | `appservice` | GitOps source of truth |

### Tier-0 session wrapper ownership (settling reconciliation open question 1)

The [reconciliation doc](ops-upgrade-reconciliation-2026-07.md) left open who
owns the Tier-0 harness-neutral session wrapper. This matrix records the
**proposed default, pending operator ratification**:

- **`actionq` owns the wrapper mechanism** — actionq is the session lifecycle
  authority; the wrapper spawns, observes, and closes sessions, which is
  actionq's state.
- **`agentops` owns the capsule/exhaust contract** (`session-capsule/v1`
  schema and the exhaust field list) **and the cross-domain projection** of
  session data — these are cross-domain contracts consumed by the scribe,
  reconciler, and cockpit, not actionq-internal state.

This follows the ownership rule directly: the session lifecycle *state* is
actionq's; the cross-domain *contract and projection* are agentops'. Until an
operator ratifies or overrides this, treat it as the working assignment for
backlog placement.

## Related documents

- `sprintctl/docs/plans/adr-outbox-sync-model.md` — canonical protocol
  decision (outbox, identities, cursors, failure cases).
- [`session-mechanization-plan.md`](session-mechanization-plan.md) — Tier
  0/1/2 mechanisms, scribe, metrics.
- [`write-surface-policy.md`](write-surface-policy.md) — which surfaces may
  issue the commands above.
- [`ops-upgrade-reconciliation-2026-07.md`](ops-upgrade-reconciliation-2026-07.md)
  — verified facts underlying these assignments.
