# Handoff 2026-09-23-e1-first-use-and-branch-sweep.v1

<!-- Rendered from the canonical JSON beside this file. Do not hand-edit:
     `agentops handoff validate` and `ack` read the JSON, never this. -->

**Objective.** Take E1 (agentops#2514) from platform-live to first use: land vuoro-cloud #85 and #86 (owner repository binding), promote the new image as poc.36, then walk the operator through creating workspace 'kotona' with repo 'vuoro', run the MCP tools/list check, do the D-044 proofs and connector registration. In parallel, finish the workspace-wide branch sweep from the ledger (every branch lands on main or is retired; checkouts and worktrees match their remote).

**Next action.** Check vuoro-cloud #85 CI (`fj -H git.apps.kotona.app pr status bayleaf/vuoro-cloud#85`). When all four checks pass, ff-merge it. Then rebase #86 (/projects/dev/_wt/vuoro-cloud-binding) onto origin/main, push --force-with-lease, wait for CI, ff-merge, and begin the poc.36 promotion (new image digest, pin commit on local main, rehearse, then promote-release).

## Predecessor

- harness: claude-code
- session: b2bee73e-4813-422f-b4c9-a9ed0b3cb894
- model: claude-opus-5-5
- context used: unknown%
- transcript: unknown
- origin: `workstation:/projects/dev/agentops/docs/dispatch/handoffs/2026-09-23-e1-first-use-and-branch-sweep.v1.json` (authoritative copy; an ack from another host goes through it)

Read-only after transfer: once a successor acks, the predecessor makes no
edits and takes no external actions. It stays consultable.

## Constraints

- Design for use, not disposal: no trial counters, phase clocks or expiring pilots. GitOps rollback is the reversibility.
- vuoro.cloud deploys go through `scripts/promote-release.sh DIGEST`, run from the vuoro-cloud main checkout (it builds on LOCAL main). The YubiKey is plugged in: say a touch is coming and run it; do not wait for a 'go'. If the image changes, commit 'Pin the workload manifests to the generation N image' (the four apps/ manifests to ghcr.io/bayleafwalker/vuoro-cloud@sha256:<forgejo digest>) on local main BEFORE running the script. Rehearse the candidate in a throwaway clone first. Never run a touch step in the same tool batch as a step it depends on.
- Dispatch promote-deployment with POST .../actions/workflows/promote-deployment.yaml/dispatches {ref:main, inputs:{deployment_tag, image_digest}} (the fj dispatch returns 500). Verify at the artifact: pod imageIDs, Job status, rollout/status, then the live endpoint.
- Every guard is forced into its failure case before it is trusted.
- vuoro-cloud: canonical origin is Forgejo; land with a fast-forward-only REST merge (credctl exec pr.merge ... {"Do":"fast-forward-only"}). Rebase before merging when main has moved. GitHub repos: gh pr merge (agentops uses --merge; appservice, vuoro and auditctl use --squash).
- The auto-mode classifier blocks bulk git deletions, flag flips and secret-store writes from the agent. Hand those to the operator as ONE exact `!` command, or a frozen-list script built from LIVE refs; never route around them.
- Reports state what was decided and done. Only permission-blocked or hardware steps go to the operator, as exact commands in one place. Do not write incident recordings into Claude memory: durable guidance goes in repo docs.
- The Talos v1.14.1 fleet rollout is owned by another session (handoff 2026-09-23-talos-1-14-1-fleet-rollout.v1, launched in appservice as claude session b2ec1d19). Do not touch the appservice Talos pins or upgrade gates.

## Decisions

- **vuoro.cloud runs v0.1.0-poc.35 (image 3ccd4434): tenant runtime vuoro-service 0.1.73 (work+audit only, tenant_schema 2, generation 2), MCP edge flag on, OAuth clients file mounted** — Verified live: /oauth/authorize for claude-connector returns 303 to GitHub sign-in; an unregistered client gets 400; rollout generation 2 has converged. Notes 3598-3601 on #2514
- **PR #86 (branch e1-owner-repo-binding): add_repository fills an omitted descriptor.project_id from the workspace's project, and the dashboard gains a Bind repository form** — No owner could bind a repository: project_id is never returned to a browser session and vuoro-bootstrap was deleted. The test fails with the fill removed and with the mismatch guard removed
- **Branch sweep: five repos done; the other repos are classified in the ledger with decided actions** — Operator rule 2026-09-23. Deletion tips are logged for restore
- **Langfuse (appservice #1712, draft) must be reworked for durable ClickHouse/Valkey storage before landing** — dynamic_pvc_allowlist.yaml frames it as a disposable pilot with an expiry, which conflicts with design-for-use
- **Memory holds only communication-preferences and model-tiering; durable guidance moved to the workspace template (agentops #242), vuoro-cloud CLAUDE.md (#85), appservice docs (#1713) and auditctl (#18)** — Operator: memory is for communication preferences only

## Rejected

- **Running promote-release.sh straight on main without the pin commit** — validate-deployment-distribution refuses a tag whose commit's manifests pin a different digest. Four YubiKey touches were wasted on poc.34 twice
- **A standalone pin-commit PR** — It fails CI because the newest tag still records the old digest. The pin goes in the promotion PR itself, directly under the signed candidate
- **Landing sprintctl devbox-orphan (Forgejo upload-artifact pin)** — sprintctl CI runs on GitHub Actions, which cannot resolve a code.forgejo.org action URL. Retired
- **Rebasing sprintctl dispatch-ready-20260808** — Its extraction landed; its claimcore targets the claim model main deleted. Retired
- **Landing Langfuse with the pilot exception confirmed** — An expiring pilot is exactly the disposal framing the operator rejected
- **Claiming hostproto Wave 1 passes all gates** — node --test chrome/test/ FAILS. The commit message was corrected before any push

## Repo state

Digest definition: v3 (see the handoffs README).

| path | branch | head | dirty | unpushed | diff_sha256 |
|---|---|---|---|---|---|
| `/projects/dev/vuoro-cloud` | main | `0a2dfbdd762f` | no | 0 | `e3b0c44298fc1c14…` |
| `/projects/dev/agentops` | main | `63e98d3c38a1` | yes | 0 | `80398663e9a1b7f3…` |
| `/projects/dev/appservice` | main | `ad201c478b66` | no | 0 | `e3b0c44298fc1c14…` |
| `/projects/dev/hostproto` | land/wave1-mock-harness | `4ccb35901e44` | yes | 5 | `618cddda24dc327e…` |

**Running:**

- vuoro-cloud PRs: #85 (pem ignore + Actions-log route; 3/4 checks green, credential-free-gates pending) and #86 (owner repository binding; CI pending, needs a rebase after #85 lands).
- appservice #1712 Langfuse: draft, held for the durable-storage rework.
- Talos rollout session b2ec1d19 in appservice (separate owner).
- Worktrees still held for pending work: /projects/dev/_wt/vuoro-cloud-docs (#85), /projects/dev/_wt/vuoro-cloud-binding (#86), /projects/dev/_wt/vuoro-cloud-runtime-pin (on e1-oauth-clients, landed; remove), /projects/dev/_wt/agentops-guidance (landed; remove), /projects/dev/_wt/appservice-docs (landed; remove), /projects/dev/_wt/appservice-talos (landed; remove once the Talos session no longer needs it). hostproto checkout is on branch land/wave1-mock-harness (local, unpushed).

## Unresolved

- E1 step 4 is operator-only after #86 is deployed. They sign in at vuoro.cloud (/join with an invitation if not yet a user: POST /api/control/v1/operator/invitations with the operator token, control.py:1272), create workspace 'kotona', and bind repo_id 'vuoro' with git remote https://github.com/bayleafwalker/vuoro. Check: the workspace reaches READY; namespace vuoro-ws-<id[:12]>; the pod shows two ready containers.
- E1 steps 5-6: D-044 live proofs (tenant isolation, restore drill; each forced to fail first). Then the operator registers the claude.ai connector (client id claude-connector; secret at ~/.config/vuoro/credentials/claude-connector.secret). First use ends in a PR in an operator repo, which closes #2514. Also capture which MCP protocol revision the connector sends.
- Pre-existing test tenant vuoro-ws-01m14w25eykc is still on vuoro-service 0.1.52 until its next reconcile event.
- Kubernetes phase drift on the homelab (kubelet v1.36.4 against pin v1.37.0) is out of scope for the Talos session. It needs its own track.
- agentops handoff validate bug: diff_sha256 excludes self-paths from `status --porcelain` but not from `git diff HEAD`, and hook-written untracked audit shards move the digest. Not filed yet.
- Follow-ups from note 3599: migrate_tenant never re-applies the Deployment; reconcile does not write tenant_schema_version; gateway.py:1116 execution:* authorities; legacy execution/knowledge roles on pre-roll tenants; the two unported gateway checks from the retired codex branch (nonblank audience, key-file vs pem match).

## Evidence

- sprintctl: `agentops#2514 notes 3597-3601`
- artifact: `/projects/dev/agentops/docs/dispatch/handoffs/2026-09-23-branch-sweep-ledger.md`
- artifact: `/projects/dev/_artifacts/agentops/branch-sweep-2026-09-23/retired-branches.tsv`
- artifact: `/projects/dev/agentops/docs/dispatch/handoffs/2026-09-23-talos-1-14-1-fleet-rollout.v1.json`

## sprintctl bundle

- none (sprintctl unavailable or produced no bundle)

## Successor

- session: (unacknowledged)
- acknowledged: —
