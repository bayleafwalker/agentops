# Vuoro Ecosystem Architecture Remediation Implementation Plan

**Created:** 2026-07-25  
**Reworked:** 2026-07-26  
**Mode:** documentation only; no backlog, deployment, or production mutation

References:

- [Findings dossier](/projects/dev/agentops/docs/assessments/vuoro-architecture-findings-2026-07-25.md)
- [Operator packet](/projects/dev/agentops/docs/assessments/vuoro-architecture-operator-packet-2026-07-25.md)
- [Preflight checklist](/projects/dev/agentops/docs/assessments/vuoro-architecture-preflight-checklist-2026-07-25.md)

## Execution model

Work is organized into reasoning units, not blanket waves. A unit may proceed when its declared dependencies and repository authorization are satisfied. Each unit has four distinct roles:

- **Decision owner:** approves contracts, authority, and accepted risk.
- **Builder:** implements only in the owning repository.
- **Primary verifier:** runs the authored validation after implementation.
- **Secondary reviewer:** a fresh Spark-class context that did not implement the unit and independently reviews the pinned implementation diff, contracts, tests, and command evidence.

The builder may not self-close a unit. Secondary review is required before publication, backlog closure, or dependent-unit clearance. Operational work in `appservice`, deployment jobs, Flux, Kubernetes, image publication, or live data requires separate authorization outside this plan.

## Verification record contract

Store each unit's evidence in the owning workflow's protected verification record. Do not put claim tokens, credentials, connection strings, or unredacted environment output in Markdown.

Each record must contain:

- unit ID and finding IDs;
- input and output revision SHAs for every affected repository;
- builder and independent reviewer identities/context IDs;
- commands, working directories, tool versions, exit status, and redacted output summary;
- fixture/backend/isolation details and fault schedule where applicable;
- exact contract decisions and accepted capability differences;
- minimized counterexamples and residual risks;
- reviewer verdict: `PASS`, `FAIL`, or `BLOCKED`.

Only `PASS` clears the unit. A review that only restates builder evidence is invalid.

## Track S - Claim lifecycle safety

### S0 - Approve the cross-authority safety protocol

**Findings:** F2, F7  
**Decision owners:** `actionq`, `actionq-dispatcher`, and `sprintctl` maintainers  
**Mutations:** documentation/contracts only

Define before code:

1. `actionq` is execution authority; `sprintctl` is coordination authority.
2. The action claim incarnation proof is opaque and cannot be replaced by `claimed_by`.
3. Renewal ordering and partial-success handling. Recommended order is action claim first, sprint claim second.
4. Ownership-loss behavior: terminate or stop the worker, prohibit all terminal writes, read current authority state, and record a recoverable coordination failure.
5. Unknown outcome behavior when a renewal response is lost after commit.
6. Immediate pre-settlement proof for both authorities.
7. Idempotency and recovery when the first cross-tool terminal write succeeds and the second fails.
8. One-shot supervision strategy, or an explicit TTL-bound restriction if supervision is deferred.

**Exit:** approved protocol and test history table exist. No S1/S2 implementation begins without it.

**Secondary review:** fresh Spark-class reviewer attacks the protocol with pause, partition, sweep/reclaim, response-loss, shutdown, and partial-settlement histories. Any history permitting an unfenced worker to continue or settle fails the gate.

### S1 - Fence action terminal transitions

**Depends on:** S0  
**Owner:** `actionq`

Implement claimant-incarnation proof on complete/fail/reject APIs and persistence paths. Stale terminal attempts must not mutate state and must produce a durable rejection event. Include migration/version compatibility behavior.

**Primary validation:** targeted action claim tests covering renew, expiry, sweep, reclaim, and stale terminal attempts.

**Secondary implementation review:** inspect the pinned diff and run disposable-backend histories for wrong-owner renewal, sweep/reclaim followed by stale complete/fail/reject, lost renewal response, and repeated terminal calls. Assert exactly one accepted terminal event per action incarnation.

### S2 - Supervise execution, renew both authorities, and settle safely

**Depends on:** S1  
**Owner:** `actionq-dispatcher`; coordinated client changes may require `sprintctl`

Implement real renewal methods in dispatcher client protocols and concrete clients. The daemon must renew both claims; `session.heartbeat` remains observability only. One-shot execution must use a supervised runner capable of renewal or be explicitly rejected when work can exceed TTL. Ownership loss terminates execution and prevents settlement. Re-prove both authorities immediately before terminal writes and implement S0 recovery semantics for partial settlement.

