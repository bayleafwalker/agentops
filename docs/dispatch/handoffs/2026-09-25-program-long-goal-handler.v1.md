# Handoff 2026-09-25-program-long-goal-handler.v1

<!-- Rendered from the canonical JSON beside this file. Do not hand-edit:
     `agentops handoff validate` and `ack` read the JSON, never this. -->

**Objective.** Hold the long goal: E1 (agentops#2514) reaches first use. Everything but the acceptance line is done and live on generation 43: D-044 restore drill and live tenant isolation passed, the claude.ai Vuoro connector works in chat. The acceptance line (a claude.ai Routine calls list_ready_work/describe_work and opens a PR with its verdict) is blocked on the Routine side. Next: land the small hardening follow-ups found on 2026-09-25, update the implementation matrix, and re-run the Routine once the platform exposes custom-connector tools.

**Next action.** Ask the operator for merge approval for this session (it does not transfer), then: (1) one vuoro-cloud PR with the three hardening follow-ups -- a checksum annotation on apps/control/deployment.yaml for Secret vuoro-oauth-clients so control restarts when the clients file changes (control.py:122 loads it once); control refuses to start when any client_secret_hash is the all-zero placeholder; tests/ test_deployment_distribution.py ignores the gitignored .artifacts/ tree -- plus docs/IMPLEMENTATION-MATRIX.md rows for live claude.ai authorization, D-044 isolation and live tools/call (now proven, cite docs/evidence/2026-09-25-*). Worktree off origin/main, ruff format, check-fast, PR via fj, CI green, credctl ff-merge, image publish, pin generation 44, hand the operator promote-release.sh marked RUN NOW, merge the candidate, dispatch promote-deployment (204), verify at the artifact (images, 0 restarts, /mcp 401, token endpoint wrong secret -> invalid_client and real secret -> invalid_grant). (2) Ask whether to send the queued Claude Code feedback draft about the Routine gap (/feedback).

## Predecessor

- harness: claude-code
- session: 3424a321-11b0-43d4-841f-715a2d55adc6
- model: claude-opus-5-5
- context used: unknown%
- transcript: unknown
- origin: `workstation:/projects/dev/agentops/docs/dispatch/handoffs/2026-09-25-program-long-goal-handler.v1.json` (authoritative copy; an ack from another host goes through it)

Read-only after transfer: once a successor acks, the predecessor makes no
edits and takes no external actions. It stays consultable.

## Constraints

- Merge and mutation approval was given on 2026-09-25 for session 3424a321 only. Ask again.
- The classifier denies some merge/push/deploy/secret actions even with approval. On a denial, stop, give the operator one exact ! command with precondition and expected result, never route around it. A granted retry allows re-running the same command. Editing a script whose purpose is a SOPS/Secret write counts as the same outcome.
- Merge only after every CI check passes, and confirm the checks ran on the PR head sha (fj actions tasks | grep <head>). vuoro-cloud is fast-forward-only: credctl merge --repository forgejo:bayleaf/vuoro-cloud --pr N --head-sha <40-char sha from git ls-remote origin refs/pull/N/head> --style fast-forward-only --forgejo-url https://git.apps.kotona.app.
- Never dereference Secret/SOPS values, PATs, OAuth tokens or invitation codes into the session. Scripts may read token files and print only claims/booleans. SOPS edits are the operator's (docs/runbooks/credential-rotation.md).
- YubiKey signing (scripts/promote-release.sh <digest> <gen> from /projects/dev/vuoro-cloud, shared checkout on clean main) is the operator's, handed over marked RUN NOW. Flux deploys only signed tags, so any change under apps/ or platform/ needs a new generation.
- Force every guard into its failure case before trusting it; verify at the artifact. In shell chains never pipe a guarded step through grep before && (it masks the exit code); use pipefail.
- Keep the operator's prompt free: every wait runs as a background task.
- Global git identity only. Scratchpad worktrees off origin/main; never edit or pull the shared checkouts (except the operator's promote-release.sh run); never bare git stash. Five worktrees under /tmp/claude-1000/-projects-dev/93862d02-*/scratchpad belong to another session -- leave them.
- Run ruff format (uv run --extra test ruff format src tests scripts inside nix develop; ruff is not on PATH) before check-fast in vuoro-cloud.
- Cloudflare answers 403 to the default Python-urllib User-Agent on api.vuoro.cloud; set a User-Agent in scripts.
- The PoC cluster API needs the operator tunnel: nmcli connection up vuoro-cloud-operator (no sudo), KUBECONFIG=~/.config/vuoro/kube/poc.yaml; bring it down after (nmcli connection down vuoro-cloud-operator). It is DOWN now.
- Memory holds only communication preferences; durable guidance goes in repo docs.

## Decisions

- **vuoro-cloud main = 4241b9b08e6960ebc4a4de37609f7363a8287773 = signed tag v0.1.0-poc.43, live on the PoC with image sha256:a3fe97cd556cf462023fde963cc1a1e0b86a8a4e799eb656ce9a5d3461622e76 (all pods ready, 0 restarts, verified 14:3xZ)** — Generations 40-43 shipped today: 40 = #100-#106 stack (93ba8688), 41 = #109 single X-Request-ID (7d948df5), 42 = #113 real claude-connector hash (same image), 43 = #116 /mcp diagnostics (a3fe97cd).
- **Gateway tenant /api proxy forwards exactly one X-Request-ID (vuoro-cloud #109)** — The runtime (vuoro gateway_identity._single_header) rejects repeated headers; before the fix every direct POST /api/invoke/v1 failed with 'duplicate x-request-id'.
- **claude-connector client secret: hash of the existing ~/.config/vuoro/credentials/claude-connector.secret registered in platform/runtime-secrets/oauth-clients.secret.yaml (vuoro-cloud #113, operator-run)** — a7e0320 had committed the template placeholder hash (0 x 64), so /oauth/token returned invalid_client for any secret. After gen 42, vuoro-control was restarted by hand (12:39Z) because it loads the clients file only at startup.
- **D-044 restore drill PASSED on gen 41 (docs/evidence/2026-09-25-d044-restore-drill.md, vuoro-cloud #112)** — T0 forced run exit 1 (items 1-3 missing), T1 run exit 0 match, observation 01M3BYC1DS4FN0DY6GQXZ2R7KQ (workspace, restored), step 12 retirement verified live (7/7 accepted). kotona has 0 open items; drill items 1-3 are done.
- **D-044 live tenant isolation PASSED on gen 42 (docs/evidence/2026-09-25-d044-live-isolation.md, vuoro-cloud #115)** — Two OAuth grants (kotona, isolation-proof): describe_work 1-3 found only with the kotona token; header injection ignored; per-namespace mcp logs matched each grant's calls exactly.
- **Workspace isolation-proof (01M3CA7V972W3HQSYWBG7V6JBB, ns vuoro-ws-01m3ca7v972w, repo vuoro-cloud bound) stays for now** — Created for the isolation proof; the operator decides whether to keep it. blocker12-canary belongs to another user on the old runtime without MCP and was not usable.
- **claude.ai connector Vuoro registered by the operator (Sign in now + Use your own OAuth client claude-connector + secret); grant 01M3CBEBGYWYKG24XYF83KDKFC for kotona; chat describe_work(1) correct** — First live hosted tools/call. Keep the MCP out of local Claude Code/Codex harnesses: it is read-only (vuoro:work.read) and the CLI is the write path; revisit at E2.
- **E1 first-use acceptance NOT met; blocked on the Routine side** — Routine trig_011h9rgNW69ZiNzbnmmp1n2G (Vuoro attached, ListConnectors connected/enabledInChat true) never exposed Vuoro tools. Gen-43 gateway trace of run cse_01HT8fdWFfrZsEDCkEagCK4m: /oauth/token 200 -> server/discover (MCP-Protocol-Version 2026-07-28) 200 -> tools/list 200 with both tools. agentops PR #248 (GitHub) carries verdict 'no' and stays open as negative evidence. agentops#2514 notes 3612-3615.
- **Drill PAT files and all OAuth test-grant token files were shredded** — The drill PAT (token 01M3BTNG1X9C18D2FHE3YX88NA) and grants 01M3CA5Q802J5KECYJA2Y94M0K / 01M3CAQ5M9P7ZF9RVMGEXGXTBJ remain valid server-side until expiry or browser-session revocation.

## Rejected

- **Omitting X-Request-ID on direct invoke** — The runtime then fails correlation ('gateway identity request correlation failed'); the gateway fix was the only route.
- **Using blocker12-canary as the second isolation tenant** — Different owner, runtime f5c9c6 without the mcp container, NOLOGIN roles.
- **Agent-authored SOPS clients-file rewrite** — Classifier-denied [Secret-Store Writes], including editing the helper script; the operator ran the runbook steps.
- **Attaching Vuoro to a routine via the scheduling API** — The schedule skill's routine-usable connector list omits Vuoro; the operator created the routine in the web UI, which attached it.
- **Reading a routine's 'Use Vuoro for this' follow-ups as operator approval** — The routine correctly refused non-live input; do not message routines expecting it to act.

## Repo state

Digest definition: v4 (see the handoffs README).

| path | branch | head | dirty | unpushed | diff_sha256 |
|---|---|---|---|---|---|
| `/projects/dev/agentops` | main | `bcb2d4c73326` | yes | 0 | `2714d8e04f92c101…` |
| `/projects/dev/vuoro-cloud` | main | `4241b9b08e69` | no | 1 | `e3b0c44298fc1c14…` |
| `/projects/dev/appservice` | main | `ad201c478b66` | no | 0 | `e3b0c44298fc1c14…` |

**Running:**

- Nothing is running. All background tasks and subagents of session 3424a321 have finished; its scratch worktree and local branches are removed; the operator tunnel is down.

## Unresolved

- OPERATOR BOOKKEEPING (carried from v5): vuoro-cloud #102-#105 still open/unmerged although in main. Operator command: T=$(cat ~/.config/forgejo/workstation-scope-token); for n in 102 103 104 105; do curl -sS -o /dev/null -w "$n %{http_code}\n" -X POST -H "Authorization: token $T" -H 'Content-Type: application/json' https://git.apps.kotona.app/api/v1/repos/bayleaf/vuoro-cloud/pulls/$n/merge -d '{"Do":"manually-merged","MergeCommitID":"5015debd2a68054d0cadbff537d0de76f14f8ffc"}'; done -- expect 200 each.
- Queued Claude Code feedback draft (Routine never exposes a connected custom connector's tools although tools/list returns them) awaits the operator's /feedback review; not sent.
- Re-run the Routine (needs a new run_once_at or RemoteTrigger run) once the platform exposes custom-connector tools; then #2514 can close on that trace and PR #248's verdict is superseded.
- Hardening follow-ups (next_action): control checksum annotation for vuoro-oauth-clients; refuse the all-zero client hash at startup; test_deployment_distribution scans .artifacts/; runtime logs item-not-found as 'work source failed' (vuoro repo).
- Optional operator revocations: drill PAT 01M3BTNG1X9C18D2FHE3YX88NA and test grants 01M3CA5Q802J5KECYJA2Y94M0K (kotona) / 01M3CAQ5M9P7ZF9RVMGEXGXTBJ (isolation-proof) via DELETE .../workspaces/{id}/tokens|grants/{id} with a browser session; decide whether to keep workspace isolation-proof.
- Served sprintctl cannot reach vuoro.cloud: vuoro-client 0.1.0 sends no Authorization on /api/catalog/v1 and /api/meta/v1/handshake (client.py:87,:146) -> 401. Needs a vuoro-client release + sprintctl pin bump.
- Docs drift: IMPLEMENTATION-STATUS.md stale (poc.34); docs/IMPLEMENTATION-MATRIX.md still lists live claude.ai authorization / D-044 isolation / live tools/call as open; GETTING-STARTED step 4 (connect Claude) can now be written from the 2026-09-25 connector registration.
- Carried from v5: onboarding follow-ups (track('repository_bound') not an allowed analytics event, api.py:44-56; gap 6 connect-a-client panel); legacy tenant 01m14w25eykc NOLOGIN re-list not confirmed; Talos plan Part 4 and appservice #1744 (never arm Talos and k8s phases together).
- agentops fix/handoff-sprintctl-stdout (scripts/handoff.py runs sprintctl handoff without --output -) is still unmerged; this handoff was created with --no-sprintctl.
- PRs of 2026-09-25: vuoro-cloud #107-#118 (Forgejo, all merged); agentops #248 (GitHub, open, Routine verdict 'no'). Routine trig_011h9rgNW69ZiNzbnmmp1n2G runs cse_01U365TB3GHnHxb2cgGx5fVw and cse_01HT8fdWFfrZsEDCkEagCK4m (RemoteTrigger get_run_log). The shared checkout /projects/dev/vuoro-cloud is on main at 4241b9b (= origin/main) after the operator's gen-43 promote run.

## Evidence

- sprintctl: `agentops#2514 notes 3612-3615`
- artifact: `/projects/dev/vuoro-cloud/docs/evidence/2026-09-25-d044-restore-drill.md`
- artifact: `/projects/dev/vuoro-cloud/docs/evidence/2026-09-25-d044-live-isolation.md`
- session: `3424a321-11b0-43d4-841f-715a2d55adc6`

## sprintctl bundle

- none (sprintctl unavailable or produced no bundle)

## Successor

- session: d5ca23ce-779a-43e9-a44e-4bebdc05f0f4
- acknowledged: 2026-09-26T06:13:20Z
