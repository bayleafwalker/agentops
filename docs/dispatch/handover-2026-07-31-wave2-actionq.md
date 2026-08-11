# Wave 2 ActionQ handoff — 2026-07-31

## Stop state

Execution was stopped at the operator's request. The active goal was not
completed: ActionQ #2034 is shipped but awaits tracker reconciliation, and
#2035 is planned but unclaimed and unimplemented.

Machine-readable Sprintctl snapshot:
`/tmp/actionq-wave2-sprint-543-handoff.json`. The file was produced locally;
served handoff recording was refused because the current identity lacks the
handoff-record authority.

## Completed in this session

### ActionQ #2033

- Merged PR: <https://github.com/bayleafwalker/actionq/pull/7>
- Release: <https://github.com/bayleafwalker/actionq/releases/tag/v0.1.12>
- Merge commit: `c420175dcd1b5fe2961122ce5cce005875f2fcce`
- Reviewed source: `cb5e73b377d69a79b7c5d93c24d09b717e85436a`
- OCI image digest:
  `sha256:fc58a0c0cb6e25add7bc71f54a87e8805b8730d64007c1c11d1b6dea1946eca5`
- Final gate: 324 passed, 7 skipped; real OCI isolation histories passed.

### ActionQ #2034

- Merged PR: <https://github.com/bayleafwalker/actionq/pull/8>
- Release: <https://github.com/bayleafwalker/actionq/releases/tag/v0.1.13>
- Merge commit/tag target: `ebc856a2ac3957f9274a2cfb50179f49fd90ce2c`
- Independently reviewed source:
  `51afbf1f01bde91172539c6f58994d35a5c0bbbf`
- Final independent verdict: GO.
- Full disposable-PostgreSQL suite: 344 passed, 10 skipped.
- Execution-group histories: 22 passed, including claim/realize,
  claim/stop, sweep/requeue-after-stop, prefix starvation, and crossed-group
  deadlock regressions.
- ActionQ wheel SHA-256:
  `be2e5727b30d29636ce51c5a85130a25c96dae11b2cf0569ec5e4c5c905549a8`.
- Tracker refs #584–#586 and verification note #2178 are recorded.

The implementation adds immutable `execution-group/v1` projections, exact
envelope validation, `max_parallel`, `continue-independent`, permanent
`stop-new-claims`, served Vuoro operations, and schema migration v5.

### Auditctl prerequisite for ActionQ #2035

- Merged PR: <https://github.com/bayleafwalker/auditctl/pull/5>
- Merge commit: `df73a4e5ad96873cfa6768d1af573b1e0d98608e`
- Independently reviewed source:
  `3f79d5dcc398c586750e0bc58b985dbab63f0aaa`
- Final independent verdict: GO; no findings.
- Full suite: 70 passed, 9 skipped.
- Publisher subprocess contract is now v2 and freezes
  `candidate.reviewed`, source `actionq-review`, immutable findings pointers,
  no approval authority, and reconcile-before-retry behavior.
- #2035 refs #587–#588 and decision note #2179 are recorded.

## Immediate tracker reconciliation

ActionQ #2034 is still `active` only because claim #324's rotated token was
not durably captured. The old token is correctly fenced; served mode refuses
legacy adoption. The claim expires at:

`2026-07-31T20:42:36.781295Z`

Do not bypass the claim fence. After expiry:

1. From `/projects/dev/actionq`, run served maintenance/read checks and confirm
   claim #324 is expired or swept.
2. Re-claim/reconcile #2034 with a fresh proof under `workstation-vuoro`.
3. Mark #2034 done from that claim and release it, citing PR #8, v0.1.13,
   reviewed SHA `51afbf1...`, and note #2178.
4. Confirm #2035 becomes ready before claiming it.

The lost-proof condition and expiry are recorded on #2034 as note #2180.

## ActionQ #2035 frozen packet

Live state at stop: pending, unclaimed, blocked only by #2034. It has no
candidate branch or worktree. Baseline must be exact released ActionQ
`v0.1.13` / `ebc856a2...`.

### Package and authority boundary

- `actionq-contracts`: exact dependency-light contracts and canonicalization.
- `actionq`: ordinary actions, immutable spec/request binding, PostgreSQL
  lifecycle, claims, cancellation, settlement.
- `actionq-runner`: artifact resolution, fresh workspaces, verification,
  integration, review-result publication, recovery journals.
- Auditctl: independent bounded review observation only.
- Sprintctl/compiler: topology, readiness, dependencies, acceptance.
- No Git push, branch, PR, merge, approval, or disposition authority is added.

### Contract IDs

- `action-creation-request/v1`
- `verification-profile/v1`
- `candidate-verification-spec/v1`
- `candidate-verification-result/v1`
- `candidate-integration-spec/v1`
- `candidate-integration-result/v1`
- `candidate-review-spec/v1`
- `candidate-review-result/v1`