**Primary validation:** execution longer than initial TTL; daemon and one-shot paths; worker kill; action renewal failure; sprint renewal failure after action renewal; response loss; shutdown during renewal; first settlement write succeeds and second fails.

**Secondary implementation review:** fresh Spark-class reviewer traces every execution path and proves it either renews both authorities or is explicitly TTL-bounded. The reviewer independently runs the fault-history matrix and blocks publication on duplicate side effects, stale settlement, or an unhandled unknown outcome.

## Served-readiness amendments (2026-07-26)

These tracks refine the earlier implementation plan after the served-mode
readiness and UX audit. They are source and configuration work only. Releasing
the adapter wheel, updating a Vuoro pin or tag, and reconciling an appservice
deployment require their owning repositories and separate operator authority.

The two Vuoro CLI assessment labels previously referred to as `O1` and `O2`
are named `V0` and `V1` in this plan. `O*` is reserved for the UX-plan
observations below, avoiding a misleading collision between CLI completeness
and UX policy.

### Track G — Served command completeness

- **G0 — Inventory and classify command surfaces.** Maintain a route-to-
  catalog-operation inventory. Mark every unavailable aggregation explicitly;
  do not silently open a direct backend as a fallback.
- **G1 — Event reads.** Provide `work.read.events` and served `event list`.
  Reuse the catalog operation in every served consumer rather than opening a
  direct database connection.
- **G2 — Event creation.** Provide `work.event.add` and served `event add`.
  The server selects the authenticated actor; a served client must not need or
  transmit a client actor value.
- **G3 — Item creation.** Provide `work.item.create` and served `item add`.
  Resolve tracks in the server repository scope and preserve the established
  response shape.
- **G4 — Sprint reads.** Provide a basic `work.read.sprint` and served
  `sprint show`. Client-side polling is acceptable for `--watch`; `--detail`
  must fail explicitly until its aggregate has a catalog operation.
- **G5 — Catalog and doctor coverage.** Add every G1--G4 operation to the
  catalog contracts, command-route map, and doctor probes. Treat absent
  operations as a blocked compatibility state, not a local fallback.
- **G6 — Release and deployed verification.** After separately authorized
  Vuoro/appservice release work, verify catalog/doctor and the real served
  calls from both workstation and devbox-agent. This task is not authorization
  to publish a wheel, change a pin, deploy, or reconcile.

### Track U — UX fail-closed robustness

- **U0 — Decide and record the policy.** The operator must decide UX-plan O1
  and O6 before enforcement: whether marker-less remote/served execution
  always fails closed or may proceed after explicit corroboration, and which
  invocation-scoped mechanism supplies that corroboration. Recommended:
  fail closed by default and permit an explicit `--repo-id` plus a
  per-invocation opt-in flag. Do not introduce a persistent global bypass.
- **U1 — Introduce parsing and preflight scaffolding.** Build the shared
  reference parser, repository precedence resolver, and universal preflight
  before migrating individual command groups.
- **U2 — Enforce the marker-less guard.** Require the U0 corroboration for
  remote/served commands, retain unchanged local behavior, and expose the
  resolved context or a precise failure taxonomy.
- **U3 — Keep daemon/service identity explicit.** Daemon and service
  environments must supply a marker or explicit repository identity. Reconcile
  their environment split before any daemon rollout; never add a global daemon
  allowlist or persistent bypass.
- **U4 — Surface actionable failures.** Classify malformed references,
  mismatches, missing markers, unavailable catalog operations, and tombstoned
  targets so ordinary agents can act without operator guesswork.
- **U5 — Prove safe handling with disposable fixtures.** Test tombstones and
  remote-like paths only against disposable fixtures; do not use production
  stores as a UX test harness.

**Dependencies.** G1--G5 source work may proceed independently of U0. UX
acceptance for a G command depends on the applicable I/U parsing, preflight,
and guard work. G6 depends on landed G1--G5 paths and separately authorized
release work. U2 and daemon rollout are blocked on U0; U1, U4 taxonomy
scaffolding, and disposable-fixture work may proceed before that decision.

### Independent secondary-review checklist

Before accepting a G/I/U implementation, a fresh reviewer must verify:

- malformed and mismatched references, resolver precedence, and redacted
  resolved-context output;
