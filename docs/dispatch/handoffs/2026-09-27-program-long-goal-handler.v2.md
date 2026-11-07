# Handoff 2026-09-27-program-long-goal-handler.v2

<!-- Rendered from the canonical JSON beside this file. Do not hand-edit:
     `agentops handoff validate` and `ack` read the JSON, never this. -->

**Objective.** Carry the vuoro.cloud program forward: finish Milestone 1 (record and resume real work) per the operator-reviewed plan (agentops docs/plans/2026-09-27-backlog-ideation.md, 'Revision after operator review', PR #253), land #2519 (assertion replay protection), implement the admin/user identity and vuoro-cli design once its PR exists, and keep release trains moving (vuoro release -> vuoro-cloud pin -> signed promotion -> tenant roll). State at handoff (2026-09-27 ~12:00 EEST): generation 47 (v0.1.0-poc.47, vuoro-cloud 332faa4, image sha256:4c5f0a49…) is live and verified; tenants kotona and isolation-proof run vuoro-service 0.1.76 (sha256:2815fbd3…, sprintctl 0.8.0, work schema 17). E2 run/evidence and E3 propose+reconciler are merged; M1-1..M1-3 (#2521-#2523) are accepted; the first reconstructable automated session exists (vuoro#140, run_M3ZZS6FM0WRW90GNMWX35649PJ, conformance CONFORMANT, TS-16 coverage 1/2).

**Next action.** Ack this record. Then, at or after 15:00 EEST (the operator's 5h window resets then; pause until then): (1) Check the in-flight work listed under RUNNING and pick up whatever has reported: #2520 claims lease (a local Opus orchestrator from session bef3ec08; results arrive as PRs on bayleafwalker/sprintctl and bayleafwalker/vuoro titled '(agentops#2520)'; find them with gh pr list --search 2519/2520); vuoro#134 (#2519 runtime replay protection; cloud session session_01VtuKHjxZabGYYxkpBTkzt2 is applying the fix-up); the admin-identity/vuoro-cli design PR on agentops branch docs/admin-identity-vuoro-cli-design (cloud session session_01GbNnkdsZpHQ2NAZwy7S96Y). (2) Every PR gets an independent adversarial review by a fresh read-only subagent, posted on the PR (on Forgejo, put the review in the PR body at creation: fj's token cannot comment), before merge. (3) When vuoro#134 passes review: merge; then the vuoro-cloud side in order: Forgejo #136 (edge-proof key mount) + #132 (docs) + #134 (api.vuoro.cloud / redirect) as one generation, then vuoro-service release with #134's runtime, runtime pin, promotion, tenant roll (kotona then isolation-proof), and only after every tenant runs it: Forgejo #135 (gateway mints jti). Then #2526 (edge schema deviations; enable ENFORCE_EDGE_PROOF_AND_REPLAY in the strict-client job) and #2525 (M1-5 successor runs). (4) When the design PR opens and has its summary comment: dispatch a local Opus orchestrator to implement it in independent worktrees (operator request). (5) After #2520 lands: sprintctl 0.9.0 release, vuoro pin + service release, cloud generation, tenant roll with schema-18 migration, then grant vuoro:work.claim; then #2524 (M1-4 settlement proof).

## Predecessor

- harness: claude-code
- session: bef3ec08-dbcc-4a95-902a-fbc16833f9b3
- model: claude-opus-5-5
- context used: unknown%
- transcript: unknown
- origin: `workstation:/projects/dev/agentops/docs/dispatch/handoffs/2026-09-27-program-long-goal-handler.v2.json` (authoritative copy; an ack from another host goes through it)

Read-only after transfer: once a successor acks, the predecessor makes no
edits and takes no external actions. It stays consultable.

## Constraints

- Merge/mutation/publish/deploy approval: the operator approved mutations against main, deployments and running-service mutations for session bef3ec08 only. Ask again.
- Before merging any PR, an independent review by a fresh read-only subagent must be posted on the PR (GitHub comment; Forgejo: in the PR body at creation). This includes commits the session writes itself (rebase glue, pin bumps, one-line fixes). The auto-mode classifier blocks unreviewed/self-approved merges ([Merge Without Review], [Self-Approval]); on a denial, stop and give the operator the exact command, never route around it.
- vuoro-cloud (Forgejo) is fast-forward-only: credctl merge --repository forgejo:bayleaf/vuoro-cloud --pr N --head-sha <40-char> --style fast-forward-only --forgejo-url https://git.apps.kotona.app. Same for gitops-nixos and cred-broker. fj needs --repo bayleaf/<repo> outside a checkout; fj pr status can crash; use `fj actions tasks --repo … --host git.apps.kotona.app` for CI.
- Promotion: pin the four workload manifests to the Forgejo-built digest first, then the operator runs scripts/promote-release.sh sha256:<digest> <gen> (YubiKey), agent verifies signed tag (GNUPGHOME=~/.config/vuoro/openpgp git verify-tag) and CI, ff-merges the candidate, operator dispatches promote-deployment.yaml with curl (workstation-scope-token), agent verifies Flux SourceVerified + pod imageIDs. Tenant rolls are an operator browser-console PATCH {desired_state:READY}; each runs vuoro-migrate on the new image (forward-only; take a CNPG Backup CR first).
- Cloud work: dispatch with `claude --cloud` from a trusted checkout (credit-billed), not Routines (plan window). Include every repo the session must push to in its sources; if a session starts from a seed bundle and hits a push 403, ask the operator to attach the repo mid-session. Follow-ups: claude -p '<msg>' --cloud <session_id> --output-format json.
- TS-16 unamended: cloud callers only queue effects; acceptance is trusted-side (interactive, or opt-in trusted-side auto-accept). vuoro:effect.propose and vuoro:work.claim stay reserved until durable intent store / exclusive lease exist and every tenant runtime serves the tools (the edge refuses assertions carrying authorities with no tools).
- Operator preferences: no artificial gates (criteria are cheap checks of finished work, not entry gates; bias to trying); maximal changes on main, no stale feature branches; vuoro.cloud owns telemetry, homelab-analytics consumes it and may prescribe actions; product direction is split-horizon with vuoro.cloud as the primary endpoint (see memory product-direction-split-horizon).
- Scratchpad worktrees off origin/main; never edit or pull the shared checkouts under /projects/dev except where the operator asks (audit shards are now committed automatically by the audit-shards-commit timer; do not commit shards by hand).

## Decisions

- **TS-16 kept unamended (operator 2026-09-26/27)** — Codex review C1: synchronous propose is apply authority. Effects are queued intents; acceptance trusted-side; opt-in auto-accept policy only trusted-side. agentops #251.
- **Milestones M1 record+resume / M2 one bounded effect / M3 widen replace the 'next 10 dispatches'** — Operator review of PR #253; M1 filed as #2521-#2525; lease owner for effect intents recommended sprintctl (R4).
- **Telemetry owned by vuoro.cloud; homelab-analytics consumes and may prescribe actions** — Operator decision 2026-09-27, recorded on agentops PR #256.
- **blocker12-canary tenant (orphaned synthetic owner) kept until an audited admin retirement path exists** — Operator decision; no bypass of membership checks.
- **Audit shards committed automatically** — agentops #257/#260 + gitops-nixos #6: hourly user timer, commits only shard paths in each checkout, protected mains land via shard-only PR + credctl ff merge.

## Rejected

- **Retrying classifier-denied merges or using the operator's Forgejo token to work around fj scope limits** — Routing around a denial; hand the exact command to the operator instead.
- **Deleting Routines via API** — Not supported by RemoteTrigger; seven finished build Routines were disabled instead (operator may delete in UI). 'Vuoro connector validation' (trig_011h9rgNW69ZiNzbnmmp1n2G) is kept: it is the evidence Routine tracked by the TS-16 cohort.

## Repo state

Digest definition: v4 (see the handoffs README).

| path | branch | head | dirty | unpushed | diff_sha256 |
|---|---|---|---|---|---|
| `/projects/dev/agentops` | main | `ffb8d12453c7` | yes | 0 | `c127f0e2c35c108f…` |
| `/projects/dev/vuoro` | main | `3a0006a13771` | no | 0 | `e3b0c44298fc1c14…` |
| `/projects/dev/vuoro-cloud` | main | `332faa4c2087` | no | 0 | `e3b0c44298fc1c14…` |
| `/projects/dev/sprintctl` | main | `20ff17d770db` | no | 0 | `e3b0c44298fc1c14…` |

**Running:**

- Nothing is running under session bef3ec08 any more: the #2520 orchestrator was killed by the 5h usage limit (~12:3x EEST) and the remaining cloud sessions have finished.
- audit-shards-commit.timer (user systemd, hourly; protected mains via shard-only PR + credctl): ~/.local/state/agentops/audit-shards/last-run.json, journalctl --user -u audit-shards-commit.
- Cloud session session_01GbNnkdsZpHQ2NAZwy7S96Y (admin identity + vuoro-cli design): branch docs/admin-identity-vuoro-cli-design pushed (e4c47d1); PR not opened as of 15:02. Check its log (RemoteTrigger get_run_log) and follow up with `claude -p ... --cloud session_01GbNnkdsZpHQ2NAZwy7S96Y` if it stalled.

## Unresolved

- vuoro#134 (#2519): fix-up pushed at b4f109e (07:46 UTC), addressing the cross-process replay blocker (route-aware claims + edge requires client_id/grant_id while audiences are shared), the deterministic lock test, a relaxed jti check (<=8192 chars), and a proofed-use cap of 7. NOT yet re-reviewed: run a fresh adversarial re-review, post it, then merge.
- #2520 claims lease: sprintctl#98 (feat/work-claim-lease-2520 @10c6173, CI green, no review posted) and vuoro#141 (feat/claim-contract-ledger-2520 @1689194). The orchestrator had fixed review findings M1, m1-m3, n1, n3, n4 and a re-review ran, but its verdict was never posted (the orchestrator died). Do a fresh independent review of both PRs, post it, fix what remains, then merge #98, release sprintctl 0.9.0 (remember verification/validate_release_contract.py RELEASE_VERSION), then #141, pin, and continue the release chain. Its scratch files are in /tmp/claude-1000/-projects-dev-agentops/bef3ec08-dbcc-4a95-902a-fbc16833f9b3/scratchpad/orch-2520/ (pr-sprintctl.md, pr-vuoro.md, worktrees).
- Forgejo vuoro-cloud PRs ready (reviewed, in body): #132 docs drift, #134 api.vuoro.cloud expired-session redirect, #136 edge-proof key mount; #135 gateway jti held until every tenant runs #134's runtime.
- Admin/user identity + vuoro-cli design: cloud session session_01GbNnkdsZpHQ2NAZwy7S96Y pushed branch docs/admin-identity-vuoro-cli-design (e4c47d1); PR not yet opened at handoff. Operator wants a local Opus orchestrator to implement it in independent worktrees once it lands, then the same for remaining work.
- Planning PRs open for operator reading (do not merge without operator): agentops #253 backlog (revised to milestones), #254 UI/UX + docs library, #255 ecosystem split-horizon architecture, #256 telemetry/audit/operator actions.
- Old read-only connector grant 01M3CBEBGYWYKG24XYF83KDKFC and test grants 01M3CA5Q802J5KECYJA2Y94M0K / 01M3CAQ5M9P7ZF9RVMGEXGXTBJ and drill PAT 01M3BTNG1X9C18D2FHE3YX88NA still active (operator: may keep for tests).
- Follow-ups not yet filed: re-check devbox sprintctl CLI version (#2502 was withdrawn on workstation evidence only).
- sprintctl items: #2520 (p1, PRs above) blocks #2524; #2525 M1-5 waits for vuoro#134; #2526 edge schema deviations (after #134); #2527 OAuth scope upgrade gap.

## Evidence

- sprintctl: `agentops sprint 559: #2466 #2467 #2515 #2516 #2517 #2490 #2521 #2522 #2523 accepted 2026-09-27 (decisions #144-#153); #2520-#2527 open`
- session: `bef3ec08-dbcc-4a95-902a-fbc16833f9b3`

## sprintctl bundle

- none (sprintctl unavailable or produced no bundle)

## Successor

- session: 10b73718-a84c-4da8-923c-297e4d9743eb
- acknowledged: 2026-09-27T12:02:27Z
