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
