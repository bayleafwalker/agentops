---
doc_id: portable-feature-batch.agentops.v1
status: proposed-candidate-only
supersedes: []
---

# Portable agent workflows: practical feature batch

Status: selected architecture for local candidate implementation, 2026-10-24.
This batch decomposes the [portable agent workflows plan](2026-10-24-portable-agent-workflows.md)
and its [contract inventory](../../evidence/2026-10-24-portable-workflow-contract-inventory.md)
into implementation slices. Owner choices do not block local source work:
implement against this architecture, marking provisional interfaces and
unknowns explicitly. Owner review, release, and compatibility qualification
remain later cross-owner evidence; this document does not ratify owner APIs or
authorize deployment. Source pins and evidence heads remain snapshots while
producer slices are in progress.

## Intended operator outcome

An operator can choose an authorized backlog, repository scope, budget, deadline,
and eligible host; start a bounded programme through a supported launch surface;
leave the initiating workstation; and later inspect verified candidate work,
uncertain operations, and explicit next actions from a different authorized
host. The fresh host must recover required owner facts and permitted source
inputs without the first host's private archive. It must never mistake a URL,
reservation, heartbeat, handoff, or published environment for proof of worker
startup or authority.

The programme may investigate and split work inside its authorization envelope,
but cannot expand repository scope, grants, budget, deadline, concurrency, or
landing policy. Native harnesses retain planning, model choice and native
continuation. Sprintctl remains work authority; Sovite remains execution-lease
and attempt authority; providers own native session state; Vuoro coordinates and
records; AgentOps owns shared guidance and diagnostics. Other owners retain
their source, host, credential, and service boundaries.

## User and operator requirements

1. **Prepare a run.** Show canonical repository identity and source revision,
   target branch and permitted paths, governing item/document revisions,
   dependency refs, source/artifact access class, requested harness/model, and
   the actual resolved capability/configuration when observable. Refuse to start
   when required source is missing, stale, inaccessible, or digest-mismatched.
2. **Set bounds.** Capture explicit goal, completion evidence, replanning limits,
   deadline, spend ceiling, aggregate concurrency ceiling, checkpoint interval,
   stop conditions, review/landing policy, and escalation route. Unknown cost
   coverage is shown as unknown, never zero.
3. **Dispatch and know what happened.** Distinguish intent, submitted,
   acknowledged, started, useful progress, candidate, verified, accepted,
   landed, and deployed observations. Show source, host, environment and native
   operation/session evidence with freshness and provenance. On response loss,
   reconcile the same operation before any retry.
4. **Continue elsewhere.** A separately authorized successor can reconstruct
   current work, predecessor notes/evidence, changed owner records and required
   source artifacts from owner reads and explicitly permitted transfer. It gets
   no authority from a copied packet, predecessor link, or reservation; a new
   attempt is linked to its predecessor and must pass current access checks.
5. **Review and return.** Present exact candidate commit and artifact digests,
   checks and tested head, independent review, and canonical landing receipt as
   separate results. Make blocked, refused, stale, untested, and uncertain
   states actionable. Retrying a merge or launch after ambiguous response
   requires reconciliation first. Deployment is outside this batch.
6. **Stop safely.** Budget/deadline exhaustion, revocation, stale source,
   expired execution fence, loss of required telemetry, or unresolved external
   effect halts new work and leaves an inspectable state. A reassigned work item
   alone does not cancel an old process.

## Feature packages and dependency order

Packages extend the eight programmes in the [programme index](../../dispatch/programmes/2026-10-24/08-integration.md)
and its linked programme briefs; they do not create a parallel authority or
backlog. Local candidate implementation follows the selected architecture
without waiting for owner decisions. Owner-specific changes still follow each
repository's review and release process, which supplies later compatibility
and qualification evidence.

