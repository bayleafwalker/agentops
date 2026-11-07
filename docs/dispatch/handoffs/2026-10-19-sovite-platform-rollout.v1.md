# Handoff 2026-10-19-sovite-platform-rollout.v1

<!-- Rendered from the canonical JSON beside this file. Do not hand-edit:
     `agentops handoff validate` and `ack` read the JSON, never this. -->

**Objective.** Finish implementing and rolling in Sovite Platform 0.1.0 from the operator's three supplied files, with public source, private appservice deployment, real workload/recovery evidence, and landed GitOps.

**Next action.** After handoff ack and validation, run with exec_command sandbox_permissions=require_escalated: cd /projects/dev/sovite && .venv/bin/python .state/live_assessment.py poll ; then gh run list -R bayleafwalker/sovite --limit 2. Read this handoff's unresolved list and the task artifacts before making any qualification or deployment claim.

## Predecessor

- harness: codex
- session: unknown
- model: GPT-6
- context used: unknown%
- transcript: unknown
- origin: `workstation:/projects/dev/agentops/docs/dispatch/handoffs/2026-10-19-sovite-platform-rollout.v1.json` (authoritative copy; an ack from another host goes through it)

Read-only after transfer: once a successor acks, the predecessor makes no
edits and takes no external actions. It stays consultable.

## Constraints

- Latest user clarification: usual provisioning is PRIVATE DEPLOYMENT but PUBLIC SOURCE REPOSITORY. Source is now https://github.com/bayleafwalker/sovite (public); appservice is private. Do not return to private-source provisioning.
- User requested a handoff while rollout was active. No successor has been launched or acknowledged. Predecessor becomes read-only at successor ack.
- Follow /projects/dev/AGENTS.md and repository AGENTS.md. Use direnv exec /projects/dev/appservice for kubectl/flux; context admin@main and kubeconfig /projects/dev/appservice/clusters/.kube/config. Network commands require exec_command require_escalated; empty sandbox output is not evidence of absence.
- Commit/push/PR/merge/deploy are authorized by original task and workspace instructions. Do not ask for routine permission again. No subagents were authorized or spawned.
- Keep credentials out of transcripts and public source. Sovite .env, .state/runtime-kubernetes.json, .state/keys/qualification-private.pem are private host-persistent files. appservice runtime.secret.yaml is SOPS encrypted. Signer stays on workstation, never in API/worker/native workload.
- Do not touch unrelated changes in /projects/dev/appservice (feat/homelab-analytics-v0.1.3, dirty .claude/settings.local.json) or agentops (many preexisting files). Task-owned GitOps worktree is /projects/dev/appservice-sovite, now on main.
- Do not call this production-qualified: current bundle is development, with a one-day commissioning qualification explicitly excluding unobserved task competence and recovery. Finish observation before upgrading claims or enforced mode.
- This handoff and ignored Sovite .state are host-persistent, not cross-host replicated. Source commits are replicated. GitOps changes remain staged and uncommitted. Do not publish handoff/private site evidence into public agentops without separately sanitizing it.

## Decisions

