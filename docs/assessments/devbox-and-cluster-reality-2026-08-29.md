# devbox-agent and cluster reality — 2026-08-29

**Item:** agentops #2311 (sprint #551, cross-repo-dogfood-r0)
**Question:** verify devbox-agent and cluster reality before R1 planning. The
cross-repo dogfood plan §10 records this as unverified and names one specific
open question: whether the three `vuoro-service` digests are still three.

Measured on 2026-08-29 from the workstation, read-only.

## The named question: still three

| Deployment | `vuoro-service` digest |
|---|---|
| `vuoro-shared/vuoro-shared` | `sha256:92508004…` |
| `vuoro-dev/vuoro-dev` | `sha256:aeeb8088…` |
| `vscode/agent-cockpit` | `sha256:d35c6b84…` |

Three distinct digests, unchanged. `vuoro-shared` carries the 0.1.55 image released
on 2026-08-29; `vuoro-dev` and `agent-cockpit` remain on their own older builds.
**vuoro #2314 is still open and now confirmed rather than inferred.**

## Cluster

| Check | Result |
|---|---|
| Kustomizations | 88 total, 87 Ready |
| Not ready | `flux-system/external-secrets-pilot` — `suspend: true`, deliberate |
| Pods | 249, **0 unhealthy** |
| HelmReleases | 0 not Ready |
| GitRepository `cluster` | `main@sha1:059aa59f` |
| appservice `origin/main` | `059aa59f` — **fully reconciled, no drift** |

`gateway-api` is pinned at `v1.6.1@sha1:8bb74df0` and `truecharts` tracks `master`.

**openbao is healthy**, contrary to the claim carried into this session that a
longhorn dependency had it wedged for 17 days. The namespace is 17 days old, but
`openbao-0/1/2` have been Running 9 days with zero restarts, the snapshot CronJob
completed 2 days ago, and its Kustomization reports `ReconciliationSucceeded` with
a passing health check at the current revision. The 17 days is the namespace's age,
not a stall. The dependency on `longhorn` is real and was correctly removed from
`homelab-analytics`, but it is not holding openbao.

## devbox-agent

Reachable over `ssh devbox-agent`, user `agent`, host `devbox`, `/projects/dev`
present with 35 repositories (the workstation has more; the trees are independent
clones by design).

Served work authority **functions**, but only through the host-specific profile:
`SPRINTCTL_VUORO_PROFILE=…/devbox-agent-vuoro-shared.json`, supplied by
`.envrc.local`. Using the workstation profile fails with `cannot stat the
configured credential file` — correct behaviour, since the credential is
`~/.config/vuoro/credentials/vuoro-shared-agent` there, not the workstation's file.
With the right profile, `sprint list` returns the live sprints.

| Tool | devbox-agent | Note |
|---|---|---|
| `sprintctl` | **0.3.2** | deployed adapter is **0.3.4** — stale |
| `auditctl` | present | |
| `kctl` | present | |
| `claude` | 2.1.220 | |
| `codex` | 0.147.0 | |

**The one finding that matters: devbox-agent is two releases behind on sprintctl.**
0.3.4 carries both fixes made on 2026-08-29 — `record_handoff_generated` preserving
`git_context`, and the `work.read.handoff` crash for any sprint holding an active
reservation. A session interrupted on devbox-agent today would hit the exact defect
that item #2311's sibling work fixed, because `uv tool` installs there do not
propagate from the workstation. This is drift of precisely the kind
`align-and-converge` exists to report.

## Method note

Two measurements in this assessment were initially wrong in the same way, and both
were caused by the measuring environment rather than by the thing measured:

- `kubectl get pods -n openbao` returned "No resources found" because `KUBECONFIG`
  does not persist between tool invocations. Re-run with it set, three healthy pods.
- An earlier survey in this session reported "zero open PRs anywhere" because `gh`
  calls in the `-R <name>` form returned empty with exit 0 rather than failing.

Both are the defect shape recorded as *empty is not absent*: a step reporting
success while doing nothing, where an empty result and an unreachable endpoint are
indistinguishable from the output alone. State absence only when the channel
demonstrably answered. This assessment's negative findings — 0 unhealthy pods, 0
non-Ready HelmReleases — were each confirmed against a positive control in the same
query.

## Disposition

R1 planning may proceed on this basis. Two items carried forward, neither blocking:

1. **vuoro #2314** — `vuoro-dev` and `agent-cockpit` remain on older digests.
2. **devbox-agent sprintctl 0.3.2 → 0.3.4** — a per-host install, not fixed here,
   and the first real test case for the alignment run once it exists.
