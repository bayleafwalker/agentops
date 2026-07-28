---
doc_id: vuoro-substrate-simplification-refactoring
status: ratified
ratified_at: 2026-07-28
ratified_by: operator
supersedes: []
---

# Vuoro Substrate Simplification and Refactoring Assessment

**Created:** 2026-07-26  
**Mode:** read-only planner assessment  
**Status:** ratified architecture scope; live execution state remains in Sprintctl
**Scope:** `vuoro`, `sprintctl`, `actionq`, `actionq-dispatcher`, and relevant `agentops` dispatch/cockpit contracts

## Executive recommendation

The substrate has sound domain-authority boundaries, but its delivery topology has accumulated duplicate coordinators, duplicate network paths, transitional backend modes, and repeated contract projections. The highest-leverage simplification is to converge on:

1. one execution coordinator implementation and one `actionq-daemon` entrypoint;
2. one fenced execution-session state machine spanning action and sprint claims without merging their authorities;
3. two supported Sprintctl consumer modes: local/offline and Vuoro-served;
4. one owner-mediated read/write path per domain for the cockpit;
5. one canonical dispatch request contract and one canonical manifest contract;
6. protocol-version compatibility implemented through shared internals rather than duplicated code paths; and
7. explicit retirement dates for pilot, shadow, direct-server, and stub surfaces.

This is not a recommendation to merge repositories or state machines. `actionq` must retain execution-queue authority, `sprintctl` must retain work/claim authority, Vuoro must remain a transport/composition shell, and `agentops` must remain a contract and cockpit consumer rather than a new domain authority.

## Assessment method and evidence limits

The original pass inspected implementation and architecture documents without
running tests or runtime commands. This revision reconciles that assessment
against repository heads and live Sprintctl state on 2026-07-28. Historical
line references still describe the 2026-07-26 source shape; implementation
must use the revision-bound work-item refs below rather than treating those
line numbers as current.

The assessment cross-checks:

- `docs/assessments/vuoro-architecture-findings-2026-07-25.md`;
- `docs/assessments/vuoro-architecture-implementation-plan-2026-07-25.md`;
- `docs/assessments/vuoro-architecture-operator-packet-2026-07-25.md`; and
- `docs/assessments/vuoro-architecture-preflight-checklist-2026-07-25.md`.

Absence of a reference in this document is not evidence that a surface is unused. Every deletion or mode retirement requires a repository-wide consumer inventory and a fresh secondary implementation review.

## Current-state and backlog crosswalk

Sprintctl is authoritative for execution status. This table is a dated
projection that prevents already-landed convergence work from being planned
again; re-read each item before dispatch.

| Recommendation | 2026-07-28 state | Governing backlog |
| --- | --- | --- |
| R1 coordinator convergence | Landed and independently verified. Actionq owns the kernel and `actionq-daemon`; `actionq-dispatcher` is a compatibility shim and no longer publishes the daemon entrypoint. | actionq #2010, #2012, #2013; agentops #2014 |
| R2 fenced supervision and settlement | Action claim fencing, governed kernel supervision, retained fault evidence, and the convergence review are landed. Any further protocol redesign must start from these revisions, not the 2026-07-26 call sites. | actionq #2011; agentops #2014 |
| R3 legacy Actionq HTTP retirement | Catalog parity and consumer inventory remain prerequisites. | agentops #2039 |
| R4 two Sprintctl consumer modes | Cutover is complete; retirement and parity evidence remain live owner work. Owner-only Postgres administration remains explicitly out of the consumer-mode removal. | sprintctl #1164, #2038 |
| R5 cutover-surface disposition | Partially represented by the split-backend retirement ledger; pilot/projection retention decisions must be recorded before deletion. | sprintctl #1164, #1218, #1234 |
| R6 cockpit owner-mediated reads/writes | Sprint activation is owner-mediated, but direct read-schema and Actionq fallback removal remain. | agentops #2039 |
| R7 canonical dispatch request | The portable execution envelope is ratified, but the browser/MCP/request-field convergence decision remains. | agentops #2040; agentops #2036 is downstream execution-envelope work |
| R8 shared invocation/profile internals | Service request-field sharing landed at Vuoro `cb825c9`; client invocation and profile-loader consolidation remain separate bounded work. | vuoro #2024, #2041 |
| R9 recovery prototype disposition | Marked recovery shipped, but the disconnected in-memory service reconciler still needs an explicit keep/remove/owner-route decision. | vuoro #2042 |
| R10 truthful adapter locking | Immutable wheel URLs and revision provenance are landed; the release-lock/runtime-descriptor split remains. | vuoro #2043 |
| R11 generated/direct Agentops projections | Covered with R7 so generated projections cannot precede the field-semantics decision. | agentops #2040 |

## Priority summary

| ID | Priority | Change class | Recommendation | Expected benefit |
| --- | --- | --- | --- | --- |
| R1 | P0 | Semantic redesign | Select one execution coordinator and retire the duplicate daemon/entrypoint | Very high |
| R2 | P0 | Safety redesign | Implement one fenced execution-session and settlement state machine | Very high |
| R3 | P1 | Semantic retirement | Retire the legacy Actionq HTTP facade and cockpit CLI/server dual path | High |
| R4 | P1 | Semantic redesign | Reduce Sprintctl consumer modes to local and served | Very high |
| R5 | P1 | Staged retirement | Remove or productize migration-era pilot, shadow, and projection switches | High |
| R6 | P1 | Semantic boundary change | Replace cockpit schema coupling with owner-mediated read models | High |
| R7 | P1 | Contract redesign | Collapse redundant dispatch-kind aliases and canonicalize the request | High |
| R8 | P2 | Mechanical consolidation | Share Vuoro v1/v2 invocation internals and profile loading | Medium |
| R9 | P2 | Product decision | Remove or owner-route the disconnected recovery prototype | Medium |
| R10 | P2 | Mechanical plus policy | Make adapter locking coherent while keeping explicit domain composition | Medium |
| R11 | P2 | Mechanical consolidation | Generate or directly consume Agentops contract projections | Medium |