- **Imported and hash-verified all 67 manifest-listed release files; source commits 1dc63da, 2ef7a48 and de4920d are pushed to public GitHub main.** — The supplied ZIP is a complete application, so work is integration and live qualification rather than rewriting it. Product/readiness documents are preserved as docs/PLATFORM-SPEC.md and docs/RELEASE-READINESS.md.
- **Installed six actual services in appservice namespace sovite: control, worker, native harness, Ollama, PostgreSQL and Garage; private HTTPS is https://sovite.apps.kotona.app.** — Existing live cluster, private Cilium Gateway API, Longhorn and registry are available. All six pods were Ready at handoff. Current deployment was applied directly for commissioning; Flux ownership is still to land.
- **Use existing internal registry with digest-pinned runtime and native images; upstream serving/state images also pinned.** — Runtime digest sha256:52edd55d49ef7dd4a52b9138bf9a72ea73b1edb88c3280e544925c09ec4e9f96; native sha256:6e5ae3b77d311ffd7e90721ee4fcb21ff2a9a8511a6d76db38f1b5ca1965c61e. All site pins are in private appservice docs/sovite/site.yaml. Application source inside images is the imported release; subsequent source changes are chart/scripts/tests/docs only.
- **Stage qwen3:4b outside inference, transfer model files into its PVC, give runtime no registry/Internet access.** — Observed model identity matches sha256:359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7. Actual GPU is shared GTX 1060 3GB, not a dedicated board; Ollama reports 35% CPU/65% GPU at 8192 context with 1GiB GPU overhead reserve.
- **Added chart support for runtimeClassName, GPU overhead, read-only approved ConfigMap input, exact Cilium gateway/API identities and persistence labels.** — Live worker API access failed with only CIDR policies; Cilium kube-apiserver identity fixed it. Native input is a synthetic retry_policy.py fixture. New render tests prove dual workspace sources and absent API bindings fail.
- **Observed worker allowed database/S3 and API reads in sovite, denied Internet/external DNS, foreign namespace pods and Secrets; native allowed model but denied database/S3/Internet and had no platform credentials.** — Actual packet/API negative checks, not inferred manifest guarantees. API reads returned sovite pods 200, default pods 403, sovite Secrets 403. Native state/Internet connections timed out; credential-presence Boolean was false.
- **Enrolled DB, Garage and native ledger in existing Longhorn backup-tier; model cache in scratch.** — Live Volume labels were inspected and match. Daily/weekly existing jobs cover backup-tier. No completed backup or restore for Sovite has yet been verified. Backup baseline updated for native ledger/cache.
- **Added scripts/qualify_kubernetes.py for workstation-held signing through loopback PostgreSQL tunnel.** — It verifies live runtime fingerprint and active generation; connects through localhost while signing the true deployment DB identity. Current one-day commissioning qualification ID da2e87b1b1164e8eb2bb0c73f6cf0116, runtime sha256:8615e5628db99ffe180e56c59ef8a018fc4e718a563311c9e88f467c0a15ac1d, generation sha256:2565701e726a7850cd78ae85cc021a4e0c9946cc92d4be4ec8fcc517bd961867. Expires epoch 1792524444.9971757 (2026-10-20 approximately 19:27 UTC).
- **Moved task-owned appservice worktree from feat/sovite-platform to main after fast-forwarding unused local main to fetched origin/main e7d92ce4.** — Required self-reference guard correctly rejects a composition declaring main when checked on a feature branch. Main was not checked out elsewhere. All staged task changes were preserved; temporary feat/sovite-platform branch can be retired after landing.

## Rejected

- **Private Forgejo source repository** — Initial auto-review required explicit destination approval; user approved, but fj repo create then failed for missing write:user and credctl explained repository-unregistered. User subsequently corrected policy to public source. Public GitHub creation/push succeeded. Do not broaden broker authority or use admin/personal token files.
- **Sandboxed pytest/network results** — Sandboxed pytest hung; stopped only task-owned PID 289294. Same release suite outside sandbox passed 40 tests in 9.69s. Both new deployment tests also passed. Network tools must be escalated.
- **Treating a free nvidia.com/gpu slot as exclusive hardware** — Probe showed one GTX 1060 3GB split into three time-slice slots, two already used by Jellyfin and Immich. Current Sovite allocation is shared and model partly CPU. Measure latency and do not claim dedicated GPU capacity.
- **CIDR-only Kubernetes API egress** — Live worker requests returned URLError. Added scoped Cilium kube-apiserver entity policy on 6443; then allowed and denied RBAC checks passed.
- **Blindly treating model tar pipeline as clean success** — Tar of the whole Docker-written cache had permission errors on optional metadata JSON and root directory timestamps. Blobs/manifests transferred; live ollama list verifies expected model and actual inference has loaded it. Future staging should transfer only required blobs/manifests using --no-same-owner --no-same-permissions --no-overwrite-dir and set -euo pipefail; independently verify digests.
- **Ignoring secret-scan finding or disabling hooks** — gitleaks flagged a SHA-256 for sovite/api.py in docs/STATE-INTEGRATION.json. Added exact path/line-specific allowlist in .gitleaks.toml; scans then passed.
- **Claiming full qualification from existing readiness records** — Archive evidence is upstream-local scope. Current cluster still needs completed model/native workloads, operator/browser verification, cancellation/recovery and backup/restore evidence.

## Repo state

Digest definition: v5 (see the handoffs README).

| path | branch | head | dirty | unpushed | diff_sha256 |
|---|---|---|---|---|---|
| `/projects/dev/sovite` | main | `de4920ddf01a` | no | 0 | `e3b0c44298fc1c14…` |
| `/projects/dev/appservice-sovite` | main | `e7d92ce42948` | yes | 0 | `95fb548ba9fa2f51…` |
| `/projects/dev/appservice` | feat/homelab-analytics-v0.1.3 | `45025128ecd2` | yes | 0 | `4ac8c43318b9d40d…` |
| `/projects/dev/agentops` | main | `47ddcab2c17c` | yes | 0 | `7779e6ffcc9482e9…` |

**Running:**

