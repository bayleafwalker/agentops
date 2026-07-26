# Vuoro Ecosystem Architecture & Implementation Findings Dossier  
**Created:** 2026-07-25  
**Owner:** agentops assessment pass (read-only review only)  
**Context:** codex-spark assessment across `agentops`, `vuoro`, `sprintctl`, `auditctl`, `actionq`, and `actionq-dispatcher` for code + architecture alignment.  

This dossier records discovered issues, risks, and correction pathways.  
No sprint backlog items are created or updated in this pass.

## Executive summary

- General posture is **intentionally conservative and mostly coherent**: ownership boundaries exist, contracts are codified, and core dispatch machinery is in place.
- The dominant risk is not implementation chaos but **boundary integrity**:
  - served-vs-direct control-plane wiring,
  - contract parity across layers,
  - claim/lease lifecycle behavior under long-running execution,
  - and mode-dependent identity semantics.
- Recommended order: fix critical path issues first (served cutover + claim lease liveness), then high-severity identity/contract risks, then medium-risk parity/traceability cleanup.

## Dossier scope

- Repos inspected:
  - `/projects/dev/agentops`
  - `/projects/dev/vuoro`
  - `/projects/dev/sprintctl`
  - `/projects/dev/auditctl`
  - `/projects/dev/actionq`
  - `/projects/dev/actionq-dispatcher`
- Review mode: read-only, with background-context checks against available scripts/docs.
- No code changes were made by this pass.

## Findings and correction pathways

### F1 — Incomplete Vuoro workstation served cutover (Critical)

**Severity:** Critical  
**Scope:** cross-repo deployment posture (`agentops`, `sprintctl`, `actionq`, and others in `/projects/dev`)  

**Observed issue:**  
Validation indicates residual direct-backend configuration markers still present in multiple repos despite served-path expectation (e.g., `SPRINTCTL_URL`, `SPRINTCTL_BACKEND=remote`, direct DB host references).

**Evidence references:**
- Workstation cutover validation output patterns in:
  - `templates/dispatch/scripts/validate_vuoro_workstation_cutover.py`
  - `docs/assessments/vuoro-pre-clean-room/...` notes captured in prior assessment review

**Risk / blast radius:**
- Runtime authority can bypass intended Vuoro-served path, weakening tenant/claim safety and increasing drift risk between repos and environments.

**Root cause hypothesis:**  
Environment-mode migration is incomplete and partially rolled back/annotated in committed shell state files rather than isolated local overrides.

**Correction pathway:**
1. Standardize `.envrc` and shell config across the impacted repos to a canonical served-mode block:
   - `SPRINTCTL_BACKEND=served`
   - `SPRINTCTL_VUORO_PROFILE=<active-profile>`
2. Remove direct DB/host references from committed workspace files used by runtime.
3. Keep rollback-only direct-backend snippets in local-only files, not shared checked-in configuration.
4. Re-run workstation cutover validator; require zero violations before marking complete.

**Pass criteria:**
- Cutover validator returns clean for all active member repos.
- No direct-backend residue in files expected to represent served-mode runtime configuration.

---

### F2 — Missing claim lease renewal for long-running execution (Critical)

**Severity:** Critical  
**Scope:** `actionq`, `actionq-dispatcher` (with implications into `sprintctl`)  

**Observed issue:**  
Long-running execution does not actively renew queue/sprint leases during runtime in several execution paths. Expired claims can be reclaimed while worker is still running, enabling duplicate execution races.

**Evidence references:**
- `actionq-daemon`/workflow logic in `actionq` and `actionq-dispatcher`
- `actionq/db.py` terminal path and sweep/reclaim behavior

**Risk / blast radius:**
- Duplicate action completion/retry behavior under timeout pressure.
- Hard-to-debug race conditions across queue + sprint claim transitions.

**Root cause hypothesis:**  
Current lifecycle assumes external sweeper behavior and fixed claim TTLs, but no periodic in-run heartbeat/renewal enforcement in executor paths.

**Correction pathway:**
1. Add periodic claim renewal during active execution in dispatcher (`run_forever` / one-shot prepare/execute/settle path).
2. Require ownership-token/claim identity checks at terminal transitions.
3. Add bounded backoff + explicit stale-claim refusal when renewals are impossible.
4. Add integration test for long-running action where claim TTL is shorter than execution window.