| Order | Package and concrete capability | Owner interfaces and later qualification evidence | Acceptance evidence |
|---|---|---|---|
| 0 | **Source and interface baseline.** At launch reconcile canonical source, candidate ancestry, deployed/released versions, open reservations, and exact owner schemas. Define synthetic fixtures for stale/missing refs, wrong repo/workspace, revoked grants, response loss and unknown usage. | Use verified local source pins and explicit provisional interfaces for implementation; owner release references are reconciled during later compatibility qualification. | Reproducible source-pin table, dependency graph, and fixture expectations. Each API/schema cited with owner and revision; unresolved assumptions are listed, not silently made normative. |
| 1 | **Authorized programme packet and readiness view.** Compose current work readiness, repository/change scope, source citations/digests, bounds, evidence pointers and access requirements. Validate before dispatch; produce a human-readable dry-run. | Sprintctl work/readiness and continuation reads; Vuoro context/evidence forwarding; AgentOps documentation/projection. Local fields follow this selected architecture; owner review and the established generator/release path later qualify compatibility. | Clean-host fixture reconstructs the same bounded packet from authorized owner reads; stale revisions, wrong workspace, unknown refs and absent bytes refuse dispatch with a reason. Packet alone grants no access or authority. |
| 1 | **Host and repository readiness/onboarding.** Diagnose caller-visible provider capability, runtime/config version, headless auth, network, source reachability and isolation. Dry-run idempotent repository registration and scoped grants; resume partial setup without duplicating identity or widening permissions. | Programme 02 gitops-nixos host profile; programme 03 cred-broker and Appservice onboarding/landing controls; Vuoro and Sprintctl bindings. | Disposable commissioning records actual host/runtime/config and negative checks for missing auth, drift, inaccessible source, duplicate repo, ambiguous scope and revoked grant. Owner-specific apply receipts; no host or credential claims from source inventory alone. |
| 2 | **Repository execution attempts.** Implement a supported Sovite-owned worker lifecycle for exact authorized bindings: admit, start, renew, status, hand back, complete and lookup; isolate worktree, credentials, output storage and control plane. Native harness resumption stays native. | Programme 05 Sovite F2/R4, programme 02 host assumptions and stable packet assumptions from stage 1. Implement against provisional local contracts; owner releases later qualify the Vuoro adapter and cross-owner behavior. | Owner tests plus cross-owner disposable histories for lost start response, crash during edit, expired fence, takeover while old process runs, revoked capability and inaccessible predecessor handle. Prove old attempt cannot publish under replacement fence; exact artifacts remain readable only under owner policy. |
| 2 | **Continuation and operator request flow.** Project changed/current owner state, request dependencies and performed-vs-attested outcomes; continue authorized bounded work or provide manual next step when native wake is unavailable. | Sprintctl candidate requirement draft at `sprintctl/docs/plans/2026-10-24-portable-continuation-requirements.md`; Vuoro request/context owner work from programme 04; preserve Sprintctl work/request authority. | Successor on unrelated host obtains bounded current delta and permitted context; stale or withdrawn request, dead requester, shared dependant, duplicate delivery and false performed report retain explicit owner state. No wake/resume assertion without runtime receipt. |
| 2 | **Offline continuation page archive.** Preserve explicitly supplied, schema-validated successful owner page responses as separate bounded observations with page order, request/returned cursors, snapshot/checkpoint identities, observed time, digest domain, per-list completeness, and stop reason. It performs no owner reads, cursor chasing, source dereference, or atomic merge; authenticity, currentness, and authority stay unknown. | Sprintctl's existing one-response continuation contract and candidate requirements. Any automatic paging or owner contract change still requires explicit Sprintctl scope approval and owner release. Captured refusal/error envelopes remain unsupported until the owner defines their response schema. | A fresh offline reader distinguishes retained pages from owner history, detects changed bytes and repeated cursors, preserves unknown/incomplete states independently for each list, and refuses oversized or credential-shaped content. Refusal-envelope handling fails closed pending an owner schema. Existing one-read CLI behavior remains unchanged. |
| 3 | **Operational visibility and usage coverage.** Correlate attempt progress, startup, completion, provider usage, failure and notifications; distinguish heartbeats from useful progress; preserve privacy and tenant scope. | Appservice candidate requirement draft at `appservice/docs/plans/2026-10-24-portable-observability-requirements.md`; telemetry programme 06, Appservice observability and owner exporters. | Synthetic missing/late/conflicting usage, stale heartbeat, duplicate notification, failed exporter and cross-tenant cases. Unknown spend and stale progress are visible; notifications deduplicate by correlated attempt; no transcript or secret ingestion. |
| 3 | **Supported launch and capability composition.** Show caller-specific supported/unsupported launch choices and distinguish published setup from task-creation capability. Keep a manual user-launched path with explicit evidence when automation is unavailable. | Vuoro Cloud candidate requirement draft at `vuoro-cloud/docs/plans/2026-10-24-portable-environment-capability-requirements.md`; programme 03 and current provider capability. No inference from docs, URLs, or published environments. | For each advertised caller/provider generation, an owner-supported capability statement and a disposable launch/startup receipt. Unsupported mode returns an honest manual action; no task-submit support is inferred by this document. |
| 4 | **Exact candidate review and landing preparation.** Bind checks/reviews to exact candidate head; prepare canonical landing and rollback actions; retain ambiguous outcomes for reconciliation. Deployment is outside this batch. | Appservice landing prerequisites; AgentOps shared evidence; repository owners' CI, review and protected landing policy; credential-broker authority. | Mismatched tested head, stale review, lost merge response, and successful merge with cleanup failure yield correct separate status. Canonical receipts name exact commit and policy result. |
| 5 | **Two-repository, two-host pilot.** Run a disposable bounded programme, interrupt/replace host, continue on an independently authorized second host, then repeat on Mars Founder and a second repository before broad portability claims. | Programme 08 pilot; all preceding owner packages at usable released revisions; operator-authorized disposable scopes. | Full history from preparation through candidate and return, including injected host loss and independent candidate verification. Capture exact source/artifact refs, owner receipts, resource bounds, unresolved defects and unsupported modes. No production deployment implied. |