- Sovite six Ready cluster services in namespace sovite. Source current on public main de4920d. Site GitOps is not yet landed; do not assume Flux owns these live resources yet.
- Two generated commissioning tasks: incident running and native queued at last poll. Helper poll only reads status/artifacts and verifies audit; it saves completed synthetic artifact bodies under ignored .state.
- Loopback PostgreSQL port-forward: direnv exec /projects/dev/appservice kubectl -n sovite port-forward svc/sovite-postgres 15432:5432. Original unified exec session 25952; may survive handoff. Check before starting another.
- Stopped Docker model-staging container named sovite-model-stage remains; model cache .state/model-cache is host-persistent and partly root-owned. Temporary cluster staging pod was deleted. No staging Internet allowance exists in runtime policies.
- Public source GitHub Actions CI run 39311296727 may still be executing. All build and push processes are complete.

## Unresolved

- First priority: poll live commissioning tasks using the ignored .state/live_assessment.py helper. At 2026-10-19 about 19:28:50 UTC, incident job 9ae8e424747a48cfaff8a18c9fb6b1cf was running attempt 1 and native job c37fddc214a64919821da52dcb8790f1 queued attempt 0. Submitted about 19:27:25 UTC. One worker processes sequentially. Inspect resulting artifacts in .state/artifact-<grant>.json, test truthful namespace tool use and native fixture answer 96 seconds/source lines. Do not print production bodies; these fixtures are synthetic.
- Observe actual bounded/native task latency and failures. Native service suppresses Codex stdout/stderr in adapters.py; if native_runtime_failed, reproduce diagnostically inside its isolated pod without adding platform credentials or disabling boundaries. Native uses --sandbox read-only, temporary HOME and fixed Responses provider. Container bubblewrap compatibility has not yet been demonstrated.
- Source CI run 39311296727 for de4920d was in_progress at handoff; previous run 39310532727 passed. Full original 40 tests and new 2 render tests passed locally. Need check new CI and any later source changes.
- Appservice full required mise run validate passed in 46.73s after fixes (366 rebuild tests + existing guards etc). /tmp/sovite-appservice-validate.log. All 10 changed files are staged, NOT committed or pushed. Review, document actual evidence and land through standard CI path; if branch protection requires PR create/merge it. Then reconcile Flux source cluster and flux-entry; verify sovite Kustomization and services remain healthy. Finish by removing task-owned worktree/retiring temporary branch, preserving unrelated original checkout.
- Need live cancellation, inhibit/resume and receipt revocation, state restart, expired lease/uncertain-effect recovery where suitable, and backup/isolated restore. Current qualification is commissioning-only. Do not sign required enforced checks that have not passed. An enforced transition changes generation/runtime binding and requires new evidence and explicit bundle reload through CLI; startup intentionally does not reload an existing active generation.
- Need operator console browser check on deployed site and scoped caller integration instructions. No browser tools were available. node is absent from bare shell but project mise environments provide it. Potential existing Playwright projects: /projects/dev/cv-studio/tests/e2e, /projects/dev/homelab-analytics/apps/web/frontend, /projects/dev/browser-workbench/oracle/playwright. No new user-level Codex config or caller token provisioning was done.
- Write private appservice operations/runbook and actual deployment evidence; keep public source free of site credentials/internal evidence. Site values/bundle/review live under appservice-sovite/docs/sovite and ignored source .state/appservice-site. Rendered appservice platform.yaml has explicit namespaces added to reviewed output for offline guards, and is owned by Flux Kustomize, not a simultaneous Helm release.
- Signing key and private runtime JSON currently host-persistent under ignored .state; encrypted runtime secret is staged in private GitOps. Decide/document signer recovery custody; do not silently put signing private key into cluster or public Git.
- Stop task-owned loopback DB tunnel when no longer needed and remove stopped Docker container sovite-model-stage if appropriate. No production data or other namespaces were modified by assessment.

## Evidence

- artifact: `/home/bayleaf/Sovite-Platform.md`
- artifact: `/home/bayleaf/Sovite-Platform-0.1.0.zip`
- artifact: `/home/bayleaf/Sovite-Readiness.md`
- artifact: `/projects/dev/sovite/docs/PLATFORM-SPEC.md`
- artifact: `/projects/dev/sovite/docs/RELEASE-READINESS.md`
- artifact: `/projects/dev/sovite/.state/live_assessment.py`
- artifact: `/projects/dev/sovite/.state/live-tasks.json`
- artifact: `/projects/dev/sovite/.state/commissioning-evidence.json`
- artifact: `/projects/dev/sovite/.state/appservice.rendered.review.json`
- artifact: `/projects/dev/appservice-sovite/docs/sovite/site.yaml`
- artifact: `/projects/dev/appservice-sovite/clusters/main/kubernetes/apps/sovite/app/platform.yaml`
- artifact: `/tmp/sovite-tests.log`
- artifact: `/tmp/sovite-appservice-validate.log`

## sprintctl bundle

- none (sprintctl unavailable or produced no bundle)

## Successor

- session: c254db4b-5e24-4059-b3c9-3bad96c4a731
- acknowledged: 2026-10-19T19:31:47Z
