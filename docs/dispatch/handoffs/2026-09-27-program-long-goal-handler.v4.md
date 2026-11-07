# Handoff 2026-09-27-program-long-goal-handler.v4

<!-- Rendered from the canonical JSON beside this file. Do not hand-edit:
     `agentops handoff validate` and `ack` read the JSON, never this. -->

**Objective.** Carry the vuoro.cloud program forward under the adopted architecture (agentops docs/architecture/2026-09-27-agentic-ecosystem-and-split-horizon.md, #255: coordination without custody; vuoro.cloud primary coordination ledger, protected horizon owns authority) and the decided backlog (agentops docs/plans/2026-09-27-backlog-ideation.md, #253). State at handoff (2026-09-27 ~23:45 EEST): generation 50 is LIVE and every tenant is rolled. Gen 48 (v0.1.0-poc.48, 7e6011e, image 74fdb1f9) edge-proof mount + API-root redirect. Gen 49 (v0.1.0-poc.49, 0bce4b8, image adacef6e): vuoro-cloud #139 admin plane refused at the public edge (admin unit 1.2), #141 insert-only hash-chained audit_events (admin unit 1.1, control migration 014; verified live: guards all ENABLE ALWAYS, chain ok over 68 rows, VACUUM done), #135 gateway mints random 128-bit jti (agentops#2519). Gen 50 (v0.1.0-poc.50, 2c58ce9, image c4acb4e1): tenant runtime vuoro-service 0.1.78 (ghcr sha256:ac4d65671ae4f13b7097fbded3a487f2dc32f9e3a6ec58887e783b7e25b09c48, attested) / vuoro-mcp-edge 0.1.5 / sprintctl 0.10.0 (56bfbc4, wheel d8cc3515...; #2539 verification profiles as requirement sets, #2540 lease operator contract: 600 s authority TTL, heartbeat 120 s, claim-superseded with generations, work.lease.report-outcome-v1), remote schema 18. Tenants kotona (01M3ABJS1QW0Q6BNDCHP0DDTYF) and isolation-proof (01M3CA7V972W3HQSYWBG7V6JBB, operator is owner) both run ac4d6567 with both containers ready; claude mcp list connected. vuoro main 5a5db34 includes #144-#149; sprintctl main 56bfbc4 includes #99-#101.

**Next action.** Ack this record. Ask the operator to re-grant merge/deploy/mutation approval (it does not carry over). Then, in order of value: (1) Operator decision: grant vuoro:work.claim now that every tenant serves the claim tools (the handoff precondition is met), then #2524 (M1-4). (2) Resume the admin-identity track: agentops #262 (design) + #263 (authz addendum slice 0; needs Q2's explicit step-up for freeze/unfreeze in its O.1-O.2 units) — both open, need current-head reviews. Units 1.3, 1.4 and 3.1 exist as UNPUSHED local branches in /projects/dev/vuoro-cloud (feat/admin-1.3-admin-identity 3c648f4, feat/admin-1.4-cli-admin 9b8b89d, feat/admin-3.1-control-resource 25691c4; their old /tmp worktrees are gone after the reboot, run ). The predecessor's specs and reviews (spec-u13.md, review-u13.md, review-262-r*.md, review-263*.md, #139/#141 reviews) are copied to /projects/dev/archive/2026-09-27-orch-admin-notes/. 1.3 is stacked on #141's PRE-fix head: rebase onto vuoro-cloud main (2c58ce9; #141 landed with two extra fix commits), then push and open a PR with a fresh review. (3) Cheap follow-ups from tonight's reviews: vuoro-cloud gateway sends "id": null on its own pre-id refusals (gateway.py ~349, ~894-898, ~960-962) while edge 0.1.5 omits id; config.py:39 assertion_ttl_seconds has no upper bound (>30 breaks every runtime); vuoro docs/plans/2026-09-26-e2-e3-shared-contract.md:216 still names 0.1.77; vuoro-service OperationRejectedError has no details param, so claim-superseded generations don't reach the wire; #141 review leftovers for unit 1.5 (check_guards should flag unknown triggers; 016 grant matrix must give runtime roles exactly SELECT+INSERT on audit_events, nothing on audit_chain_head, no owner-role membership). (4) #2529 remainder, #2541-#2543 (same pg.py, now unblocked), #2533 audit capture repair (local), #2532, #2535, #2536/#2537. Procedure notes: vuoro-cloud allows ONLY fast-forward merges and refuses a branch behind main — update with POST /pulls/<n>/update?style=merge, verify the diff vs main is identical to the reviewed head, wait for all 4 statuses (credential-free-gates runs last), then credctl merge --style fast-forward-only. A generation is: runtime/feature PRs merged -> wait for main's publish job -> pin PR (4 apps/ manifests to the Forgejo sha-<main> index digest via docker buildx imagetools inspect) -> review -> merge -> CNPG Backup CR in vuoro-data -> operator runs scripts/promote-release.sh <digest> <gen> (YubiKey; on "No such device" run gpg --card-status with GNUPGHOME=~/.config/vuoro/openpgp and retry) -> verify-commit/verify-tag -> ff-merge candidate -> dispatch curl (agent can run it now) -> flux reconcile source + the three kustomizations (apps stalls on platform otherwise) -> verify pod imageIDs -> tenant rolls by owner PATCH from the browser console.

## Predecessor

- harness: claude-code
- session: 88e08983-bd74-4705-89d5-5b898a16c605
- model: claude-opus-5-5
- context used: unknown%
- transcript: unknown
- origin: `workstation:/projects/dev/agentops/docs/dispatch/handoffs/2026-09-27-program-long-goal-handler.v4.json` (authoritative copy; an ack from another host goes through it)

Read-only after transfer: once a successor acks, the predecessor makes no
edits and takes no external actions. It stays consultable.

## Constraints

- PoC cluster needs `nmcli connection up vuoro-cloud-operator` and KUBECONFIG=/home/bayleaf/.config/vuoro/kube/poc.yaml; network tools need the sandbox disabled.
- The classifier blocks agent reads of production databases (kubectl exec psql, control-pod python); hand those queries to the operator as exact `!` commands. Creating CNPG Backup CRs and flux reconciles were allowed.
- Tenant rolls are the operator's owner PATCH from the api.vuoro.cloud browser console (X-CSRF-Token from the vuoro_csrf cookie); the controller has no fleet resync.

## Decisions

- **Merged conflicting CHANGELOG-only PR branches by merging main in (no force-push)** — Force-push was denied earlier; each merge was checked mechanically (non-CHANGELOG diff byte-identical to the reviewed head) and noted on the PR.
- **sprintctl released as 0.10.0, not 0.9.1** — #99/#100 change the adapter catalog (profile enum->pattern, new op, removed ttl_seconds input, renamed code/event), which changes vuoro's pinned catalog hashes.
- **Gen 49 control-plane only, lease runtime as separate gen 50** — Kept the signed control-plane changes independent of the longer release chain; gen 49 needed no tenant roll.
- **#2540: a report under a stale-but-not-taken-over lease stays lease-expired (not settled)** — INV-L1 names stale leases explicitly; both reviewers agreed; the holder reactivates and reports under a new key.

## Rejected

- **Rewriting shipped 0.9.0 history in the plan** — #253 keeps the contract normative and lists shipped deviations as follow-ups.
- **Opening replacement Forgejo PRs to dodge a force-push denial** — classifier treats it as the same outcome.

## Repo state

Digest definition: v4 (see the handoffs README).

| path | branch | head | dirty | unpushed | diff_sha256 |
|---|---|---|---|---|---|
| `/projects/dev/agentops` | main | `2e8e82ebbed9` | yes | 0 | `95f844356e2478f6…` |
| `/projects/dev/vuoro` | main | `5a5db34ba7f4` | no | 0 | `e3b0c44298fc1c14…` |
| `/projects/dev/vuoro-cloud` | main | `2c58ce9777cd` | no | 0 | `e3b0c44298fc1c14…` |
| `/projects/dev/sprintctl` | main | `56bfbc446892` | no | 0 | `e3b0c44298fc1c14…` |

## Unresolved

- #2531: handoff digest v4 includes sibling versions of the same track; do not ack superseded versions (2026-09-27 v1-v3 of this track exist).
- agentops #254 (UX/docs library) READY WITH CHANGES; operator has not read it.
- Cloud sessions from the predecessor opened no PRs yet: agentops#2538 shard-guard self-protection (session_01YYBRQ7FjYGSZyZQSSGcjgT), agentops#2534 doc-drift (session_014HgyH3cbusJWrfcM4gwDk2 agentops, session_01H3dSjcPei1jjZmBxsvWwZh sprintctl). Check their tracker items / sessions.
- #145 predecessor_run_id: a run_id becomes a read key for that run's notes/evidence within workspace+repo work:read; needs explicit agreement or a predecessor-side grant before a durable store enables continuation. vuoro-cloud needs an MCP_TOOL_SCOPES row for read_predecessor_context when it ships.
- Operator decisions still open: keep/drop the five held branches (appservice/outctl WIP, two devbox-orphan branches); keep isolation-proof workspace (recommend keep).
- GitHub mirrors of vuoro-cloud lag Forgejo main; agentops main has the audit timer's modified shard and untracked .codex/hooks.json, counts.sql, d14-restore-test.sh — not ours, leave them.
- Backups taken 2026-09-27 in vuoro-data: vuoro-postgres-pre-gen48-kotona-20260927, -pre-gen48-isolation-proof-20260927, -pre-gen49-20260927, -pre-gen50-20260927 (all completed). Promote runs: #517 gen 48, #536 gen 49, #544 gen 50.
- Scratch in /tmp (lease worktrees, wip-2540.patch) is superseded by merged sprintctl#100 and is lost on reboot; nothing needed. Local sprintctl branch feat/lease-operator-contract-2540-v2 can be deleted.

## Evidence

- session: `88e08983-bd74-4705-89d5-5b898a16c605`

## sprintctl bundle

- `/projects/dev/agentops/docs/dispatch/handoffs/2026-09-27-program-long-goal-handler.v4.sprintctl-bundle.json` (sha256 `6021af6f0c9b9414…`)

## Successor

- session: 3040bff0-f66b-48fd-a25c-7cbc0dbc6f5e
- acknowledged: 2026-09-28T07:44:39Z