## Findings and proposals

### R1 - Two packages implement and publish the execution coordinator

**Change class:** semantic redesign; do not perform as a mechanical move  
**Priority:** P0  
**Decision owners:** `actionq` and `actionq-dispatcher`

**Exact evidence**

- `actionq/pyproject.toml:39-43` publishes `actionq-daemon`, while `actionq-dispatcher/pyproject.toml:33-35` publishes another command with the same name.
- The Actionq daemon defines its own coordinator client, subprocess-backed `actionctl` adapter, pause/config model, polling loop, harness routing, session events, and terminal settlement at `actionq/actionq/daemon.py:83-160,193-220,363-460,577-594,740-760`.
- The dispatcher defines the same queue client protocol and pause/claim/cycle loop at `actionq-dispatcher/actionq_dispatcher/core.py:32-73,101-229`.
- The dispatcher adds the governed-build capabilities that are not equivalent to the generic Actionq daemon: isolated worktree creation, sprint claim acquisition, ACL/prompt preparation, post-validation, and cross-authority settlement at `actionq-dispatcher/actionq_dispatcher/core.py:258-449`.
- The dispatcher daemon adds a second session lifecycle around that core at `actionq-dispatcher/actionq_dispatcher/daemon.py:560-717`.
- Repository documentation conflicts: `actionq/README.md:148-169` calls the in-package daemon the Actionq-owned coordinator and treats the dispatcher configuration as legacy, while `actionq-dispatcher/README.md:15-28` and its repository guidance assign coordinator ownership to `actionq-dispatcher`.

**Current complexity**

There are two configuration parsers, two pause mechanisms, two action clients, two routing stacks, two session-record implementations, two systemd surfaces, and two settlement paths. Any claim renewal, cancellation, recovery, telemetry, or routing correction can be implemented twice or only in one path. The identical console-script name also makes the active implementation dependent on installation order.

**Simpler target**

Select one canonical coordinator package and one console entrypoint. The recommended target is:

- `actionq` owns queue persistence, lifecycle transitions, claim receipts, schema compatibility, owner CLI, and the Vuoro execution adapter;
- `actionq-dispatcher` owns the coordinator kernel, one-shot and daemon scheduling shells, harness execution, worktrees, gates, ACLs, session evidence, and cross-domain orchestration; and
- one-shot and daemon operation call the same `prepare -> supervise -> validate -> settle/recover` kernel.

If owners instead choose the Actionq repository as the canonical package, the same separation still applies internally: queue authority and coordinator code must be distinct packages/modules, and the standalone dispatcher must be retired. Keeping both is not an acceptable steady state.

**Prerequisites and dependencies**

- Resolve the ownership conflict before Track S unit S2.
- Inventory installed entrypoints, systemd units, cron jobs, config paths, smoke scripts, and deployment references.
- Define a compatibility shim and explicit removal date for the losing entrypoint.
- Preserve the dispatcher-only worktree, ACL, gate, and artifact behavior.

**Migration and compatibility risks**

- Installation order may currently select different daemons on different hosts.
- Existing configuration shapes and state files are not interchangeable.
- Session event payloads and crash-recovery records may differ.
- Removing either daemon before capability parity could drop safety gates or operational recovery behavior.

**Expected benefit**

Very high. Every later renewal, routing, session, and settlement change has one implementation and one secondary review surface.

**Explicit non-goals**

- Do not move queue SQL or claim authority into the dispatcher.
- Do not make Vuoro the execution coordinator.
- Do not remove worktree, ACL, gate, timeout, budget, or evidence boundaries.

**Required secondary implementation review**

A fresh Spark-class reviewer must inspect the pinned cross-repository implementation, enumerate every old entrypoint/config/service reference, compare event and recovery behavior, and prove that one-shot and daemon modes exercise the same coordinator kernel. The review fails if two independently evolving settlement or renewal paths remain.

### R2 - Claim, supervision, and settlement need one state machine, not more adapters

**Change class:** safety-critical semantic redesign  
**Priority:** P0  
**Decision owners:** `actionq`, `actionq-dispatcher`, and `sprintctl`

**Exact evidence**

- Dispatcher protocols expose claim/complete/fail/reject but no action or sprint renewal at `actionq-dispatcher/actionq_dispatcher/core.py:32-69`.
- `PreparedSession` stores the Sprintctl claim proof, while the Actionq claim incarnation is not represented at `actionq-dispatcher/actionq_dispatcher/core.py:76-91`.
- Successful settlement writes Sprintctl done first and then completes Actionq at `actionq-dispatcher/actionq_dispatcher/core.py:402-449`.
- One-shot execution blocks synchronously in the worker call at `actionq-dispatcher/actionq_dispatcher/core.py:451-477`.
- The dispatcher daemon heartbeat supervises a process but then calls the same unfenced settlement path, and a settlement exception triggers a second Actionq fail attempt at `actionq-dispatcher/actionq_dispatcher/daemon.py:702-717`.
- The second Actionq daemon has another unfenced complete/fail sequence and fail-on-exception path at `actionq/actionq/daemon.py:740-760`.
- Actionq already implements claimant-checked renewal but terminal transitions lack current-incarnation proof at `actionq/actionq/db.py:645-752,780-873`.

