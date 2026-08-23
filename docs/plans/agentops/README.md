# Agent-Ops Plans

Cross-repo planning for the agent-ops substrate lives here because the substrate is not owned by `homelab-analytics`.

These files live in the `/projects/dev/agentops` repo. Treat this repo as the coordination and future operator-surface home for the flat `/projects/dev` workspace, where implementation repos are siblings rather than nested under a `repos/` directory.

## Live cross-repository architecture successor

- `native-runtime-federation-realignment-2026-08-20.md` - current execution,
  advisory-reservation, federation, cross-repository handoff, and retired
  Outctl boundary. This is the **sole live successor** for the execution and
  ownership direction covered by the older substrate, simplification,
  dispatcher-meta, and waved-dispatch plans. Its ActionQ deletion milestone is
  now implemented in owner source (`actionq` 0.1.26); the operator rollout and
  federation extraction remain incomplete and separately gated.

## Current hand-off backlogs (2026-08-23, draft)

- `2026-08-23-handoff-loop-and-telemetry.md` - hand-off backlog from the vuoro
  requirements pathway (`vuoro/docs/plans/2026-08-23-requirements-pathway-v5-v7.md`,
  G3.1 / G4, decisions D-8, D-9): Track T workflow telemetry (v4.1, starts
  before v5) and Track L unattended hand-off loop (v7, L-1 early). Consumer is
  the orchestration-planning session; the pathway itself is still draft for
  owner ratification and authorizes nothing.

## Current supporting mapping

- `volatile-context-native-runtime-integration-mapping-2026-08-20.md` - current
  mapping from the immutable volatile-context handoff to native runtimes,
  Sprintctl revision CAS, and ActionQ federation references.

## Historical and domain-specific plans

Nothing in the lists below is a second live cross-repository execution or
ownership plan. Domain contracts remain authoritative inside their domains;
where older files discuss daemons, claims, Outctl, or fan-out, the live
successor above controls the cross-repository direction.

- `volatile-context-implementer-bundle.md` - landed revision-gated volatile
  context implementation handoff and cross-repository ownership note; the
  imported bundle is historical and checksum-pinned.
- `post-cockpit-waved-dispatch-program.md` - superseded 2026-08-20; preserves
  the 2026-08-01 cross-repository reconciliation and wave history.
- `agent-ops-substrate-plan.md` - historical master substrate plan; its
  execution/ownership direction is superseded by the live successor above.
- `ecosystem-simplification-plan.md` - superseded historical cross-member
  simplification program and completion evidence.
- `boundary-resolutions.md` - historical 2026-08-12 ratification; R1, R2, and
  R5 were superseded on 2026-08-20 while R3 and R4 remain current.
- `auditctl-workstream-d-plan.md` - standalone auditctl tool plan.
- `agent-cockpit-workstream-e-plan.md` - agent-cockpit frontend plan for the future cockpit surface inside this repo.
- `cockpit-agentops-readiness-2026-04-28.md` - readiness and sequencing assessment for cockpit and substrate rollout.
- `meta-sprint-cross-repo-dispatch-plan.md` - superseded historical
  dispatcher-meta proposal; do not use as an implementation backlog.
- `generalized-dispatch-practices-plan.md` - historical shared dispatch model;
  reuse only portions consistent with the live successor.
- `substrate-resilience-plan.md` - historical daemon-era failure taxonomy and
  recovery plan; daemon growth/recovery mechanisms are not current backlog.

Historical ops-upgrade / outbox-mechanization tranche (2026-07):