Implement each package locally against the selected architecture, using
explicit provisional interfaces and fixtures where owner APIs are not yet
released. Owner review and release validate compatibility later; they do not
stop source implementation. Launch, landing, and end-to-end behavior can be
implemented as candidates, while cross-owner qualification remains a separate
evidence step. Deployment is excluded from this batch.

## Owner requirement drafts to reconcile

These proposed owner-scoped drafts are committed on local candidate branches.
The pins identify source for review; they do not establish owner acceptance,
release, implementation, or deployment:

The versioned pin data is maintained in
[`portable-feature-batch-pins.v1.json`](portable-feature-batch-pins.v1.json).
Verify the pinned local source objects with
`python scripts/verify_portable_batch_pins.py --repo vuoro=/path/to/vuoro`
and repeat `--repo OWNER=PATH` for the other four local repositories. The
verifier performs local Git object, local branch-tip, and
draft-blob checks and reports the draft SHA256 in JSON. It disables Git lazy
fetch and does not inspect working-tree contents, contact a remote, compare a
release artifact, or establish owner acceptance, release, implementation,
qualification, or deployment. An absent repository mapping or unavailable or
stale local evidence fails the check; obtain the candidate object locally
through the repository's normal process before retrying.

| Owner | Candidate branch and commit | Draft |
|---|---|---|
| Vuoro | `cloud/20261024/programme-01-contract-foundation` at `fe7ce5a2e61d7e9d7b8786ba8bdafd08f59a91fc` | `docs/plans/2026-10-24-mcp-toolset-projection-requirements.md` |
| Sovite | `cloud/20261024/programme-09-p05-f2-contract` at `6e9cb948b57a03df6525a295121ae5c966b3e169` | `docs/contracts/worker-execution-remote-operations-requirements.md` |
| Appservice | `cloud/20261024/programme-08-integration-appservice-exact` at `17cbe5bd46a40800f0d168920449a2932e4d98f4` | `docs/plans/2026-10-24-portable-observability-requirements.md` |
| Sprintctl | `cloud/20261024/programme-09-p04-request-lifecycle` at `2bd514e1f02b97cb656eb88db7d1f6a9989b1c9c` | `docs/plans/2026-10-24-portable-continuation-requirements.md` |
| Vuoro Cloud | `cloud/20261024/programme-08-integration-vuoro-cloud-exact` at `260571aafa299d5300099163b8a836820d5779d4` | `docs/plans/2026-10-24-portable-environment-capability-requirements.md` |

These are implementation inputs under the selected architecture, not ratified
shared APIs. Reconcile them with owners and canonical sources during later
compatibility qualification; this does not hold source work. Toolset projection
cannot manufacture owner operations; Sovite requirements cannot assign
Sprintctl work state; continuation references do not transfer execution
authority; telemetry does not become work authority; and capability metadata
does not create a launch path.

## Local implementation candidates

These source slices advance locally reviewable parts of the batch. Their local
commits do not establish owner acceptance, release, live qualification, or
deployment:

