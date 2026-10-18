# agentops

[![pages](https://github.com/bayleafwalker/agentops/actions/workflows/pages.yml/badge.svg)](https://github.com/bayleafwalker/agentops/actions/workflows/pages.yml)

[Explore the interactive AgentOps ecosystem map.](https://bayleafwalker.github.io/agentops/)

[Read the Vuoro system shape and end-to-end walkthrough.](docs/architecture/vuoro-system-shape.md)

[Vuoro Cloud](https://vuoro.cloud/) is the invitation-only hosted pilot.
For a local evaluation without a Cloud account, use the
[disposable settlement demo](https://github.com/bayleafwalker/vuoro/tree/main/packages/vuoro-demo).
The [bounded hosted-to-native proof](docs/evidence/2026-10-09-mi1-bindery/README.md)
records its scope and capture limits; it is separate from the public site's
illustrated takeover.

Canonical dispatch skills, schemas, sync utilities, read-only reporting and
cross-repository guidance for the `/projects/dev` agent-ops substrate.

[Estate delivery and current qualification handoff.](docs/architecture/2026-10-17-estate-evidence-delivery.md)
The [full roadmap source progress](docs/architecture/2026-10-17-estate-roadmap-source-progress.md)
separates merged implementation from release, installation and outcome qualification.

The implementation repos remain separate:

- `sprintctl` owns sprint/work-item state. ([bayleafwalker/sprintctl](https://github.com/bayleafwalker/sprintctl))
- Vuoro workspace and `vuoro-knowledge` own current knowledge/artifact work;
  retired `kctl` is historical migration input only. See the
  [estate delivery plan](docs/plans/agentops/2026-10-17-estate-evolution-plan.md).
- `auditctl` owns audit capture and findings; its central schema3 design keeps
  observation and decision history distinct from current authority. Historical
  shard import and cutover remain gated. ([bayleafwalker/auditctl](https://github.com/bayleafwalker/auditctl))
- `actionq` is contracting toward federation of work/execution references,
  relations, assurance, acceptance, and reconciliation. Release 0.1.26 removed
  its daemon, harness/worktree execution plane, and standalone server source;
  the queue and Vuoro adapter remain the extraction boundary. ([bayleafwalker/actionq](https://github.com/bayleafwalker/actionq))
- selected native harnesses/runtimes own execution and session behavior;
  `actionq-dispatch` 0.2.0 is an inactive tombstone whose retained
  `dispatcher-once` command fails closed. ([bayleafwalker/actionq-dispatch](https://github.com/bayleafwalker/actionq-dispatch))
- `appservice` owns Kubernetes/GitOps deployment. (private — internal operations only)

Outctl is retired from active Vuoro scope and retained only as a frozen
discovery artifact. See the
[2026-08-20 native-runtime/federation realignment](docs/plans/agentops/native-runtime-federation-realignment-2026-08-20.md).

This repo owns cross-repo substrate plans:

```text
docs/plans/agentops/   # cross-repo plans
site/index.html         # interactive map of the wider AgentOps ecosystem
```

The agent-cockpit UI (`apps/web/`) was retired from the cluster (appservice #1647) and its
source deleted in 2026-09; recover it from git history if needed.

[Two-year KAOS roadmap](docs/plans/agentops/2026-10-18-kaos-2028-roadmap.md): goals, features, product onboarding and project activities traced to current state.

Operator-action request lifecycle and TUI/UI delivery: [planned refinement](docs/plans/agentops/2026-10-18-operator-actions.md).

Estate-wide contract rewrite: [requirements map](docs/plans/agentops/2026-10-18-estate-contract-rewrite.md) and [architecture discovery](docs/plans/agentops/2026-10-18-estate-contract-architecture-discovery.md).