**Current complexity**

Action claim, Sprintctl claim, session heartbeat, process PID, takeup state, worktree state, and terminal outcomes are tracked in separate records with no single legal-transition table. Cross-tool writes cannot be atomic, but current code expresses them as ordered calls and exception handling rather than an explicit recoverable protocol.

**Simpler target**

Create one coordinator-owned `ExecutionSession` state machine containing:

- opaque Actionq claim receipt/incarnation;
- opaque Sprintctl claim ID/token;
- worker process and cancellation state;
- renewal deadlines and last confirmed authority states;
- validation result;
- settlement intent and per-authority settlement results; and
- durable recovery status for unknown or partial outcomes.

The state machine should expose a narrow owner-client interface: `claim`, `renew`, `prove_current`, `settle`, and `read_state`. It must not pretend the two authorities form one transaction. A durable settlement journal and idempotent recovery replace nested best-effort exception paths.

**Prerequisites and dependencies**

- Complete architecture-plan S0 protocol design.
- Complete R1's canonical-coordinator decision before implementing S2 supervision.
- Implement Actionq terminal fencing in S1 before coordinator settlement.
- Decide cancellation semantics for every supported harness.

**Migration and compatibility risks**

- Mixed-version clients could be unable to provide new claim receipts.
- A lost renewal response can create an unknown rather than failed state.
- Forced worker termination cannot undo already-issued external side effects.
- Settlement ordering changes may alter operator-visible failure states.

**Expected benefit**

Very high. Safety reasoning moves from multiple call sites into one transition table and one fault-history suite.

**Explicit non-goals**

- Do not merge Actionq and Sprintctl claims into one authority.
- Do not use claimant names as fencing proofs.
- Do not call session heartbeat an authority renewal.
- Do not hide partial settlement behind a generic retry.

**Required secondary implementation review**

Use the architecture plan's S0-S3 fault matrix, but review the canonical coordinator only. A fresh Spark-class reviewer must independently exercise expiry, response loss, sweep/reclaim, each renewal failure, cancellation failure, shutdown, stale settlement, and both partial-settlement orders. Any continued execution or accepted settlement after ownership loss fails the gate.

### R3 - Actionq's legacy HTTP facade creates a third execution API

**Change class:** semantic retirement  
**Priority:** P1  
**Decision owners:** `actionq`, `vuoro`, and `agentops`

**Exact evidence**

- Actionq describes `ActionQApplication` as shared by the CLI, a legacy HTTP facade, and Vuoro at `actionq/README.md:51-65`.
- `actionq-server` is still a published entrypoint at `actionq/pyproject.toml:39-43`.
- The server independently exposes compatibility, sessions, dispatches, and dispatch mutation at `actionq/actionq/server.py:25-58,79-88,153-166`.
- The cockpit selects between CLI and server for sessions at `agentops/apps/web/lib/cockpit/actionq.js:9-59`, but requires the server for dispatch rows at `agentops/apps/web/lib/cockpit/actionq.js:62-80`.
- Dispatch writes also select between direct `actionctl` and the server at `agentops/apps/web/lib/cockpit/dispatch.js:22-43,132-181`.

**Current complexity**

Execution data is available through owner CLI JSON, the legacy owner HTTP server, and the Vuoro execution adapter. The cockpit carries fallback and capability logic for two of those paths. Compatibility and output contracts can drift independently.

**Simpler target**

Use Vuoro as the only browser-facing network transport for execution reads and dispatch mutation. Retain `actionctl` as the owner/operator and migration CLI, not as a cockpit fallback. Remove `actionq-server` after catalog parity, deployment cutover, and a deprecation window.

If Vuoro is not selected, choose the owner HTTP API and remove the Vuoro execution projection. Do not retain both network APIs indefinitely.

**Prerequisites and dependencies**

- Catalog operations must cover session rows, dispatch rows, and dispatch creation.
- The canonical dispatch request from R7 must be available.
- Cockpit authentication, authorization, caching, and error contracts need parity fixtures.
- Deployment changes require separate `appservice` authorization.

**Migration and compatibility risks**

- The current server may expose reads not yet present in the Vuoro catalog.
- CLI fallback may be masking network or deployment outages.
- Browser authentication and Actionq actor provenance must remain explicit.

**Expected benefit**

High. Removes one service, one deployment/config mode, two cockpit branches, and one contract family.

**Explicit non-goals**

- Do not remove `actionctl` operator or migration commands.
- Do not let the cockpit connect directly to Actionq tables.
- Do not let Vuoro own Actionq lifecycle semantics.

**Required secondary implementation review**

A fresh Spark-class reviewer must compare old CLI, old server, and target transport fixtures at pinned revisions, including authorization and rejected writes. Removal is blocked until all declared cockpit capabilities have parity or an approved deletion decision.

### R4 - Sprintctl has three consumer modes and scattered served-mode forks

**Change class:** semantic redesign with a mechanical first phase  
**Priority:** P1  
**Decision owner:** `sprintctl`; Vuoro reviews the served boundary

**Exact evidence**

