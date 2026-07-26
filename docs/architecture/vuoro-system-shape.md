# Vuoro system shape

Vuoro is the public name for a family of tools with deliberately separate
state owners. The tools documented here are the current operational system.
The [`vuoro`](https://github.com/bayleafwalker/vuoro) repository is the target
client/service composition layer; it packages those capabilities without
moving their domain state machines into a new owner.

## Operating modes

```text
                         shared operator view
                      ┌────────────────────────┐
                      │ agent-cockpit          │
                      │ reads projections;     │
                      │ dispatches via actionq │
                      └───────┬────────────────┘
                              │ HTTP / owning contracts
              ┌───────────────▼────────────────┐
served mode   │ vuoro-service                  │
              │ auth, catalog, compatibility,  │
              │ released adapter composition   │
              └───────────────┬────────────────┘
                              │ pinned domain adapters
remote mode   ┌───────────────▼────────────────┐
              │ PostgreSQL authorities         │
              │ sprintctl · actionq · kctl ·   │
              │ auditctl                       │
              └────────────────────────────────┘

local mode    agent / owning CLI ──► repo-local SQLite and artifacts
              machine-local effects stay on the executing machine
```

- **Local mode** calls an owning CLI directly. Repo-local SQLite databases,
  claim recovery records, Git worktrees, and other machine effects remain
  local.
- **Remote mode** uses the same domain tool against its shared PostgreSQL
  authority. It is a backend choice, not a separate state owner.
- **Served mode** sends a transport-only `vuoro-client` request to
  `vuoro-service`. The service authenticates the caller, checks compatibility,
  and invokes a pinned adapter for the owning domain. It does not replace the
  domain authority.
- **Cockpit** composes read models and submits dispatch through documented
  APIs. It does not write the domain databases directly.

These paths can coexist. A served request may reach a remote domain authority,
while its bounded worker still performs Git and filesystem effects locally.
No diagram arrow implies a distributed transaction: handoffs use explicit
receipts, append-only evidence, idempotency, and recovery.

## One end-to-end walkthrough

The concrete property to preserve across adapters and deployment composition
is:

1. An operator or integration creates a sprintctl work item. Sprintctl records
   the item and its event history as the work authority.
2. An agent starts a claim. The returned claim ID and secret token—not an actor
   name, branch, or hostname—prove the live ownership incarnation.
3. Dispatch submits an action through actionq. Actionq-dispatch creates a
   bounded Git worktree, applies path and command policy, invokes one worker,
   and runs pre- and post-gates.
4. A failed worker or invalid result is not published or used to close the work
   item. The queue records the failed/rejected outcome, and the independent
   verification gate remains authoritative for acceptance.
5. The same owner can resume from its private claim recovery record. A
   different owner requires an explicit handoff or recovery that rotates
   ownership proof; stale proof must no longer settle the item.
6. After a valid result clears independent verification, the owning CLI
   records completion and releases the claim. Auditctl indexes the resulting
   events into portable evidence, and the cockpit projects the sprint, claim,
   dispatch, and audit outcome.

The walkthrough is a system-level acceptance scenario, not a claim that all
six steps are one atomic operation. A complete proof must inject failure
between boundaries, demonstrate rejection of stale ownership proof, resume or
recover without duplicate settlement, and compare the audit and cockpit
projections with their owning records.

## Ownership summary

| Concern | Authority |
| --- | --- |
| Work items, dependencies, claims, handoffs | sprintctl |
| Actions, sessions, execution claims, outcomes | actionq |
| Bounded worktree and worker coordination | actionq-dispatch |
| Knowledge extraction, review, publication | kctl |
| Audit index and portable evidence shards | auditctl |
| Shared contracts, dispatch guidance, cockpit application | agentops |
| Client/service packaging and released adapter composition | vuoro |
| Environment deployment and credentials | appservice |

