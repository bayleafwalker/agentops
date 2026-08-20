# Vuoro system shape

Vuoro is the public name for a family of tools with deliberately separate
state owners. The `vuoro` repository is a transport and released-adapter
composition layer; it does not absorb the domain state machines or become an
execution scheduler.

## Current target boundary (2026-08-20)

The governing cross-repository alignment is
[`native-runtime-federation-realignment-2026-08-20.md`](../plans/agentops/native-runtime-federation-realignment-2026-08-20.md).
It incorporates ActionQ's execution-plane deletion plan, Sprintctl v0.3.0's
advisory reservation contract, and the merged retirement of Outctl from the
active project.

```text
                         shared operator view
                      ┌────────────────────────┐
                      │ Agent Cockpit          │
                      │ owner projections and │
                      │ federated references  │
                      └───────────┬────────────┘
                                  │ owning APIs / released adapters
                  ┌───────────────▼────────────────┐
served mode       │ vuoro-service                  │
                  │ auth, catalog, compatibility,  │
                  │ transport and composition      │
                  └───────┬──────────────┬─────────┘
                          │              │
             ┌────────────▼──────┐  ┌────▼─────────────────────┐
work domain  │ Sprintctl         │  │ ActionQ federation       │
             │ items, revisions, │  │ work/execution refs,     │
             │ advisory reserves │  │ relations, assurance,    │
             │ and CAS mutation  │  │ acceptance/reconciliation│
             └───────────────────┘  └──────────────────────────┘

execution    coordinator ──► selected native harness/runtime
edge                         │
                             ├── immutable Git/PR/evidence references
                             └── OpenTelemetry ──► selected
                                 Langfuse or Phoenix + object storage
```

The ActionQ federation box is a **target**, not a claim that deletion has
already shipped. ActionQ's `delete/session-wrapper-execution-plane` branch at
`27f4215` still has two operator gates: removal of the cluster
`actionq-server` deployment and permanent shutdown of the devbox dispatch
service. Until those gates and owner-local deletion tranches complete, the
queue/server/daemon are deployed compatibility surfaces only. New design must
not deepen their use.

## Operating modes

- **Local mode** calls an owning domain CLI directly. Repository databases,
  Git worktrees, and other machine effects remain on that host.
- **Served mode** sends a transport-only request to Vuoro Service. The service
  authenticates the caller, checks catalog compatibility, and invokes a pinned
  adapter for the owning domain. It owns neither the domain decision nor the
  native runtime.
- **Native execution** occurs in the selected first-party harness/runtime.
  Provider capabilities are unequal. Every federated execution reference must
  record the assurance actually observed (for example pre-flight binding,
  post-hoc attribution, requested-model-only, or unverified).
- **Cockpit** composes owner read models and federated references. It does not
  write databases directly or turn a relationship row into execution
  authority.

No arrow implies a distributed transaction. Cross-owner workflows use
expected revisions, idempotent owner operations, immutable references, explicit
acceptance, and reconciliation.

## End-to-end walkthrough

1. An operator or coordinator creates/decomposes Sprintctl work with explicit
   dependencies. A native session may create an advisory reservation. Multiple
   execution reservations can overlap; the overlap is visible and grants no
   capability.
2. The coordinator reads the item's current revision and selects one
   dependency-cleared reasoning unit. Independent repositories may run in
   parallel; same-repository integration remains sequential.
3. The coordinator starts the selected native harness/runtime. ActionQ records
   or later reconciles an external execution reference, its relation to the
   work, evidence/acceptance requirements, and its real binding-assurance
   level. ActionQ does not launch, lease, heartbeat, poll, or settle the native
   runtime.
4. Sequential continuation passes an accepted commit or PR, verification
   evidence, the relevant work revision, and explicit instructions. A mutable
   branch head, host-local worktree path, queue claim, or bearer token is not a
   durable handoff.
5. A fresh verifier inspects the actual diff and runs the owner-defined gates.
   Standard telemetry may retain observations, but telemetry is not acceptance
   authority.
6. Sprintctl applies a successful status transition only through its owning
   operation with the expected revision. ActionQ reconciles the external
   execution/evidence/acceptance references; Kctl and Auditctl retain their own
   knowledge and audit facts.

Failure recovery is deliberate: inspect native runtime state and durable owner
records, then resume or start a native session and reconcile the new reference.
There is no automatic parent-action re-claim or fan-out replay loop.

## Ownership summary

| Concern | Authority/boundary |
|---|---|
| Work items, dependencies, revisions, notes, advisory reservations | Sprintctl |
| Native agent execution, tools, and session lifecycle | Selected native harness/runtime |
| Federated work/execution identity, relations, assurance, evidence requirements, acceptance and reconciliation | ActionQ target federation layer |
| Knowledge extraction, review, publication | Kctl |
| Audit index and portable evidence records | Auditctl |
| Shared contracts, dispatch guidance, project binding, cockpit source | Agentops |
| Client/service transport and released adapter composition | Vuoro |
| Deployment, credentials, telemetry routing | Appservice |
| Raw/native harness observations | OpenTelemetry plus the operator-selected Langfuse or Phoenix/object-storage path; non-authoritative |

Outctl is not an active member. Its repository is a frozen discovery artifact;
no plan may assign it scheduling, capture, projection, retention, or evidence
authority. `actionq-dispatcher` is likewise only a compatibility launcher for
historical callers and must not gain `dispatcher-meta` or any other workflow
behavior.