| Owner | Candidate branch and head | Implementation slice | Evidence boundary |
|---|---|---|---|
| AgentOps | P06 `cloud/20261024/programme-06-telemetry` at `b4855f2ed45e05f410148a18e4c32d2e9981ef37`; P08 `cloud/20261024/programme-08-integration-agentops-exact`, implementation head before the exact-head metadata refresh `a35a6c4d47f2c44a1f2d8f26f44abd2a10c6ad24`, tree `46c92b3d1dbda1816af3ce89ec0648047b5e76ee`. The refresh commit became the branch tip; a later local slice adds the manual prompt renderer and observation schema. | P06 holds the local metadata projection. P08 contains the bounded batch preparer, local publish outbox, read-only continuation packet, exact-candidate review packet, source pin verifier, and feature-batch documentation. The later `--format prompt` slice emits only a bounded user-launch prompt, and only for zero-dependency requests with passing local source/pin checks; it never dispatches. | Exact-head refresh used static JSON/diff checks only; no tests/builds/CLI. Pin verifier passed all five local mappings. The later prompt/schema slice received static AST/JSON/diff checks only. Local source freshness, owner readiness, provider capability, task receipts, and landing policy remain unverified. |
| Vuoro | P01 `cloud/20261024/programme-01-contract-foundation` at `fe7ce5a2e61d7e9d7b8786ba8bdafd08f59a91fc`; P08 `cloud/20261024/programme-08-integration-vuoro-exact` at `9d7003ee2b693c91695f124bc16dc30639bd74ca`, tree `3991ed38259cead99a1d8f5986f678d313618f1c` | Contract reader bounds JSON depth/node count and 4 MiB wire bodies; OpenAPI header/query/path serialization defaults are corrected. An opt-in `vuoro-demo.sovite_execution` client is pinned to the local Sovite P08 candidate. | Latest P08 head received static checks only; no tests/builds or demo runtime wiring. Client is provisional; MCP projection remains empty. Historical focused receipts are in the [integration evidence](../../evidence/2026-10-24-cloud-programme-integration.md). |
| Sovite | P05 admin `cloud/20261024/programme-05-enrollment-admin-api` at `c7284c3232f03704335685357279ce189ad5bb46`; P08 `cloud/20261024/programme-08-integration-sovite-exact` at `1e66dc1a951d1ac1e24321f7bdf27db5b7c04b71`, tree `e65b32425f504ce74fa5773d61e6405cea9ea8b2` | P05 has blocker-only validation of expiring `helper-host-class-evidence/v1` against required bundle pins; its latest hardening bounds integer timestamps before conversion and turns invalid/overflow values into a fixed blocker. P08 adds current-owner lease scheduling, fence-bound lookup, bounded diagnostics, explicit local credential refusal, opt-in `sovite.execution_client.ExecutionClient`, and a separate opt-in `sovite-remote-worker` CLI. It fails closed on remote control errors, validates exact lookup outcomes, stops after status failure, and never executes recovered pull/start. | Latest heads received static checks only. CLI/routes/client remain provisional; task/resolved payload internals are unqualified. No durable restart journal or qualified gateway adapter/capability recovery; an unrecovered pull reservation waits for owner expiry. No runtime wiring or owner release. Default worker composition still requires SQL/S3. |
| Appservice | P06 `cloud/20261024/programme-06-telemetry` (`7fabc910445292eb7dd5acbac636f5fd572ebf43`); P07 receipt `cloud/20261024/programme-07-retention-receipts` (`1286309f67d32bdc5eb00e1fca96a7e3e853cbb1`) and current-source `cloud/20261024/programme-09-p07-current-source` at `766151c25ddc3dabb914301c1be4892bf336f332`; P08 `cloud/20261024/programme-08-integration-appservice-exact` at `17cbe5bd46a40800f0d168920449a2932e4d98f4`, tree `74be9ad05391353bf8cb84019e2d1fa10ecbdaee` | P06 covers native309 normalization/receipt projection; P07 adds bounded receipt/parser hardening, strict UTF-8/BOM rejection, and source-route inventory; P08 offline onboarding plan v2 rejects normalized Forgejo identity collisions and keeps remote state explicitly unknown without network/database reads. | Latest P07/P08 heads received static checks only; plan v2 was not tested or run against Forgejo. Historical P06/P07 checks belong to earlier tested heads; no live onboarding qualification is claimed. |
| Sprintctl | P04 `cloud/20261024/programme-04-requests-continuation` at `0f00448ea085b54bb452d2583e10f626c8ab1cd0`; P08 `cloud/20261024/programme-08-integration-sprintctl` at `ec6d5465b7f6e60edc4e1afd7462faf6150e68cf`, tree `5fa2315031dc8ba034b9d2f3f5059614aa8b1c26` | P08 archives supplied pages offline with `run collect`/`collect-inspect`; `run collect-fetch` retrieves explicitly supplied source pages and discloses valid in-flight reads that exceed its requested deadline. | Latest P08 head received static checks only; no tests/CLI runs. Owner error/refusal envelopes and authorization for automated paging remain unresolved. Historical focused receipts are in the [integration evidence](../../evidence/2026-10-24-cloud-programme-integration.md). |
| Vuoro Cloud | P02 `cloud/20261024/programme-02-recovery` at `ded0a6c5cd08c4763e422d3b9d1e93898f210170`; P03 `cloud/20261024/programme-03-cloud-product` at `eea1e76bd419586c8092673fa2bded2f606eafb1`; P06 `cloud/20261024/programme-06-telemetry` at `567f08454611f03b41cb5387cb95d316093abc59`; P08 `cloud/20261024/programme-08-integration-vuoro-cloud-exact` at `260571aafa299d5300099163b8a836820d5779d4`, tree `02642ed7678faa834518b4df5d0ef1e92c9baf15`; P09 correlation `cloud/20261024/programme-09-telemetry-correlation` at `a9022a2a5f64d312c1655636e34530027e190b0c` | P02 recovery guards; P03 adds a member-authorized request read adapter and epoch/sequence guards against stale browser responses after selection changes; P06/P09 cover synthetic telemetry correlation; P08 adds freshness/review cues and packaged web assets. | Latest P03 received JS syntax/diff checks only; P06 and P08 received static checks only. Adapter/telemetry are not live-qualified. No task submission, owner acceptance, or deployment is claimed. Historical receipts apply only to their named/tested heads. |