**Pass criteria:**
- Long-running action cannot be reclaimed until explicit end-of-work state is emitted.
- No duplicate in-flight execution for a single action under controlled timeout expiry.

---

### F3 — Repo identity canonicalization mismatch in `sprintctl` (High)

**Severity:** High  
**Scope:** `sprintctl` backend selection and authority command paths  

**Observed issue:**  
`repo_id` derivation is path-based in local/backend-resolution paths while authority paths use committed repo identity, creating possible cross-mode identity drift.

**Evidence references:**
- `sprintctl/sprintctl/backend.py`
- `sprintctl/sprintctl/cli.py`
- `sprintctl/tests/`

**Risk / blast radius:**  
Tenant/project interpretation can diverge by mode, especially across clones/worktrees and served/local execution boundaries.

**Root cause hypothesis:**  
Inconsistent source-of-truth order for `repo_id`.

**Correction pathway:**
1. Make identity resolution source-of-truth explicit and shared across modes.
2. Validate identity marker vs authority UUID mismatch at command boundaries.
3. Add regression tests for directory rename/move/worktree clone scenarios.

**Pass criteria:**
- Same logical repo resolves to one canonical ID in local, served, and authority modes.

---

### F4 — Backend lease-lineage divergence in `sprintctl` (High)

**Severity:** High  
**Scope:** `sprintctl` sqlite vs postgres claim lease behavior  

**Observed issue:**  
Lease lineage (`lease_epoch` semantics) differs across storage backends; one backend increments/fences while the other does not (or behaves differently).

**Evidence references:**
- `sprintctl/sprintctl/db.py`
- `sprintctl/sprintctl/db/pg.py`
- `sprintctl/docs/protocols/claim-ownership.md`

**Risk / blast radius:**  
Operational tooling that assumes monotonic fencing/lease lineage may behave inconsistently when backends differ.

**Root cause hypothesis:**  
Backend-specific behavior was not normalized or explicitly documented as a compatibility boundary.

**Correction pathway:**
1. Choose one of:
   - parity implementation across backends, or
   - explicit backend capability contract with strict guards/tests.
2. Update protocol docs to describe supported behavior by backend.
3. Add parity-focused tests that fail if assumptions diverge.

**Pass criteria:**
- No hidden backend behavior divergence for claim lease expectations under accepted production modes.

---

### F5 — Dispatch contract parity drift in `agentops` (High)

**Severity:** High  
**Scope:** `agentops` runtime/API/UI/workspace surfaces  

**Observed issue:**  
Allowed action/output enums and manifest fields are not fully synchronized across schema, MCP interface, runtime normalizer, and UI paths.

**Evidence references:**
- `templates/dispatch/manifest.schema.json`
- `apps/web/lib/cockpit/dispatch-manifest.js`
- `apps/web/app/cockpit/api/mcp/route.js`
- `apps/web/lib/cockpit/dispatch.js`
- `apps/web/components/cockpit/dispatch-composer.js`

**Risk / blast radius:**  
Clients can send values/skills that are valid in one layer and invalid in another, causing silent inconsistency and protocol drift.

**Root cause hypothesis:**  
Contracts are maintained separately without a canonical generated/shared contract export.

**Correction pathway:**
1. Define single canonical schema source for:
   - manifest action classes/skills,
   - MCP request enum set,
   - dispatcher normalizer,
   - UI selectors.
2. Add parity tests at boundary edges (schema ↔ runtime ↔ MCP ↔ UI).
3. Add explicit negative tests for unsupported combinations.

**Pass criteria:**
- One enum set and one manifest contract accepted consistently across all dispatch entry points.

---

### F6 — Claim handoff shape and mode portability mismatch (`sprintctl`) (Medium)

**Severity:** Medium  
**Scope:** `sprintctl` served-vs-local command semantics  

**Observed issue:**  
CLI behavior for handoff/claim commands differs by mode; JSON effect shapes and option acceptance are not uniform.

