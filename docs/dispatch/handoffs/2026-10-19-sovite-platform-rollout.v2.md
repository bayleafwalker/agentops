# Handoff 2026-10-19-sovite-platform-rollout.v2

<!-- Rendered from the canonical JSON beside this file. Do not hand-edit:
     `agentops handoff validate` and `ack` read the JSON, never this. -->

**Objective.** Finish rolling in Sovite Platform (now 0.1.1) on appservice: public source, private Flux-owned deployment, real workload competence and recovery/restore evidence, then decide whether qwen3:4b on the shared GTX 1060 is fit for purpose.

**Next action.** cd /projects/dev/sovite && .venv/bin/python .state/live_assessment.py poll  (sandbox disabled); when both v5 tasks are terminal, grade .state/artifact-incident-forensics.json and .state/artifact-native-code-review.json against the expected answers before any claim.

## Predecessor

- harness: claude-code
- session: c254db4b-5e24-4059-b3c9-3bad96c4a731
- model: claude-opus-5-5
- context used: unknown%
- transcript: unknown
- origin: `workstation:/projects/dev/agentops/docs/dispatch/handoffs/2026-10-19-sovite-platform-rollout.v2.json` (authoritative copy; an ack from another host goes through it)

Read-only after transfer: once a successor acks, the predecessor makes no
edits and takes no external actions. It stays consultable.

## Constraints

