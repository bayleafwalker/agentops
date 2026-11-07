# Handoff 2026-09-23-program-long-goal-handler.v1

<!-- Rendered from the canonical JSON beside this file. Do not hand-edit:
     `agentops handoff validate` and `ack` read the JSON, never this. -->

**Objective.** Hold the long goal across sessions: E1 reaches first use and agentops#2514 closes, while every follow-up that no session owns yet is taken to landed. Coordinate the two running sessions without doing their work, and own the orphan follow-ups listed here.

**Next action.** Run ListAgents and confirm both owned sessions are reachable. Then start on the agentops handoff validate bug: write a test in scripts/tests/test_handoff.py that fails today (commit a handoff, ack it, validate), fix diff_sha256 to exclude self-paths from `git diff HEAD` too, and land it via PR.

## Predecessor

- harness: claude-code
- session: b2bee73e-4813-422f-b4c9-a9ed0b3cb894
- model: claude-opus-5-5
- context used: unknown%
- transcript: unknown
- origin: `workstation:/projects/dev/agentops/docs/dispatch/handoffs/2026-09-23-program-long-goal-handler.v1.json` (authoritative copy; an ack from another host goes through it)

Read-only after transfer: once a successor acks, the predecessor makes no
edits and takes no external actions. It stays consultable.

## Constraints

- Do not duplicate owned tracks. E1 first use and the branch sweep belong to the E1 successor (handoff 2026-09-23-e1-first-use-and-branch-sweep.v2, session 6ff8a58f-38ce-4fc8-9db3-1385651d3f22). The Talos v1.14.1 fleet rollout belongs to handoff 2026-09-23-talos-1-14-1-fleet-rollout.v1 (launched as claude session b2ec1d19 in appservice). Reach them with SendMessage via ListAgents names; ask, don't take over.
- Design for use, not disposal. Every guard is forced into its failure case before it is trusted. Land work on main yourself (PR, CI, merge); only permission-blocked or hardware steps go to the operator, as one exact `!` command.
- Claude memory holds only communication preferences. Durable guidance goes in repo docs: the workspace template is agentops/templates/workspace/AGENTS.agentops.md, re-rendered by scripts/render_workspace_agents.py --apply.
- Before large new changes, if context passes about 60%, write a handoff with the /handoff skill.

## Decisions

- **You own these orphan follow-ups** — No running session owns them, and each blocks or weakens the target state
- **Langfuse (appservice #1712, draft; agentops#2394): rework for durable storage before landing** — docs/scripts/rebuild/dynamic_pvc_allowlist.yaml:81-98 frames it as a disposable pilot with an expiry. Replace that with the normal PVC and backup path for ClickHouse and Valkey, remove the placeholder entries, then land it with the README prerequisites (langfuse-app SOPS secret, ClickHouse operator, authentik provider). The apps/kustomization wiring is the last step
- **Homelab Kubernetes phase drift** — Kubelets run v1.36.4 while KUBERNETES_VERSION pins v1.37.0; the Kubernetes phase was never run. Once the Talos session reports its disarm (it must not overlap), open a track per docs/talos-kubernetes-upgrade.md Step 2: arm, run, then disarm immediately (no self-clearing condition)
- **agentops handoff validate bug** — scripts/handoff.py diff_sha256 drops self-paths from `status --porcelain` but not from `git diff HEAD`, so a committed and then acked handoff invalidates itself. Hook-written untracked _artifacts audit shards move the digest on every session. Fix it with a test that fails today
- **hostproto Wave 1 (local branch land/wave1-mock-harness, 4ccb359, on 4 never-pushed main commits)** — `tools/devshell.sh node --test chrome/test/` FAILS; the other gates pass. Fix it, add the s2/item6-agentops-paths commit (only its AGENTS.md hunk differs), push, land. Confirm with the E1 successor first, because the ledger lists hostproto under the sweep
- **E1 follow-ups from #2514 note 3599 (vuoro-cloud)** — controller.migrate_tenant never re-applies the Deployment and reuses the Job name. Reconcile never writes tenant_schema_version. gateway.py:1116 hardcodes execution:* authorities. Legacy execution/knowledge roles remain on pre-roll tenants. Two gateway checks were never ported (nonblank audience; key-file vs configured pem match). Coordinate vuoro-cloud promotions with the E1 successor: one promotion pipeline, and YubiKey touches are the operator's

## Rejected

- **Landing Langfuse as an expiring pilot** — It conflicts with the 2026-09-22 design-for-use direction
- **Arming the Kubernetes phase alongside a Talos phase** — upgradesettings.yaml: never arm both in one commit; a control plane mid-reboot while another runs upgrade-k8s is the dangerous overlap

## Repo state

Digest definition: v3 (see the handoffs README).

| path | branch | head | dirty | unpushed | diff_sha256 |
|---|---|---|---|---|---|
| `/projects/dev/agentops` | main | `63e98d3c38a1` | yes | 0 | `a59dfacd3e942932…` |
| `/projects/dev/appservice` | main | `ad201c478b66` | no | 0 | `e3b0c44298fc1c14…` |
| `/projects/dev/vuoro-cloud` | main | `0a2dfbdd762f` | no | 0 | `e3b0c44298fc1c14…` |
| `/projects/dev/hostproto` | land/wave1-mock-harness | `4ccb35901e44` | yes | 5 | `618cddda24dc327e…` |

**Running:**

- E1 successor session 6ff8a58f (E1 steps 4-6, branch sweep).
- Talos rollout session b2ec1d19 in appservice.

## Unresolved

- Whether kctl agent/p2.2-schema-runtime-kctl is still needed before kctl retires in S4. It is listed in the sweep ledger; the E1 successor decides it from the S4 plan.

## Evidence

- sprintctl: `agentops#2514 notes 3597-3601; agentops#2394`
- artifact: `/projects/dev/agentops/docs/dispatch/handoffs/2026-09-23-e1-first-use-and-branch-sweep.v2.json`
- artifact: `/projects/dev/agentops/docs/dispatch/handoffs/2026-09-23-talos-1-14-1-fleet-rollout.v1.json`
- artifact: `/projects/dev/agentops/docs/dispatch/handoffs/2026-09-23-branch-sweep-ledger.md`

## sprintctl bundle

- none (sprintctl unavailable or produced no bundle)

## Successor

- session: 93862d02-be4d-4942-8361-d862b3765ec8
- acknowledged: 2026-09-23T17:03:43Z
