# Corrected native-runtime federation program closure and retained-boundary ADR

Status: **source and evaluation tranche closed; operator cutover, W1 review,
knowledge publication, and two public repository publications remain open**.

Evidence snapshot: 2026-08-20T08:44Z. GitHub states were fetched from the
canonical repositories. Served Sprintctl state was read from repository
`_orchestration`; no served or runtime state was changed while preparing this
record.

## Executive decision

The corrected end state is native-runtime federation, not a replacement
execution plane:

- native Codex, Claude, OpenCode, and other harness sessions execute work;
- Git remains code and review authority;
- Sprintctl owns work intent, advisory reservations, and owner-side
  expected-revision compare-and-swap;
- ActionQ retains federation, evidence, acceptance, settlement,
  reconciliation, and a bounded historical archive, but no daemon, harness,
  session-wrapper, or HTTP execution plane;
- acceptance remains an explicit evaluator/operator decision; and
- deployment truth remains in the deployment owner and is not inferred from a
  source merge.

The takeover experiment is **NARROW**, not PROVE or KILL. Direct Git plus a
concise `HANDOFF`, exact receipts, explicit settlement, and acceptance is the
default for bounded single-repository continuation. Retain the takeover
machinery only as an optional read-only reconciliation/export adapter when
multiple execution or evidence authorities genuinely compete.

Local `worker-fast` inference is also **NARROW**: one real bounded repository
repair succeeded under a frontier coordinator's mechanical oracle and
independent refinement, but the route remains `experimental_unqualified`.
Availability and one accepted result do not qualify a general Agentops hybrid
route.

## Executive outcome matrix