- Backend markers and environment selection accept `local`, `remote`, and `served` at `sprintctl/sprintctl/backend.py:70-86,186-242`.
- `remote` opens Postgres and performs a schema handshake directly inside the CLI process at `sprintctl/sprintctl/cli.py:157-176`.
- Served mode defines a separate profile dataclass and partial profile parser at `sprintctl/sprintctl/backend.py:29-42,114-183`.
- Served mode then converts that duplicate profile into `vuoro_client.Profile` at `sprintctl/sprintctl/served.py:33-52`.
- The served facade has one public wrapper and one `asyncio.run` call per operation at `sprintctl/sprintctl/served.py:55-217,221-384`.
- A second data structure maps exact CLI paths to operations at `sprintctl/sprintctl/served_routes.py:42-94`, while command bodies still contain mode-specific behavior and unsupported-capability messages throughout `sprintctl/sprintctl/cli.py`.
- The served optional dependency is pinned to a raw commit because there is no release tag at `sprintctl/pyproject.toml:19-27`.

**Current complexity**

Local and direct-Postgres modes share store-shaped code, while served mode bypasses it through command-specific functions. Capability differences are encoded in route data, wrapper functions, and individual Click commands. A new operation requires edits across all three layers. Direct Postgres is both a consumer mode and the implementation substrate used by the owner adapter, which obscures the boundary.

**Simpler target**

Support two end-user modes:

- `local`: SQLite/offline owner implementation; and
- `served`: Vuoro client transport.

Keep Postgres as an internal owner implementation and explicit migration/administration target, not as a general consumer `SPRINTCTL_BACKEND=remote` mode. Introduce one synchronous served gateway that owns event-loop creation and accepts operation name, arguments, repo scope, idempotency, and transient proof. Make the capability table active routing data or delete it; do not maintain both route metadata and hand-written wrappers.

The safe mechanical first phase is to move profile parsing into the Vuoro client package and lazy-import it only when served mode is selected. Served mode already requires that package, so Sprintctl does not need a duplicate profile model merely to protect local imports.

**Prerequisites and dependencies**

- Served catalog parity for required direct-Postgres commands.
- Resolution of claim-proof and handoff differences in Tracks S and H.
- A decision on owner-only Postgres migration, repair, export, and diagnostics commands.
- A released, tagged Vuoro client artifact.
- Consumer inventory proving which repositories still require direct remote mode.

**Migration and compatibility risks**

- Direct remote mode currently supports capabilities that served mode explicitly rejects.
- Owner repair and schema commands must not be forced through runtime credentials.
- Local/offline recovery behavior is intentionally different and must remain.

**Expected benefit**

Very high. Removes one supported consumer mode and centralizes served transport/capability handling.

**Explicit non-goals**

- Do not remove local SQLite/offline use.
- Do not remove the Postgres owner implementation or migration role.
- Do not claim local and served capabilities are identical.
- Do not expose migration DSNs through Vuoro client profiles.

**Required secondary implementation review**

A fresh Spark-class reviewer must inventory every CLI command across local, direct-Postgres, and served modes, classify it as retained, migrated, owner-only, or removed, and execute positive/negative parity fixtures against disposable implementations. Unsupported semantic differences must remain explicit.

### R5 - Cutover scaffolding has become a product-sized subsystem

**Change class:** staged retirement or explicit productization  
**Priority:** P1  
**Decision owner:** `sprintctl`

**Exact evidence**

- The cutover module says three independent opt-in systems were built for observation shadowing, authority-command rollout, and guarded projection reads at `sprintctl/sprintctl/cutover.py:1-21`.
- The CLI imports cutover, dual-write, pilot, shadow, sync, and projection-read modules at `sprintctl/sprintctl/cli.py:23-38`.
- Projection-read fallback and partial projection semantics occupy command-path logic at `sprintctl/sprintctl/cli.py:1225-1414`.
- Best-effort shadow mirroring is embedded in normal event handling at `sprintctl/sprintctl/cli.py:2102-2169`.
- Pilot configuration owns three additional repository-local files at `sprintctl/sprintctl/pilot.py:21-27,140-246`.
- Pilot status, verification, synchronization, and cutover evidence remain public CLI surfaces at `sprintctl/sprintctl/cli.py:3295-3423`.
- Projection reads have another versioned file and environment override at `sprintctl/sprintctl/projection_reads.py:1-13,32-35,125-246`.

**Current complexity**

Temporary migration safety now includes independent config files, local outboxes, projection databases, environment overrides, CLI groups, parity reports, rollback rehearsal, and fallback behavior inside ordinary reads and writes. A cutover toolchain without an exit condition becomes a permanent second architecture.

**Simpler target**

Record an explicit disposition for each surface:

| Surface | Recommended disposition |
| --- | --- |
| observation pilot | retire after final cutover evidence and retention export |
| dual-write/shadow comparison | retire after the selected authority is stable |
| cutover evidence builder | archive as historical verification tooling or move to owner-only maintenance tooling |
| projection read cache | either promote to a supported offline cache with one config contract, or remove it |
| authority outbox | retain if it remains the durable owner-command mechanism |

Do not keep pilot enablement, projection-read enablement, and authority rollout as three independent steady-state knobs.

**Prerequisites and dependencies**

- Confirm which cutover milestones are complete.
- Identify every active config file and automation consumer.
- Define retention/export requirements for pilot evidence.
- Complete R4's target backend decision.

**Migration and compatibility risks**

- Removing shadow evidence too early can eliminate rollback confidence.
- Projection caches may be relied on for offline reads.
- Historical commands may appear in runbooks or automation even when disabled.

**Expected benefit**

High. Reduces operational modes, state files, CLI branches, and test matrices.

**Explicit non-goals**

- Do not remove the durable authority outbox merely because it originated in cutover work.
- Do not delete evidence required for audit or incident reconstruction.
- Do not convert a non-authoritative cache into authority.

**Required secondary implementation review**