- Public source (github.com/bayleafwalker/sovite), private deployment (appservice). Do not move source to private Forgejo.
- Commit/push/deploy are approved; land appservice changes by pushing to main after `mise run validate`. Before rebasing onto a moved origin/main, inspect incoming commits and file overlap first (the auto-mode classifier refuses blind rebase+push).
- kubectl/flux only via `direnv exec /projects/dev/appservice ...` (context admin@main). Network commands need sandbox disabled; empty sandboxed output is not evidence.
- Flux now owns sovite (Kustomization flux-system/sovite, path clusters/main/kubernetes/apps/sovite/app). Change config by: edit /projects/dev/sovite/.state/appservice-site/{bundle,site}.yaml -> render -> copy into GitOps -> push -> reconcile -> `sovite reload` -> re-qualify. Procedure in appservice docs/runbooks/sovite-operations.md. Do not kubectl apply platform.yaml by hand any more.
- Any bundle or image change invalidates the qualification (platform reports qualified:false and refuses work) until re-signed with scripts/qualify_kubernetes.py through the loopback DB tunnel.
- Signing key stays on the workstation (.state/keys); never in cluster, Secret or Git. .state, .env and runtime-kubernetes.json are private host-persistent files; keep credentials out of transcripts and public source.
- Do not call this production-qualified. Qualification is one-day development commissioning only (current id a9fc34cfa3eb43368e3acfa2845a9e79, expires ~2026-10-20 20:45 UTC); its scope excludes task competence and recovery.
- Changing application code (sovite/*.py) is a release: bump version everywhere listed in commit 289ae3a, regenerate RELEASE-MANIFEST.json with scripts/package_release.py (extract with python zipfile; unzip is not installed), rebuild both images (--target runtime and --target native-codex) to 192.168.20.221:5000 and pin digests in site.yaml.
- Do not touch unrelated work: /projects/dev/appservice (feat/homelab-analytics-v0.1.3, dirty .claude/settings.local.json), agentops preexisting changes, sovite untracked .auditctl/ and _artifacts/.

## Decisions

- **Model call timeout 600s, grant timeouts 1800s, worker.jobTimeoutSeconds 1800 (new chart value, source faa2255)** — Ollama logged POST /api/chat 500 at exactly 2m0s: default 120s model timeout; and the worker silently capped every job at 300s (SOVITE_JOB_TIMEOUT_SECONDS unset). Measured ~5-8.6 tok/s on the shared GPU.
- **Reasoning kept ON: local-reasoner think:true, native-reasoner reasoning_effort:low, bounded num_predict 4096** — Direct probe: with think:false / effort:none qwen3:4b on Ollama 0.40.6 writes reasoning into content and emits no structured tool call (tasks 'completed' with zero tool use). Only reasoning-on produced tool calls. At num_predict 2048 the bounded call spent all output on reasoning (model_empty_result).
- **Released 0.1.1 (source 289ae3a + d192717, CI green): native Codex gets -c web_search="disabled"; malformed tool calls are returned to the model as an error instead of failing the task** — Round 3 native looped on Codex web_search (Ollama 403, no Internet by design) then exited non-zero -> external_execution_uncertain. Round 4 bounded made a tool call with an extra namespace key -> whole job failed invalid_tool_arguments. Malformed calls are still never executed; undeclared tools and denied operations stay fatal. Operator approved the release.
- **Landed GitOps under Flux: appservice ed2be7bd, b1dd9e29, b0a2f1f5, 0222a3f0 on main** — Takeover was a no-op for pod templates; encrypted runtime Secret hash-matched the live Secret on 9/9 keys. Live images: runtime sha256:2c5e3c860bdd6670764babe387bef83b7c3118355b52d37dcae97415629ba44a, native sha256:9aff6cde4d4f433e9150a04aa6ac32bf5ff014cb4b4da60d1b75a470a1c36d2b. Active generation sha256:40495a9c6e8504de5830440e21011286c2e18f0852a11ebc770500b900c29ba9.
- **Wrote private runbook appservice docs/runbooks/sovite-operations.md (render/activate/qualify procedure, signer custody, capacity and reasoning findings)** — Procedure previously existed only in a Codex transcript.
- **Helper .state/live_assessment.py: `submit [grant]` submits one or both; idempotency keys now -v5; prior rounds' receipts in .state/live-tasks.v1..v4.json and artifacts *.v2.json** — Each round needs fresh keys; re-run only the grant under test to save shared-GPU time.

## Rejected

- **think:false / reasoning_effort:none to save tokens** — Kills structured tool calls with qwen3:4b on Ollama 0.40.6 (probed directly). Do not retry.
- **num_predict 1024 or 2048 with thinking on (bounded)** — 2048 returned only reasoning -> model_empty_result. 4096 is the current value.
- **Treating 'completed' as success** — Rounds 1-2 completed with zero tool calls and wrong answers. Always grade the artifact: incident must name real pods from a kubernetes-read call; native must report 96 seconds with source lines from retry_policy.py.
- **Disabling web_search via bundle/config without code** — Native HOME is a fresh temp dir and env is explicitly constructed; only the adapter command line can set it (now done in 0.1.1).
- **pkill -f with a pattern that also appears in the running bash command** — Killed its own shell (exit 144). Use pgrep and kill by PID.

## Repo state

Digest definition: v5 (see the handoffs README).

| path | branch | head | dirty | unpushed | diff_sha256 |
|---|---|---|---|---|---|
| `/projects/dev/sovite` | main | `d19271707c63` | yes | 0 | `258f357da31ed1fe…` |
| `/projects/dev/appservice-sovite` | main | `0222a3f06fdb` | no | 0 | `e3b0c44298fc1c14…` |
| `/projects/dev/appservice` | feat/homelab-analytics-v0.1.3 | `45025128ecd2` | yes | 0 | `4ac8c43318b9d40d…` |
| `/projects/dev/agentops` | main | `fa674a80ee2d` | yes | 0 | `82614da0657a481b…` |

**Running:**

- Round 5 Sovite tasks in namespace sovite (incident running, native queued behind it; one worker, sequential). Native may take up to ~30 min.
- Loopback PostgreSQL port-forward on 127.0.0.1:15432 (kubectl -n sovite port-forward svc/sovite-postgres), owned by predecessor session c254db4b as a background task; it dies with that session. Check with `pgrep -af 'port-forward svc/sovite-postgres'` and restart if absent.
- A read-only background poll loop in the predecessor session; harmless.

## Unresolved

- FIRST: grade round 5 (submitted 2026-10-19 20:45:33 UTC on 0.1.1). At 20:54 UTC incident 2dd86164458f4c2b92d6844b5921a043 was running attempt 1 (>9 min, implying multiple turns), native 99594af5531345d880ab35e50f492be1 queued. Run poll; inspect .state/artifact-<grant>.json (trace/steps for incident; answer for native) and Ollama POST timeline (`kubectl -n sovite logs deploy/sovite-ollama | grep 'GIN.*POST'`).
- If round 5 still fails competence: the remaining lever is the model/hardware (qwen3:4b, ~17/37 layers on a time-sliced GTX 1060 3GB shared with Jellyfin/Immich, 4-9 min per turn). Give the operator concrete options (larger/other local model, dedicated GPU, accept bounded-only) with measured latencies and a recommendation; do not keep iterating blind.
- Check appservice Offline Validate CI for 0222a3f0 (State protocol contracts passed; Offline Validate not seen in the last listing).
- Still not done: live cancellation, inhibit/resume, receipt revocation, state restart, lease/uncertain-effect recovery, backup and isolated restore (no Sovite backup/restore verified yet), operator console browser check, scoped caller integration instructions.
- Cleanup when finished: stop the loopback PostgreSQL port-forward (localhost:15432; restarted by the predecessor session as a background task), remove stopped Docker container sovite-model-stage, retire the temporary feat/sovite-platform branch and the /projects/dev/appservice-sovite worktree (now clean on main == origin/main).

## Evidence

- artifact: `/projects/dev/appservice-sovite/docs/runbooks/sovite-operations.md`
- artifact: `/projects/dev/appservice-sovite/docs/sovite/deployment-review.json`
- artifact: `/projects/dev/sovite/.state/live_assessment.py`
- artifact: `/projects/dev/sovite/.state/live-tasks.json`
- artifact: `/projects/dev/sovite/.state/commissioning-evidence.json`
- artifact: `/projects/dev/sovite/.state/artifact-native-code-review.v2.json`
- artifact: `/projects/dev/sovite/.state/artifact-incident-forensics.v2.json`
- artifact: `/projects/dev/agentops/docs/dispatch/handoffs/2026-10-19-sovite-platform-rollout.v1.md`
- session: `claude-code c254db4b-5e24-4059-b3c9-3bad96c4a731`

## sprintctl bundle

- none (sprintctl unavailable or produced no bundle)

## Successor

- session: 61293f23-c813-4102-a5fe-e8f8dcbc9127
- acknowledged: 2026-10-20T05:13:43Z
