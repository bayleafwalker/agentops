# Corrected native-runtime federation program: full session handoff

Date: 2026-08-20

Status: **source/evaluation tranche reasonably complete; W0 and W1 complete;
W2 active as unreviewed dormant-source implementation; operator cutover,
publications, knowledge/workflow closure, and W2-W6 remain open. W7 is
unauthorized.**

This is the canonical continuation handoff for the 20 August program. The
[closure assessment](corrected-native-runtime-federation-program-closure-2026-08-20.md)
contains the retained-boundary ADR and exact W1 acceptance addendum. This
document gathers the complete session narrative, processed workstreams,
remaining issues, ownership boundaries, and storage classifications needed by
the next coordinator.

## End state and session boundary

The plans were realigned away from an ActionQ-owned execution/control plane:

- native Codex, Claude, OpenCode, and other harness sessions execute work;
- Git owns code and review authority;
- Sprintctl owns work intent, advisory reservations, and owner-side
  `status_revision` compare-and-swap;
- ActionQ retains federation, evidence, acceptance, settlement, reconciliation,
  and bounded historical archive responsibilities, but no daemon, harness,
  session-wrapper, or HTTP execution plane; and
- evaluator/operator acceptance remains explicit.

Source truth, runtime truth, and deployment truth were kept separate. This
program session performed no appservice dispatch or reconciliation, cluster
mutation, live schema/catalog migration, daemon stop, Nix deployment, or
production credential mutation.

## Exact merged and released ledger

| Tract | Authoritative result | Qualification |
| --- | --- | --- |
| Plan realignment | Agentops #45 `038c345`; Vuoro #49 `4af415d`; generated Kctl #6 `5f009bf`; generated Auditctl #8 `c8ca47b` | Merged. |
| ActionQ tranches 1-3 | ActionQ #30 `9dccf4e084da88f3f0c52bb9d845b64bed89d202` | Removed the session wrapper, nine daemon modules, seven harness adapters, routing, `scope_iterate`, `usage_limit`, `git_evidence`, `harness_profiles`, and `server.py`; reported 13,169 to 8,273 LOC and 487 passed, 19 skipped, zero failed. Source retirement, not runtime retirement. |
| Dispatcher | actionq-dispatch #2 `510822a8ed1ee24e5eafdfd92aaf8a76f3f425e4`; `actionq-dispatcher-v0.2.0` | Terminal fail-closed tombstone. It is not a compatibility executor and must not be invoked or scheduled for new work. |
| Tranche 4 W0 | ActionQ #31 `89ec87607d71af1156771db2e0c927d74017f5a0`; [owner ratification](https://github.com/bayleafwalker/actionq/pull/31#issuecomment-5353774023) | Separate `federation-schema/v1` and `federation/v1`; execution migrations 001-012 frozen; compatibility writable through W4; database-enforced redacted archive at W5; W7 unauthorized. |
| Tranche 4 W1 | ActionQ #33, R1 **ACCEPT** at exact head `de0f17e2bffbf656f6e3aa0df3e2b1c768376fc7`; merge `edc6f41f38646531e8e6114128cec25cade7a700` | GitHub test success; full suite 489 passed, 19 skipped, zero failed; 51-member portable proof SHA-256 `1c3b37539a5bde36d812fe3a31430216235d0300be95bc875a1f79dfe646307c`. Pins reachability/classification only; no deployment/cutover authority. |
| Sprintctl | #41 `160b4cc`; release PR #42 `ef372b6805adc6c73d9650c3570f2aab4c846094`; v0.3.1; generated context #43 `f17c72f`; manifest cleanup #44 `db52e2f` | Adds opaque `status_revision`, bounded 4,096-byte allowlisted `work-item-context/v1`, read-only precheck, and authoritative under-lock recheck. Wheel SHA-256 `f59f0859c9a090cfb6fd8f71fa134c036e69182f413cf4e8a176b03d0e735112`; attestation verified. |
| Acceptance Lab | Provenance adapter #2 `01f0bca`; campaign #3 `d18e75726fa0230b28c8c7e6c950e06aaabb2b04` | Both cases PASS/1.0. The takeover case grades the honest intermediate state at `4412ca1`, not the final adjudication. |
| FlowLab | v0.1.0 at `5e002ab`; grounding #1 `d6ebec65`; campaign/ADR #2 `0189b70d4f4812680027cc5583f06eca85f264ce` | Public and disclosure-reviewed. Published hashes bind public/synthetic artifacts, not low-entropy secrets. |
| Cluster alignment | #1 `27f4480`; coordinator candidate `0a05a37` | Public bounded read-only capability proof, not a controller or deployment. |
| Agentops guidance | #46 `161ec4a824e2dff916a25992495a26c8b734fb1a` | Current retirement boundary and host assembly proposal. |
| Canonical closure | #47 `6c01869b8a0c5ad3dfaf3313385f9a162900dab8` (accepted head `ab92db8`) | Original closure; the companion assessment's dated addendum supersedes its earlier W1-open snapshot. |