A fresh Spark-class reviewer must trace every removed flag/file/command from configuration through CLI and storage, confirm retained outbox semantics, and review archived evidence. The review fails if a normal write still silently depends on a removed pilot path.

### R6 - Cockpit reads are coupled directly to owner schemas

**Change class:** semantic boundary change  
**Priority:** P1  
**Decision owners:** `agentops`, `sprintctl`, and `actionq`

**Exact evidence**

- The cockpit constructs its own Postgres pool from `SPRINTCTL_URL` at `agentops/apps/web/lib/cockpit/sprintctl.js:4-27`.
- It reimplements repository, sprint, work-item, attention, takeup, claim, and event projections with direct SQL at `agentops/apps/web/lib/cockpit/sprintctl.js:29-359`.
- Sprint activation calls an owner SQL function directly at `agentops/apps/web/lib/cockpit/sprintctl.js:365-398`.
- Actionq reads use a mix of CLI subprocess and legacy HTTP server at `agentops/apps/web/lib/cockpit/actionq.js:9-80`.

**Current complexity**

The cockpit must know table names, joins, timestamps, status values, pagination, takeup event reconstruction, and stored-function error codes. Domain schema evolution therefore requires synchronized cockpit changes even when the public domain contract is stable.

**Simpler target**

Make the cockpit a consumer of owner-mediated read models and commands, preferably through Vuoro for browser-facing network access. Domain owners return stable cockpit-neutral payloads; Agentops retains presentation-only summaries and UI state. Sprint activation must travel through an authenticated owner API rather than a direct database connection.

**Prerequisites and dependencies**

- Add owner read operations for repository inventory, sprint summaries, claims, takeup, and events.
- Define pagination and cache semantics.
- Complete R3's Actionq transport decision.
- Preserve read-only workspace and browser write-token boundaries.

**Migration and compatibility risks**

- Direct SQL may currently expose richer or cheaper bulk reads.
- Replacing it with many small operations could cause latency regressions.
- Cockpit-specific aggregation must not be pushed into a domain state machine without a reusable contract.

**Expected benefit**

High. Removes database credentials and schema knowledge from the web app and narrows cross-repository release coupling.

**Explicit non-goals**

- Do not move Sprintctl or Actionq state transitions into Agentops.
- Do not add a second cockpit-owned persistence layer.
- Do not replace efficient bulk reads with unbounded request fan-out.

**Required secondary implementation review**

A fresh Spark-class reviewer must compare old SQL results and new owner-API results on revision-bound fixtures, including pagination, time serialization, tenant isolation, empty states, and authorization. Direct database writes or undisclosed schema fallbacks fail the gate.

### R7 - Dispatch kinds are aliases, not distinct execution semantics

**Change class:** contract redesign  
**Priority:** P1  
**Decision owners:** `agentops`, `actionq`, and the canonical coordinator

**Exact evidence**

- Actionq maps `implement`, `review`, `test`, `investigate`, `document`, and `custom` to the single `scope-iterate` action type at `actionq/actionq/application.py:20-27`.
- The cockpit duplicates the same mapping at `agentops/apps/web/lib/cockpit/dispatch.js:8-20`.
- The Actionctl fallback reduces a normalized dispatch to action type, project, target, source, creator, and numeric priority at `agentops/apps/web/lib/cockpit/dispatch.js:132-143`; fields such as title, prompt, harness, model, output expectation, and group ID are not represented on that path.
- Runtime request enums and validation are locally defined at `agentops/apps/web/lib/cockpit/dispatch.js:7-11,72-129`.

**Current complexity**

`kind`, `output_expectation`, and `action_type` appear to describe overlapping concepts, but all kinds execute one action type. Different transports preserve different subsets of the request. Routing and UI labels therefore look richer than the queue's durable contract.

**Simpler target**

Choose one durable semantic field for requested work outcome and one execution action type. Recommended:

- `action_type` selects the coordinator handler, initially `scope-iterate`;
- `output_expectation` is a closed, durable requested artifact/outcome;
- routing class is derived once from the expectation and repository policy; and
- remove `kind` unless it has a distinct behavior that can be demonstrated and tested.

Store the full canonical request or a stable reference in Actionq so every accepted transport preserves equivalent intent.

**Prerequisites and dependencies**

- Architecture-plan C0 must decide field semantics, not only enum ownership.
- Inventory saved requests, MCP clients, cockpit UI, workflow scripts, and queue rows.
- Define a versioned compatibility adapter for v1 requests.

**Migration and compatibility risks**

- Existing consumers may rely on current `kind` labels.
- Historical queue rows may not contain enough information to reconstruct expectations.
- Mapping changes can alter model routing.

**Expected benefit**

High. Removes duplicate mappings and prevents transport-dependent loss of dispatch intent.

**Explicit non-goals**

- Do not add one Actionq action type per UI label without different execution semantics.
- Do not make the UI label the queue authority.
- Do not silently reinterpret historical rows.

**Required secondary implementation review**

A fresh Spark-class reviewer must send a fixture matrix through HTTP, MCP, cockpit normalization, owner transport, queue persistence, and coordinator routing. Every accepted path must preserve the same canonical request.

### R8 - Vuoro v1/v2 and profile compatibility duplicate internals

**Change class:** safe mechanical consolidation first; wire-version retirement is separate  
**Priority:** P2  
**Owners:** `vuoro` and `sprintctl`

**Exact evidence**

