# Handoff 2026-10-01-vuoro-cloud-gen66-and-ecosystem.v1

<!-- Rendered from the canonical JSON beside this file. Do not hand-edit:
     `agentops handoff validate` and `ack` read the JSON, never this. -->

**Objective.** Continue the vuoro.cloud rollout and the ecosystem work started on 2026-09-30.
Live and verified: - gen 62 = G3: migration 021, owner role. - gen 63 = G4: unit 1.5 DB role split complete. - gen 64: chatgpt-connector OAuth client. - gen 65: chatgpt-connector gets the claude-connector /mcp scopes. The operator tested
  ChatGPT with all 8 tools: 5 work fully, and 3 need ready backlog to act on
  (claim_work/heartbeat/report_outcome).
- Shared authority vuoro-shared migrated from schema 18 to 20 on vuoro-service 0.1.82
  (appservice #1810). Backup: vuoro-postgres-vuoro-20260930T221313Z.dump.age.

Remaining: - Promote gen 66 (#200 follow-ups + #202 D7 hardening, migration 022; pin #205 merged,
  vuoro-cloud main 931e09a, image sha256:0a309f54772238f4230338d3d28bb0c8fa12360b073b5000a361bdd791a475e2).
- Gen 67: admin 2.2a, #203, head fddf9c3, approved. - Gen 68: tenant runtime vuoro-service 0.1.82 plus the read_predecessor_context row. - The queued ecosystem units below.

**Next action.** 1. Ack. 2. Ask the operator to run, in a normal terminal (not nix develop):
   cd /projects/dev/vuoro-cloud; git switch main && git pull --ff-only;
   scripts/promote-release.sh sha256:0a309f54772238f4230338d3d28bb0c8fa12360b073b5000a361bdd791a475e2
   It prints `created pull request #N` for v0.1.0-poc.66.
3. Verify candidate #N first-hand:
   - signatures: GNUPGHOME=<scratch keyring imported from config/trusted-promoters.openpgp.asc>
     git verify-commit/verify-tag --raw gives GOODSIG/VALIDSIG AB73C1C5617B5098038CDA953AF95EDEB8243BE7;
   - shape: empty commit on 931e09a; tag trailers Deployment-Generation 66 / OCI-Digest 0a309f54;
   - all 7 apps/ digests match; the only migration since poc.65 is 022.
4. Get an independent Sonnet review comment posted on the candidate, wait for all 4 CI checks,
   then: credctl merge --repository forgejo:bayleaf/vuoro-cloud --pr N --head-sha <sha>
   --style fast-forward-only --forgejo-url https://git.apps.kotona.app
5. Dispatch: POST .../actions/workflows/promote-deployment.yaml/dispatches with
   {"ref":"v0.1.0-poc.66","inputs":{"deployment_tag":"v0.1.0-poc.66","image_digest":"sha256:0a309f54..."}}
   (token ~/.config/forgejo/workstation-scope-token; 204 means queued).
6. Verify:
   - Flux apps is at poc.66;
   - the vuoro-control-migrate Job is Complete;
   - SELECT name FROM schema_migrations WHERE name='022_d7_reassert.sql' returns a row;
   - pods are healthy, with 0 permission denied.
   Record the result on vuoro-cloud PR #202.
7. Then gen 67 (admin 2.2a, #203). Bring the branch up to date with main using
   POST /pulls/203/update?style=merge, and verify the patch-id equals the reviewed one.
   Merge on green CI, pin, promote and verify per its spec
   (docs/plans/2026-09-30-admin-slice-2.2-spec.md). After it ships, the operator runs
   `vuoro-cli admin login` again so the token carries vuoro:admin.principal.

## Predecessor

- harness: claude-code
- session: adf01c72-9707-4082-9cde-3a5261b444f6
- model: claude-opus-5-5
- context used: unknown%
- transcript: unknown
- origin: `workstation:/projects/dev/agentops/docs/dispatch/handoffs/2026-10-01-vuoro-cloud-gen66-and-ecosystem.v1.json` (authoritative copy; an ack from another host goes through it)

Read-only after transfer: once a successor acks, the predecessor makes no
edits and takes no external actions. It stays consultable.

## Constraints

- Review before merge. Every PR, pin and candidate gets an independent review comment posted on the PR before merge: Opus 5.5 for code, Sonnet 5.5 for pins, candidates and release bumps. Merge only at the reviewed head with green CI. On vuoro-cloud, merge only fast-forward with credctl merge. If a branch had to be updated from main, verify that the patch-id equals the reviewed patch before merging.
- Promotion needs the operator's YubiKey. Only the operator runs scripts/promote-release.sh. Give the command as numbered steps that say where each runs, in a normal terminal, never chained after `nix develop`.
- vuoro.cloud production access: export KUBECONFIG=/home/bayleaf/.config/vuoro/kube/poc.yaml; nmcli connection up vuoro-cloud-operator, and bring it down after the checks. Appservice/homelab cluster access (vuoro-shared and others): KUBECONFIG=/projects/dev/appservice/clusters/.kube/config, context admin@main, which is agent-usable. Network commands need the sandbox disabled.
- The SOPS rule is "don't read the operator's SOPS password/age key". Tooling decryption (sops exec-file, make validate) is allowed. Never print secret values.
- Design hierarchy: intent, then architecture docs and ADRs, then implementation. Intent beats docs; a docs/intent mismatch means proposing a doc correction. Open design questions go to a planner that derives answers from the docs. Only genuine gaps go to the operator.
- Do not pull or commit on agentops shared local main while value-routing dispatch runs are live (session 9b66e044 owns #2540, #2562-2566, #2570, #2578, #2579). Use worktrees cut from origin/main in every repo. sprintctl shared local main carries another session's unpushed commits.
- If the permission classifier denies an action, do not split or reroute it. Stop and ask the operator.
- One cause per vuoro-cloud generation. Gen 66 ships #200 + #202 together because #200 has no runtime effect.

## Decisions

- **chatgpt-connector has the same /mcp scopes as claude-connector (gen 65).** — Operator request. Verified live; the operator tested all 8 tools.
- **Cross-principal read of notes/evidence via run continuation stays as shared contract §4 designs it.** — The operator confirmed it. Notes and evidence must not hold secrets; this is documented in sprintctl and vuoro.
- **ActionQ's abstraction is relocated per split horizon, not superseded. The conformance suite lives in vuoro, with each provider bound through its served operations. There is no narrow interface inside sprintctl.** — Operator intent: "enable somewhere, not necessarily actionq; split horizon". Derived from the docs in vuoro #164; the register is in vuoro docs/direction/disposition-register.yaml.
- **sprintctl 0.11.0 (schemas 19 and 20) released; vuoro-service 0.1.82 released; vuoro-shared migrated to schema 20.** — Run continuation (read_predecessor_context) end to end. Old 0.10.x clients keep working over HTTP; this was verified.

## Rejected

- **Extracting the lease/claim surface inside actionq (tranche 4 in actionq db.py)** — The freeze's Decision excludes leases from the authority contract; leases belong to sprintctl work.lease.* per #253 R4.
- **Retiring the action-resource projection without a replacement** — The operator needed the abstraction; per the register it must become a derived query.

## Repo state

Digest definition: v5 (see the handoffs README).

| path | branch | head | dirty | unpushed | diff_sha256 |
|---|---|---|---|---|---|
| `/projects/dev/vuoro-cloud` | main | `1c93dd88a945` | no | 0 | `e3b0c44298fc1c14…` |
| `/projects/dev/agentops` | main | `11b93f19794c` | yes | 2 | `daf15f5bd05681a2…` |

## Unresolved

- Gen 68, vuoro.cloud: move the tenant runtime from vuoro-service 0.1.79 to 0.1.82 in both config/compatibility.json and apps/runtime-config/compatibility.json, and add `"read_predecessor_context": "vuoro:work.read"` to MCP_TOOL_SCOPES (comment agentops#2525), in one generation. Each tenant DB migrates 18 to 20 through the controller's vuoro-migrate-<gen> Job on reconcile (the owner PATCHes desired_state READY). Take a CNPG backup per tenant first.
- The workstation sprintctl is 0.10.0. Reinstall from the v0.11.0 tag when no session is mid-command: uv tool install --force --reinstall 'sprintctl[remote,served] @ git+...@v0.11.0'.
- The operator should pull agentops shared local main when no dispatch run is active, to activate the #296 audit-capture fix. Follow-ups: #2591 (subagent-exit.sh) and #2592 (re-attribute about 670 misfiled rows).
- #2555, the tenant-provisioner role: the plan is ready; G1 builder not started. Summary at /tmp/claude-1000/-projects-dev-agentops/adf01c72-9707-4082-9cde-3a5261b444f6/scratchpad/plan-2555.md. Two roles: vuoro_tenant_owner (not CNPG-managed) and vuoro_tenant_provisioner (CNPG-managed, inRoles owner). Rolls out over G1 to G3. The materializer is agent-runnable under the corrected SOPS rule.
- Admin slice 2 items: #2582 (2.2b, which carries m1/n4/n5/n6 from the 2.2a review), #2583 (2.3), #2584 (2.4, next free migration number), #2585 (R), #2586/#2587 (O.1/O.2), #2588 (F-2). Also #2589 and #2590.
- Abstraction units: #2593 (provider-neutral lease suite in vuoro), which starts when #2570 is done; then #2594, then #2595 (harvest the ActionQ freeze; this meets the precondition for archiving actionq).
- ActionQ retirement residue, to be done in other repos: - copy the invariants into sprintctl release tests; - remove vuoro's actionq shims and the stale effect_tools.py docstring; - close the 12 stale actionq tracker items, per D1 as amended.
- sprintctl #2596: proposal for a note maxLength and a response byte budget.
- Audit index: one orphaned index-only event from 2026-08-30 (`ad:01M1A6GS4F86X97XNZ448RZXT6` is probably it). Re-emit it or accept the loss; do not run `auditctl rebuild` with `--allow-index-only` until this is decided.
- Nits filed in reviews, not blocking: appservice #1810 empty-CSV-on-refusal; D7 quoted-identifier allowlist regex.

## Evidence

- session: `adf01c72-9707-4082-9cde-3a5261b444f6`
- artifact: `/projects/dev/agentops/docs/dispatch/handoffs/2026-09-29-vuoro-cloud-role-split.v2.json`
- artifact: `/tmp/claude-1000/-projects-dev-agentops/adf01c72-9707-4082-9cde-3a5261b444f6/scratchpad/preflight-022.sql`
- artifact: `/tmp/claude-1000/-projects-dev-agentops/adf01c72-9707-4082-9cde-3a5261b444f6/scratchpad/plan-2555.md`
- artifact: `/projects/dev/vuoro-cloud-admin-2.2a/docs/plans/2026-09-30-admin-slice-2.2-spec.md`

## sprintctl bundle

- none (sprintctl unavailable or produced no bundle)

## Successor

- session: 77af7e1f-00fa-4195-a0d4-80b5ac2e99e1
- acknowledged: 2026-10-01T17:13:14Z