| Workstream | Authoritative evidence | Outcome | Remaining boundary |
| --- | --- | --- | --- |
| Plan realignment | Agentops [#45](https://github.com/bayleafwalker/agentops/pull/45) at `038c345`; Vuoro [#49](https://github.com/bayleafwalker/vuoro/pull/49) at `4af415d`; generated Kctl [#6](https://github.com/bayleafwalker/kctl/pull/6) at `5f009bf`; generated Auditctl [#8](https://github.com/bayleafwalker/auditctl/pull/8) at `c8ca47b` | Merged | Current guidance still needs the host-local root assembly update described below. |
| ActionQ execution retirement | ActionQ [#30](https://github.com/bayleafwalker/actionq/pull/30) at `9dccf4e084da88f3f0c52bb9d845b64bed89d202`; CI success | Source complete | Appservice phases, running unit shutdown, and NixOS deployment are not complete or implied. |
| Dispatcher retirement | actionq-dispatch [#2](https://github.com/bayleafwalker/actionq-dispatch/pull/2) at `510822a8ed1ee24e5eafdfd92aaf8a76f3f425e4`; terminal release [`actionq-dispatcher-v0.2.0`](https://github.com/bayleafwalker/actionq-dispatch/releases/tag/actionq-dispatcher-v0.2.0) | Merged and released as a deterministic fail-fast tombstone | Existing launchers still require operator retirement; the tombstone is not a compatibility executor. |
| Tranche-4 architecture | ActionQ W0 [#31](https://github.com/bayleafwalker/actionq/pull/31) at `89ec87607d71af1156771db2e0c927d74017f5a0`; CI success | Contract ratified | W1 [#33](https://github.com/bayleafwalker/actionq/pull/33) is an open draft and R1 is **BLOCKED** pending classification/completeness remediation; W2-W6 and operator decisions remain future work. W7 is not authorized. |
| Volatile context and CAS | Sprintctl [#41](https://github.com/bayleafwalker/sprintctl/pull/41) at `160b4cc`; release [v0.3.1](https://github.com/bayleafwalker/sprintctl/releases/tag/v0.3.1) at `ef372b6805adc6c73d9650c3570f2aab4c846094` | Merged, tested, and released | Native-hook installation and any deployment remain operator-owned and were not performed. |
| Cluster-alignment proof | cluster-alignment-mvp [#1](https://github.com/bayleafwalker/cluster-alignment-mvp/pull/1) at `27f4480`; coordinator-integrated candidate `0a05a37` | Capability proof published | It is a bounded read-only proof, not a cluster controller or deployment. |
| Local-inference dogfood | Receipt SHA-256 `bee8f37c820fc83bb503771511f3a2ce7447e530db55dfd1426c733994b0443b`; OpenCode session `ses_fe1ee6077ffekc2oWIsZl36Chd` | One attempt accepted after coordinator refinement | `experimental_unqualified`; no formal route promotion. |
| Acceptance Lab | Provenance adapter [#2](https://github.com/bayleafwalker/acceptance-lab/pull/2) at `01f0bca`; campaign [#3](https://github.com/bayleafwalker/acceptance-lab/pull/3) at `d18e757` | Evaluation path landed | The takeover campaign case intentionally evaluates the earlier `4412ca1` state; it is not the later final adjudication. |
| FlowLab | Baseline release [v0.1.0](https://github.com/bayleafwalker/flowlab/releases/tag/v0.1.0) at `5e002ab`; Auditctl grounding [#1](https://github.com/bayleafwalker/flowlab/pull/1) at `d6ebec6`; campaign [#2](https://github.com/bayleafwalker/flowlab/pull/2) at `0189b70` | Evaluation and ADR landed | Capacity-policy interventions remain unmeasurable; no production instrumentation was added. |
| Takeover experiment | Final experiment `208f38d`; publication audit `c083ddbc59d4db1b601d53dd0f3cf79ba270f4b7`; blind reviewer preferred direct control | Final verdict **NARROW** | Public `bayleafwalker/vuoro-takeover-experiment` repository is absent. |
| Durable workflow closure | Sprintctl item `2217`, events `2392` and `2393`; Auditctl `ad:01M0F3TF5R9WR90WKZDGCBT5F7` | Findings and authority rejection recorded | Item is pending; Kctl intake awaits an actor with `knowledge.candidate.intake`. |

## Exact source and release ledger

### ActionQ and tranche 4

ActionQ PR #30 removed the session wrapper, daemon modules, harness adapters,
routing, scope iteration, usage limit, Git evidence, harness profiles, and the
HTTP server. Its merged source no longer supplies the old daemon entry point.
That fact must not be translated into a runtime-cutover claim.

The ratified W0 contract is ActionQ PR #31. It chooses separate
`federation-schema/v1` and `federation/v1` domains, preserves execution
migrations 001-012 byte-for-byte, treats legacy claim/lease as writable
compatibility only through W4, and requires a database-enforced redacted
archive at W5. Storage remains an internal `actionq.storage` boundary unless a
second real consumer and separate packaging RFC justify extraction.

As of the evidence snapshot, W1 PR #33 is **OPEN, DRAFT** at head
`d0fa1fee10270a9608997b92db4fb3ef2e1db1f2`. Its GitHub `test` check is
successful. The PR adds a machine-readable reachability inventory and
falsifiers; its reported focused gate is 70 passing tests and its reported
full PostgreSQL suite is 473 passed, 20 skipped. No GitHub reviews or comments
are recorded. The independent R1 boundary review is nevertheless **BLOCKED**
pending classification/completeness remediation; that review result has not
yet been submitted as a GitHub review or comment. A green static gate is not
acceptance. The PR changes no ActionQ Python, SQL, package metadata, catalog,
runtime, deployment, or appservice state and grants no authority for W2,
module movement, or extraction.

### Sprintctl volatile-context pilot

Sprintctl PR #41 adds an opaque `status_revision`, a bounded 4,096-byte
allowlisted `work-item-context/v1` projection, and a read-only mutation
precheck. The precheck supplies early feedback only: the owning status command
compares the revision again under the authoritative lock. The opt-in hook is
inert until configured, writes no authority state, and fails closed for a
recognized status precheck when bound context or the served API is missing or
stale.

PR #41 passed Python 3.11, Python 3.12, disposable PostgreSQL, and Kctl producer
checks. Release PR [#42](https://github.com/bayleafwalker/sprintctl/pull/42)
merged at `ef372b6805adc6c73d9650c3570f2aab4c846094`; annotated tag `v0.3.1`
points to that commit. The released wheel
`sprintctl-0.3.1-py3-none-any.whl` has SHA-256
`f59f0859c9a090cfb6fd8f71fa134c036e69182f413cf4e8a176b03d0e735112`.

### Evaluation and dogfood

The local-inference worker ran once through OpenCode 1.18.18 using
`local3090/worker-fast` and the `ao-mechanical-bulk` agent. It completed in
26.235 seconds, reported 17,959 input tokens, 2,727 output tokens, 219,771
cache-read tokens, and zero model cost. The worker could not commit, push,
mutate Sprintctl, or touch a cluster. It corrected a genuine manifest defect:
Git administrative metadata had been classified as undeclared payload after
the package became a Git worktree. The frontier coordinator removed one
redundant predicate, then required 12/12 tests, a positive 26-file manifest
gate, a negative undeclared-file gate, an empty protected-path diff, and
`git diff --check` before accepting the candidate.

Acceptance Lab's two campaign cases each score 1.0/PASS. The local-inference
case requires the unqualified-route limitation as a cited fact. The takeover
case requires the evaluator to report G1 unproven, G7/G8 pending, and the
verdict withheld at commit `4412ca1`; PASS means that intermediate state was
reported honestly. It does not conflict with the later completed experiment.

FlowLab's sanitized campaign contains eight Auditctl-shaped reconstruction
records, two measurable sessions, zero resolved blockers, one unresolved
blocker, and one truncated session. It records one strong mechanical pass and
one strong independent-review failure. Context warming, competitive duplicate
search, and exogenous speculation remain **UNMEASURABLE**. Its accepted ADR
retains Acceptance Lab for scenario scoring and FlowLab for aggregate flow
metrics, narrows local inference to oracle-backed tasks, and recommends native
instrumentation without authorizing it.

### Final takeover adjudication

The completed experiment passes G0-G7. G8 passes with two recorded packaging
defects: the sealed packets omitted a substantive pre-interruption inventory
and an explicit continuation-eligibility rule. The byte-preserved blind review
preferred the direct-control path with moderate confidence. After unblinding,
the direct path used four rather than five state locations and 148 rather than
212 glue lines, while both paths required six post-interruption operator
actions, contained the stale candidate, and bound all six criteria to exact
revisions.

The retained result is exact-revision evidence, explicit settlement,
lineage-preserving stale-result import, adversarial replay, and an optional
rebuildable explanation/export view for true multi-authority cases. The
rejected result is a general takeover runner, a new execution control plane,
or a mandatory projection for ordinary bounded continuation.

## Manifest and current-guidance cleanup

Legacy ActionQ daemon/dispatcher hook publisher selections have been removed
from the current repository manifests. Current GitHub status is:

| Repository | PR | Merge commit | Check state at merge |
| --- | --- | --- | --- |
| ActionQ | [#32](https://github.com/bayleafwalker/actionq/pull/32) | `f8600e0` | `test` success |
| Vuoro | [#50](https://github.com/bayleafwalker/vuoro/pull/50) | `130af1a` | `test` success |
| Sprintctl | [#44](https://github.com/bayleafwalker/sprintctl/pull/44) | `db52e2f` | Python 3.11/3.12, Kctl producer, and disposable PostgreSQL success |
| Kctl | [#7](https://github.com/bayleafwalker/kctl/pull/7) | `5d75970` | Python 3.11/3.12 and Sprintctl compatibility success |
| Auditctl | [#9](https://github.com/bayleafwalker/auditctl/pull/9) | `a32cff4` | No GitHub checks reported |
| Outctl | [#5](https://github.com/bayleafwalker/outctl/pull/5) | `22ddb9f` | Merged with baseline-equivalent Python and native failures; package jobs skipped |
| homelab-analytics | [#15](https://github.com/bayleafwalker/homelab-analytics/pull/15) | `da10f21` | Dependency audit success; baseline-equivalent `verify-fast` and `docker-smoke` failures |
| homelab-gitops-template | [#1](https://github.com/bayleafwalker/homelab-gitops-template/pull/1) | `9fea25a` | Kustomize/repository check success |

The Outctl and homelab-analytics merges do not prove those repositories' wider
CI is healthy. Their PRs record focused manifest/contract gates and identify
the failing jobs as existing baseline conditions; the cleanup did not repair
the frozen product suites.

Agentops current guidance was separately corrected by [#46](https://github.com/bayleafwalker/agentops/pull/46)
at `161ec4a`. That merge adds the retirement boundary and the
[host-local root-guidance proposal](../workspace/root-actionq-retirement-guidance-proposal.md).
The assembled `/projects/dev/AGENTS.md` still contains obsolete
`dispatcher-once`/daemon examples. Because that file is host-local and not a
repository authority, its owner must apply the proposal on each host; copying
one host's assembled file wholesale is not an authorized substitute.

## Source, runtime, and deployment are separate facts

| Plane | Current evidence | What it does not prove |
| --- | --- | --- |
| Source | ActionQ #30, dispatcher #2/release, W0 #31, and guidance/manifest cleanups are merged | No process was stopped, no namespace ownership changed, no image was rolled out, and no schema/catalog was migrated. |
| Runtime | The last explicit handoff reported the devbox daemon still running; this closure task did not query or mutate it | Runtime retirement remains unproven until the operator stops and disables the unit and captures evidence. |
| Deployment | Appservice branches `retire/actionq-server-phase1` at `7e24a9d` and `retire/actionq-server-phase2` at `565c534` exist with no PRs; both have diverged from current `main`. Gitops-nixos [#16](https://github.com/bayleafwalker/gitops-nixos/pull/16) remains an open draft at `50bc3d5`. | Neither appservice phase is reconciled. The NixOS change is not deployed. The PR #16 GitHub job failed before executing any steps and has no logs; the PR records a successful local `nix flake check`. |

No appservice dispatch, Flux reconciliation, Kubernetes mutation, service
stop, NixOS deploy, schema mutation, or catalog cutover was performed as part
of this program-closure record.

## Operator escalation order

ActionQ #30 is already merged. The remaining retirement must preserve this
order:

1. Update/review as needed, merge, and reconcile appservice
   `retire/actionq-server-phase1`. Prove that `ns/vscode` remains healthy and is
   owned by `actionq-db`, including the ActionQ CNPG cluster and agent-cockpit.
2. Only after that proof, update/review as needed, merge, and reconcile
   `retire/actionq-server-phase2`. Prove safe removal of the ActionQ server app
   and cockpit's `COCKPIT_ACTIONQ_SERVER_URL`.
3. On devbox, interactively run
   `sudo systemctl disable --now actionq-dispatch.service`; both disable and
   stop are required.
4. Only after steps 1-3, merge and deploy gitops-nixos PR #16, then capture the
   resulting unit/package evidence.

Do **not** bump `ACTIONQ_REQUIRED_REVISION` to make the legacy launcher appear
healthy. Once ActionQ #30 is merged, the old pin cannot be satisfied by current
main because the package intentionally has no `actionq-daemon` entry point.
Repinning would install a package that cannot satisfy the unit's contract.

## Ratified tranche-4 decisions still required

These are genuine semantic or operator decisions, not routine implementation
gaps:

1. Before W3, choose the legacy read-retention duration, the
   durable-authoritative export target, the restore objective, and the
   destructive-archive approval path. W3 must exercise export and restore.
2. Separately authorize any schema migration or deployment execution. W0
   authorizes neither.
3. Approve the final catalog cutover only after the ActionQ/Vuoro releases and
   current external-consumer evidence satisfy the frozen order.
4. Before W6 closes, ratify whether `actionq-runner` is retired, extracted, or
   transferred and prove zero reachability from federation roots.
5. If a second real storage consumer appears, decide through a separate
   packaging RFC whether it justifies replacing the internal
   `actionq.storage` boundary with a published distribution.
6. W7 remains separately **unauthorized**. Archive deletion, old-catalog
   removal, migration-loader removal, credential destruction, or retention
   expiry requires a new destructive-retirement plan, current zero-consumer
   evidence, and a restore rehearsal. Indefinite redacted retention is the
   safe default until then.

## Durable closure and publication ledger

Sprintctl served item `2217`, “Close corrected native-runtime federation
evaluation program,” is currently `pending`, assigned to `meta-coordinator`,
with no active reservation. Its refs `680`-`687` bind the primary ActionQ,
dispatcher, Sprintctl release, cluster-alignment, Acceptance Lab, FlowLab, and
gitops-nixos artifacts.

- Event `2392` records the NARROW decision at experiment commit `208f38d`, the
  direct-Git default, and the retained multi-authority adapter boundary.
- Event `2393` records that Kctl intake was rejected because actor
  `workstation-vuoro` lacks `knowledge.candidate.intake`. It points to Auditctl
  receipt `ad:01M0F3TF5R9WR90WKZDGCBT5F7` and leaves publication pending for
  an authorized actor.
- The Sprintctl item remains pending because `_orchestration` has no committed
  UUID authority binding for the required CAS status transition. This report
  does not grant itself that authority.

The two unpublished repositories remain visible gaps:

- GitHub repository `bayleafwalker/q-spec` does not exist. A reviewed bundle
  is host-persistent at
  `/projects/dev/_artifacts/q-spec-public-review-20260820/q-spec-reviewed.bundle`
  with SHA-256
  `5d8283edf6c8cdb1c12e272eb6bf996fadbda6a050d624d00ffad5f91f166768`.
  The accepted review commit is
  `d7a493452318d463e1b1c19e2a0a3439b51ff513`; the intermediate cleanup commit
  `f56565b` is not the normative publication head.
- GitHub repository `bayleafwalker/vuoro-takeover-experiment` does not exist.
  The publication audit is at
  `c083ddbc59d4db1b601d53dd0f3cf79ba270f4b7`. Its host-persistent bundle is
  `/projects/dev/_artifacts/takeover-publication-20260820/vuoro-takeover-experiment-c083ddbc.bundle`
  with SHA-256
  `a4ac6148636f8d103eb5afa3444f7ffb8e028dc1e0aee7edc96e718ec5cb33fd`.

Both packages are transport evidence, not durable-authoritative publication;
neither is cross-host-ready and neither has a verified replica. The root
workspace proposal is durable in Agentops Git, while applying it to each
host-local assembled `AGENTS.md` remains pending.

## Requirement and evidence audit

| Requirement | Evidence assessment | Status |
| --- | --- | --- |
| Realign plans to the native-runtime federation end state | Agentops #45, Vuoro #49, Kctl #6, Auditctl #8, and Agentops #46 are merged | **Proven complete for versioned plans/current guidance** |
| Remove ActionQ execution/server source and retire the dispatcher | ActionQ #30 and actionq-dispatch #2/release are merged; successful ActionQ CI and tombstone evidence recorded | **Proven complete in source** |
| Complete runtime and deployment retirement | Ordered branches and held Nix PR exist, but no phase reconciliation, health proof, interactive stop/disable, or deploy evidence exists | **Incomplete; operator-owned** |
| Ratify tranche-4 architecture before extraction | W0 #31 merged; W1 #33 is a green open draft but independent R1 is BLOCKED pending classification/completeness remediation | **W0 complete; W1 blocked/incomplete; W2-W7 not claimed** |
| Deliver volatile-context freshness/CAS | Sprintctl #41 and v0.3.1 are merged/released with four green check families and pinned wheel digest | **Proven complete in released source; deployment not claimed** |
| Deliver cluster-alignment capability proof | Public repository main contains #1 at `27f4480`; bounded runtime tests and manifest gates recorded | **Proven as a read-only capability proof** |
| Dogfood local inference through frontier coordination | Frozen packet, one worker attempt, coordinator refinement, cold positive/negative gates, and receipt hash exist | **Proven for one experimental task; route qualification explicitly not proven** |
| Run Acceptance Lab and FlowLab evaluation | Acceptance #2/#3 and FlowLab #1/#2 merged with green checks and deterministic reports | **Proven complete for the sanitized campaign; production compatibility/capacity benefit not proven** |
| Complete fair takeover experiment and independent review | Final commit `208f38d`, publication audit `c083ddbc`, G0-G8 adjudication, and blind direct-control preference exist | **Proven complete with NARROW verdict** |
| Publish takeover and q-spec histories | GitHub reports both repositories absent; reviewed bundles are host-persistent only | **Incomplete; operator repository creation/publication required** |
| Remove legacy hook publishers from current manifests | Eight cleanup PRs are merged; exact exceptional CI states are recorded above | **Proven complete for manifest selection; wider Outctl/analytics CI remains unhealthy** |
| Close durable workflow/knowledge state | Sprint events and Auditctl receipt exist, but item `2217` is pending and Kctl intake was authority-rejected | **Incomplete by design; authorized CAS and Kctl publisher required** |
| Avoid unauthorized production mutation | No appservice, cluster, runtime, schema, catalog, or deployment action occurred in this closure work; all such work is explicitly staged | **Proven for this program execution record** |

## Closure condition

This document closes the corrected 20 August source/evaluation tranche and
records its retained architecture. It does not close the operator rollout or
tranche-4 implementation program. Full program closure requires, at minimum:

- classification/completeness remediation and independent R1 acceptance of W1
  PR #33;
- ordered appservice phase evidence, daemon disable/stop, and PR #16 deployment;
- creation and reviewed publication of q-spec and the takeover experiment;
- an authorized Kctl intake decision and Sprintctl item CAS closure; and
- application of the versioned root-guidance proposal to each host-local
  assembled workspace guide.

Until those facts exist, source merges must not be narrated as a running-system
cutover, and this record must remain a closure handoff rather than a declaration
that every future tranche is complete.