- marker-less remote/served behavior, unchanged local behavior, and absence
  of a global daemon bypass;
- disposable tombstone coverage and the failure taxonomy;
- catalog/doctor coverage only for commands whose G/#1984 paths have landed;
- response-shape parity, authenticated server actor selection, and explicit
  failure for unavailable aggregates.

---

### S3 - Integrated safety review

**Depends on:** S1 and S2  
**Owners:** all three domain maintainers

A fresh reviewer examines the combined pinned revisions, not only per-repo diffs. Validate authority ordering, API compatibility, migration sequencing, rollback behavior, and end-to-end histories. Publication is prohibited until the integrated verdict is `PASS`.

## Track P - Workstation served policy

### P1 - Decide validator policy and repair the validator

**Finding:** F1  
**Owner:** `agentops`

Choose literal-only or approved-sourced configuration policy. Update checker fixtures and documentation before changing any consumer. Explicitly confirm the eight-repository target list with owners; keep `vuoro` out unless separately approved.

Reconcile the checker result with the historical runtime-cutover ledger. Report
runtime cutover evidence and configuration-policy conformance as separate
facts; a lexical checker failure does not by itself invalidate prior runtime
evidence.

**Static validation:**

```bash
python /projects/dev/agentops/templates/dispatch/scripts/validate_vuoro_workstation_cutover.py \
  --root /projects/dev \
  --profile /projects/dev/agentops/templates/dispatch/environment-record/profiles/workstation-vuoro-shared.json
```

**Secondary implementation review:** fresh Spark-class reviewer evaluates fixtures for active literal configuration, approved sourced configuration, commented direct wiring, active overrides, missing files/profile, and local-only rollback. A purely lexical pass without policy agreement fails.

### P2 - Align selected consumer configuration

**Depends on:** P1  
**Owners:** each selected consumer repository  
**Authorization:** separate per-repository build context; operational changes remain out of scope

Change only repositories confirmed by the checker scope and owner decision. Preserve repository-local documentation and local-only rollback mechanisms.
Report absent, independently owned, or intentionally excluded repositories
instead of describing a partial subset as a clean full-workspace gate.

**Read-only smoke pattern:**

```bash
cd /projects/dev/<repo>
direnv exec . sprintctl doctor
direnv exec . sprintctl sprint list --json
```

Run from the actual repository working directory. Evidence must assert the effective repo ID and a known tenant-specific result; wildcard-authorized HTTP success is insufficient.

**Secondary implementation review:** fresh reviewer checks every selected repository diff, reruns the static checker, and performs tenant-distinguishing read-only smoke checks for at least two repositories. No lifecycle writes.

## Track I - Repository identity and references

### I0 - Approve identity and public-reference contracts

**Finding:** F3  
**Owner:** `sprintctl`; Vuoro reviews authorization boundary

Define invariants between work-adapter tenant slug, committed marker identity,
path fallback, authority UUID, and canonical `repo#id` public references.
Specify precedence among explicit reference/flag, environment, committed
marker, and guarded cwd compatibility.

### I1 - Implement stable identity mapping and precedence

**Depends on:** I0

Change resolution so a renamed clone or linked worktree follows the chosen
canonical identity without collapsing distinct identity types. Reject explicit
reference, marker, environment, and cwd disagreements rather than silently
choosing one repository.

### I2 - Parse and render scoped references

**Depends on:** I0

Accept canonical `repo#id` references on ambiguity-prone surfaces. Retain bare
numeric IDs only where the resolved repository makes them unambiguous. Render
the effective repository, target, backend, and resolution source while
redacting credentials and tokens.

### I3 - Verify identity boundaries

**Depends on:** I1 and I2

**Primary validation:**

```bash
cd /projects/dev/sprintctl
pytest -q tests/test_backend_mode.py tests/test_backend_served_mode.py tests/test_vuoro_work_adapter_integration.py
```

Add cases for renamed clones, nested cwd, linked worktrees, missing marker,
malformed and mismatched references, precedence, unauthorized repo, wildcard
credentials, marker-less invocation, and local/served behavior.

**Secondary implementation review:** fresh Spark-class reviewer traces cwd to marker, `BackendConfig.repo_id`, served facade, invocation envelope, Vuoro authorization, and work store. Run the targeted tests plus read-only, tenant-distinguishing smoke checks from two actual repository working directories.