Current manifest publisher cleanup is also merged: ActionQ #32 `f8600e0`,
Auditctl #9 `a32cff4`, homelab-analytics #15 `da10f21`,
homelab-gitops-template #1 `9fea25a`, Kctl #7 `5d75970`, Outctl #5
`22ddb9f`, Sprintctl #44 `db52e2f`, and Vuoro #50 `130af1a`. No current
manifest selects a retired daemon/dispatcher publisher. The wider Outctl and
homelab-analytics baseline failures remain; those merges did not claim to fix
them.

## Evaluation findings and retained dispositions

### Frontier-coordinated local inference

A frontier coordinator dispatched OpenCode 1.18.18
`local3090/worker-fast` through `ao-mechanical-bulk`. The worker repaired a
real cluster-alignment manifest defect in 26.235 seconds, reporting 17,959
input tokens, 2,727 output tokens, 219,771 cache-read tokens, and zero model
cost. The coordinator removed a redundant predicate and required 12/12 tests,
a positive 26-file gate, a negative undeclared-file gate, an empty
protected-path diff, and `git diff --check`. Receipt SHA-256:
`bee8f37c820fc83bb503771511f3a2ce7447e530db55dfd1426c733994b0443b`.

Disposition: **NARROW / `experimental_unqualified`**. Retain only for bounded,
oracle-backed mechanical work under frontier assessment. One success does not
qualify a general route.

### Acceptance Lab and FlowLab

FlowLab contains eight sanitized reconstruction records, two measurable
sessions, zero resolved blockers, one unresolved blocker, and one truncation.
It contains both a strong mechanical pass and a strong independent-review
failure. Context warming, competitive duplicate search, exogenous speculation,
and capacity-policy interventions are **UNMEASURABLE**.

Retain Acceptance Lab for deterministic scenario scoring and FlowLab for
aggregate flow measurement and ADRs. Instrumentation is a future proposal,
not authorized deployment.

### Takeover experiment

The physically isolated takeover B2 candidate was `e55b60da` with EV001-EV006;
late same-thread A was `c72f01e`. Direct-control B was `b15514e`, with late A
at `2e3e5fd`. G0-G8 finally passed. The two packaging defects were omission of
a substantive pre-interruption inventory and an explicit
continuation-eligibility rule.

The blind reviewer preferred cobalt, later unblinded as direct control, with
moderate confidence; review commit `37ea8e33`. Final commit `208f38d` records
the **NARROW** verdict:

- default bounded single-repository continuation to Git plus a concise
  `HANDOFF`, exact receipts, explicit settlement, and acceptance;
- retain optional read-only multi-authority reconciliation/export,
  lineage-preserving stale-result import, and adversarial replay; and
- reject a general takeover runner, execution control plane, or mandatory
  projection.

Publication audit `c083ddbc59d4db1b601d53dd0f3cf79ba270f4b7` is **ACCEPT**:
result bytes are unchanged and no secret, private transcript/prompt, or
low-entropy secret hash is present.

## ActionQ continuation state

### Runtime retirement remains operator-owned

ActionQ source retirement is complete; runtime retirement is unproven.
Appservice phase 1 at `7e24a9d` must transfer `ns/vscode` and the identity
registry to the staying `actionq-db` owner before phase 2 at `565c534` removes
the server and cockpit URL. Both branches have diverged from main and require
owner refresh/review. Deleting the old pruned app first could delete
`ns/vscode`, including cockpit and the ActionQ CNPG cluster.

The devbox unit was last reported running. The operator must interactively run
`sudo systemctl disable --now actionq-dispatch.service`; disable matters as
much as stop. Never bump `ACTIONQ_REQUIRED_REVISION`: current ActionQ
intentionally lacks `actionq-daemon`, so repinning cannot satisfy the unit.

Gitops-nixos #16 remains a draft at `50bc3d5`. Local `nix flake check` passed;
the GitHub job failed before running steps because of a runner/billing/spending
condition. Merge/deploy only after phase-1 proof, phase-2 proof, and
stop-and-disable proof.

### W2 is active but not durable

W2 currently exists only in clean worktree `/tmp/actionq-w2.WCZFso`, branch
`feature/federation-authority-v1`, based on `edc6f41`. It is not committed,
pushed, reviewed, or merged. Dormant source presently includes federation
migration 001, `federation_schema.py`, `federation.py`, package data, conftest,
and tests. It covers:

