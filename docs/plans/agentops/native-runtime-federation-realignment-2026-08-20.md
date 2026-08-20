---
doc_id: native-runtime-federation-realignment-2026-08-20
status: active
created_at: 2026-08-20
owner: agentops
supersedes:
  - boundary-resolutions:R1
  - boundary-resolutions:R2
  - boundary-resolutions:R5
  - meta-sprint-cross-repo-dispatch-plan
  - cockpit-and-post-cockpit-waved-dispatch-program:execution-lane
---

# Native-runtime and federation realignment

This is the current Agentops planning boundary for execution, cross-repository
coordination, work reservations, and harness evidence. It records a directional
realignment; it does not claim that the deployed ActionQ services have already
been removed.

## Owner evidence

The decision is based on three newer owner records:

- ActionQ `delete/session-wrapper-execution-plane` at `27f4215`, especially
  `HANDOFF.md` and
  `docs/plans/2026-08-20-execution-plane-deletion-order.md`, reduces ActionQ
  from an execution plane to a federation layer. Its stated end state has no
  worker daemon, queue, leases, or fan-out engine. The branch is not yet
  `actionq` `origin/main`; its deletion tranches remain gated as described
  below.
- Sprintctl `origin/main` at `15afc87` (`v0.3.0`) implements advisory,
  overlapping reservations. A reservation is coordination metadata, never a
  capability. Work mutation is protected by expected-revision compare-and-swap,
  not by exclusive claim proof, bearer tokens, TTLs, or coordinator delegation.
- Agentops commit `67f1f6d` retired Outctl from the Vuoro project binding. The
  repository remains a frozen discovery artifact. New harness-evidence work
  belongs at native runtime boundaries and uses standard OpenTelemetry plus a
  selected Langfuse or Phoenix deployment and object storage; it does not grow
  another Vuoro state owner.

These records supersede earlier Agentops plans where those plans prescribe an
ActionQ-owned execution daemon, an internal ActionQ runner, dispatcher-meta
growth, exclusive Sprintctl claims, or Outctl as an active member. Historical
implementation and evidence passages remain valid descriptions of their dates.

## Target boundary

| Concern | Current target owner/boundary |
|---|---|
| Work items, revisions, dependencies, notes, and advisory reservations | Sprintctl; reservations expose overlap, while expected-revision CAS protects mutations |
| Agent execution, tool use, worktree behavior, and session continuation | The selected native harness/runtime and the coordinating session; not an ActionQ daemon or a replacement Vuoro scheduler |
| Federated work identity, relations, authority/evidence requirements, external execution references, acceptance, reconciliation, and backend qualification | ActionQ's retained federation layer |
| Per-vendor execution binding assurance | Recorded beside every external execution reference; never normalized into a stronger common guarantee |
| Cross-repository sequencing | A coordinator-owned plan over explicit Sprintctl dependencies and immutable Git/PR/evidence references |
| Harness telemetry and large raw evidence | Standard OpenTelemetry and the selected Langfuse or Phoenix/object-storage path, subject to explicit retention and redaction policy |
| Curated knowledge and audit records | Kctl and Auditctl respectively |
| Shared contracts, instruction distribution, validation, and cockpit composition | Agentops |
| Deployment and credentials | Appservice, under separate authorization |

ActionQ may retain work identities and parent/child or predecessor relations.
Those relations describe federated work; they do not authorize ActionQ to poll,
launch, supervise, retry, or settle a native runtime. A native execution result
is referenced by immutable Git commit/PR and evidence identifiers plus the
runtime's own session/execution identifier. The federation record also states
the assurance actually available: for example pre-flight binding, post-hoc
attribution, requested-model-only, or unverified.

## Cross-repository replacement path

The former dispatcher-meta design is not migrated into ActionQ or another
long-running coordinator. Its useful requirements move as follows:

1. Sprintctl holds the human work decomposition, explicit dependencies, status
   revisions, and advisory reservations. Overlapping execution reservations are
   visible; they are not rejected as an exclusivity violation.
