---
doc_id: portable-feature-batch.agentops.v1
status: proposed-candidate-only
supersedes: []
---

# Portable agent workflows: practical feature batch

Status: proposed requirements and sequencing, 2026-10-24. This candidate
decomposes the [portable agent workflows plan](2026-10-24-portable-agent-workflows.md)
and its [contract inventory](../../evidence/2026-10-24-portable-workflow-contract-inventory.md)
into an implementable batch. It is not an accepted cross-owner contract, owner
API ratification, implementation status, runtime qualification, or deployment
authorization. Reconcile every source pin and work reference at implementation
start.

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
   checks and tested head, independent review, canonical landing receipt, and
   deployment receipt as separate results. Make blocked, refused, stale,
   untested, and uncertain states actionable. Retrying a merge or launch after
   ambiguous response requires reconciliation first.
6. **Stop safely.** Budget/deadline exhaustion, revocation, stale source,
   expired execution fence, loss of required telemetry, or unresolved external
   effect halts new work and leaves an inspectable state. A reassigned work item
   alone does not cancel an old process.

## Feature packages and dependency order

Packages extend the eight programmes in the [programme index](../../dispatch/programmes/2026-10-24/08-integration.md)
and its linked programme briefs; they do not create a parallel authority or
backlog. An owner may implement its own package only through that repository's
review and release process.