**Evidence references:**
- `sprintctl/sprintctl/cli.py`
- `sprintctl/tests/test_served_lifecycle_routes.py`
- `sprintctl/tests/test_claims.py`

**Risk / blast radius:**  
Automation/scripts assuming uniform command contracts can fail or mis-handle responses.

**Root cause hypothesis:**  
Legacy/local and served flows were intentionally differentiated without complete contract harmonization.

**Correction pathway:**
1. Add mode-specific contract documentation for each command.
2. Introduce schema-shape adapters or explicit stable fields for all paths.
3. Add integration fixtures for both modes.

**Pass criteria:**
- Explicitly documented and tested command contracts by mode.

---

### F7 — Terminal ownership fencing gap in execution layers (Medium)

**Severity:** Medium  
**Scope:** `actionq` terminal state transitions / dispatcher settle path  

**Observed issue:**  
Terminal transitions (`complete`/`fail`/`reject`) are status-gated but may not always verify live claimant/process ownership, allowing cross-path stale completion risk.

**Evidence references:**
- `actionq/actionq/db.py`
- `actionq-dispatcher` execution and settle handlers

**Risk / blast radius:**  
Potential incorrect finalization if stale/overlapping process paths race.

**Root cause hypothesis:**  
Terminal state transitions rely on row status rather than owner token identity at finalize moment.

**Correction pathway:**
1. Add ownership token checks before terminal transition attempts.
2. Ensure terminal writes always include ownership proof or claim receipt.
3. Add tests for stale runner/overlap terminal race conditions.

**Pass criteria:**
- Terminal events reject when caller is not current owner of the active claim.

---

### F8 — Vuoro operational compatibility gaps (Medium)

**Severity:** Medium  
**Scope:** `vuoro` service/client operational CLI surface  

**Observed issue:**  
Service CLI paths for compatibility/migration/admin operations are explicitly stubbed/deferred in implementation.

**Evidence references:**
- `packages/vuoro-service/src/vuoro_service/cli.py`

**Risk / blast radius:**  
Operational workflows that expect runnable compatibility/migration/admin commands fail early and may skip maintenance playbooks.

**Root cause hypothesis:**  
Feature surface intentionally deferred until adapter registration and ownership boundary tasks complete.

**Correction pathway:**
1. Document intended command availability by mode/environment.
2. Gate runbooks to avoid invoking unavailable commands.
3. Implement deferred paths once adapter and ownership checks are in place.

**Pass criteria:**
- No documented workflow references unavailable operational commands.

---

## Shared correction sequence (recommended)

### Wave A — Boundary correctness (Critical)
1. F1 (served cutover)
2. F2 (claim lease renewal)

### Wave B — Identity and contract consistency (High)
3. F3 (repo identity canonicalization)
4. F4 (lease-lineage parity/contract)
5. F5 (dispatch contract parity)

### Wave C — Runtime hardening (Medium)
6. F6 (mode portability contract docs)
7. F7 (terminal ownership fencing)
8. F8 (vuoro deferred command handling clarity)

## Verification plan (read-only safe checklist)

For each finding closure, re-run:
- `python templates/dispatch/scripts/validate_vuoro_workstation_cutover.py --root /projects/dev --profile ...` (for F1)
- `python templates/dispatch/scripts/validate_vuoro_profiles.py --project ...` (supporting env profile checks)
- Focused unit/integration tests in modified repo scopes
- Scripted regression checks for claim lifecycle and handoff behaviors where implemented
- Manual contract consistency check with a representative run-through of:
  - manifest read/load,
  - MCP dispatch input validation,
  - claim prepare/terminalization paths

## Acceptance criteria (global)

- No new direct-backend runtime residues for served-path repos.
- No unbounded cross-mode repo identity divergence.
- No claim-lifecycle race from missing in-run lease renewal.
- Single canonical dispatch contract accepted across schema/API/UI.
- Terminal claim transitions are ownership-safe.

## Notes

- This dossier is documentation only.
- It is intentionally not yet represented as sprint backlog items.
- Execution roadmap is in: [vuoro-architecture-implementation-plan-2026-07-25.md](/projects/dev/agentops/docs/assessments/vuoro-architecture-implementation-plan-2026-07-25.md)
