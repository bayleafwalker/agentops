# Agent-Ops Plans

Cross-repo planning for the agent-ops substrate lives here because the substrate is not owned by `homelab-analytics`.

These files live in the `/projects/dev/agentops` repo. Treat this repo as the coordination and future operator-surface home for the flat `/projects/dev` workspace, where implementation repos are siblings rather than nested under a `repos/` directory.

Current plan set:

- `agent-ops-substrate-plan.md` - master cross-repo substrate plan.
- `auditctl-workstream-d-plan.md` - standalone auditctl tool plan.
- `agent-cockpit-workstream-e-plan.md` - agent-cockpit frontend plan for the future cockpit surface inside this repo.

Repo-owned companion plans:

- `/projects/dev/sprintctl/docs/plans/sprintctl-multi-agent-takeup-plan.md`
- `/projects/dev/sprintctl/docs/plans/pg-backend-remote-mode-plan.md`
- `/projects/dev/actionq/docs/plans/actionq-server-daemon-workstream-c-plan.md`

Current implementation repos relevant to these plans:

- `/projects/dev/actionq` - existing Postgres-backed queue and `actionctl`.
- `/projects/dev/actionq-dispatcher` - existing `dispatcher-once` coordinator implementation.
- `/projects/dev/appservice` - existing GitOps source of truth; current actionq CNPG lives under `clusters/main/kubernetes/apps/actionq-db/`.

Target repos that do not exist yet:

- `/projects/dev/auditctl`

Future in-repo implementation target:

- `/projects/dev/agentops/apps/web` - planned agent-cockpit operator frontend.

Pilot consumer:

- `/projects/dev/homelab-analytics/docs/plans/agent-ops-pilot-consumer-plan.md`