- action-independent resources and a frozen state machine;
- immutable owner plus expected-absence/exact-revision CAS;
- ACL, source-owned relations/cycles, external refs, and verified evidence;
- acceptance, settlement, supersede, and canonical digests;
- independent idempotency/decision ledger;
- persistent denied/stale/conflict decisions and response-loss replay; and
- `NOLOGIN` role separation.

Current focused evidence is 67 passing tests; PostgreSQL 18.4 integration is 39
passing. Remaining gates are the full suite, artifact validator, build/wheel
invariants, diff review, stronger falsifiers, independent R2, commit, push, and
draft PR. W2 grants no runtime, catalog, CLI, Vuoro, release, or schema
deployment mutation.

### W3-W7 sequence

- **W3:** before work starts, the operator ratifies legacy read-retention
  duration, durable-authoritative export target, restore objective, and the
  destructive-archive approval path. Implement deterministic backfill/rebuild
  and exercise export/restore; reject identity/digest drift, gaps, inferred
  acceptance/settlement, and pruned v1 history.
- **W4:** add separate `federation/v1` while preserving `execution/v1`
  byte-for-byte. Use coordinated ActionQ and Vuoro owner PRs, exact released
  wheel URL/digest and literal candidate SHA, and a five-domain composition
  validator. Reject stale global catalog revision before any ActionQ write.
  Serving/cutover requires separate operator authority.
- **W5:** only after deployed Vuoro/client rediscovery and current (at most one
  hour old) evidence, prove zero consumers, remove supported legacy writes,
  revoke runtime credentials/effective grants/sequences in the database,
  expose only redacted archive-reader views, and capture durable-authoritative
  pre/post Auditctl denial/read receipts. Repository tests cannot substitute
  for deployment evidence.
- **W6:** keep an internal `actionq.storage` seam unless a second real consumer
  plus packaging RFC justifies a distribution; keep facades and independent
  migration domains/rollback. Separately ratify whether `actionq-runner` is
  retired, extracted, or transferred and prove zero federation reachability.
- **W7:** **unauthorized**. No archive deletion, old catalog/loader removal,
  credential destruction, or retention expiry without a new destructive plan,
  W1-W6 completion, current zero-consumer proof, retained export, restore
  rehearsal, and exact targets/backups/approvals. Default to indefinite
  redacted retention.

## Pending public repositories

### q-spec

`bayleafwalker/q-spec` is absent. The reviewed publication head is
`d7a493452318d463e1b1c19e2a0a3439b51ff513`, not intermediate `f56565b`. It
aligns ActionQ federation v1, Sprintctl v0.3.1 reservation/CAS, and Kctl
served/Git authority; obsolete claims are historical and non-normative. The
review found it disclosure-safe.

The host-persistent transport bundle is
`/projects/dev/_artifacts/q-spec-public-review-20260820/q-spec-reviewed.bundle`,
SHA-256
`5d8283edf6c8cdb1c12e272eb6bf996fadbda6a050d624d00ffad5f91f166768`.
The source path `/tmp/q-spec-retirement.307WPx` is session-local/ephemeral.
After the operator creates an empty public repository, push baseline main,
then the reviewed branch, open a draft PR, independently review, and merge. Do
not publish the intermediate branch. A missing license/top-level README is a
discoverability/reuse concern, not a security blocker.

### Takeover experiment

`bayleafwalker/vuoro-takeover-experiment` is absent. Its host-persistent
transport bundle is
`/projects/dev/_artifacts/takeover-publication-20260820/vuoro-takeover-experiment-c083ddbc.bundle`,
SHA-256
`a4ac6148636f8d103eb5afa3444f7ffb8e028dc1e0aee7edc96e718ec5cb33fd`.
After the operator creates an empty public repository, push
`audit/publication-readiness:main` and verify the result.

These bundles are transport aids, not durable-authoritative records or
cross-host-ready handoffs. Neither has a verified replica.

## Guidance and durable workflow state

Agentops #46 is the Git-backed root-guidance proposal. Workstation
`/projects/dev/AGENTS.md` is now assembled with the corrected ActionQ retirement
boundary, and obsolete active daemon/dispatcher start instructions are absent.
Its host-local SHA-256 is
`dd2e6ca1776121aede51c60755a781eee28f9f02ad8b690be67b3cfececf4cdc`
(mtime 2026-08-20 12:08:32 +0300). This is host-persistent only. Apply the
documented asset-sync/assembly process separately on devbox-vm and the legacy
pod; do not call the workstation file cross-host-replicated.

