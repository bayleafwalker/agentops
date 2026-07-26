# Vuoro Ecosystem Remediation Implementation Plan
**Date:** 2026-07-25  
**Mode:** documentation only (no sprint backlog changes)

This plan turns the findings dossier into executable workstreams while keeping change sets isolated and verifiable.

- Primary reference: [vuoro-architecture-findings-2026-07-25.md](/projects/dev/agentops/docs/assessments/vuoro-architecture-findings-2026-07-25.md)
- Execution guardrail: [vuoro-architecture-preflight-checklist-2026-07-25.md](/projects/dev/agentops/docs/assessments/vuoro-architecture-preflight-checklist-2026-07-25.md)

## Governance and sequencing

- **Wave A (Critical)** must complete before enabling any additional hardening.
- **Wave B (High)** follows once Wave A is validated.
- **Wave C (Medium)** follows once Waves A/B are stable.

For each task below:
- `Scope`: repos/files to touch
- `Steps`: exact work sequence
- `Validation`: commands/checks
- `Exit criteria`: must pass before next task

---

## Wave A — Boundary correctness

### A1) Enforce complete Vuoro served cutover

- **Findings:** F1
- **Scope:** `agentops`, `sprintctl`, `actionq`, `vuoro`, `homelab-analytics`, `_orchestration`, `aligned-equity`, `box`, `scribectl` (or every active member with runtime integration)
- **Steps:**
  1. Capture baseline with cutover checker (record output and timestamp).
  2. Normalize `.envrc` in each target repo to the canonical served block using the same profile.
  3. Remove/relocate commented or fallback direct-backend snippets to local-only files.
  4. Re-run checker and confirm zero violations.
- **Validation:**
  - `python templates/dispatch/scripts/validate_vuoro_workstation_cutover.py --root /projects/dev --profile /projects/dev/agentops/templates/dispatch/environment-record/profiles/workstation-vuoro-shared.json`
  - repo-specific smoke run: `. .envrc && sprintctl sprint list` should route through Vuoro-served context.
- **Exit criteria:**
  - No `SPRINTCTL_BACKEND=remote`, `SPRINTCTL_URL`, or direct DB host hints in covered repos’ committed runtime configs.
  - `validate_vuoro_workstation_cutover` passes.

### A2) Add in-flight claim lease renewal for long-running execution

- **Findings:** F2
- **Scope:** `actionq`, `actionq-dispatcher`, `sprintctl` (if coupled claim TTL config applies)
- **Steps:**
  1. Add heartbeat ticker during active execution in dispatcher flow (`run_forever` and one-shot worker path).
  2. Call renewal endpoint before claim deadline expiry (with jitter + retry/backoff).
  3. Persist renew-result status in session metadata for traceability.
  4. If renew fails repeatedly, mark claim as unhealthy and prevent terminal transitions.
  5. Mirror equivalent claim-ownership refresh for sprintctl claim where used.
- **Validation:**
  - Add long-run integration test with execution duration > lease TTL.
  - Simulate dead process/reconnect and assert no duplicate claim execution.
- **Exit criteria:**
  - Reclaimed-by-sweep scenario does not occur while action is executing with successful renewals.
  - Duplicate execution for one action is eliminated in test harness.

---

## Wave B — Identity and contract consistency

### B1) Canonicalize `repo_id` resolution

- **Findings:** F3
- **Scope:** `sprintctl/sprintctl/backend.py`, `sprintctl/sprintctl/cli.py`
- **Steps:**
  1. Define and document single source-of-truth resolver order.
  2. Use marker/authority-stored identity before path-derived fallback.
  3. Emit explicit warning/error on marker mismatch.
  4. Add tests for workspace clone/name changes and served-local mode transitions.
- **Validation:**
  - `pytest` targeted identity/backend tests in `sprintctl/tests/`.
- **Exit criteria:**
  - same logical repo resolves same identity across local and served/authority command paths.

### B2) Normalize lease-lineage contract

- **Findings:** F4
- **Scope:** `sprintctl/sprintctl/db.py`, `sprintctl/sprintctl/db/pg.py`, docs under `sprintctl/docs/protocols`
- **Steps:**
  1. Decide parity strategy: full alignment or explicit capability flag.
  2. If full parity: implement equivalent lease epoch behavior in sqlite path.
  3. If explicit flag: codify behavior per backend in protocol docs and validation checks.
  4. Add parity test asserting backend behavior contract at callsites.
- **Validation:**
  - targeted unit tests for claim rotation/handoff/ambiguous handoff across both backends.
- **Exit criteria:**
  - No hidden divergence in accepted claim lineage behavior.

### B3) Unify dispatch contract enums across agentops stack

- **Findings:** F5
- **Scope:**
  - `templates/dispatch/manifest.schema.json`
  - `apps/web/lib/cockpit/dispatch-manifest.js`
  - `apps/web/app/cockpit/api/mcp/route.js`
  - `apps/web/lib/cockpit/dispatch.js`
  - `apps/web/components/cockpit/dispatch-composer.js`
  - any manifest parser/renderer tests
- **Steps:**
  1. Choose canonical enum/action-class definitions.
  2. Share canonical JSON source through import or generator.
  3. Normalize all five surfaces to the same enum/type set.
  4. Add regression tests for unsupported values at each boundary.