- `InvocationRequest` and `InvocationRequestV2` repeat every field except transient credentials at `vuoro/packages/vuoro-service/src/vuoro_service/contracts.py:89-118`.
- The server already funnels both endpoints into one internal dispatcher at `vuoro/packages/vuoro-service/src/vuoro_service/app.py:226-442`.
- The client duplicates catalog lookup, schema validation, request construction, stale-catalog handling, error mapping, result validation, and return logic between v1 and v2 at `vuoro/packages/vuoro-client/src/vuoro_client/client.py:177-273`.
- Sprintctl duplicates the Vuoro `Profile` shape and parser, then converts it back at `sprintctl/sprintctl/backend.py:29-42,114-183` and `sprintctl/sprintctl/served.py:33-52`.

**Current complexity**

Adding a common invocation field or changing error handling requires synchronized edits in two client branches and two Pydantic models. Profile rules are split between Agentops JSON Schema, Sprintctl's handwritten parser, and the Vuoro client dataclass.

**Simpler target**

- Define a shared internal invocation field model and derive v1/v2 request models from it.
- Implement one client `_invoke_version` path that selects endpoint/schema and conditionally adds transient credentials.
- Keep both wire endpoints until compatibility data proves v1 can sunset.
- Put profile loading/validation in `vuoro-client`; Sprintctl lazy-imports it only in served mode.
- Package the canonical profile schema with the client release or generate the loader from the released schema artifact.

**Prerequisites and dependencies**

- Tagged Vuoro client release.
- Compatibility tests for both wire versions.
- Decision on v1 support lifetime.

**Migration and compatibility risks**

- Over-aggressive model inheritance can change emitted/default fields.
- V1 must never send transient credentials.
- Local Sprintctl import must remain independent of the served extra.

**Expected benefit**

Medium. Removes duplicate protocol and profile code without changing authority.

**Explicit non-goals**

- Do not silently collapse wire v1 and v2.
- Do not move transient claim proofs into operation arguments.
- Do not make Sprintctl local mode require Vuoro dependencies.

**Required secondary implementation review**

A fresh Spark-class reviewer must compare byte-level request shapes, validation errors, stale-catalog behavior, credential redaction, optional dependency behavior, and v1/v2 result validation before and after consolidation.

### R9 - Recovery types exist on both sides without a connected product path

**Change class:** product/ownership decision, followed by mechanical deletion or adapter work  
**Priority:** P2  
**Decision owners:** `vuoro` and the eventual recovery-record domain owner

**Exact evidence**

- The client defines its own recovery record dataclass and append-only JSONL store at `vuoro/packages/vuoro-client/src/vuoro_client/recovery.py:20-144`.
- The service defines a second Pydantic recovery model and an in-memory reconciler at `vuoro/packages/vuoro-service/src/vuoro_service/recovery.py:20-199`.
- The service application exposes health, handshake, catalog, and invocation routes, but no recovery import/reconciliation route at `vuoro/packages/vuoro-service/src/vuoro_service/app.py:165-225,414-443`.
- The client CLI exposes only local begin, observe, request-command, and export operations at `vuoro/packages/vuoro-client/src/vuoro_client/cli.py:23-117`.

**Current complexity**

Two nearly equivalent record contracts can drift, while the service reconciler is in-memory and not composed into the deployed app. The client promises export for a handoff path that has no corresponding transport contract.

**Simpler target**

Choose one:

1. remove the service reconciler and keep client export explicitly external until a domain owner accepts the feature; or
2. assign the records to an owner adapter, publish one versioned schema, and expose import/status/decision through normal Vuoro catalog operations backed by durable owner storage.

The recommended default is option 1 until durable ownership exists. Vuoro should transport a domain operation, not become recovery authority.

**Prerequisites and dependencies**

- Consumer and incident-runbook inventory.
- Retention and audit decision.
- Durable owner and reconciliation state machine if option 2 is selected.

**Migration and compatibility risks**

- Operators may already rely on local recovery exports.
- Deleting local export would remove outage evidence.
- Productizing the in-memory reconciler without durable storage would create false authority.

**Expected benefit**

Medium. Removes a disconnected promise or turns it into an owned, auditable feature.

**Explicit non-goals**

- Do not remove local incident evidence without a replacement.
- Do not let Vuoro accept recovery decisions in memory.
- Do not auto-apply requested commands.

**Required secondary implementation review**

A fresh Spark-class reviewer must start from incident runbooks, trace every producer and consumer, and prove either complete removal of the unused server surface or durable end-to-end ownership. An in-memory production decision path fails review.

### R10 - Adapter pinning is generic in data but partly hard-coded in composition

**Change class:** mechanical contract cleanup; preserve explicit composition  
**Priority:** P2  
**Owner:** `vuoro`; domain owners approve adapter contract changes

**Exact evidence**

- The manifest requires the same twelve fields, including `migration_entrypoint`, for every adapter at `vuoro/packages/vuoro-service/src/vuoro_service/composition.py:37-100`.
- Wheel files are checksum-verified separately at `vuoro/packages/vuoro-service/src/vuoro_service/composition.py:109-120`.
- Runtime loading checks installed distribution version and dynamically resolves only the registration function at `vuoro/packages/vuoro-service/src/vuoro_service/composition.py:209-222`.
- Application construction, compatibility calls, and imports remain domain-specific at `vuoro/packages/vuoro-service/src/vuoro_service/composition.py:265-317`.
- Audit registration is additionally special-cased instead of using `_load_function` at `vuoro/packages/vuoro-service/src/vuoro_service/composition.py:307-317`.

**Current complexity**

The data model suggests fully generic composition, but actual construction is deliberately explicit and heterogeneous. Some pin fields are operational metadata rather than serve-time inputs. Verifying a wheel file and separately checking an installed version also creates two artifact identities to reason about.

