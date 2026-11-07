# Handoff 2026-09-26-program-long-goal-handler.v1

<!-- Rendered from the canonical JSON beside this file. Do not hand-edit:
     `agentops handoff validate` and `ack` read the JSON, never this. -->

**Objective.** Carry the vuoro.cloud program past E1 (done 2026-09-26) through E2/E3 and the forward backlog. Live: generation 45 (v0.1.0-poc.45, image sha256:f48ac1cf…, verified: all pods ready, 0 restarts, /mcp 401, token endpoint invalid_client/invalid_grant). Next: roll kotona to runtime 0.1.75 (operator PATCH), review and carry the cloud-run PRs (E2, E3, #2515, #2516), release and promote them as generation 46, and keep dispatching forward backlog work as credit-billed cloud sessions.

**Next action.** Ack. Then: (1) ask the operator for the kotona roll (browser console on an https://api.vuoro.cloud tab: PATCH /api/control/v1/workspaces/01M3ABJS1QW0Q6BNDCHP0DDTYF {"desired_state":"READY"} with X-CSRF-Token from the vuoro_csrf cookie; last time it answered 200 and workspace generation moved) and verify its runtime pod on vuoro-service 0.1.75 (sha256:404db825…, both containers ready) and `claude mcp list` ✔; (2) review the open cloud-run PRs against vuoro docs/plans/2026-09-26-e2-e3-shared-contract.md: vuoro #130 (E3), vuoro-cloud GitHub replica #5 (E2 attribution/scopes), #6 (E3 scope), #4 (#2515 kustomize output), sprintctl #96 (#2516); E2's vuoro PR was still pending at handoff (run cse_01J9NF1dudeHUhY8z3FCQ2qx). Merge order E2 then E3 (rebased). Carry vuoro-cloud replica branches to Forgejo (git fetch github <branch>; push to origin; fj pr create; CI on head; credctl ff-merge); close the replica PRs unmerged. (3) After E2 lands, dispatch #2519 (jti replay cache) with `claude --cloud` (see dispatch procedure below). (4) Read the Codex adversarial review of the trusted-service design when it exists (scratchpad review-trusted-service.md, background job started 15:00) before any trusted-service slice-1 work.

## Predecessor

- harness: claude-code
- session: d5ca23ce-779a-43e9-a44e-4bebdc05f0f4
- model: claude-opus-5-5
- context used: unknown%
- transcript: unknown
- origin: `workstation:/projects/dev/agentops/docs/dispatch/handoffs/2026-09-26-program-long-goal-handler.v1.json` (authoritative copy; an ack from another host goes through it)

Read-only after transfer: once a successor acks, the predecessor makes no
edits and takes no external actions. It stays consultable.

## Constraints

- Merge/mutation/publish/deploy approval was given 2026-09-26 to session d5ca23ce only. Ask again.
- The classifier still blocks some actions even with approval (it blocked the vuoro-cloud #119 merge, the Forgejo manually-merged API call, and one promote dispatch, while later identical merges/dispatches passed). On a denial: stop, give the operator one exact ! command with a checked precondition and expected result; never route around it.
- Merge only when every CI check passed on the PR head sha. vuoro-cloud is fast-forward-only: credctl merge --repository forgejo:bayleaf/vuoro-cloud --pr N --head-sha <40-char> --style fast-forward-only --forgejo-url https://git.apps.kotona.app. fj needs --repo bayleaf/vuoro-cloud outside a checkout (else it prints nothing).
- SOPS: changing values inside SOPS-encrypted files is normal work (sops set/edit, then make verify-runtime-pin). SOPS configuration and keys (.sops.yaml, age keys) are operator-only. Never print or dereference secret values.
- YubiKey signing (scripts/promote-release.sh <digest> <gen> from /projects/dev/vuoro-cloud on clean main) is the operator's, handed over marked RUN NOW. Flux deploys only signed tags; pin the four apps/ manifests first, then tag.
- Cloud dispatch: use `claude --cloud "<brief>"` from the target repo's checkout (credit-billed: origin claude_code_cli, bucket ccr_promotional, verified with get_session). From an agent Bash tool wrap it: `timeout 60 script -qec 'claude --cloud "<brief>"' /dev/null < /dev/null` (piped stdout is refused; folder must be trusted). Routines (RemoteTrigger/API fire) bill the five_hour plan window: use only for scheduled/recurring jobs. Follow-ups: `claude -p "msg" --cloud <session_id>`. Workers push branches + PRs only; vuoro-cloud's GitHub repo is a replica — workers push feature branches there titled [carry to Forgejo], never main.
- Protected paths in agentops (e.g. .claude/settings.json): a directly authored PR must declare itself with a title starting 'hand-pass:'.
- Operator tunnel for the PoC API: nmcli connection up vuoro-cloud-operator, KUBECONFIG=~/.config/vuoro/kube/poc.yaml; bring it down after. It is DOWN now.
- Scratchpad worktrees off origin/main; never edit or pull the shared checkouts (except the operator's promote-release.sh run); never bare git stash. Global git identity. Keep the operator's prompt free: waits run as background tasks.

## Decisions

- **E1 (agentops#2514) accepted 2026-09-26 (decision #143)** — Hosted Routine run cse_01Vfxn4vCX59bhcZtmQe3YLs authenticated over OAuth, called list_ready_work + describe_work 1-3, opened bayleafwalker/vuoro#124 (merged); gateway gen-44 logs confirm. Root cause of the 09-25 'no': edge sent per-method resultType; fixed in vuoro #123 (0.1.74).
- **Operator decisions for cloud work (agentops docs/plans/2026-09-26-cloud-enablement-plan.md, merged #249)** — Report repo bayleafwalker/vuoro; cloud sessions branch+PR only; E2 runs/evidence first, claim_work only on an exclusive durable lease; no CLI credentials to Routines; single-repo until E2; SOPS value edits are normal work; trusted-service boundary adopted pending Codex review.
- **E2/E3 shared contract (vuoro #129, docs/plans/2026-09-26-e2-e3-shared-contract.md)** — Pre-resolves #2517 (actor = external_subject on both paths), scope->authority table (work:evidence, work:claim, effect:propose), toolset seam modules and ownership, run-handle protocol, idempotency, durable-lease rule, diff-shaped intents; merge E2 before E3.
- **Generations 44 and 45 shipped and verified live** — 44 = vuoro-cloud #119 (clients-file checksum, placeholder refusal, .artifacts skip) + #120 (runtime 0.1.74); 45 = #123 (docs, runtime 0.1.75, bootstrap vuoro-client 0.1.1) + #124 pin; candidate #125 signed (YubiKey), promote run #468 succeeded.
- **Releases today** — vuoro-service 0.1.74 (a8a82629) and 0.1.75 (404db825), vuoro-mcp-edge 0.1.1/0.1.2, vuoro-client 0.1.1 (wheel b5fb6bad… reproducible), sprintctl v0.7.4 (pins vuoro-client 0.1.1).

## Rejected

- **Sending the /feedback draft about Routines not exposing connector tools** — The cause was our server (per-method resultType), not the platform.
- **Routines for one-off dispatch** — They bill the five_hour plan window (origin force_run_trigger), not the cloud credit.
- **materialize-kubernetes-secrets.py to change the runtime image** — It regenerates every secret value; use sops set on the single key.
- **Dispatching #2519 in parallel with E2** — Both edit vuoro_service gateway_identity and the gateway's assertion minting.

## Repo state

Digest definition: v4 (see the handoffs README).

| path | branch | head | dirty | unpushed | diff_sha256 |
|---|---|---|---|---|---|
| `/projects/dev/agentops` | main | `bcb2d4c73326` | yes | 0 | `0bb8426b122d389c…` |
| `/projects/dev/vuoro-cloud` | main | `7e43ad001640` | no | 1 | `e3b0c44298fc1c14…` |
| `/projects/dev/vuoro` | main | `3a0006a13771` | no | 0 | `e3b0c44298fc1c14…` |

## Unresolved

- OPERATOR LIST (scratchpad OPERATOR-ACTIONS.md): mark vuoro-cloud PRs #102-#105 manually-merged (classifier-denied for the agent; command in the file); reinstall local sprintctl 0.7.4 (installed tool is 0.7.0 with vuoro-client 0.1.0: cd /projects/dev/sprintctl && git pull --ff-only && uv tool install --reinstall --from . 'sprintctl[remote,served]'); optional revocations (drill PAT 01M3BTNG1X9C18D2FHE3YX88NA, test grants 01M3CA5Q802J5KECYJA2Y94M0K / 01M3CAQ5M9P7ZF9RVMGEXGXTBJ); keep/delete workspace isolation-proof (recommend keep); the shared agentops checkout needs a pull to pick up #250 (kubectl rule) — user ~/.claude/settings.json is already fixed.
- kotona still on runtime 0.1.74 until the operator's PATCH; then verify 0.1.75 and claude mcp list ✔.
- Trusted-service design (agentops docs/plans/2026-09-26-trusted-service-boundary-design.md): Codex adversarial review pending (background job at 15:00 writes scratchpad oracle-cloud-envs/review-trusted-service.md). Flags to act on: Talos env has no policy-enforcing CNI (platform/policies would be ignored after cutover); control egress 443 open (network-policies.yaml:66-72); D-048 decision-log + TS-1/TS-16 amendment when slice 1 starts.
- compatibility.json's 'sprintctl' key is ambiguous (image composition 0.7.3 vs client install 0.7.4); split client vs runtime package sets.
- E2 and E3 reservations #73/#74 and #2517 reservation #72 held by workstation-vuoro for the cloud runs; release on close. #2479 (RunManifest) looks already done by vuoro #122 — reconcile/close.
- Probe sessions cse_01RGwUG3fHjBH3qMuRdvAQLr and session_01UHhvQ8grs9FEXoAFbTgwud/cse_01RAC1RV… are idle cloud sessions; harmless.
- RUNNING: Cloud run E2 (Routine trig_015KsriQReYAdwUAL87EY9fy, session cse_01J9NF1dudeHUhY8z3FCQ2qx): vuoro-cloud replica PR #5 open; vuoro PR pending.
- RUNNING: Cloud run E3 (trig_01BpYaRyUrvS3oEy4mMA1QcM, cse_01WeXX4betVYvLQUjwQiyUoH): vuoro #130 and vuoro-cloud replica #6 open.
- RUNNING: Cloud run #2516 (trig_0113z7eQiRjmDhKoqUBP67WY, cse_01DGzbMAxdKfm1fBkTthzLCE): sprintctl #96 open.
- RUNNING: Cloud run #2515 (trig_01CMfMzbs3YSzk4RiQwfVScN, cse_01BxzokrQcaWchWQ5fBPddMn): vuoro-cloud replica #4 open.
- RUNNING: Background job in session d5ca23ce: at 15:00 local runs Codex (gpt-5.6-sol, read-only) review of the trusted-service design into scratchpad oracle-cloud-envs/review-trusted-service.md. If the predecessor process ends first the job dies with it; re-run with prompt oracle-cloud-envs/prompt-review.md.
- RUNNING: Tracking files (predecessor scratchpad, readable on this host): /tmp/claude-1000/-projects-dev-agentops/d5ca23ce-779a-43e9-a44e-4bebdc05f0f4/scratchpad/{CLOUD-RUNS.md,OPERATOR-ACTIONS.md,oracle-cloud-envs/}

## Evidence

- sprintctl: `agentops#2514 decision #143, event #3623 (#2517 decision), #3624/#3625`
- artifact: `bayleafwalker/vuoro docs/evidence/2026-09-26-e1-first-use-routine.md`
- artifact: `bayleafwalker/vuoro docs/plans/2026-09-26-e2-e3-shared-contract.md`
- artifact: `bayleafwalker/agentops docs/plans/2026-09-26-cloud-enablement-plan.md`
- session: `d5ca23ce-779a-43e9-a44e-4bebdc05f0f4`

## sprintctl bundle

- none (sprintctl unavailable or produced no bundle)

## Successor

- session: bef3ec08-dbcc-4a95-902a-fbc16833f9b3
- acknowledged: 2026-09-26T12:07:10Z