The Sprintctl artifact is an offline candidate format, not a replacement for
`run brief` or `result packet create`. It does not fetch pages, inspect source
URLs, or transfer access. Its hash shows consistency of the represented bytes;
authenticity, currentness, authority, and atomicity remain unknown/not
established.

## Later cross-owner compatibility and qualification gates

The gates below define evidence required before making cross-owner support or
portability claims. They do not block local implementation slices. Deployment
is outside this feature batch and is not a gate or deliverable here.

- **Cross-owner schema / generated MCP tool projection:** compatibility
  qualification awaits the contract owner closing the EC-00 conditions recorded
  in the inventory, selecting and releasing the supported projection, and each
  consumer pinning and qualifying that release. The inventory reports the
  candidate projection as empty and other acceptance conditions open. Local
  source may proceed against the selected architecture without publishing a
  guessed schema or treating this candidate as ratification.
- **Remote execution operations:** local provisional routes now exist on the
  Sovite P08 candidate. Cross-owner qualification awaits Sovite owner design,
  review, release and adversarial owner evidence for remote renew,
  status, handback, complete and lookup, enrollment/revocation, and fencing.
  Existing internal reserve/start or inference-only connector behavior does not
  establish these operations.
- **Task submission:** qualification awaits explicit product/provider support
  exposed to the actual caller and a qualified disposable launch. A published environment,
  available CLI, task URL, or manual launch is not task-submit support.
- **Portable source/artifact transfer and onboarding:** qualification awaits source
  authority, access class, exact digest, narrow grant, transfer path and
  successor authorization being evidenced by their respective owners. The
  absent gitops-nixos, cred-broker and Mars Founder trees in the inventory are
  not implementation evidence.
- **Run-wide progress and cost claims:** qualification awaits released owner
  correlation and exporter coverage plus synthetic failure evidence. Heartbeat alone is not
  useful progress; absent usage is not zero spend.
- **End-to-end portability/reliability claim:** qualification awaits completion
  of the two-host, two-repository pilot under current owner releases with exact
  receipts. Candidate source, local fake queues, or source review alone cannot
  close this gate.
- **Landing:** remains an owner policy and release gate. This batch prepares
  candidate review evidence but does not authorize main merges or promotion.
  Deployment is explicitly excluded from the batch.

## Evidence and status rules

For each feature, preserve original failed checks and record candidate commit,
artifact digest, dependency pins, exact tested head, command and result,
owner/release revision, environment and assurance limits. State whether
evidence is source inspection, owner test, disposable integration, live
qualification, or deployment observation. Do not promote one level into
another. Keep `blocked`, `not run`, `unknown`, `refused`, `stale`, and
`uncertain` distinct from `passed`.

Local implementation proceeds against the selected architecture with
provisional assumptions stated. Cross-owner qualification is ready when a
package has an owner-reviewed boundary, ordered dependencies, reproducible
acceptance evidence, and named remaining blockers. Operator review of qualified
cross-owner behavior follows owner API and artifact releases and a pilot report
that identifies remaining limits. This document itself closes no qualification
gate and authorizes no deployment.