- **Validation:**
  - existing + new tests in `apps/web/tests/*` plus contract schema tests.
- **Exit criteria:**
  - same request value accepted/rejected consistently across MCP, API, UI, and runtime.

---

## Wave C — Runtime hardening

### C1) Standardize claim handoff mode contracts

- **Findings:** F6
- **Scope:** `sprintctl/sprintctl/cli.py`, `sprintctl/tests/test_served_lifecycle_routes.py`, docs for served vs local commands
- **Steps:**
  1. Document mode-specific request/response shapes explicitly.
  2. Add schema adapters or stable aliases to reduce parser breakage.
  3. Add integration fixtures for both modes.
- **Validation:**
  - command contract tests for local and served mode.
- **Exit criteria:**
  - scripts can choose mode explicitly without shape ambiguity.

### C2) Add terminal ownership fencing in settle transitions

- **Findings:** F7
- **Scope:** `actionq/actionq/db.py`, `actionq-dispatcher` execution handlers
- **Steps:**
  1. Add claimant/process ownership token in terminal transition calls.
  2. Reject terminal actions when token mismatches current owner.
  3. Record rejected terminalization attempts in event log with reason.
- **Validation:**
  - tests for stale runner attempting complete/reject/fail on non-owned claim.
- **Exit criteria:**
  - stale runner finalization is rejected and does not mutate terminal state.

### C3) Clarify/complete Vuoro operational compatibility surfaces

- **Findings:** F8
- **Scope:** `packages/vuoro-service/src/vuoro_service/cli.py`, `docs` runbooks
- **Steps:**
  1. Mark unavailable operations as explicitly gated by adapter/identity condition.
  2. Update runbooks and user-facing docs.
  3. Implement deferred paths when upstream dependency and ownership requirements are present.
- **Validation:**
  - command-level doc tests/manual runbook exercise.
- **Exit criteria:**
  - no workflow references hidden no-op/fail-hard command paths.

---

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
- **G1 — Event creation.** Provide `work.event.add` and served `event add`.
  The server selects the authenticated actor; a served client must not need or
  transmit a client actor value.
- **G2 — Item creation.** Provide `work.item.create` and served `item add`.
  Resolve tracks in the server repository scope and preserve the established
  response shape.
- **G3 — Sprint reads.** Provide a basic `work.read.sprint` and served
  `sprint show`. Client-side polling is acceptable for `--watch`; `--detail`
  must fail explicitly until its aggregate has a catalog operation.
- **G4 — Catalog and doctor coverage.** Add every G1--G3 operation to the
  catalog contracts, command-route map, and doctor probes. Treat absent
  operations as a blocked compatibility state, not a local fallback.
- **G5 — Release and deployed verification.** After separately authorized
  Vuoro/appservice release work, verify catalog/doctor and the real served
  calls from both workstation and devbox-agent. This task is not authorization
  to publish a wheel, change a pin, deploy, or reconcile.

### Track I — Identity and references

- **I0 — Parse references before command dispatch.** Accept canonical
  `repo#id` references for every relevant item, sprint, claim, and event
  surface; retain bare numeric IDs only where the resolved repository makes
  them unambiguous.
- **I1 — Make precedence deterministic.** Resolve repository identity in this
  order: explicit reference/flag, committed marker or authority identity, then
  guarded local-path compatibility. Reject mismatches instead of choosing a
  convenient repository.
- **I2 — Render resolved context safely.** Show the effective repository,
  target, and backend before consequential calls, while redacting credentials,
  tokens, and profile-secret material.
- **I3 — Test identity boundaries.** Cover renamed clones, malformed and
  mismatched references, served/local precedence, and marker-less invocation
  without depending on live shared state.

### Track U — UX fail-closed robustness

- **U0 — Record the policy.** Remote and served execution without a repository
  marker fails closed by default. An explicit `--repo-id` plus an
  invocation-scoped opt-in flag may corroborate a marker-less invocation;
  neither is a persistent global bypass.
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

**Dependencies.** G1--G4 require U1--U3 where their CLI routes accept a
repository or target reference: parse and resolve context before issuing a
served operation, and enforce the marker-less guard before an authority call.
G5 depends on landed G1--G4 paths and separately authorized release work.

### Cutover evidence and configuration conformance

- **P1 — Reconcile static and historical evidence.** Compare the static
  workstation checker with the historical runtime-cutover ledger. A checker
  failure may reveal configuration-policy drift without invalidating recorded
  runtime evidence; report the two facts separately and correct the checker or
  executable configuration deliberately.
- **P2 — Configuration conformance.** Keep committed executable environment
  files on the served profile, remove direct-backend rollback wiring from them,
  and validate a deliberate repository subset when a declared workspace member
  is absent or on an independently owned branch. Report exclusions rather than
  calling the full workspace gate clean.

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

## Cross-cutting validation checklist (after each wave)

- `python templates/dispatch/scripts/validate_vuoro_profiles.py` for active members
- `python templates/dispatch/scripts/validate_verification_artifacts.py --root <repo>`
- `python templates/dispatch/scripts/sync_skills.py check --repo <repo>` for affected repos
- Targeted tests for modified modules

## Risk and rollback notes

- Any change touching claim lifecycle must be staged with rollback commands prepared.
- If validation fails mid-wave, freeze that wave and open a constrained follow-up issue (no further waves continue).
