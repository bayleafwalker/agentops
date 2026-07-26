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
  - `python templates/dispatch/scripts/validate_vuoro_workstation_cutover.py --root /projects/dev --profile workstation-vuoro-shared`
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

## Cross-cutting validation checklist (after each wave)

- `python templates/dispatch/scripts/validate_vuoro_profiles.py` for active members
- `python templates/dispatch/scripts/validate_verification_artifacts.py --root <repo>`
- `python templates/dispatch/scripts/sync_skills.py check --repo <repo>` for affected repos
- Targeted tests for modified modules

## Risk and rollback notes

- Any change touching claim lifecycle must be staged with rollback commands prepared.
- If validation fails mid-wave, freeze that wave and open a constrained follow-up issue (no further waves continue).
