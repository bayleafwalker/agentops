# Handoff 2026-10-20-vuoro-cloud-release-resume.v1

<!-- Rendered from the canonical JSON beside this file. Do not hand-edit:
     `agentops handoff validate` and `ack` read the JSON, never this. -->

**Objective.** Promote all of vuoro-cloud main (incl. homepage PR #276) to production and RESUME the held estate (held since 2026-10-11/13 at signed tag v0.1.0-poc.76), using two signed tags: poc.77 = new image with tenant controller at replicas 0 (migrations 026-029 + same-image role probe), poc.78 = replicas 0->1. Then restore the traffic-gated workspace, the four scaled-down runtimes and the service controls, and verify live. Secondary: dispatch the Forgejo runner scale-out plan after poc.78 is verified; Sovite R4/S3 follow-on work.

**Next action.** Check PR #281 (https://git.apps.kotona.app/bayleaf/vuoro-cloud/pulls/281, head 07a6b8bd1ae2089b1cb74010eed823afee682509): at 20:03Z focused/integration/release-evidence were success and credential-free-gates pending. If not merged yet, when all four are success FF-merge it via the Forgejo API {"Do":"fast-forward-only","head_commit_id":"07a6b8bd..."} (token ~/.config/forgejo/admin-token, never print). Then re-run the local qualification receipt on merged main (see constraints), tell the operator a YubiKey PIN prompt plus two touches are coming, and run `scripts/promote-release.sh sha256:bc23edbff629296973f6f80ceef081e53bb89a9b464200657719ca08e822b09c` from a clean checkout of vuoro-cloud main.

## Predecessor

- harness: claude-code
- session: 61293f23-c813-4102-a5fe-e8f8dcbc9127
- model: claude-opus-5-5
- context used: unknown%
- transcript: /home/bayleaf/.claude/projects/-projects-dev-appservice/61293f23-c813-4102-a5fe-e8f8dcbc9127.jsonl
- origin: `workstation:/projects/dev/agentops/docs/dispatch/handoffs/2026-10-20-vuoro-cloud-release-resume.v1.json` (authoritative copy; an ack from another host goes through it)

Read-only after transfer: once a successor acks, the predecessor makes no
edits and takes no external actions. It stays consultable.

## Constraints

- Operator approvals given in chat this session (2026-10-20): production reads (DB queries, workspace maintenance inventory); the named CNPG backup and its verification; the controller role probe Job; `flux resume` of flux-system/vuoro-cloud-apps; per-workspace maintenance restore; FF-merging PR #276 and the image-pin PR into vuoro-cloud main; for poc.77 AND poc.78: running promote-release.sh, merging each candidate PR, dispatching promote-deployment. Operator: 'Production and merges to main are expected. Approved'. The auto-mode classifier blocks these unless the approval is visible; quote it if asked.
- vuoro-cloud: origin = canonical Forgejo (git.apps.kotona.app/bayleaf/vuoro-cloud), github = passive replica. main is protected and FF-only; merge via API {"Do":"fast-forward-only"}. Flux follows only signed semver tags v0.1.0-poc.N (TagAndHEAD verification); merging main deploys nothing by itself.
- Promotion signing key is on the owner's YubiKey (serial 22905026, fpr AB73C1C5617B5098038CDA953AF95EDEB8243BE7, GNUPGHOME=~/.config/vuoro/openpgp): owner types the PIN once, then two physical touches per promotion (commit + tag). Say when each touch is coming and wait. promote-release.sh takes the OCI index digest, ff-merges local main from canonical, makes a signed empty commit + signed tag (Deployment-Generation, OCI-Digest), pushes release/poc<N>-promotion-candidate, opens the PR. Then FF-merge the candidate PR (keeps signature) and dispatch: curl -X POST -H 'Authorization: token $(cat ~/.config/forgejo/workstation-scope-token)' .../actions/workflows/promote-deployment.yaml/dispatches -d '{"ref":"<tag>","inputs":{"deployment_tag":"<tag>","image_digest":"<digest>"}}' (204 = queued). promote-deployment copies the image to ghcr.io/bayleafwalker/vuoro-cloud.
- vuoro production access: `nmcli connection up vuoro-cloud-operator`, KUBECONFIG=/home/bayleaf/.config/vuoro/kube/poc.yaml (NOT the appservice kubeconfig). Control DB: `kubectl -n vuoro-data exec vuoro-postgres-1 -c postgres -- psql -d vuoro_control`. Network commands need the sandbox disabled.
- Unsuspending flux-system/vuoro-cloud-apps applies the migration Job AND the controller together (wait:false, no ordering). That is why poc.77 holds the controller at replicas 0. Never unsuspend while a tag with controller replicas 1 and an unverified migration is selected. Rollback is a NEW higher signed tag pinning the old digest (sha256:02b792fd...); the DB rollback is restoring backup vuoro-postgres-pre-poc77-202610201716.
- Do not run admin 2.3 `retire apply`: no Deployment runs the retire worker; queued work would block roll/transfer.
- Local qualification: `nix develop --command uv run --extra test python scripts/qualify_composition.py --postgres-bin /nix/store/szhijyida48s1sbdgjad0dcyaymgn426-postgresql-16.14/bin --controller-image-source 547af64e5e351eb74bd4b0a6b8fcba79650e78d6 --registry-token-file ~/.config/forgejo/registry-read-token --out .artifacts/qualification/receipt.json`; after migration add --live-probe .artifacts/qualification/controller-role-probe.log --live-pod .artifacts/qualification/controller-role-probe-pod.json (from scripts/run-controller-role-probe.sh, which refuses unless the controller is at 0), then `python scripts/qualification_receipt.py verify --require-release <receipt>`. Registry token is package:read only (verified); no admin-token fallback.
- Grade artifacts; never treat 'completed' as success. Never print tokens or secrets. Remove your own worktrees/branches after merge; merge your PRs after green CI.
- Sovite (appservice): Flux-owned; change procedure in appservice docs/runbooks/sovite-operations.md (edit .state/appservice-site -> render -> copy into GitOps via semantic diff -> mise run validate in a main worktree -> push -> reconcile -> re-probe egress -> update commissioning-evidence scope -> .state/renew-qualification.sh). Never call it production-qualified. Signing key stays in /projects/dev/sovite/.state/keys.
- appservice `mise run validate` must run in a worktree on branch main (/projects/dev/_wt/appservice-main exists). The /projects/dev/appservice checkout is on another branch with unrelated dirty files: do not touch.

## Decisions

- **Two signed tags (poc.77 staging with controller replicas 0, poc.78 resume replicas 0->1) instead of one tag from main** — Documented pattern (docs/plans/2645-*, 2646-hosting0194-staging-successor.md:211-224; precedent bf27c63 + 9905719) and run-controller-role-probe.sh refuses unless the controller is at 0; the probe's catalog check only passes after migration 029.
- **Pin the publish-image OCI INDEX digest sha256:bc23edbff629296973f6f80ceef081e53bb89a9b464200657719ca08e822b09c (built from main 547af64)** — poc.76 also pinned the index digest of its source build (sha-58ca400 -> 02b792fd); verified via registry HEAD.
- **Homepage copy for the resumed state (hero, Sovite wording, one illustration term) plus a neutral 'invitations paused' message on 503 mutations-frozen** — Operator chose 'Release and resume'; the paused message only shows if writes are frozen again.
- **Re-enable writes via the dashboard operator console (PATCH /api/control/v1/operator/service-controls), provisioning via CLI or console** — `vuoro-cli admin service-controls set` only sends provisioning by design; the console toggles all *_enabled.
- **Sovite hardening agreed: R4 removes DB URL/operator/caller tokens from worker pods; S3 routes hosted CLI compile/activate via the API; S4/S6 split DB roles** — Author/activator split holds only over the API; DB credentials are the trust root and workers currently get the full control env (chart sovite.runtimeEnv). Recorded in agentops #402.
- **Forgejo general runner: three replicas, one per worker, dind 4 CPU/6 GiB; dispatch after poc.78 verified** — Single runner queued vuoro PR CI ~40-75 min; changing CI mid-promotion risks the pipeline. Plan: /home/bayleaf/.local/state/vuoro-resume-20261020/plan.md.
- **Accept the dashboard withholding MCP connect guidance (capabilities.mcp_repository_binding not qualified; config/compatibility.json capabilities {})** — Honest gating; homepage FAQ still explains connecting.

## Rejected

- **One tag from main straight to resume** — Applies migration Job and controller replicas 1 together; probe and empty-outbox check cannot run first.
- **OAuth dynamic client registration** — Pre-registered clients only, by design (oauth_server.py, client-distribution-v1).
- **Raising the existing runner's capacity instead of more pods** — One dind daemon/node/disk; contention makes timing tests flakier (test_scenario_stale_success_is_refused flaked once).

## Repo state

Digest definition: v5 (see the handoffs README).

| path | branch | head | dirty | unpushed | diff_sha256 |
|---|---|---|---|---|---|
| `/projects/dev/_wt/vuoro-cloud-home` | release/poc77-staging-pins | `07a6b8bd1ae2` | no | 0 | `e3b0c44298fc1c14…` |
| `/projects/dev/_wt/appservice-main` | main | `e7b57c2be6d1` | no | 0 | `e3b0c44298fc1c14…` |

**Running:**

- Background watcher in the predecessor session (task buj7nwazg) will FF-merge PR #281 when CI is green; it dies with the predecessor session, so verify the PR state rather than assuming.
- Forgejo Actions has one general runner; vuoro PR CI ~15 min per run plus queue.

## Unresolved

- PR #281 merge (see next_action). After merge, re-run the local qualification receipt on merged main (the earlier receipt was on 07a6b8b's parent commit; all 21 scenarios passed, only blocker no-live-probe).
- poc.77: promote-release.sh (YubiKey), FF-merge candidate PR, dispatch promote-deployment, wait for the GHCR copy, then `flux resume ks vuoro-cloud-apps -n flux-system`. Verify: new migration Job UID, its imageID = bc23edbf, terminal success, schema_migrations = 24 baseline rows + exactly 026,027,028,029 (ledger column is `name`), ACL changes only the 028/029 grants, outbox still empty, control/admin/gateway pods on the new imageID, web serves the new landing ("Try the guided demo").
- Live probe: scripts/run-controller-role-probe.sh (controller at 0), then qualify_composition.py with --live-probe/--live-pod, then qualification_receipt.py verify --require-release.
- poc.78: pin commit changing only apps/tenant-controller/deployment.yaml replicas 0->1 (PR, CI, FF-merge), re-check empty outbox, promote-release.sh (YubiKey), merge, dispatch. Verify fresh controller pod logs vuoro-controller-preflight/v1 status pass migration_head 029 and manifest-loaded hash = compatibility ConfigMap; no VuoroCloudTenantControllerCrashLooping alert.
- Tenant restore: workspace 01M3ABJS1QW0Q6BNDCHP0DDTYF is traffic-gated (maintenance_mode+read_only) by operation 01M4P1CGVGDKWYTVSPC6YDKSKX (2026-10-11 17:50) -> `traffic-gates restore` with that engage id (admin-plane.md:604-631). Four other workspaces (01M14W25..., 01M3CA7V..., 01M43WES..., 01M4H11J...) are READY, not in maintenance, but their vuoro-service Deployments were scaled to 0 by kubectl patch (writer hold): check whether the resumed controller restores them; if not, find the documented restore path before scaling by hand.
- Service controls: baseline before freeze = signup true, mutations true, provisioning true (operation 01M4JE3EJR554S8BJ7Y1CAYF0B); frozen by 01M4NCMRH8XVNDAR2ZW5WYGQPA (mutations false, provisioning false). Restore after tenants verified; confirm with a fresh show. Then POST invite-requests should stop returning 503 mutations-frozen.
- Record the backup evidence on the server: `vuoro-cli admin backup record --evidence /home/bayleaf/.local/state/vuoro-resume-20261020/backup-evidence.json ...` (needs the admin UV login ceremony; pair with a YubiKey session).
- Post-checks: fresh-tenant provisioning, existing tenant reconcile, gateway /mcp, dashboard, a new completed backup; update vuoro-cloud IMPLEMENTATION-STATUS.md 'Current facts' (signed tag, image, live state) and write docs/evidence/<date>-poc77-78-resume.md.
- After poc.78 verified: dispatch the runner scale-out (plan at /home/bayleaf/.local/state/vuoro-resume-20261020/plan.md; summary in decisions).
- Sovite: main now at 1bd42db = 0.1.16 merged by ANOTHER session (PRs #2/#3 private-workflow, +2695 lines, not built or deployed). appservice runs 0.1.15 (cdcaa12, images runtime sha256:3dffb967..., codex sha256:f5c073ec...), qualification 8b25ed52 valid to 2026-10-27 17:08 UTC. Review 0.1.16 before any deploy. Next own work: R4 (with the agreed worker-credential removal), then S3.
- Cleanup: worktree /projects/dev/_wt/vuoro-cloud-home (branch release/poc77-staging-pins) after #281 merges; throwaway postgres container sovite-s1-pg (127.0.0.1:25432) when Sovite PG tests are done; operator VPN connection vuoro-cloud-operator when finished.
- Reference commits: vuoro-cloud 547af64e5e351eb74bd4b0a6b8fcba79650e78d6 (PR #276 merged; main); vuoro-cloud 07a6b8bd1ae2089b1cb74010eed823afee682509 (PR #281 head: staging pins + digest-agnostic receipt test); appservice e7b57c2b (sovite 0.1.15 deploy); sovite cdcaa12 (Release 0.1.15, S2); agentops PR #402 (plans: S2 release + agreed hardening)

## Evidence

- artifact: `/home/bayleaf/.local/state/vuoro-resume-20261020/prestate.txt`
- artifact: `/home/bayleaf/.local/state/vuoro-resume-20261020/backup-evidence.json`
- artifact: `/home/bayleaf/.local/state/vuoro-resume-20261020/plan.md`
- artifact: `/home/bayleaf/.local/state/vuoro-resume-20261020/receipt-local.json`
- artifact: `/home/bayleaf/.claude/projects/-projects-dev-appservice/memory/vuoro-cloud-held-resume.md`
- session: `61293f23-c813-4102-a5fe-e8f8dcbc9127`

## sprintctl bundle

- none (sprintctl unavailable or produced no bundle)

## Successor

- session: (unacknowledged)
- acknowledged: —