| Order | Package and concrete capability | Required owner enablers | Acceptance evidence |
|---|---|---|---|
| 0 | **Source and interface baseline.** At launch reconcile canonical source, candidate ancestry, deployed/released versions, open reservations, and exact owner schemas. Define synthetic fixtures for stale/missing refs, wrong repo/workspace, revoked grants, response loss and unknown usage. | Programme 01 contract foundation; all owners publish exact source and release references. | Reproducible source-pin table, dependency graph, and fixture expectations. Each API/schema cited with owner and revision; unresolved assumptions are listed, not silently made normative. |
| 1 | **Authorized programme packet and readiness view.** Compose current work readiness, repository/change scope, source citations/digests, bounds, evidence pointers and access requirements. Validate before dispatch; produce a human-readable dry-run. | Sprintctl work/readiness and continuation reads; Vuoro context/evidence forwarding; AgentOps documentation/projection. Contract fields only after owner review under the established generator/release path. | Clean-host fixture reconstructs the same bounded packet from authorized owner reads; stale revisions, wrong workspace, unknown refs and absent bytes refuse dispatch with a reason. Packet alone grants no access or authority. |
| 1 | **Host and repository readiness/onboarding.** Diagnose caller-visible provider capability, runtime/config version, headless auth, network, source reachability and isolation. Dry-run idempotent repository registration and scoped grants; resume partial setup without duplicating identity or widening permissions. | Programme 02 gitops-nixos host profile; programme 03 cred-broker and Appservice onboarding/landing controls; Vuoro and Sprintctl bindings. | Disposable commissioning records actual host/runtime/config and negative checks for missing auth, drift, inaccessible source, duplicate repo, ambiguous scope and revoked grant. Owner-specific apply receipts; no host or credential claims from source inventory alone. |
| 2 | **Repository execution attempts.** Implement a supported Sovite-owned worker lifecycle for exact authorized bindings: admit, start, renew, status, hand back, complete and lookup; isolate worktree, credentials, output storage and control plane. Native harness resumption stays native. | Programme 05 Sovite F2/R4 and accepted owner contracts; programme 02 commissioned host; stable packet assumptions from stage 1. Vuoro adapter only after Sovite owner release. | Owner tests plus cross-owner disposable histories for lost start response, crash during edit, expired fence, takeover while old process runs, revoked capability and inaccessible predecessor handle. Prove old attempt cannot publish under replacement fence; exact artifacts remain readable only under owner policy. |
| 2 | **Continuation and operator request flow.** Project changed/current owner state, request dependencies and performed-vs-attested outcomes; continue authorized bounded work or provide manual next step when native wake is unavailable. | Sprintctl candidate requirement draft at `sprintctl/docs/plans/2026-10-24-portable-continuation-requirements.md`; Vuoro request/context owner work from programme 04; preserve Sprintctl work/request authority. | Successor on unrelated host obtains bounded current delta and permitted context; stale or withdrawn request, dead requester, shared dependant, duplicate delivery and false performed report retain explicit owner state. No wake/resume assertion without runtime receipt. |
| 2 | **Offline continuation page archive.** Preserve explicitly supplied, schema-validated owner page responses as separate bounded observations with page order, request/returned cursors, snapshot/checkpoint identities, observed time, digest domain, per-list completeness, and stop reason. It performs no owner reads, cursor chasing, source dereference, or atomic merge; authenticity, currentness, and authority stay unknown. | Sprintctl's existing one-response continuation contract and candidate requirements. Any automatic paging or owner contract change still requires explicit Sprintctl scope approval and owner release. | A fresh offline reader distinguishes retained pages from owner history, detects changed bytes and repeated cursors, preserves unknown/refused/incomplete states independently for each list, and refuses oversized or credential-shaped content. Existing one-read CLI behavior remains unchanged. |
| 3 | **Operational visibility and usage coverage.** Correlate attempt progress, startup, completion, provider usage, failure and notifications; distinguish heartbeats from useful progress; preserve privacy and tenant scope. | Appservice candidate requirement draft at `appservice/docs/plans/2026-10-24-portable-observability-requirements.md`; telemetry programme 06, Appservice observability and owner exporters. | Synthetic missing/late/conflicting usage, stale heartbeat, duplicate notification, failed exporter and cross-tenant cases. Unknown spend and stale progress are visible; notifications deduplicate by correlated attempt; no transcript or secret ingestion. |
| 3 | **Supported launch and capability composition.** Show caller-specific supported/unsupported launch choices and distinguish published setup from task-creation capability. Keep a manual user-launched path with explicit evidence when automation is unavailable. | Vuoro Cloud candidate requirement draft at `vuoro-cloud/docs/plans/2026-10-24-portable-environment-capability-requirements.md`; programme 03 and current provider capability. No inference from docs, URLs, or published environments. | For each advertised caller/provider generation, an owner-supported capability statement and a disposable launch/startup receipt. Unsupported mode returns an honest manual action; no task-submit support is inferred by this document. |
| 4 | **Exact candidate review and landing preparation.** Bind checks/reviews to exact candidate head; prepare canonical landing and rollback actions; retain ambiguous outcomes for reconciliation. Deployment remains separately gated. | Appservice landing prerequisites; AgentOps shared evidence; repository owners' CI, review and protected landing policy; credential-broker authority. | Mismatched tested head, stale review, lost merge response, successful merge with cleanup failure, and no-deploy cases yield correct separate status. Canonical receipts name exact commit and policy result. |
| 5 | **Two-repository, two-host pilot.** Run a disposable bounded programme, interrupt/replace host, continue on an independently authorized second host, then repeat on Mars Founder and a second repository before broad portability claims. | Programme 08 pilot; all preceding owner packages at usable released revisions; operator-authorized disposable scopes. | Full history from preparation through candidate and return, including injected host loss and independent candidate verification. Capture exact source/artifact refs, owner receipts, resource bounds, unresolved defects and unsupported modes. No production deployment implied. |

Stage 1 packet/readiness and host diagnostics may advance independently using
fixtures. Execution and continuation must use explicit provisional assumptions
until their owning APIs are reviewed and released. Launch composition, landing,
and end-to-end pilot depend on qualified owner releases; a cross-repository
integration candidate is not a substitute for an owner release.

## Owner requirement drafts to reconcile

These proposed owner-scoped drafts are committed on local candidate branches.
The pins identify source for review; they do not establish owner acceptance,
release, implementation, or deployment:

| Owner | Candidate branch and commit | Draft |
|---|---|---|
| Vuoro | `cloud/20261024/programme-01-contract-foundation` at `fe7ce5a2e61d7e9d7b8786ba8bdafd08f59a91fc` | `docs/plans/2026-10-24-mcp-toolset-projection-requirements.md` |
| Sovite | `cloud/20261024/programme-09-p05-f2-contract` at `6e9cb948b57a03df6525a295121ae5c966b3e169` | `docs/contracts/worker-execution-remote-operations-requirements.md` |
| Appservice | `cloud/20261024/programme-08-integration-appservice-exact` at `109f6c36cf5a2512ea31069acfabdce15e4c7e09` | `docs/plans/2026-10-24-portable-observability-requirements.md` |
| Sprintctl | `cloud/20261024/programme-09-p04-request-lifecycle` at `7be36d224f5833b430f5b0796005cb13a7a9ad43` | `docs/plans/2026-10-24-portable-continuation-requirements.md` |
| Vuoro Cloud | `cloud/20261024/programme-08-integration-vuoro-cloud-exact` at `535b167cade42d3b25d7a8cb855634cf96c83195` | `docs/plans/2026-10-24-portable-environment-capability-requirements.md` |

Reconcile these with their owners and canonical sources before selecting
implementation tasks. They are not ratified shared APIs. Toolset projection
cannot manufacture owner operations; Sovite requirements cannot assign
Sprintctl work state; continuation references do not transfer execution
authority; telemetry does not become work authority; and capability metadata
does not create a launch path.

## Blocked gates

- **Cross-owner schema / generated MCP tool projection:** blocked until the
  contract owner closes the EC-00 conditions recorded in the inventory, selects
  and releases the supported projection, and each consumer pins and qualifies
  that release. The inventory reports the candidate projection as empty and
  other acceptance conditions open. Do not publish a guessed schema or treat
  this candidate as ratification.
- **Remote execution operations:** blocked on Sovite owner design, review,
  implementation, release and adversarial owner evidence for remote renew,
  status, handback, complete and lookup, enrollment/revocation, and fencing.
  Existing internal reserve/start or inference-only connector behavior does not
  establish these operations.
- **Task submission:** blocked on explicit product/provider support exposed to
  the actual caller and a qualified disposable launch. A published environment,
  available CLI, task URL, or manual launch is not task-submit support.
- **Portable source/artifact transfer and onboarding:** blocked on source
  authority, access class, exact digest, narrow grant, transfer path and
  successor authorization being evidenced by their respective owners. The
  absent gitops-nixos, cred-broker and Mars Founder trees in the inventory are
  not implementation evidence.
- **Run-wide progress and cost claims:** blocked on released owner correlation
  and exporter coverage plus synthetic failure evidence. Heartbeat alone is not
  useful progress; absent usage is not zero spend.
- **End-to-end portability/reliability claim:** blocked until the two-host,
  two-repository pilot completes under current owner releases with exact
  receipts. Candidate source, local fake queues, or source review alone cannot
  close this gate.
- **Landing/deployment:** each remains an owner policy and release gate. This
  requirements batch does not authorize main merges, promotion, production
  service mutation or deployment.

## Evidence and status rules

For each feature, preserve original failed checks and record candidate commit,
artifact digest, dependency pins, exact tested head, command and result,
owner/release revision, environment and assurance limits. State whether
evidence is source inspection, owner test, disposable integration, live
qualification, or deployment observation. Do not promote one level into
another. Keep `blocked`, `not run`, `unknown`, `refused`, `stale`, and
`uncertain` distinct from `passed`.

Work is ready for owner implementation when a package has an owner-reviewed
boundary, ordered dependencies, reproducible acceptance evidence, and named
blockers. Work is ready for operator review only after the relevant owners have
released their APIs and artifacts and the pilot report identifies remaining
limits. This document itself closes no implementation or qualification gate.
