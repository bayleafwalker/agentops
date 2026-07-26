# Vuoro Ecosystem Architecture Findings Dossier

**Created:** 2026-07-25  
**Reworked:** 2026-07-26  
**Owner:** agentops assessment pass  
**Status:** planning evidence; no backlog or production changes

## Purpose and evidence standard

This dossier records implementation findings across `agentops`, `vuoro`, `sprintctl`, `actionq`, and `actionq-dispatcher`. A finding is **confirmed** only when it names the current implementation location and observed behavior. A **policy decision** or **hypothesis** must not be executed as a defect repair until its decision gate is complete.

Implementation line references below describe the revisions inspected on 2026-07-26. Every build unit must pin its own input and output revisions in the verification record because line numbers can move.

## Corrected executive summary

- Claim renewal and terminal ownership fencing are one safety invariant and must be designed, built, and independently reviewed together.
- Workstation cutover currently exposes a checker-policy mismatch; it does not by itself prove that active runtime traffic bypasses Vuoro.
- Sprint repository identity is already propagated and authorized in served mode, but effective identity remains path-derived in one resolver.
- SQLite/Postgres `lease_epoch` behavior is a documented capability boundary. It becomes a defect only if production policy requires epoch fencing.
- Dispatch contracts have confirmed bidirectional drift across schema, runtime, MCP, and UI.
- Vuoro advertises operational CLI commands that are unavailable, while authority for migrations remains with domain-owner CLIs.

## Findings

### F1 - Workstation cutover validator and policy disagree

**Status:** Confirmed tooling-policy mismatch; active bypass not proven  
**Severity:** High until policy and live tenant-routing proof are complete  
**Owners:** `agentops` validator policy; each selected repository owns its runtime configuration

**Evidence**

- The checker owns an explicit eight-repository scope in `templates/dispatch/scripts/validate_vuoro_workstation_cutover.py:19-28,60-61`: `_orchestration`, `actionq`, `agentops`, `aligned-equity`, `box`, `homelab-analytics`, `scribectl`, and `sprintctl`.
- It scans `.envrc` text lexically, including comments, and requires exact literal exports at `validate_vuoro_workstation_cutover.py:37-50`.
- Several `.envrc` files retain commented rollback wiring. `homelab-analytics` sources active served exports from another file, which the checker does not inspect.
- The `--profile` argument is an absolute profile path, not a profile name (`validate_vuoro_workstation_cutover.py:57`).
- `vuoro` is not in the checker scope and retains its own remote backend configuration; it must not be swept into workstation-client edits without an owner decision.

**Decision required**

Choose and document one policy before editing consumers:

1. Require literal served exports in every selected `.envrc` and prohibit committed rollback snippets there; or
2. Make the validator shell-aware enough to recognize approved sourced canonical configuration and distinguish active wiring from comments.

**Closure evidence**

- Checker fixtures cover literal served configuration, approved sourced configuration, comments, active overrides, missing profile, and local-only rollback.
- Static validation passes with the absolute profile path.
- Read-only smoke checks from the actual working directory of at least two repositories assert the effective repo ID and return tenant-distinguishing records. HTTP success under wildcard credentials is insufficient.

### F2 - Dispatcher does not renew execution or coordination claims

**Status:** Confirmed  
**Severity:** Critical  
**Owners:** `actionq` for execution authority; `actionq-dispatcher` for orchestration; `sprintctl` for coordination authority

**Evidence**

- `actionq` already provides claimant-checked renewal in `actionq/actionq/db.py:645-752` and exposes it in `actionq/actionq/cli.py:152-175`.
- Dispatcher clients implement claim/complete/fail but no renewal at `actionq-dispatcher/actionq_dispatcher/clients.py:31-72`.
- One-shot execution blocks synchronously in `core.py:451-477`, so it cannot renew while invoking work.
- The daemon heartbeat at `daemon.py:901-914` is session observability only; it renews neither authority.
- Daemon sprint claim TTL is derived as `max(heartbeat_interval * 2, 1)` at `daemon.py:600-616`.
- Sprint claim heartbeat validation already exists in SQLite, Postgres, and served authority paths (`sprintctl/db.py:1521-1609`, `sprintctl/pg.py:2179-2198`, `sprintctl/authority.py:582-635`).

**Safety constraint**

Do not implement renewal as an isolated timer. Define authority ordering, partial-renewal behavior, worker cancellation, unknown outcomes, recovery, and immediate pre-settlement proof together with F7.

### F3 - Effective sprint repository identity is path-derived

**Status:** Confirmed, narrower than originally stated  
**Severity:** High  
**Owner:** `sprintctl`; Vuoro owns authorization enforcement

**Evidence**

- Served calls already propagate `repo_id` (`sprintctl/served.py:55-82`), and Vuoro rejects missing or unauthorized scoped IDs (`vuoro_service/app.py:326-359`).
- `resolve_repo_identity()` reads the marker but derives the effective ID from `repo_root.name` at `sprintctl/backend.py:89-111`; `load_backend_config` forwards that value at `backend.py:222-240`.
- Existing tests assert mismatch failure but do not prove stable identity after rename (`sprintctl/tests/test_backend_mode.py:104-136`).
- Work-adapter tenant slugs and authority-command committed UUIDs are different identity types. The repair must define their mapping and invariants rather than collapse them.
- Wildcard Vuoro credentials can authorize the wrong repo, so successful requests are not tenant-routing proof.

**Closure evidence**

End-to-end tests cover renamed clones, nested working directories, linked worktrees, missing markers, mismatch policy, unauthorized repos, and local/served behavior. Live smoke evidence must distinguish tenants.

### F4 - `lease_epoch` differs by backend under a documented capability boundary

