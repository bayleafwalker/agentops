---
doc_id: agent-cockpit-deployment-handoff
status: reviewed
last_verified: 2026-07-18
supersedes: null
---

# agent-cockpit deployment handoff (appservice)

Deployment status (operator attestation, 2026-07-18): deployed. This
workstation is not permitted through the runtime firewall, so the deployed
image tag, environment values, and smoke checks below remain operational
evidence to capture from an authorized host.

Operational handoff for running, rebuilding, and reconfiguring the
agent-cockpit web app (sprint item #951). Application source is
agentops-owned (`agentops/apps/web/`); **deployment truth is
appservice-owned** (`appservice/clusters/main/kubernetes/apps/agent-cockpit/app/`),
reconciled by Flux from `appservice` `main`. Rollout ordering context:
[`outbox-mechanization-rollout-sequencing.md`](outbox-mechanization-rollout-sequencing.md)
Tranche A.

## Topology

| Surface | Value |
|---|---|
| Deployment | `vscode/agent-cockpit`, 1 replica, `Recreate` strategy |
| Image | `${REGISTRY_IP}:5000/agent-cockpit:<tag>` (currently `0.1.13`) — `REGISTRY_IP` is a Flux postBuild substitution from `flux-system/flux/clustersettings.secret.yaml` |
| In-cluster DNS | `http://agent-cockpit.agentops:3000` (ExternalName alias in namespace `agentops` → `agent-cockpit.vscode.svc.cluster.local:3000`) |
| External | `https://cockpit.apps.kotona.app/` via Cilium Gateway HTTPRoute (`https` section; plain `http` section 301-redirects) |
| Probes | readiness + liveness `GET /cockpit` on port 3000 |
| Workspace mount | `truenas-workspace-pvc` subPath `dev` at `/projects/dev`, **readOnly**; writable trigger mount at `/cockpit-triggers` (subPath `dev/.cockpit-triggers`) |
| kubeconfig | `appservice/clusters/.kube/config` (works from workstation; no devbox needed) |

Manifests: `namespace.yaml`, `deployment.yaml`, `service.yaml`,
`service-alias.yaml`, `gateway-api-routes.yaml` under
`clusters/main/kubernetes/apps/agent-cockpit/app/`.

## Image rebuild procedure

The image is built from `agentops/apps/web/Dockerfile` and pushed to the
in-cluster registry (see `appservice/docs/registry.md` for registry access
and the insecure-HTTP caveats):

```bash
cd /projects/dev/agentops/apps/web
docker build -t <registry-lb-ip>:5000/agent-cockpit:<new-tag> .
docker push <registry-lb-ip>:5000/agent-cockpit:<new-tag>
# then in appservice:
#   edit clusters/main/kubernetes/apps/agent-cockpit/app/deployment.yaml image tag
#   commit "feat(cockpit): bump agent-cockpit to <new-tag>" and push; Flux reconciles
```

Rollback = pin the previous tag in `deployment.yaml`. The registry keeps old
tags; `Recreate` strategy means a short outage per roll, acceptable for this
surface.

## Environment contract

Set in `deployment.yaml` (authoritative list — check the manifest when in
doubt):

| Var | Source | Notes |
|---|---|---|
| `SPRINTCTL_URL` | secret `sprintctl-cnpg-main-app` key `uri` | CNPG-managed app credentials |
| `ACTIONQ_URL` | secret `actionq-cnpg-main-app` key `uri` | CNPG-managed |
| `COCKPIT_WRITE_TOKEN` | secret `agent-cockpit-write` key `token`, `optional: true` | write-route auth + MCP enable; see below |
| `COCKPIT_ARTIFACTS_ROOT` | literal `/projects/dev` | **temporary workaround** — see pending actions |
| `COCKPIT_AUDIT_LOOKBACK_DAYS` | literal `3` | audit NDJSON scan window |
| `COCKPIT_ACTIONQ_SERVER_URL` | literal | actionq-server dispatch endpoint |
| `COCKPIT_ACTIONQ_DISPATCH_CONTRACT` | literal `v1` | |
| `COCKPIT_CLAUDE_HEADROOM_COMMAND` / `_FILE`, `COCKPIT_CODEX_HEADROOM_COMMAND`, `COCKPIT_HEADROOM_TRIGGER_PATH` | literals | headroom panels + refresh trigger file |
| `COCKPIT_RECONCILIATION_CACHE_MS` | *not yet set* | optional cache knob added with the reconciliation surfaces (#1109); defaults sensibly in code |

Write-token semantics: routes are **legacy-open when the env var is unset**;
once set, writes require bearer or `x-cockpit-write-token` (timing-safe
compare) and the browser UI reads `localStorage["cockpit_write_token"]`. The
MCP endpoint (`/cockpit/api/mcp`) returns 503 until the token is configured.
Retrieve the token:

```bash
kubectl -n vscode get secret agent-cockpit-write -o jsonpath='{.data.token}' | base64 -d
```

## Post-deployment verification actions (original handoff 2026-07-14)

The original handoff baseline, image `0.1.13`, predated agentops commits
`044bfaf` (#1105 sprint-activation via sprintctl handler), `f2f138d` (#1109
reconciliation surfaces), the audit.js path fix, and write-token enforcement.
The current deployed tag is not visible from this workstation. From an
authorized host, confirm that the deployed image includes those changes and
capture the following checks:

1. **Revert `COCKPIT_ARTIFACTS_ROOT` to `/projects/dev/_artifacts`.** The
   current `/projects/dev` value works around old audit.js appending
   `_artifacts` itself (double-path bug); the source fix is committed, and
   the reconciliation reader also expects the artifacts root.
2. **Set the browser token** (`localStorage["cockpit_write_token"]`) —
   enforcement goes live with the new image and UI writes 401 without it.
3. **Smoke checks:**
   - `GET /cockpit/api/repos` → 12 repos, `source: pg://sprintctl`;
   - sprint activation exercises the DB-side
     `sprintctl_sprint_activate()` (already applied to the live
     `sprintctl-cnpg-main` DB; expect `SP404`/`SP409` SQLSTATE mapping);
   - `GET /cockpit/api/reconciliation` → healthy empty review queue (no
     live capsules exist yet — expected until the Tier-0 producer ships).

## Operational notes

- The pod reads the whole workspace **read-only**; it can never repair its
  own inputs. Anything the cockpit "writes" goes through sprintctl/actionq
  services or the trigger file mount.
- `Recreate` + single replica: treat image bumps as brief planned outages.
- Failure triage order: probe failures (`GET /cockpit`) → secret-backed env
  vars present (`kubectl -n vscode exec deploy/agent-cockpit -- env | grep
  -E 'SPRINTCTL|ACTIONQ|COCKPIT'`) → CNPG cluster health (`kubectl -n
  vscode get cluster sprintctl-cnpg-main actionq-cnpg-main`).

## Related documents

- [`write-surface-policy.md`](write-surface-policy.md) — which cockpit
  routes may write and under what auth.
- [`session-mechanization-plan.md`](session-mechanization-plan.md) §Cockpit
  surfaces — what the reconciliation section renders.
- [`outbox-mechanization-rollout-sequencing.md`](outbox-mechanization-rollout-sequencing.md)
  — where this deploy sits in the rollout (Tranche A).
- `appservice/docs/registry.md` — registry endpoints and node pull config.