- `ops-upgrade-reconciliation-2026-07.md` - verified source-of-truth reconciliation underlying the tranche.
- `ecosystem-backlog-review-2026-07-17.md` - dated ecosystem evidence, plan corrections, and owner-correct backlog refinement.
- `session-mechanization-plan.md` - Tier 0/1/2 session bookkeeping, capsule, reconciler, periodic scribe, cockpit metrics.
- `state-event-command-matrix.md` - per-event classification and ownership.
- `write-surface-policy.md` - which surfaces may mutate sprint state.
- `outbox-mechanization-rollout-sequencing.md` - cross-repo execution sequencing and gates for the rollout (item #1110).
- `agent-cockpit-deployment-handoff.md` - appservice deployment handoff/runbook for agent-cockpit (item #951).
- `kctl-cockpit-knowledge-reads-followup.md` - kctl knowledge-artifact integration definition for cockpit knowledge reads (item #953).

Historical Vuoro served-substrate direction (ratified 2026-07-21):

- `vuoro-served-substrate-plan.md` - historical capability scoping, modular
  service, operation catalog, client, deployment packaging, environment,
  ratification, and recovery decision; execution portions are superseded.
- `vuoro-appservice-runtime-handoff.md` - appservice-owned persistent
  development and production deployment contract.
- `vuoro-backlog-enablement-2026-07-21.md` - approved owner-local item map,
  refinement decisions, and cross-repository critical path.
- `vuoro-continuation-blockers-2026-07-22.md` - current supervised-resumption
  blockers and entry criteria for #1195 and #1204.
- `vuoro-claim-proof-transport-clarification-2026-07-23.md` -
  operator-approved Group A contract for transient claim proofs, authenticated
  claim context, retry sidecars, parity, and proofless-recovery separation.

Vuoro phase-1 comparison study (drafted 2026-07-22, independent of the
implementation backlog above):

- `vuoro-phase1-study-corpus.md` - source material: per-capability-slice
  system/reading assignments (primary / reference / domain).
- `vuoro-phase1-study-prompt-template.md` - source material: the
  functional-investigation prompt template and method.
- `vuoro-phase1-study-backlog.md` - derived item backlog (35 items across
  primary investigations, reference reads, domain reading, and the
  cross-cutting shelf), sourcing status, and suggested execution order.
  sprintctl registration is deferred pending the same endpoint blocker as
  `vuoro-continuation-blockers-2026-07-22.md`.

Implemented dispatch contracts:

- `/projects/dev/agentops/docs/dispatch/dispatch-manifest.md` - manifest contract for repo dispatch adoption.
- `/projects/dev/agentops/templates/dispatch/manifest.schema.json` - JSON schema for dispatch manifests.
- `/projects/dev/agentops/templates/dispatch/skills/` - shared dispatch skill templates selected by manifests and repo overlays.

Semantic-verification contract:

- [`docs/verification/test-context-packet-v1.md`](../../verification/test-context-packet-v1.md) - data-only packet contract and ownership rules.
- [`templates/dispatch/schemas/test-context.schema.json`](../../../templates/dispatch/schemas/test-context.schema.json) - sole normative JSON schema.
- [`templates/dispatch/repository-baseline/`](../../../templates/dispatch/repository-baseline/) - copyable consumer baseline and CI example.

Session mechanization contracts:

- [`docs/dispatch/session-mechanization-contracts.md`](../../dispatch/session-mechanization-contracts.md) - `session-capsule/v1` and `reconciliation-proposal/v1` schemas and field contracts.
- [`templates/dispatch/session-mechanization/`](../../../templates/dispatch/session-mechanization/) - schemas and examples.
- [`templates/dispatch/skills/session-scribe/SKILL.md`](../../../templates/dispatch/skills/session-scribe/SKILL.md) - the canonical periodic scribe (item #1107): judgment procedure for a fresh dispatched session.
- [`templates/dispatch/scripts/session_scribe.py`](../../../templates/dispatch/scripts/session_scribe.py) - the scribe's mechanical half: durable cursor, capsule discovery/grouping, validated artifact writing.

Advisory experiments (delete-by-default; no gate authority):

- `execution-scope-declaration-pilot.md` - `execution-scope/v0`. Track A:
  planner concerns that never reached the frozen envelope (`PLANNER_GAP`,
  #2053-#2056). Track B: independent scope reconstruction from artifacts alone
  (#2057). Track C: scope declaration as a prospective intervention, measured by
  randomized trial (#2058). Supersedes `planner-focus-manifest-pilot.md`;
  introspective framing is closed, not deferred.

Repo-owned companion plans:

- `/projects/dev/sprintctl/docs/plans/sprintctl-multi-agent-takeup-plan.md`
- `/projects/dev/sprintctl/docs/plans/pg-backend-remote-mode-plan.md`
- `/projects/dev/actionq/docs/plans/actionq-server-daemon-workstream-c-plan.md`

Current compatibility implementations referenced by these plans:

- `/projects/dev/auditctl` - repo-local audit ledger implementation and publisher contract.
- `/projects/dev/actionq` - PostgreSQL queue and Vuoro adapter retained after
  daemon/server/harness source deletion, during extraction toward the
  federation/settlement target.
- `/projects/dev/actionq-dispatcher` - inactive 0.2.0 retirement tombstone;
  existing installations may upgrade once for a clear failure, then remove it.
- `/projects/dev/appservice` - existing GitOps source of truth; current actionq CNPG lives under `clusters/main/kubernetes/apps/actionq-db/`.

Future in-repo implementation target:

- `/projects/dev/agentops/apps/web` - planned agent-cockpit operator frontend.

Pilot consumer:

- `/projects/dev/homelab-analytics/docs/plans/agent-ops-pilot-consumer-plan.md`
