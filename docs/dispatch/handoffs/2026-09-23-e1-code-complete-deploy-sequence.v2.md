# Handoff 2026-09-23-e1-code-complete-deploy-sequence.v2

<!-- Rendered from the canonical JSON beside this file. Do not hand-edit:
     `agentops handoff validate` and `ack` read the JSON, never this. -->

**Objective.** Take E1 (agentops#2514) from code-complete to first use: roll the vuoro.cloud tenant runtime to vuoro-service 0.1.73, get the OAuth-authenticated /mcp route live on the pilot workspace 'kotona' behind the D-044 proofs, and reach the first-use trace that ends in a PR in an operator repo.

**Next action.** cd /projects/dev/vuoro-cloud && git fetch origin && git worktree add -b e1-runtime-pin-0.1.73 /projects/dev/_wt/vuoro-cloud-runtime-pin origin/main && cd /projects/dev/_wt/vuoro-cloud-runtime-pin && read docs/runbooks/operator-actions.md 'Verify the tenant runtime pin' and config/compatibility.json, then compare its tenant_schema / generation / client_protocol sets against vuoro main 483f972 (vuoro-service 0.1.73: packages/vuoro-service/pyproject.toml and its compatibility declarations) and list every difference on agentops#2514 as a note BEFORE editing. If compatible: set packages.vuoro-service to vuoro-service-v0.1.73@sha256:f5d656b51fb4674851a0976d684f7c2543896c5fe33df7d080b199871ed4e724 in config/compatibility.json and apps/runtime-config/compatibility.json, re-materialise the controller Secret per scripts/materialize-kubernetes-secrets.py, run make verify-runtime-pin with the age identity in the environment and nix develop -c make check-fast, open the Forgejo PR, land it fast-forward. Then hand the operator note 3597's steps 2-6 as explicit commands (promote-release, clients Secret, flag flip on gateway AND tenant-controller, D-044 proofs, connector).

## Predecessor

- harness: claude-code
- session: 9189d96f-2b13-4ff6-88aa-b24f3272eb2f
- model: Claude Fable 5.1 (claude-fable-5-1)
- context used: unknown%
- transcript: unknown
- origin: `workstation:/projects/dev/agentops/docs/dispatch/handoffs/2026-09-23-e1-code-complete-deploy-sequence.v2.json` (authoritative copy; an ack from another host goes through it)

Read-only after transfer: once a successor acks, the predecessor makes no
edits and takes no external actions. It stays consultable.

## Constraints

- Design for USE, not disposal (operator directive 2026-09-22): no trial counters, phase clocks or deletion-shaped deployment; GitOps rollback is the reversibility.
- Deploying to vuoro.cloud is scripts/promote-release.sh with two hardware YubiKey touches; there is no software fallback. Connector registration and the real clients-file Secret are the operator's acts. Do not expose anything publicly yourself: no DNS, HTTPRoute, TLS or vendor registration.
- Every guard is forced into its failure case before it is trusted (break, capture, revert). A reasoned 'would fail' is not evidence. Prefer mutation-style tests: the gateway review found nine guards whose removal left the suite green.
- vuoro-cloud: origin is Forgejo (git.apps.kotona.app, ssh push), github is a passive replica; CI is .forgejo/workflows/ci.yaml; land with a fast-forward-only REST merge. Its *.pem gitignore rule needs git add -f for public keys. The workstation secret hook blocks any Bash text that reads like handling decrypted material: write long note bodies to a file and pass them by path.
- Do NOT use isolation:'worktree' for subagents; create worktrees from the main session and forbid agents from running git. Do not remove a worktree while an agent is reading from it (happened once this session).
- MCP assertions carry work:read only; the edge refuses anything broader. vuoro:effect.apply is permanently rejected by the AS; vuoro:work.claim, evidence.record, effect.propose are reserved and refused until E2 flips one row in oauth_scopes.py. E2 (#2466) is a tool addition and nothing else; #2517 (actor attribution) blocks it.
- Nothing in vuoro_service.app.create_app may reference the MCP surface (tested). vuoro's MCP code is not vendored into vuoro-cloud; the runtime image is hosted unchanged.
- Pilot workspace is slug 'kotona', repo_id 'vuoro' (note 3591). Rename before the first item exists or not at all.
- Membership removal does not bump principal_epoch (D-045); the gateway re-checks grant revoked_at and active membership per request instead.

## Decisions

- **Operation names are work.public.list-v1 and work.public.item-v1 (hyphen), registered in sprintctl 0.7.3** — vuoro_adapter_kit.catalog._NAME forbids '/' in an operation name; a v2 registers beside v1.
- **list_ready_work = status pending AND blocked false; describe_work verifies the returned work_id; upstream error text never reaches the client** — sprintctl's own get_ready_items rule; review found active/blocked items presented as ready and upstream messages passed through verbatim.
- **Access token carries grant_id; verify_access_token requires kid as-2026-09 and typ at+jwt; issuer defaults to public_api_url** — revocation must cut a live token within one request (D-045); issuer on the API host keeps the session cookie and authorize on one host so no sign-in loop.
- **Strict RFC 9700 refresh-reuse revocation, no grace window** — single connector client; a lost token response forces re-consent, accepted.
- **Pre-auth paths (/mcp, /oauth/*, well-known) use an in-memory per-replica limiter and write no DB rows; control's rejected-scope audit is a log line pre-auth** — gate (i): an unauthenticated flood must produce zero control-DB writes; tests count rows before/after.
- **Gateway forwards a re-serialised, validated JSON-RPC object and forwards the raw query string to control** — the proxy had collapsed repeated OAuth parameters, silencing control's duplicate-parameter refusal; forwarding raw bytes lets the runtime see bodies the D-046 rule refuses.
- **Tenant mcp container is behind VUORO_CLOUD_TENANT_MCP_EDGE on both gateway and tenant-controller, default false** — the pinned runtime image (0.1.52) has no mcp-serve; a crash-looping second container would stall every tenant pod. Not disposal: rollout ordering.
- **AS keys required for control only when oauth_clients_file is set; gateway requires the public key (mount is in the same commit) and answers 503 without it at runtime** — rollout order image -> Secret -> clients file must never crash-loop a service on a missing Secret.
- **First USE closes #2514: an OAuth-authenticated hosted client calls both read tools and ends in a PR in an operator repo** — operator-attested testimony is the S14 shape; a PR is a durable artifact outside the gateway's logs.

## Rejected

- **pytest.importorskip('jsonschema') as the schema gate in sprintctl tests** — jsonschema is not a dev dependency; the whole module skipped silently (32 passed, 1 skipped, zero forced failures executed). Use the repo's own conformance validator. Two pre-existing tests still skip that way: #2516.
- **A 15 s repo-keyed list cache in the MCP edge** — with per-caller assertions it would hand one caller's answer to another without the shell checking the second caller.
- **Bumping principal_epoch on membership removal** — the epoch is global across workspaces (principal-epoch backlog D-3); a bump re-identifies the user everywhere. Per-request grant and membership checks replace it.
- **oauth_authorizations.session_id as a plain FK to web_sessions** — the lifespan prunes 30-day-old sessions while consented authorizations are retained behind grants: control would crash-loop ~30 days after the first consent. Nullable ON DELETE SET NULL now, with a second-lifespan regression test.
- **Non-2xx HTTP status for JSON-RPC errors on /mcp (404 for unknown method, 400 for bad params)** — Streamable-HTTP clients treat non-2xx as transport failure and never parse the body. Errors are HTTP 200 with a JSON-RPC error; invalid params are tool errors.
- **Treating a green local nix run as proof CI will pass on vuoro-cloud** — the *.pem gitignore rule dropped the public keys from the commit; local checks saw the untracked files, CI did not. Check git status --ignored before pushing.
- **Reading Forgejo job logs via the tasks-API id or the web /actions/runs/{n}/jobs/{i}/logs route** — both 404. Use /api/v1/.../actions/runs?limit -> /runs/{id}/jobs -> /jobs/{job_id}/logs; release-evidence reasons are in the release-gate artifact zip.
- **Rolling the tenant runtime pin 0.1.52 -> 0.1.73 as a mechanical bump** — it is a 21-release jump on the tenant runtime whose pin lives in the encrypted controller Secret derived from config/compatibility.json; compatibility.json's tenant_schema and generation sets must be checked against vuoro 0.1.73 first, then make verify-runtime-pin with the age identity.

## Repo state

Digest definition: v3 (see the handoffs README).

| path | branch | head | dirty | unpushed | diff_sha256 |
|---|---|---|---|---|---|
| `/projects/dev/agentops` | main | `32ca2f3b1743` | yes | 0 | `9df9f34ca53fc73c…` |
| `/projects/dev/vuoro` | e1-call-journal | `100082231f82` | no | 0 | `e3b0c44298fc1c14…` |
| `/projects/dev/vuoro-cloud` | docs/record-generation-33 | `f6d2c4217db7` | yes | 0 | `12d536a4b16ff352…` |
| `/projects/dev/sprintctl` | main | `822784ed747f` | no | 0 | `e3b0c44298fc1c14…` |
| `/projects/dev/appservice` | main | `a318f6ee074b` | no | 0 | `e3b0c44298fc1c14…` |

**Running:**

- Nothing running. No background jobs, timers, open PRs or worktrees from this session. Images published: vuoro-service 0.1.72 (sha256:5525556b6d64ed3fb6a7db81362668b2d427922b7442962c9cb50e69324083df, rolled to homelab vuoro-shared) and 0.1.73 (sha256:f5d656b51fb4674851a0976d684f7c2543896c5fe33df7d080b199871ed4e724, not rolled anywhere). vuoro.cloud still runs the pre-E1 images; nothing E1 is deployed there.
- TRAP unchanged: /projects/dev/vuoro-cloud is checked out on docs/record-generation-33 and dirty with another task's work; origin/main is a1b870f. Work from a fresh worktree off origin/main.

## Unresolved

- Which MCP protocol revision the claude.ai connector sends (2025-11-25 vs 2026-07-28) and whether it sends ping; the edge supports both eras and answers ping, but a real capture at the gateway on first connection settles it.
- Which redirect URI Claude Code actually sends for loopback (127.0.0.1 vs localhost); the AS accepts 127.0.0.1 and [::1] any port, refuses localhost. Confirm before relying on Claude Code as a client.
- D-044 live proofs are still owed on the cluster: tenant isolation before the public route, restore drill before the workspace holds real work. Both must be forced to fail first.
- The vuoro-cloud release-evidence job failed on main run 577 (after #75) with a runner DNS fault in terraform.validate (Could not resolve host git.apps.kotona.app); it passed on the next runs. Environmental, but watch for recurrence.
- Multi-repository workspaces cannot use MCP (#2518); actor attribution differs between OAuth and PAT paths (#2517, blocks E2); assertion jti replay cache (#2519).
- vuoro-cloud decision log D-045/D-046 and the two runbooks live on vuoro-cloud origin/main a1b870f (17-DECISION-LOG.md at the repo root, docs/runbooks/operator-actions.md, docs/runbooks/credential-rotation.md); the local checkout is on another branch, so read them with git show origin/main:<path>. vuoro packages/vuoro-mcp-edge/README.md is on vuoro main 483f972.

## Evidence

- sprintctl: `agentops#2514 notes 3593-3597 (step landings, review decisions, deploy-side sequence)`
- sprintctl: `agentops#2516, #2517 (dep #923 blocks #2466), #2518, #2519`
- artifact: `/projects/dev/agentops/docs/design/e1/e1-stronger-baseline-design-2026-09-22.md`
- artifact: `/projects/dev/agentops/docs/design/e1/README.md`
- artifact: `/projects/dev/sprintctl/docs/reference/work-public-contract.md`
- artifact: `/projects/dev/agentops/docs/dispatch/handoffs/2026-09-22-e1-phase0-landed-decisions-taken.v2.json`

## sprintctl bundle

- none (sprintctl unavailable or produced no bundle)

## Successor

- session: b2bee73e-4813-422f-b4c9-a9ed0b3cb894
- acknowledged: 2026-09-23T10:31:47Z