Durable-authoritative Sprintctl state is `_orchestration` sprint 437 item
`2217`, still `pending`, assigned to `meta-coordinator`, with no active
reservation. Refs `680`-`688` bind the core artifacts; event `2392` records the
takeover NARROW decision, `2393` the Kctl authority rejection, and `2394` the W1
acceptance/merge and dormant-only W2 boundary. The item cannot CAS-close because
`_orchestration` lacks a committed UUID authority binding. Do not bypass it.

Durable-authoritative Auditctl receipt
`ad:01M0F3TF5R9WR90WKZDGCBT5F7` records rejected knowledge publication and
pending authority. The host-local export
`/projects/dev/_artifacts/dev/audit/events-2026-08-20.ndjson` is
semi-ephemeral evidence, not the authority. Kctl publication remains pending:
the served intake correctly rejected `workstation-vuoro`, which lacks
`knowledge.candidate.intake`. Do not widen authority. An authorized publisher
must intake/review/publish or reject, then attach the durable reference.

## Discovered issues and risks

1. Namespace prune/ownership makes the strict two-phase appservice order
   mandatory.
2. Source, runtime, and deployment state are easily but incorrectly conflated.
3. The stale daemon pin cannot be repaired by revision bumping.
4. Both appservice retirement branches have diverged from main.
5. Nix CI has an infrastructure failure despite a local pass.
6. Takeover sealed packets omitted two continuation-critical fields.
7. W1 was initially green despite incomplete classification and falsifiers;
   those defects were corrected before R1 ACCEPT.
8. The Acceptance Lab takeover case deliberately records an intermediate
   state, not the final verdict.
9. One successful local-inference attempt is insufficient for qualification.
10. FlowLab context/capacity claims remain unmeasurable.
11. Outctl and homelab-analytics wider baseline CI remains unhealthy.
12. The q-spec and takeover public remotes are absent.
13. q-spec lacks a license and top-level README.
14. Root-guide assembly and sync is per-host, not automatically replicated.
15. Sprint authority binding and Kctl publisher authority remain missing.
16. Agentops #47 remains stale about W1 until the companion addendum merges.
17. W2 is worktree-local and independently unreviewed.

## Next actions by owner and tract

| Owner/tract | Next action | Gate/boundary |
| --- | --- | --- |
| W2 owner and R2 reviewer | Finish gates and falsifiers; commit/push a draft PR; run independent R2. | Do not merge until R2 ACCEPT. No production mutation. |
| Appservice operator | Refresh/review phase 1, reconcile and prove health/ownership; only then refresh/review phase 2, reconcile, and prove health. | User-owned escalation channel; strict order. |
| Runtime/Nix operator | Interactively stop and disable the unit; then merge/deploy gitops-nixos #16 and capture evidence. | Requires both appservice phase proofs first. |
| Publication coordinator | After two empty public repositories exist, publish q-spec through reviewed PR and takeover audited main; verify. | Use only accepted/audited heads. |
| Knowledge/workflow owners | Authorized Kctl actor adjudicates; commit `_orchestration` authority binding; expected-revision CAS-close item `2217`. | Never bypass role or CAS authority. |
| Documentation owners | Independently review and merge the W1 addendum/full handoff; sync root guidance to other hosts. | Host assembly stays host-local until deliberately synchronized. |
| W3-W6 owners/operators | Follow the sequential packet and decision gates above. | Each later packet/cutover is separately reviewed and authorized. |
| Optional measurement/deployment | Install Sprintctl native precheck hooks only as operator-owned deployment; propose FlowLab instrumentation separately. | Neither is authorized by this handoff. |

## Storage and authority classification

| Classification | Current records |
| --- | --- |
| Cross-host-replicated / durable Git | Merged GitHub PRs and releases; public FlowLab and cluster-alignment repositories; Agentops proposal and closure. This addendum/handoff joins this class only after merge. |
| Durable-authoritative | Served Sprintctl item/events/refs; Auditctl receipt. Kctl has no accepted knowledge record and remains pending. |
| Host-persistent / semi-ephemeral on WorkstationLinux | `_artifacts` bundles, receipts, Auditctl export, and takeover working repository; no verified replicas. |
| Host-persistent only | Assembled workstation `/projects/dev/AGENTS.md`. |
| Session-local / ephemeral | `/tmp/q-spec-retirement.307WPx` and active W2 worktree `/tmp/actionq-w2.WCZFso` until their content is committed and pushed. |

## Reasonable continuation endpoint

The source/evaluation tranche and W1 closure are complete and reviewed. Public
proofs already exist for FlowLab and cluster alignment. Takeover and q-spec are
disclosure-cleared but await repository creation. Runtime rollout correctly
remains operator-owned. Federation work is sequenced with W2 active in a
session-local worktree and no downstream cutover authority implied.