Canonical JSON uses exact fields, sorted UTF-8 JSON, no floats or unknown
keys. Contract digests are `sha256:<hex>`; CAS locators are
`artifact:sha256:<same-hex>` and must resolve to byte-identical content.
PostgreSQL canonical request/spec bytes are authoritative; CAS is not a second
authority.

### Immutable creation identity

Each generated ordinary action has one compiler-derived immutable
`request_ref = artifact:sha256:<sha256(canonical action-creation-request/v1)>`.
The request binds plan, topology, role, subject, spec ref/digest, and an
`input_set_digest` over every ordered immutable input. Exact replay returns the
same action; same logical plan/role/subject with different bytes conflicts
without writes. Wave integration binds every eligible passed member in frozen
#2034 ordinal order; no member is privileged.

### Topology and outcomes

- `independent`: verify/review one candidate; no synthetic integration.
- `stacked`: each candidate source equals the previous candidate commit/tree;
  the exact stack tip is the combined subject; no synthetic commit.
- `wave-integrated`: all candidates share the frozen base; integrate every
  passed member in ordinal order in a fresh environment and create one
  deterministic candidate.

Disposition outcomes:

- verification: `passed` or `candidate-failed`;
- integration: `integrated` or `conflict` (conflict publishes no integration
  bundle/receipt);
- review: `no-findings` or `findings-recorded` (neither is approval).

Missing/corrupt artifacts, binding mismatches, non-passed prerequisites,
unregistered profiles, cancellation, resource/runtime failure, and Auditctl
reconciliation conflict/inconclusive are protocol failures and produce no
candidate result artifact.

### Deterministic gates

- Profiles come only from an operator-owned read-only
  `verification-profile/v1` registry and are frozen by exact bytes/digest.
- Only exact `passed` verification results can feed integration.
- Integration commit author/email/time are derived policy; message is
  `actionq integration <spec_digest>`. Commit metadata is not stored inside
  the spec, avoiding a digest circularity.
- Audit reconciliation uses existing CLI reads only: newest 1,000 matching
  observations or 10 pages, 10-second subprocess deadline. Exact match means
  published; none permits at most one retry; divergent immutable refs or bound
  exhaustion are visible conflict/inconclusive, never success.
- Recursive contract denylist covers claim tokens/receipts, credentials,
  secrets, local paths, worktrees, mutable refs/remotes, prompts/transcripts,
  raw logs, and approval/merge/release authority fields.

Decision notes #2181 and Audit contract note #2179 are already on #2035.

### Recommended implementation/review sequence

1. Contracts, canonical fixtures, and independent wheel build.
2. Migration 006 plus generic immutable action request/spec persistence,
   claim-time integrity validation, runtime grants, and disposable-PG
   concurrency histories.
3. Reusable CAS artifact resolver and namespaced create-only recovery journal,
   retaining #2032 publication compatibility.
4. Fresh-context candidate verification.
5. Deterministic wave integration and stacked provenance validation.
6. Immutable review result plus Auditctl v2 subprocess/reconciliation adapter.
7. Cross-action Depth-2 histories, bounded Depth-3 model, full PostgreSQL and
   real OCI gates, independent exact-SHA protocol review, release, and tracker
   settlement.

## Worktrees and source hygiene

- `/tmp/actionq-2034-execution-groups`: clean reviewed branch, already merged;
  remote branch remains because local deletion failed while canonical main was
  checked out elsewhere.
- `/tmp/auditctl-candidate-reviewed-contract`: clean reviewed branch, already
  merged; same harmless local/remote cleanup residue.
- `/projects/dev/actionq`: canonical checkout; preserve user state and start
  #2035 from a new worktree at exact `origin/main`/`v0.1.13` after claiming.
- `/projects/dev/auditctl`: local main remains ahead/behind its tracking branch;
  do not implement from it. PR #5 came from the fresh `/tmp` worktree.
- Disposable PostgreSQL container `actionq2031pg` was running at
  `postgresql://actionq:actionq@127.0.0.1:55432/actionq` during verification.

## Release artifact hashes

ActionQ 0.1.13 assets built from the independently reviewed source:

- wheel: `be2e5727b30d29636ce51c5a85130a25c96dae11b2cf0569ec5e4c5c905549a8`
- sdist: `a7773b9488f46e4c420fe04cbe117f02b0349b4c224c0932d738d1499f4ef582`
- contracts wheel: `7c38ac4ccec7c4088b95b48b2be17e6e1ec4699bed9e4bd1a1725bcb508566b0`
- runner wheel: `9c07f24883c1d37cf34656796b18c44691d889a241a5482e38a28f478e3e516c`

## Resume instruction

Resume by reading this file and the served #2034/#2035 item views. Reconcile
#2034 only after the expired claim is no longer active, then claim #2035 and
create a fresh worktree from `ebc856a2...`. Do not reuse an original worker
checkout or begin runner implementation before the contract/persistence unit
has its own executable gate.