**Simpler target**

- Keep domain application construction explicit; the differences encode ownership and credential boundaries.
- Split the release lock from the runtime adapter descriptor.
- Make the installed artifact cryptographically correspond to the locked artifact, rather than validating an adjacent wheel and an installed version independently.
- Use one small adapter registration/compatibility protocol where domains genuinely agree.
- Remove `migration_entrypoint` from the serve-time descriptor unless O1 explicitly makes Vuoro a migration orchestrator.
- Remove the audit-only registration exception or document it as an intentional contract difference.

**Prerequisites and dependencies**

- Architecture-plan O1 command-authority decision.
- Packaging/install mechanism capable of proving installed artifact identity.
- Domain-owner agreement on the minimal common adapter protocol.

**Migration and compatibility risks**

- Over-generalizing constructors can blur DSN, schema, and credential boundaries.
- Changing lock format affects release tooling and deployment packaging.

**Expected benefit**

Medium. Makes artifact and adapter contracts truthful without hiding safety-relevant differences.

**Explicit non-goals**

- Do not create a dependency-injection framework for four explicit domains.
- Do not move domain migrations into service startup.
- Do not make deployment overlays select catalog operations.

**Required secondary implementation review**

A fresh Spark-class reviewer must verify locked-to-installed artifact identity, domain registration, compatibility failure, and credential separation. The reviewer must also reject abstraction that makes migration or runtime authority ambiguous.

### R11 - Agentops validates the same contracts in several hand-maintained forms

**Change class:** mechanical consolidation after C0  
**Priority:** P2  
**Owner:** `agentops`

**Exact evidence**

- Manifest JSON Schema permits arbitrary action-class keys at `agentops/templates/dispatch/manifest.schema.json:20-34`, while cockpit validation closes them with a local set at `agentops/apps/web/lib/cockpit/dispatch-manifest.js:6-8,65-68`.
- Skill enums differ between schema and runtime at `agentops/templates/dispatch/manifest.schema.json:49-72` and `agentops/apps/web/lib/cockpit/dispatch-manifest.js:9-34`.
- Dispatch request enums and normalizers are hand-maintained in `agentops/apps/web/lib/cockpit/dispatch.js:7-20,72-129`.
- UI expectation-to-kind mapping is another projection at `agentops/apps/web/components/cockpit/dispatch-composer.js:39-49,167-178`.

**Current complexity**

JSON Schema, runtime validation, MCP schema, UI choices, and mapping functions each encode overlapping subsets. Drift is currently discovered after implementation rather than made structurally difficult.

**Simpler target**

Approve the architecture plan's separate manifest and dispatch-request contracts, then:

- consume JSON Schema directly for server-side validation where practical;
- export browser-safe enums and mappings from one generated data artifact;
- declare UI subsets as data, not duplicate validators; and
- remove handwritten enum literals outside the canonical artifact and its generated projections.

Prefer a small deterministic generator or direct schema import over a new contract framework.

**Prerequisites and dependencies**

- Complete C0 and R7's field-semantics decision.
- Decide full projection versus declared subset for UI and MCP.

**Migration and compatibility risks**

- Generated artifacts can become another source if build/check ownership is unclear.
- JSON Schema alone may not express all semantic constraints.

**Expected benefit**

Medium. Reduces contract drift and review scope across schema, runtime, MCP, and UI.

**Explicit non-goals**

- Do not force UI to expose every valid backend option.
- Do not encode execution semantics in a generic schema generator.
- Do not merge manifest and dispatch-request contracts.

**Required secondary implementation review**

Use architecture-plan C1-C3 review, with a fresh Spark-class reviewer independently extracting accepted sets and required fields from the canonical artifacts and every projection. Duplicate undeclared literal enums fail the gate.

## Boundaries that should remain separate

The following separations reduce risk and should not be refactored away:

| Boundary | Why it stays |
| --- | --- |
| Actionq action claim vs Sprintctl work claim | They protect different authorities and cannot become one transaction. |
| Queue persistence vs coordinator execution | Queue lifecycle must remain valid without importing harness, worktree, or provider behavior. |
| Vuoro client vs domain adapters | The client is transport-only and must not gain database or migration authority. |
| Runtime serve role vs migration role | Startup compatibility checks are read-only; DDL requires separate owner credentials. |
| Local Sprintctl vs served Sprintctl capability | Offline recovery and remote authorization differ intentionally. |
| Domain application constructors in Vuoro composition | Explicit differences expose DSN, schema, compatibility, and credential boundaries. |
| Cockpit presentation vs domain state machines | UI summaries are presentation; lifecycle rules and writes remain owner-mediated. |
| Verification evidence vs Markdown plans | Secrets and claim tokens stay in protected workflow records. |

## Amendments to the reworked architecture package

### Findings dossier amendments

Add three findings:

- **F9:** duplicate coordinator ownership and duplicate `actionq-daemon` entrypoints, corresponding to R1;
- **F10:** cockpit direct-schema and multi-transport coupling, corresponding to R3 and R6; and
- **F11:** migration-era Sprintctl modes lack retirement criteria, corresponding to R4 and R5.

Expand F5 to include semantic duplication among `kind`, `output_expectation`, and `action_type`, not only enum drift.

### Implementation plan amendments