## Track L - Lease capability policy

### L1 - Decide whether epoch fencing is required

**Finding:** F4  
**Owner:** `sprintctl`

Inventory consumers and production assumptions. If token fencing is sufficient, document and test the SQLite/Postgres capability difference. If epoch fencing is required, create a new design unit specifying expected-epoch inputs and enforcement before implementation.

**Secondary review:** compare accepted/rejected histories across SQLite, Postgres, and served mode and confirm all differences are documented. Incrementing a field without downstream enforcement fails review.

## Track H - Handoff portability

### H1 - Publish per-mode handoff contracts

**Finding:** F6  
**Owner:** `sprintctl`

Define versioned local and served request/response schemas, stable common fields, and explicit capability differences such as legacy adoption. Add adapters only where they preserve semantics.

**Secondary implementation review:** fresh reviewer extracts the public shapes independently, executes positive/negative fixtures in both modes, and verifies that normalized fields are stable while intentional differences remain explicit.

## Track C - Dispatch contract convergence

### C0 - Approve two canonical contracts

**Finding:** F5  
**Owner:** `agentops`

Declare separate machine-readable contracts for manifests and dispatch requests. Decide whether UI is a full projection or a documented subset. Decide defaults versus required fields for `kind` and `harness`.

### C1 - Converge manifest validation

**Depends on:** C0  
**Owner:** `agentops`

Reconcile action-class closure and `golden-child` versus session skills. Derive runtime sets from the canonical artifact or use JSON Schema plus semantic checks. Add dependency-free parity fixtures.

### C2 - Converge runtime, MCP, and HTTP dispatch boundaries

**Depends on:** C0  
**Owner:** `agentops`

Derive normalizer and MCP `inputSchema` from the dispatch-request contract. Ensure MCP advertises only runtime-valid requests and exposes the complete output contract.

### C3 - Make UI projection explicit

**Depends on:** C0  
**Owner:** `agentops`

Consume browser-safe generated constants and encode output-to-kind mapping canonically. Remove plan/audit conflation unless it is an approved alias.

**Primary validation for C1-C3:**

```bash
cd /projects/dev/agentops/apps/web
npm test
npm run build
```

**Secondary implementation review:** a fresh Spark-class reviewer independently extracts enum and required-field sets from canonical artifacts, schema, runtime exports, MCP tools/list, and UI. Require exact equality or a documented/tested subset. Run positive and negative fixtures through HTTP and MCP, including omitted-default behavior. Duplicate literal enums or an MCP-advertised runtime-invalid request fail the gate.

## Track V - Vuoro operational CLI truthfulness

### V0 - Decide command authority and availability

**Finding:** F8  
**Owner:** `vuoro`; each domain owner approves migration authority

For `check-compatibility`, `migrate`, and `admin`, select `implemented`, `intentionally unavailable`, or `owner CLI only` per environment. Decide whether Vuoro orchestrates migrations or deployment jobs continue calling owner CLIs. Exactly one authority must exist per domain.

### V1 - Align parser, docs, and implementation

**Depends on:** V0  
**Owner:** `vuoro`

Immediately make unavailable commands truthful and machine-readable. For compatibility, extract configuration/composition loading that can inspect pins and adapters without constructing a ready app. Implement migration only with a closed domain enum, pinned entrypoint, separate credentials, explicit environment confirmation, and stable audit envelope. Implement admin only from a closed authorized action registry.

**Primary validation:**

```bash
cd /projects/dev/vuoro
uv run --package vuoro-service --extra test pytest packages/vuoro-service/tests/test_app.py
uv run pytest tests/test_deployment_assets.py packages/vuoro-service/tests/test_composition.py
uv run vuoro-service --help
```

**Secondary implementation review:** fresh Spark-class reviewer starts from operator docs, enumerates commands, and compares help, exit codes, JSON shape, environment availability, and authority. Compatibility must pass compatible/incompatible/missing-config read-only fixtures. Migration/admin review uses fake adapters only and proves pinned resolution, credential separation, wrong-domain rejection, no automatic migration on serve, recovery behavior, and exactly one operational authority.

## Closure rule

A finding closes only when its decision is recorded, all dependent implementation units pass primary verification, the fresh secondary implementation review returns `PASS`, and residual risks are accepted by the owning domain. Passing one track does not unnecessarily block independent tracks; dependency edges above are authoritative.
