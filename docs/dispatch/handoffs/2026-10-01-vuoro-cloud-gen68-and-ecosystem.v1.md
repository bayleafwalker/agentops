# Handoff 2026-10-01-vuoro-cloud-gen68-and-ecosystem.v1

<!-- Rendered from the canonical JSON beside this file. Do not hand-edit:
     `agentops handoff validate` and `ack` read the JSON, never this. -->

**Objective.** Continue the vuoro.cloud rollout: finish generation 68 (tenant runtime vuoro-service 0.1.82 / sprintctl 0.11.0
+ read_predecessor_context scope), migrate the three tenants 18->20 one at a time, then the queued ecosystem units.
Shipped and verified this session (2026-10-01):
- gen 66 = v0.1.0-poc.66 (#200 + #202 D7, migration 022). Candidate #206, deploy run #800. 022 row applied 17:36:22 UTC,
  pods healthy, 0 permission denied. Recorded on vuoro-cloud#202 (issuecomment-1251).
- gen 67 = v0.1.0-poc.67 (admin 2.2a #203, migration 023). Pin #207 (dc59f11), candidate #208 (d0a67cd), deploy run #810.
  023 row applied 19:38:36 UTC, users.disabled_at/disabled_by_operation present, pods healthy, 0 permission denied.
  Recorded on #203 (issuecomment-1266).
- gen 68 code: #209 merged (66f6232; Opus review APPROVE WITH NITS issuecomment-1270; PR body amended with m1/m2).
  Image for 66f6232 = sha256:8fec868b8282f071b298736b03f9e3b87280e465faf303f4ce7a1d67836f5404 (publish run #813).
- gen 68 pin #210 open: head 903fa639f80bd9fbf0e5d98691793c459f16d851 (rebased onto 66f6232; patch-id
  6ca2a0da17c38e319490324e132e776149552f36 equals reviewed c865c15; Sonnet APPROVE issuecomment-1276, rebase note 1280).
  CI was pending at handoff (focused green; integration, release-evidence, credential-free-gates pending).
- vuoro-cli installed for the operator: gitops-nixos e796dac adds vuoro-cloud[cli] to scripts/update-agentops-tools.sh
  (pushed straight to main without a PR review; the operator was told). Installed now in ~/.local/bin from vuoro-cloud d0a67cd.


**Next action.** 1. Ack.
2. Check vuoro-cloud PR #210 CI at 903fa639f80bd9fbf0e5d98691793c459f16d851 (GET /api/v1/repos/bayleaf/vuoro-cloud/commits/<sha>/status,
   token ~/.config/forgejo/workstation-scope-token). If the head moved, re-verify patch-id 6ca2a0da17c38e319490324e132e776149552f36.
3. On 4/4 green: credctl merge --repository forgejo:bayleaf/vuoro-cloud --pr 210 --head-sha 903fa639f80bd9fbf0e5d98691793c459f16d851
   --style fast-forward-only --forgejo-url https://git.apps.kotona.app ; then clean up pin/gen68-image and /projects/dev/vuoro-cloud-pin68.
4. Take the CNPG backup vuoro-postgres-pre-gen68-20261001 and confirm completed.
5. Give the operator ONE line:
   cd /projects/dev/vuoro-cloud && git switch main && git pull --ff-only && scripts/promote-release.sh sha256:8fec868b8282f071b298736b03f9e3b87280e465faf303f4ce7a1d67836f5404
6. Continue per the first unresolved item (verify candidate, Sonnet review, merge, dispatch, verify, then tenants one at a time).

## Predecessor

- harness: claude-code
- session: 77af7e1f-00fa-4195-a0d4-80b5ac2e99e1
- model: claude-opus-5-5
- context used: unknown%
- transcript: unknown
- origin: `workstation:/projects/dev/agentops/docs/dispatch/handoffs/2026-10-01-vuoro-cloud-gen68-and-ecosystem.v1.json` (authoritative copy; an ack from another host goes through it)

Read-only after transfer: once a successor acks, the predecessor makes no
edits and takes no external actions. It stays consultable.

## Constraints

- Review before merge. Every PR, pin and candidate gets an independent review comment posted on the PR before merge: Opus 5.5 for code, Sonnet 5.5 for pins, candidates and release bumps. Merge only at the reviewed head with green CI. On vuoro-cloud, merge only fast-forward with credctl merge (a transient 401 'forge-read-failed' happened once; a plain retry merged). After any rebase/update, verify patch-id equals the reviewed patch and note it on the PR.
- git fetch origin before cutting any branch after a server-side merge; the gen-68 pin was first cut from a stale origin/main.
- Promotion needs the operator's YubiKey; only the operator runs scripts/promote-release.sh. Give it as ONE &&-chained line (operator preference, 2026-10-01): cd /projects/dev/vuoro-cloud && git switch main && git pull --ff-only && scripts/promote-release.sh sha256:<digest>. Split into numbered steps only around nix develop.
- vuoro.cloud production: export KUBECONFIG=/home/bayleaf/.config/vuoro/kube/poc.yaml; nmcli connection up vuoro-cloud-operator, and down after checks. Network commands need the sandbox disabled. The operator approved service mutations, deployments, pushes to main and production reads (psql via kubectl exec into vuoro-data/vuoro-postgres-1, db vuoro_control; kubectl logs) for this rollout.
- Flux reads the GitHub mirror (interval 1m) and lagged after GitHub clone timeouts; after dispatch, annotate gitrepository vuoro-cloud and the three kustomizations with reconcile.fluxcd.io/requestedAt and wait for lastAppliedRevision.
- New image digest lookup: docker buildx imagetools inspect git.apps.kotona.app/bayleaf/vuoro-cloud:sha-<full sha> (the registry API refuses the workstation token; docker has creds).
- SOPS rule: tooling decryption is allowed (sops set / exec-file, verify-runtime-pin.py); never read the age key or SOPS password, never print secret values.
- Design hierarchy: intent > architecture docs/ADRs > implementation; mismatches become doc-correction proposals.
- Do not pull or commit on agentops shared local main while value-routing dispatch runs are live (session 9b66e044). Use worktrees from origin/main. sprintctl shared local main carries another session's unpushed commits.
- If the permission classifier denies an action, do not split or reroute it; stop and ask the operator.
- One cause per vuoro-cloud generation.

## Decisions

- **Gen 68 ships runtime 0.1.82 and the read_predecessor_context scope together** — Handoff v1 decision; on a 0.1.79 tenant the tool returns a harmless unknown-tool error (verified in #209 review).
- **tenant_schema stays 2** — It is vuoro-cloud's own schema, independent of sprintctl remote schema (verified by builder and Opus review).
- **One CNPG backup covers all tenants** — All three tenant DBs live in the shared vuoro-data/vuoro-postgres cluster; precedent is Backup vuoro-postgres-pre-genNN-<date> with method barmanObjectStore.
- **vuoro-cli installed via the uv tool refresh, not a fetchgit derivation** — Both vuoro-cloud remotes return 401 anonymously, so a pinned Nix fetch cannot work.

## Rejected

- **Restoring the backup as the first response to a failed tenant migration** — sprintctl 0.11.0 migrates 19+20 in one transaction; if a post-migrate step fails, roll forward (fix, PATCH again) and restore only as a last resort (#209 review m1).

## Repo state

Digest definition: v5 (see the handoffs README).

| path | branch | head | dirty | unpushed | diff_sha256 |
|---|---|---|---|---|---|
| `/projects/dev/vuoro-cloud` | main | `d0a67cdac817` | no | 0 | `e3b0c44298fc1c14…` |
| `/projects/dev/vuoro-cloud-pin68` | pin/gen68-image | `903fa639f80b` | no | 1 | `e3b0c44298fc1c14…` |
| `/projects/dev/gitops-nixos` | main | `e796dac8fa26` | yes | 0 | `e3b0c44298fc1c14…` |
| `/projects/dev/agentops` | main | `6aded3fce082` | yes | 0 | `5e88839d23d87b77…` |

**Running:**

- B
- a
- c
- k
- g
- r
- o
- u
- n
- d
-  
- w
- a
- t
- c
- h
- e
- r
-  
- f
- o
- r
-  
- P
- R
-  
- #
- 2
- 1
- 0
-  
- C
- I
-  
- a
- t
-  
- 9
- 0
- 3
- f
- a
- 6
- 3
-  
- i
- n
-  
- t
- h
- e
-  
- p
- r
- e
- d
- e
- c
- e
- s
- s
- o
- r
-  
- s
- e
- s
- s
- i
- o
- n
-  
- (
- i
- t
-  
- d
- o
- e
- s
-  
- n
- o
- t
-  
- t
- r
- a
- n
- s
- f
- e
- r
- ;
-  
- r
- e
- -
- c
- h
- e
- c
- k
-  
- C
- I
-  
- y
- o
- u
- r
- s
- e
- l
- f
- )
- .

## Unresolved

- Gen 68 rollout, in order: (1) #210 CI green -> credctl merge --pr 210 --head-sha 903fa639f80bd9fbf0e5d98691793c459f16d851 fast-forward; delete branch pin/gen68-image and worktree /projects/dev/vuoro-cloud-pin68 after verifying the merge. (2) kubectl -n vuoro-data apply a Backup vuoro-postgres-pre-gen68-20261001 (cluster vuoro-postgres, method barmanObjectStore); wait for phase completed. (3) Operator one-liner promote with sha256:8fec868b8282f071b298736b03f9e3b87280e465faf303f4ce7a1d67836f5404 -> candidate PR; verify sigs (AB73C1C5617B5098038CDA953AF95EDEB8243BE7, throwaway GNUPGHOME from config/trusted-promoters.openpgp.asc), empty commit on the pin head, trailers Deployment-Generation 68 / OCI-Digest 8fec868b, 7 apps digests, no new migrations; Sonnet review; CI; merge; dispatch promote-deployment.yaml; reconcile Flux. (4) Verify control-plane pods on 8fec868b, tenant-controller restarted (picks up 0.1.82 VUORO_CLOUD_RUNTIME_IMAGE; if not, rollout restart it before any tenant PATCH), 0 permission denied. (5) Per tenant, one at a time (vuoro-ws-01m14w25eykc, vuoro-ws-01m3abjs1qw0, vuoro-ws-01m3ca7v972w): PATCH /api/control/v1/workspaces/<id> {"desired_state":"READY"} (owner-authorized), expect gateway 503 workspace-not-ready during reconcile (up to ~10 min), watch vuoro-migrate-<gen> Job Complete and vuoro-service 1/1 on 0.1.82, confirm remote schema 20. Find who/what can issue the owner PATCH before starting. (6) Record on #209.
- #209 review follow-ups: n1 checksum annotation for the vuoro-controller-runtime Secret on apps/tenant-controller/deployment.yaml; n2 tighter test (negative-scope case, call count); n3 IMPLEMENTATION-STATUS.md lines 20/144 still say 0.1.79 - update after gen 68 ships.
- Admin 2.2a ntfy enablement (spec docs/plans/2026-09-30-admin-slice-2.2-spec.md 'Operator actions' 1-4): operator chooses endpoint, SOPS secret, then an agent-prepared enable change. Not blocking.
- Operator may still need to run: nmcli connection up vuoro-cloud-operator && vuoro-cli admin login --handle operator; nmcli connection down vuoro-cloud-operator (not confirmed done).
- Workstation sprintctl is 0.10.0; reinstall from v0.11.0 when no session is mid-command.
- Operator should pull agentops shared local main when no dispatch run is active (#296 audit-capture fix). Follow-ups #2591, #2592.
- #2555 tenant-provisioner role: plan at /tmp/claude-1000/-projects-dev-agentops/adf01c72-9707-4082-9cde-3a5261b444f6/scratchpad/plan-2555.md; G1 builder not started.
- Admin slice 2 items: #2582 (2.2b, carries m1/n4/n5/n6 from the 2.2a review), #2583, #2584, #2585, #2586/#2587, #2588, #2589, #2590.
- Abstraction units: #2593 (after #2570), then #2594, then #2595. ActionQ retirement residue in other repos (sprintctl release-test invariants, vuoro actionq shims + effect_tools.py docstring, close 12 stale actionq tracker items).
- sprintctl #2596 note maxLength / response byte budget proposal.
- Audit index orphan from 2026-08-30 (likely ad:01M1A6GS4F86X97XNZ448RZXT6): re-emit or accept; no auditctl rebuild --allow-index-only until decided.
- Non-blocking nits: appservice #1810 empty-CSV-on-refusal; D7 quoted-identifier allowlist regex.

## Evidence

- session: `77af7e1f-00fa-4195-a0d4-80b5ac2e99e1`
- artifact: `/projects/dev/agentops/docs/dispatch/handoffs/2026-10-01-vuoro-cloud-gen66-and-ecosystem.v1.json`

## sprintctl bundle

- none (sprintctl unavailable or produced no bundle)

## Successor

- session: 01a102d4-c0d5-7591-90a8-34b1ba3c2617
- acknowledged: 2026-10-03T17:45:04Z
