# Handoff 2026-09-24-program-long-goal-handler.v5

<!-- Rendered from the canonical JSON beside this file. Do not hand-edit:
     `agentops handoff validate` and `ack` read the JSON, never this. -->

**Objective.** Hold the long goal: E1 (agentops#2514) reaches first use -- promote vuoro-cloud main 5015deb to the PoC as generation 40 (pin + YubiKey-signed candidate), then the D-044 proofs (restore drill, live tenant isolation), claude.ai connector registration and the first-use PR.

**Next action.** Ask the operator whether to proceed with stage 2 (the generation-40 promotion). The pin write was classifier-denied as [Production Deploy] and needs the operator's go-ahead. On yes: worktree off origin/main, change the image digest in apps/control/deployment.yaml, apps/control/migration-job.yaml, apps/gateway/deployment.yaml and apps/tenant-controller/deployment.yaml from sha256:a085d6201b4507aa3cf5ebef57950299b9d35c7281801142be9bf25d62629f71 to sha256:93ba86889176fce19601a7160fd586e742a2074679ff114c26051dcf1091ce3d. Use a commit message in the format of 25c5569, run scripts/verify-runtime-pin.py plus check-fast, and open the PR via the Forgejo API. After CI is green, credctl ff-merge it. Then hand the operator `scripts/promote-release.sh <digest> 40` marked RUN NOW (YubiKey: PIN once, two touches), merge the candidate, dispatch promote-deployment via the API (204), and verify at the artifact.

## Predecessor

- harness: claude-code
- session: b31c04da-6750-4f0a-8865-6e0708e46da7
- model: unknown
- context used: unknown%
- transcript: unknown
- origin: `workstation:/projects/dev/agentops/docs/dispatch/handoffs/2026-09-24-program-long-goal-handler.v5.json` (authoritative copy; an ack from another host goes through it)

Read-only after transfer: once a successor acks, the predecessor makes no
edits and takes no external actions. It stays consultable.

## Constraints

- Merge approval for this program was given by the operator on 2026-09-24 for session b31c04da. It does not transfer; ask again.
- The classifier denies many merge, push and deploy actions even with operator approval and allow rules. On a denial, stop, give the operator one exact ! command with its precondition and expected result, and never route around it. The operator can also grant a retry, after which the same command may be re-run.
- Merge only after every CI check passes. vuoro-cloud is fast-forward-only: `credctl merge --repository forgejo:bayleaf/vuoro-cloud --pr N --head-sha <40-char sha> --style fast-forward-only --forgejo-url https://git.apps.kotona.app`. appservice: `gh pr merge N --squash --match-head-commit <sha>`. Read full SHAs from the API; never type them from memory.
- Never dereference Secret/SOPS values, PATs or invitation codes into the session. The operator mints PATs and invitations in their own terminal (not via !).
- YubiKey signing (promote-release.sh) is the operator's and is handed over only when due, marked RUN NOW.
- Force every guard into its failure case before trusting it. Verify at the artifact (cluster, registry, API), not from a report.
- Keep the operator's prompt free: every wait runs as a background task, and the turn ends right after launching it.
- Use the global git identity only. Work in scratchpad worktrees off origin/main; never edit or pull the shared checkouts; never run a bare git stash.
- Run `ruff format` before check-fast in vuoro-cloud. Forgetting it failed CI once this session.
- Memory holds only communication preferences; durable guidance goes in repo docs.

## Decisions

- **vuoro-cloud main = 5015debd2a68054d0cadbff537d0de76f14f8ffc: #100 isolation tests, #101 onboarding UI, #102 invite approval issues the code (+ declined/spam expires the unredeemed code), #103 restore-drill tooling (+ a crash exits 2; --restored re-checks comparison.match and file sha256; runbook rewritten for the direct-invoke PAT path), #104 front-page refresh (+ invitation lifetime is 7 days), #105 existing members get a browser session on GitHub sign-in, #106 D-047 PAT authorities** — landed as one linear stack. The operator chose to run CI once on the combined tip (all 4 checks green, 20:35Z) instead of per PR. Locally on the tip: 270 unit + 172 integration + 37 security/drill tests passed.
- **Generation-40 image = sha256:93ba86889176fce19601a7160fd586e742a2074679ff114c26051dcf1091ce3d (git.apps.kotona.app/bayleaf/vuoro-cloud:sha-5015debd…, publish success)** — read from the Forgejo registry per the standing decision. ghcr.io returns 403 anonymously even for the live poc.39 digest, so it cannot be checked there.
- **D-047 (vuoro-cloud #106): new device-flow PATs carry work:read, work:write, work:sprint and work:lifecycle. Existing tokens are unchanged (tested). work:evidence, batch, maintenance and project authorities are still refused. Read-only workspaces now strip every mutating authority (is_mutating_authority), not only *:write** — operator-direction option A-prime chosen by the agent over A (which would silently widen existing work:write tokens) and B (which needs a cookie and CSRF in a shell).
- **#105 member re-sign-in: a user suspended from one workspace still gets a session, but that workspace is unreachable (empty list / 404)** — there is no user-level suspended state. Refusing users with no active membership would lock out newly admitted users. The recommendation to keep this was given; the operator did not object.
- **appservice #1764 apiserver-egress-guard, #1765 guard FAILs on unparseable policy files, #1766 forgejo runners use an emptyDir dind cache + soft anti-affinity to the openbao leader** — all merged. #1766 verified live: runners on worker-2/worker-3, no dind PVCs, worst Longhorn write latency 1297ms -> 6ms, no OpenBao persist errors.
- **Root cause of the 19:34-19:40Z cred-broker 500s: OpenBao leader openbao-1 (gpu-1) Raft writes timed out ('failed to persist entry: context canceled') while CI dind caches on 2-replica Longhorn volumes, whose replicas sat on the two openbao follower nodes, saturated disks** — fixed by #1766. The broker's catch-all 500 logs nothing, so diagnose via openbao logs and Longhorn latency in Prometheus.
- **agentops #246: handoff-session-start hook is registered globally in ~/.claude/settings.json (the project-level entry was removed). The fix matches subdirectories and skips superseded and abandoned handoffs** — verified live from agentops, a subdirectory and ~.
- **~/.claude/settings.json allow rules added: Bash(gh pr merge * --squash --match-head-commit *), Bash(credctl merge --repository forgejo:bayleaf/vuoro-cloud *), Bash(kubectl -n * get *)** — operator request. The kubectl rule is over-broad ('kubectl -n x delete pod get y' matches it); the operator was told and left it.

## Rejected

- **Forgejo auto-detection of manually merged PRs** — not enabled for vuoro-cloud. Pushing #102-#105 branches to commits already in main did not mark them merged.
- **Agent calling the POST /pulls/N/merge {Do: manually-merged} API** — classifier-denied [Merge Without Review]. The operator runs it.
- **Agent pushing a combined stack under one PR's CI** — classifier-denied [CI Bypass]. The operator ran the push.
- **Waiting for an idle Forgejo CI queue before merging** — the queue never drains while PR pushes keep arriving. Fix the storage contention instead (#1766).
- **Guessing a 40-char SHA in an operator command** — the agent printed a wrong full SHA once this session. Always read it from the API.

## Repo state

Digest definition: v4 (see the handoffs README).

| path | branch | head | dirty | unpushed | diff_sha256 |
|---|---|---|---|---|---|
| `/projects/dev/agentops` | main | `bcb2d4c73326` | yes | 0 | `c997499ae7d74361…` |
| `/projects/dev/vuoro-cloud` | main | `12786cebb40b` | no | 0 | `e3b0c44298fc1c14…` |
| `/projects/dev/appservice` | main | `ad201c478b66` | no | 0 | `e3b0c44298fc1c14…` |

**Running:**

- Nothing is running. All background jobs and subagents of session b31c04da have finished. All scratch worktrees of sessions b31c04da and 7c828907 were removed.
- CI runs queued on vuoro-cloud PR branches #102-#105 by the bookkeeping push; they finish by themselves and do not affect main.

## Unresolved

- OPERATOR BOOKKEEPING: vuoro-cloud #102-#105 still show open/unmerged although their heads (8aa576c, 7eb4449, f56305b, 9decdaf) are in main 5015deb. Command: T=$(cat ~/.config/forgejo/workstation-scope-token); for n in 102 103 104 105; do curl -sS -o /dev/null -w "$n %{http_code}\n" -X POST -H "Authorization: token $T" -H 'Content-Type: application/json' https://git.apps.kotona.app/api/v1/repos/bayleaf/vuoro-cloud/pulls/$n/merge -d '{"Do":"manually-merged","MergeCommitID":"5015debd2a68054d0cadbff537d0de76f14f8ffc"}'; done -- expect 200 each.
- STAGE 2 (next): generation-40 promotion, waiting on operator go-ahead (see next_action). Ships the full stack incl. migration 013 (one nullable column on invite_requests) and the web front (nginx CSP style-src 'self', checksum annotation recomputed). Verify after deploy: control/gateway x2/tenant-controller on 93ba…, 0 restarts, migrate Job Complete, Flux at the new tag, unauthenticated POST https://api.vuoro.cloud/mcp -> 401 with resource_metadata, front page served with /landing.css.
- STAGE 3a restore drill (after gen 40): follow docs/runbooks/restore-drill.md on main. The operator mints a device-flow PAT into ~/.config/vuoro/credentials/kotona-vuoro.token (+ a header file, umask 077) in their own terminal, then creates the drill sprint + 3 'DRILL restore $D' items via direct POST https://api.vuoro.cloud/api/invoke/v1 (X-Vuoro-Client-Protocol: 1, X-Request-ID = body request_id) and captures the baseline. The baseline covers ALL open items, so run while no other work changes. Forced run T0 -> exit 1, real run T1 -> exit 0, submit the --restored observation with --expected-evidence-digest, then clean up. Step 12 (retire items via work.lifecycle.arbitrate) is validated offline only. Whole-cluster PITR does not meet the selective single-tenant restore criterion; the runbook records that.
- STAGE 3b live isolation proof: two real OAuth grants (one per workspace) via the claude-connector client (auth code + PKCE, loopback redirect, secret at ~/.config/vuoro/credentials/claude-connector.secret) in the operator's browser. Write the walkthrough together with connector registration. The tenant MCP edge flag is already true; finish this proof before registering the connector.
- Served sprintctl cannot reach vuoro.cloud: vuoro-client 0.1.0 sends no Authorization on /api/catalog/v1 and /api/meta/v1/handshake (client.py:87,:146), so the gateway returns 401. Needs a vuoro-client release + sprintctl pin bump. Not needed for the drill (direct invoke works).
- Onboarding follow-ups: the dashboard's track('repository_bound') is not an allowed analytics event (api.py:44-56). IMPLEMENTATION-STATUS.md is stale (poc.34). Gap 6 (connect-a-client panel) waits on the connector flow. The evidence doc's displayed jq in docs/evidence/2026-09-24-landing-proof-sprintctl-0.7.3.md differs slightly from what ran.
- Legacy tenant 01m14w25eykc roles NOLOGIN (note #3606): the operator re-list to confirm empty was offered, not confirmed back.
- Operator tunnel vuoro-cloud-operator/vuoro-cloud-wg is UP; the operator brings it down after the D-044 proofs.
- Talos automation plan Part 4: in-job iSCSI assertion (needs a custom upgrade image), rollout queue, CNPG evacuation in prepare, one-rule-per-runbook-step wrappers. appservice #1744 (renovate kubelet v1.37.1) is open; never arm Talos and k8s phases together.
- sprintctl notes on agentops#2514 for this session were not written; record the gen-40 state and D-047 there.
- The shared checkout /projects/dev/vuoro-cloud is stale (12786ce). Read vuoro-cloud files from origin/main (5015deb): docs/runbooks/restore-drill.md, docs/GETTING-STARTED.md, 17-DECISION-LOG.md D-047. Merged PRs: vuoro-cloud #100-#106, appservice #1764-#1766, agentops #246.
- Handoff v3 and v4 of this slug are broken (stale digest at birth) and superseded by this one. Cause: scripts/handoff.py sprintctl_bundle runs `sprintctl handoff --format json` without `--output -`; sprintctl 0.7.3 then writes handoff-<sprint>.json into the repo root, stdout is empty, no bundle is recorded, and the stray file makes diff_sha256 stale. The fix is the agentops PR fix/handoff-sprintctl-stdout; this handoff was created with --no-sprintctl.

## Evidence

- sprintctl: `agentops#2514 notes 3602-3607`
- artifact: `/projects/dev/vuoro-cloud/17-DECISION-LOG.md`
- artifact: `/projects/dev/appservice/docs/migrations/2026-08-talos-kubernetes-upgrade-automation-plan.md`
- artifact: `/projects/dev/agentops/hooks/handoff-session-start.sh`
- session: `b31c04da-6750-4f0a-8865-6e0708e46da7`

## sprintctl bundle

- none (sprintctl unavailable or produced no bundle)

## Successor

- session: 3424a321-11b0-43d4-841f-715a2d55adc6
- acknowledged: 2026-09-25T06:00:39Z