- Add a coordinator-ownership decision to S0. S1 Actionq terminal fencing may proceed independently, but S2 must not add renewal to both coordinator implementations.
- Insert coordinator convergence between S1 and S2, or make it an explicit S2 prerequisite.
- Amend H1 so versioned local/served envelopes do not accidentally make `remote` a permanent third public mode.
- Amend C0 to decide field semantics and canonical request ownership, not only canonical enum artifacts.
- Default O1 to owner-CLI-only for `migrate` and `admin` unless a separate need proves Vuoro orchestration. O2 should remove unavailable parser surfaces before building an orchestration framework.
- Add a backend-mode retirement decision before P2 consumer cutover.
- Add a cutover-scaffolding disposition unit after served cutover evidence.
- Add a cockpit owner-API migration track dependent on R3/R4 contract parity.

### Operator packet amendments

- The operator must identify the active `actionq-daemon` binary, package, config, and service unit before dispatching claim-safety work.
- Secondary review packets for substrate refactors must include removed entrypoints, configs, flags, data files, and fallback paths, not only implementation diffs.
- A refactor cannot close while both old and new coordinator/network paths remain active without a dated compatibility window.

### Preflight checklist amendments

Add checks for:

- [ ] canonical coordinator package and entrypoint selected;
- [ ] installed binary provenance recorded on every execution host;
- [ ] old config/service/cron consumers inventoried;
- [ ] retained versus retired Sprintctl modes approved;
- [ ] cutover-only flags and state files assigned retention/removal dates;
- [ ] cockpit database and legacy-server fallbacks inventoried;
- [ ] request-field semantics approved before generating projections; and
- [ ] fresh Spark-class secondary implementation review covers deletion, compatibility shims, and fallback absence.

## Staged refactoring plan

### Stage 0 - Decisions and inventories

**Class:** planning only

1. Select the canonical execution coordinator and owning package.
2. Record active binaries, packages, services, configs, and state-file locations across environments.
3. Classify every Sprintctl command as local consumer, served consumer, owner-Postgres administration, migration, or retirement candidate.
4. Decide whether projection cache and recovery records are products or prototypes.
5. Approve canonical dispatch field semantics and transport ownership.
6. Bind all evidence to repository revision SHAs.

**Exit gate:** owners approve decisions and inventories; no runtime code changes.

**Secondary review:** fresh Spark-class architecture reviewer challenges omissions and verifies that every active path appears in the inventories.

### Stage 1 - Safe mechanical consolidation

**Class:** mechanical

1. Consolidate Vuoro client v1/v2 internals without changing wire shapes.
2. Move profile parsing/validation into the Vuoro client release and keep Sprintctl lazy imports.
3. Implement canonical Agentops contract artifacts and generated/direct projections after C0.
4. Remove truthful-unavailable Vuoro CLI commands or mark them owner-CLI-only after O1.
5. Add deprecation diagnostics that report the selected daemon/package and deprecated backend/server paths.

**Exit gate:** byte/fixture parity, no authority or lifecycle behavior change.

**Secondary review:** fresh Spark-class reviewer compares old/new serialized shapes, errors, optional dependency behavior, and command help.

### Stage 2 - Coordinator convergence and claim safety

**Class:** safety-critical redesign

1. Implement Actionq claim-incarnation fencing.
2. Create one coordinator kernel with capability modules for worktree/gates and generic harness/session behavior.
3. Migrate one-shot and daemon scheduling shells to that kernel.
4. Introduce the durable `ExecutionSession` and settlement recovery journal.
5. Implement renewal, cancellation, immediate authority proof, and partial-settlement recovery once.
6. Ship a bounded compatibility shim for the losing daemon entrypoint.

**Exit gate:** architecture-plan S1-S3 and R1/R2 secondary reviews pass on combined pinned revisions.

**Secondary review:** fresh Spark-class fault-history review; no self-review substitution.

### Stage 3 - Network and cockpit boundary convergence

**Class:** semantic migration

1. Fill Vuoro catalog parity required by Sprintctl and Actionq cockpit consumers.
2. Move cockpit reads and writes to owner-mediated operations.
3. Remove cockpit Actionq CLI fallback and direct Sprintctl database access.
4. Deprecate `actionq-server`.
5. Deprecate Sprintctl direct-remote consumer mode while retaining explicit owner Postgres administration.

**Exit gate:** revision-bound result parity, authorization, tenant isolation, bulk-read performance, and negative fixtures pass.

**Secondary review:** fresh Spark-class reviewer independently compares old and new transports and proves no hidden direct-database or legacy-server fallback remains.

### Stage 4 - Transitional-surface retirement

**Class:** mechanical deletion after semantic gates

1. Export and retain required pilot/cutover evidence.
2. Remove retired pilot, shadow, dual-write, cutover, and projection switches according to the Stage 0 disposition.
3. Remove the losing daemon, legacy server, deprecated backend mode, compatibility configs, service units, and docs after their windows close.
4. Remove or owner-route the disconnected recovery reconciler.
5. Simplify release lock and adapter descriptor contracts.

**Exit gate:** consumer searches, operational inventory, documentation, clean install behavior, and secondary deletion review all pass.

**Secondary review:** fresh Spark-class reviewer starts from clean environments and historical configs, proving supported paths work and removed paths fail with explicit migration guidance rather than silently selecting another authority.

## Overall conclusion

The substrate should be simplified by deleting duplicate delivery paths, not by collapsing domain authorities. The most important sequencing correction is to decide and converge the execution coordinator before implementing claim renewal in S2. The next largest reduction comes from treating direct Postgres, legacy HTTP, pilot, shadow, and cockpit database access as migration surfaces with explicit exits rather than permanent modes.

No implementation, tests, queue/sprint mutations, or deployment operations were performed during this assessment.
