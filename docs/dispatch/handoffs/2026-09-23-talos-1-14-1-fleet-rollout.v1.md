# Handoff 2026-09-23-talos-1-14-1-fleet-rollout.v1

<!-- Rendered from the canonical JSON beside this file. Do not hand-edit:
     `agentops handoff validate` and `ack` read the JSON, never this. -->

**Objective.** Roll the homelab Talos fleet from v1.14.0 to v1.14.1 following appservice docs/talos-kubernetes-upgrade.md Step 1 onward (canary k8s-worker-2, then control planes and k8s-worker-gpu-1, then k8s-worker-3 alone), then disarm every phase (Step 3) and run the post-upgrade health checks.

**Next action.** cd /projects/dev/appservice && git fetch origin && git merge --ff-only origin/main && export KUBECONFIG=/projects/dev/appservice/clusters/.kube/config && kubectl get clusters.postgresql.cnpg.io -A -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name,INSTANCES:.spec.instances,PRIMARY:.status.currentPrimary  # then plan the worker-2 switchovers and drain per the runbook

## Predecessor

- harness: claude-code
- session: b2bee73e-4813-422f-b4c9-a9ed0b3cb894
- model: claude-opus-5-5
- context used: unknown%
- transcript: unknown
- origin: `workstation:/projects/dev/agentops/docs/dispatch/handoffs/2026-09-23-talos-1-14-1-fleet-rollout.v1.json` (authoritative copy; an ack from another host goes through it)

Read-only after transfer: once a successor acks, the predecessor makes no
edits and takes no external actions. It stays consultable.

## Constraints

- Scope is this Talos track only. The predecessor session keeps working the E1 track (agentops#2514, vuoro-cloud); leave vuoro-cloud and E1 alone.
- Arm and disarm only in Git: each phase change is its own commit, landed through a PR on appservice origin (GitHub) with `gh pr merge --squash` after CI. Never mutate phases or SUC with kubectl.
- Do NOT arm KUBERNETES_PHASE_ENABLED. Kubelets run v1.36.4 while KUBERNETES_VERSION pins v1.37.0: the Kubernetes phase was never run. Report this, do not fix it in this track.
- Every check is forced into its failure case before it is trusted. Anything that could not run is 'could not check', not 'clean'.
- Use KUBECONFIG=/projects/dev/appservice/clusters/.kube/config; bare kubectl hits the local kind cluster. Network commands need dangerouslyDisableSandbox (silent empty output otherwise).
- If the auto-mode classifier blocks a cluster mutation (cordon, drain, switchover), report the exact denied command and a one-line `!` form for the operator in the same reply; do not route around it.
- Uncordon a node only when Longhorn reports its volumes healthy and the storage write/read probe on that node passes.

## Decisions

- **Step 0 landed as appservice main ad201c47 (PR #1714): TALOS_VERSION, both factory installer tags, talconfig and the mise talosctl pin all at v1.14.1; all three phase gates disarmed** — The runbook requires every pin to move in one commit. version-alignment passes. Installer images resolve at v1.14.1 (default sha256:0612d540..., nvidia sha256:6ab93d2f...)
- **The iSCSI preflight maps Talos v1.14.1 to open-iscsi 2.1.13 with no incompatible parameter; an unverified v1.14.2 stays UNDETERMINED** — The Sidero compat patch is absent at the extensions v1.14.1 tag (404), but upstream open-iscsi 2.1.13 (#542) registers node.session.conn_reopen_log_freq as a deprecated alias, so it parses both spellings. The broad gate still BLOCKS the 3 storage workers until each is cleanly drained: that is intended
- **Canary k8s-worker-2 is cleared by accepting downtime in a quiet window (operator option 2, 2026-09-23), not by rebuilding replicas first** — 29 of the 83 Longhorn volumes with a replica on worker-2 have their only running replica there; the operator accepted them going offline for the drain and reboot
- **Preflights run and passed 2026-09-23 about 19:30 local** — `ssh infra sudo -n talos-etcd-backup-gate` passed (snapshot about 15h old; passwordless sudo works; re-run it if more than 24h have passed). Flux: no unready ks/hr. All 6 nodes Ready on v1.14.0. SUC plans talos, talos-nvidia and kubernetes are present

## Rejected

- **Landing Renovate #1643 (talosctl pin only)** — The version-alignment guard refuses a talosctl pin that differs from TALOS_VERSION. Closed as superseded by #1714
- **Treating a missing Sidero compat patch as proof v1.14.1 is safe or unsafe** — Absence of the patch alone would mean unsafe; the safety comes from upstream 2.1.13's alias, which was read at the source

## Repo state

Digest definition: v3 (see the handoffs README).

| path | branch | head | dirty | unpushed | diff_sha256 |
|---|---|---|---|---|---|
| `/projects/dev/appservice` | main | `ad201c478b66` | no | 0 | `e3b0c44298fc1c14…` |

**Running:**

- Nothing for this track. No phase is armed and no node is cordoned.

## Unresolved

- CNPG primaries on worker-2 (forgejo/forgejo-db, vscode/sprintctl-cnpg-main, vuoro-shared/vuoro-postgres): whether each has a second instance to switch over to. If not, accept the downtime. vuoro-shared hosts the served sprintctl these sessions use.
- k8s-worker-gpu-1 is also a storage worker and uses TALOS_NVIDIA_PHASE_ENABLED. Check its sole-replica volumes and CNPG primaries (analytics, authentik, paperless, vaultwarden) before its drain.
- k8s-worker-3 holds 47 volumes (14 single-replica) and the immich and nextcloud primaries: the worst drain case, run supervised and alone.

## Evidence

- artifact: `/projects/dev/appservice/docs/talos-kubernetes-upgrade.md`
- artifact: `/projects/dev/appservice/clusters/main/kubernetes/flux-system/flux/upgradesettings.yaml`
- artifact: `/projects/dev/appservice/bin/iscsi-record-preflight.sh`

## sprintctl bundle

- none (sprintctl unavailable or produced no bundle)

## Successor

- session: b2ec1d19-782f-4d0e-bd0b-d1c6548332f3
- acknowledged: 2026-09-23T16:35:54Z