**Status:** Policy decision, not a confirmed defect  
**Severity:** Medium  
**Owner:** `sprintctl`

**Evidence**

- The protocol documents `lease_epoch` as future fencing and SQLite as carrying it for schema parity (`sprintctl/docs/protocols/claim-ownership.md:69-75`).
- Postgres rotates/increments the epoch (`sprintctl/pg.py:2333-2349`); SQLite rotates the token without incrementing it (`sprintctl/db.py:1763-1800`).

**Decision required**

Determine whether any production consumer relies on epoch fencing. If not, preserve and test the documented capability boundary. If yes, design expected-epoch inputs and downstream enforcement; incrementing SQLite alone provides no fence.

### F5 - Dispatch contracts drift across schema, runtime, MCP, and UI

**Status:** Confirmed  
**Severity:** High  
**Owner:** `agentops`

**Evidence**

- Manifest JSON Schema accepts arbitrary action-class keys (`templates/dispatch/manifest.schema.json:20-34`), while cockpit runtime rejects keys outside a fixed list (`apps/web/lib/cockpit/dispatch-manifest.js:8,65-68`).
- Schema accepts `golden-child` but omits `session-reconciler` and `session-scribe` (`manifest.schema.json:49-72`); runtime does the inverse (`dispatch-manifest.js:9-33`).
- Dispatch request enums are duplicated in `apps/web/lib/cockpit/dispatch.js:8-11`.
- MCP advertises unconstrained strings and an incomplete output list at `apps/web/app/cockpit/api/mcp/route.js:99-107`, while runtime requires valid nonempty `kind` and `harness` (`dispatch.js:97-105`).
- UI exposes an undocumented subset and conflates plan/audit labeling (`apps/web/components/cockpit/dispatch-composer.js:6-13,39-49`).
- Existing tests do not assert schema/runtime/MCP/UI parity and mask the MCP-required-field mismatch (`apps/web/tests/write-surface.test.js:112-119,157-160`).

**Closure evidence**

Separate canonical contracts exist for manifests and dispatch requests. Every projection is generated or declares a tested subset relation. A fixture matrix proves accepted and rejected values through schema, runtime, HTTP, MCP, and UI projection.

### F6 - Claim handoff contracts differ intentionally by mode without a stable common envelope

**Status:** Confirmed contract portability gap  
**Severity:** Medium  
**Owner:** `sprintctl`

**Evidence**

- The same CLI dispatches local and served paths (`sprintctl/cli.py:6503-6560,6929-7000`).
- Served handoff intentionally rejects legacy adoption and transports proof differently (`cli.py:6714-6743`).

**Closure evidence**

Publish per-mode request/response schemas and stable common fields. Do not force semantic equivalence where capabilities intentionally differ.

### F7 - Action terminal transitions lack current-incarnation fencing

**Status:** Confirmed; coupled to F2  
**Severity:** Critical  
**Owners:** `actionq` and `actionq-dispatcher`

**Evidence**

- Terminal updates are status-gated but not claimant-incarnation-gated in `actionq/actionq/db.py:780-873`.
- Dispatcher terminal clients supply actor but no claimant proof (`actionq_dispatcher/clients.py:50-72`).
- Settlement mutates sprint state before unfenced action completion (`core.py:440-449`); failure paths have the same cross-authority partial-commit exposure (`core.py:595-621`).
- Daemon settlement exceptions can trigger another unfenced fail attempt (`daemon.py:709-717`).
- Sprint item transitions already require live `claim_id` and `claim_token` in SQLite and Postgres (`sprintctl/db.py:824-876`, `sprintctl/pg.py:1588-1630`).

**Safety constraint**

Use an opaque claim receipt/token or monotonic incarnation, not the claimant name. Ownership loss must stop or terminate execution and prohibit settlement. Cross-tool writes are not atomic, so recovery and idempotency must be explicit.

### F8 - Vuoro advertises unavailable operational CLI commands

**Status:** Confirmed  
**Severity:** Medium  
**Owner:** `vuoro`; domain repositories retain migration authority unless a separate decision changes it

**Evidence**

- CLI advertises `check-compatibility`, `migrate`, and `admin` (`vuoro_service/cli.py:23-38`), but compatibility returns a static unavailable result and migrate/admin fail through argparse (`cli.py:55-61`).
- Tests enshrine only the advertised stubs (`packages/vuoro-service/tests/test_app.py:16-22`).
- Public docs say the service owns compatibility checks, migration entrypoints, and authorized admin commands (`README.md:13-15`, `docs/architecture/packaging.md:21`).
- Composition loads adapters and pins, including migration entrypoints (`composition.py:37-69,265-327`), but exposes no operational context independent of ready-app construction.
- Deployment jobs currently call domain-owner migration CLIs directly (`deploy/kustomize/base/migration-jobs.yaml:18`).

**Decision required**

For each command choose `implemented`, `intentionally unavailable`, or `owner CLI only`, by environment. Do not introduce a second migration authority or an open-ended admin action string.

## Dependency map

- `S0/S1/S2`: F2 + F7 claim safety, sequential and blocking publication of that safety change.
- `I1`: F3 identity correction, independent of claim safety.
- `C1/C2/C3`: F5 contract convergence, internally sequenced but independent of claim safety.
- `P1`: F1 policy and validator alignment, before any consumer configuration edits.
- `L1`: F4 capability decision, independent unless epoch becomes part of claim fencing.
- `H1`: F6 handoff portability contract, independent.
- `O1/O2`: F8 authority decision then truthful/implemented CLI surface.

The executable plan is [vuoro-architecture-implementation-plan-2026-07-25.md](/projects/dev/agentops/docs/assessments/vuoro-architecture-implementation-plan-2026-07-25.md).
