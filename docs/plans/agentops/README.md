# Agent-Ops Plans

Cross-repo planning for the agent-ops substrate lives here because the substrate is not owned by `homelab-analytics`.

These files live in the `/projects/dev/agentops` repo. Treat this repo as the coordination and future operator-surface home for the flat `/projects/dev` workspace, where implementation repos are siblings rather than nested under a `repos/` directory.

Current plan set:

- `agent-ops-substrate-plan.md` - master cross-repo substrate plan.
- `auditctl-workstream-d-plan.md` - standalone auditctl tool plan.
- `agent-cockpit-workstream-e-plan.md` - agent-cockpit frontend plan for the future cockpit surface inside this repo.
- `cockpit-agentops-readiness-2026-04-28.md` - readiness and sequencing assessment for cockpit and substrate rollout.
- `meta-sprint-cross-repo-dispatch-plan.md` - meta-sprint model and cross-repo dispatch via `_orchestration` sprint and actionq parent-child actions.
- `generalized-dispatch-practices-plan.md` - shared dispatch model, model routing, skills, hooks, and repo adoption levels.
- `substrate-resilience-plan.md` - failure taxonomy, backup posture, recovery runbooks, and new mechanisms required (daemon startup recovery, takeup sweep, workspace PVC backup gap).

Ops-upgrade / outbox-mechanization tranche (2026-07):

- `ops-upgrade-reconciliation-2026-07.md` - verified source-of-truth reconciliation underlying the tranche.
- `ecosystem-backlog-review-2026-07-17.md` - current ecosystem evidence, plan corrections, and owner-correct backlog refinement.
- `session-mechanization-plan.md` - Tier 0/1/2 session bookkeeping, capsule, reconciler, periodic scribe, cockpit metrics.
- `state-event-command-matrix.md` - per-event classification and ownership.
- `write-surface-policy.md` - which surfaces may mutate sprint state.
- `outbox-mechanization-rollout-sequencing.md` - cross-repo execution sequencing and gates for the rollout (item #1110).
- `agent-cockpit-deployment-handoff.md` - appservice deployment handoff/runbook for agent-cockpit (item #951).
- `kctl-cockpit-knowledge-reads-followup.md` - kctl knowledge-artifact integration definition for cockpit knowledge reads (item #953).

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

Repo-owned companion plans:

- `/projects/dev/sprintctl/docs/plans/sprintctl-multi-agent-takeup-plan.md`
- `/projects/dev/sprintctl/docs/plans/pg-backend-remote-mode-plan.md`
- `/projects/dev/actionq/docs/plans/actionq-server-daemon-workstream-c-plan.md`

Current implementation repos relevant to these plans:

- `/projects/dev/auditctl` - repo-local audit ledger implementation and publisher contract.
- `/projects/dev/actionq` - existing Postgres-backed queue and `actionctl`.
- `/projects/dev/actionq-dispatcher` - existing `dispatcher-once` coordinator implementation.
- `/projects/dev/appservice` - existing GitOps source of truth; current actionq CNPG lives under `clusters/main/kubernetes/apps/actionq-db/`.

Future in-repo implementation target:

- `/projects/dev/agentops/apps/web` - planned agent-cockpit operator frontend.

Pilot consumer:

- `/projects/dev/homelab-analytics/docs/plans/agent-ops-pilot-consumer-plan.md`