2. The coordinator selects a dependency-cleared reasoning unit and starts a
   native runtime session. The coordinator records an external execution
   reference and its binding-assurance level in the ActionQ federation surface.
3. Parallel work uses independent native sessions only when their acceptance
   oracles and repositories are independent. Same-repository integration stays
   sequential.
4. Sequential handoff passes immutable predecessor facts: accepted commit or
   PR, verification evidence, relevant Sprintctl revision, and explicit
   successor instructions. A worktree path, mutable branch head, daemon claim,
   or parent-action lease is not a cross-host handoff.
5. A fresh independent verifier reads the actual diff and evidence. Only the
   Sprintctl owner operation, with the expected revision, changes work state.
   ActionQ records/reconciles references and acceptance facts; it does not close
   the work item on Sprintctl's behalf.
6. Failure is recovered by inspecting the native runtime and durable owner
   records, then deliberately starting or resuming a native session. There is
   no automatic parent re-claim or fan-out replay loop.

This keeps the reasoning-unit and independent-review topology while removing
the bespoke execution plane it previously assumed.

## Disposition of `_orchestration#1366`

The authoritative served item **`_orchestration#1366`, dispatcher-meta
sequential handoff**, is active in sprint **`_orchestration#437`** and is
directionally obsolete as an implementation item. Its desired outcome survives
as the explicit predecessor-reference flow above, but the planned
`dispatcher-meta` process, parent-action claim, child polling loop, lease
budget, and payload injection must not be built.

This document does not mutate Sprintctl. The tracker owner must choose one of
the normal, auditable dispositions:

- supersede `_orchestration#1366` with a bounded native-runtime/federation
  contract item; or
- rewrite `_orchestration#1366` in place only if Sprintctl policy permits
  preserving its event history and the new scope is made explicit.

Until that state decision is recorded, treat `_orchestration#1366` as **do not
dispatch**. A future replacement should cover only schema/contract work for
immutable predecessor references, execution-reference assurance, and
reconciliation; it must not smuggle a scheduler back into ActionQ or Agentops.

## Migration notes for older plans

- `boundary-resolutions.md` remains the historical 2026-08-12 ratification.
  R1, R2, and R5 are superseded on 2026-08-20. R3 and R4 remain unaffected.
- `meta-sprint-cross-repo-dispatch-plan.md` is preserved as the historical
  dispatcher-meta design. It is not an implementation backlog.
- `post-cockpit-waved-dispatch-program.md` remains evidence of its 2026-08-01
  reconciliation. Its ActionQ realization steps and deferred external-runtime
  lane are replaced by this plan; Sprintctl remains the live source for item
  state.
- The imported volatile-context bundle is checksum-pinned evidence and is not
  rewritten. Its current owner mapping lives in
  `volatile-context-native-runtime-integration-mapping-2026-08-20.md`.
- Current deployed queue/server/daemon paths are compatibility surfaces during
  migration. New work must not deepen their use.

## Remaining operator choices

These are genuine choices, not documentation gaps:

1. Remove the `actionq-server` cluster deployment, which unblocks ActionQ
   deletion tranche 2. This is an Appservice mutation and requires separate
   authorization and live verification.
2. Stop `actionq-dispatch.service` on devbox permanently, which unblocks
   ActionQ deletion tranche 3. The ActionQ evidence says there is no standing
   producer demand, but the service is currently running by operator decision.
3. Select Langfuse or Phoenix and the object-storage/retention policy for
   native-runtime evidence. Outctl retirement does not make either backend an
   authority by default.
4. Record the Sprintctl disposition of `_orchestration#1366` in active sprint
   `_orchestration#437`. This plan recommends supersession, but only the
   tracker owner may make that state change.

The ActionQ branch additionally defers lease/claim extraction until the
deployment and daemon gates are decided. Agentops must not invent a migration
answer for that owner-local schema work.
