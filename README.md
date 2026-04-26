# agentops

Repo-owned planning and future operator surface for the `/projects/dev` agent-ops substrate.

The implementation repos remain separate:

- `sprintctl` owns sprint/work-item state.
- `kctl` owns knowledge artifact extraction.
- `auditctl` will own repo-local audit ledgers.
- `actionq` owns queue and session lifecycle.
- `appservice` owns Kubernetes/GitOps deployment.

This repo owns cross-repo substrate plans now and is the intended home for the future agent-cockpit UI:

```text
docs/plans/agentops/   # cross-repo plans
apps/web/              # future agent-cockpit frontend
```
