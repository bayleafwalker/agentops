# Estate-wide contract rewrite: requirements and delivery map

Status: **user-requested requirements baseline, 18 October 2026**. The estate-wide destination is accepted. The later request for architectural discovery reopens the IDL/transport choice: protobuf was the provisional lead candidate. On 21 October 2026 the operator selected TypeSpec → OpenAPI / JSON Schema 2020-12 as the estate default; see the [EC-00 contract stack ADR](../../architecture/2026-10-21-ec00-contract-stack-adr.md), which also lists the EC-00 acceptance evidence still owed. See [architectural discovery](2026-10-18-estate-contract-architecture-discovery.md). This change lands plans and registered requirements, not schemas, implementations, deployments or expanded grants.

This cross-cutting programme amends the implementation dependencies of the [two-year KAOS roadmap](2026-10-18-kaos-2028-roadmap.md) and [Operator Actions plan](2026-10-18-operator-actions.md). Existing functional outcomes remain required. The JSON companion is a requirements trace, not a second live work ledger; served Sprintctl owns item status.

## Scope and completion meaning

Replace inconsistent internal machine communications with a coherent, generated, versioned contract foundation across the estate. Cover commands, queries, service/client APIs, CLI machine modes, model-facing tool schemas, MCP mappings, events/subscriptions, runtime adapters, artifact/evidence references, operational interfaces and consumer integrations. All extant interfaces receive a disposition; this is not a permanently optional pilot.

The rewrite does not require rewriting every algorithm, in-process helper or database table, nor changing vendor-owned protocols. External products, identity protocols and native runtimes retain their own APIs behind explicit adapters. Human prose/configuration and bulk data formats may remain where their role is intentional. Retained boundaries require named ownership and rationale, not a blanket legacy exemption.

Completion means: every inventoried internal interface migrated or retired; every retained external boundary explicit; temporary shims removed; all consumers qualified; historical records reconstructible; support/recovery/export handover complete. A generated client count or green endpoint smoke test is not completion.

## Goal, object and responsibility map

Programme goal **EC-G0: Maintain coherent estate-wide communication while preserving domain meaning, authority, evidence and useful work through migration.** It AND-refines into the eight subgoals below and contributes to the original G01–G12 goals through the requirement trace.

| Subgoal | KAOS concern | Requirements |
|---|---|---|
| EC-G1 Complete coverage and accountable ownership | Avoid orphan/parallel interfaces | ER-001–004, ER-040, ER-046 |
| EC-G2 Correct typed meaning and evolution | Maintain semantics across versions/languages | ER-005–009, ER-017 |
| EC-G3 Reliable interaction | Achieve progress without duplicate effects | ER-010–016, ER-026–027 |
| EC-G4 Protected authority and evidence | Avoid unauthorized effects or false evidence | ER-018–024, ER-042 |
| EC-G5 Useful cross-runtime/domain experience | Achieve operator and domain outcomes | ER-025, ER-028–030, ER-035–039 |
| EC-G6 Operable heterogeneous estate | Maintain recovery and deployment fit | ER-031–034, ER-045, ER-047 |
| EC-G7 Safe cutover and retirement | Achieve one authority and removable legacy | ER-041, ER-046 |
| EC-G8 Demonstrated value | Improve usefulness and maintenance burden | ER-043–044, ER-048 |

Objects: ContractPackage has one semantic owner, version and generated artifacts; InterfaceBinding connects package operations to producer/consumer/runtime and transport; Operation carries typed request/result/error, revision and idempotency semantics; Event carries identity, scope and replay position; EvidenceReference binds original artifact/record/provenance; MigrationUnit names old/new binding, authoritative writer, consumers, reconciliation, rollback and retirement proof. OperatorRequest retains the separately specified OA lifecycle. Neither an envelope field nor an interface declaration creates authority.

Responsible agents: domain owners implement meaning; Agentops owns cross-estate inventory/generation guidance and migration trace; Vuoro owns portable contract/composition decisions; native runtime adapters publish and continue work; protected identity/effect owners authorize operations; Cloud composes hosting and UI; platform/host owners qualify deployment; acceptance-lab qualifies the estate; the operator decides only matters actually reserved under existing policy.

Illustrative invariants, inherited by every candidate:

- Always: applying an effect requires current protected authority bound to the exact operation/artifact, independent of transport or claimed principal fields.
- Always: an uncertain effect is reconciled before retry; cancellation or timeout does not imply rollback.
- Always: one migration unit has one authoritative writer at a time; shadow reads and derived projections are not competing writers.
- Always: a source revision, signed artifact or historical observation retains its original identity and meaning through decoding/migration.
- Always: default/unknown/unavailable state is not silently converted to success, absence or consent.
- Eventually, subject to declared availability: accepted work produces a result, explicit blocker or cancellation; delivery failure is visible and recoverable.

## Interface inventory and disposition contract

EC-01 records for each boundary: stable ID; owning repo/domain; source revision and live observation separately; producer/consumer and supported language/version; commands/events/schema/transport; authentication and protected target; authority/persistence home; data class and retention; operation/retry/delivery semantics; traffic/use evidence and unknowns; required outcome; replace/adapt/retain-external/retire decision; target package and generated projection; compatibility window; implementation item; reconciliation/cutover/rollback; shim expiry/removal evidence.

The owner map below is a **seed inventory**, not an assertion that every method or live consumer has already been discovered. EC-01 must reconcile source discovery against configured and observed use. Missing observations remain unknown. Smaller projects cannot disappear from coverage because they lack an existing tracker binding; EC-19 must commission their owner tasks before cutover.

| Estate boundary | Seed owner(s) | Intended disposition |
|---|---|---|
| Work/release/attempt, snapshots, request/continuation | Sprintctl reference provider; Vuoro contract owner | Replace internal machine interfaces; preserve settlement and provider replaceability |
| Service/client/schema-runtime/adapter-kit composition | Vuoro | Replace competing schema/client paths with selected canonical generation |
| Context, knowledge, artifacts and accepted-outcome learning | Vuoro and existing source owners | Replace internal contracts; preserve source/permission and domain ownership |
| Authority, identity/delegation and protected effects | cred-broker and target owners | Adapt internal interfaces; retain native identity/protected policy authorities |
| Audit, evidence, ingestion and reconstruction | Auditctl and accepted evidence-home owners | Replace transport, preserve original records and authoritative-home migration gates |
| CLI/MCP/runtime/session tooling | Agentops with native providers | Generate readable internal tools; retain vendor protocols at qualified adapters |
| Operator TUI/web and hosted edge | Vuoro Cloud | Replace internal clients/edge mappings; preserve request lifecycle and tenancy |
| Deployment, identity composition, telemetry and restore | Appservice | Adapt operational bindings; retain native infrastructure/vendor protocols |
| Workstation packaging and local integrations | gitops-nixos | Package selected contracts/clients/toolchains reproducibly |
| Compute/capacity/cost, model/runtime metadata | Datacluster and local-inference | Adapt observations and integration; retain native inference/compute APIs |
| Household, creative, physical/cooperative, research | homelab-analytics, scribectl, frontier-weave, aligned-equity | Migrate consumer contracts while preserving domain decisions |
| Browser/native bridge | browser-workbench | Migrate discovered Python/TS/Rust bindings, qualify browser limitations |
| Conformance and regression campaigns | acceptance-lab | Replace fixtures/clients without losing historical or negative-case evidence |
| Bindery and all smaller tools/plugins/scripts | Owner discovered through EC-01; EC-19 accountable | Explicit migration or retirement; no implicit exemption |
| Historical ActionQ/cockpit/Outctl/Kctl residue | Existing disposition owners | Reconcile and retire/adapt required surviving boundaries; never revive retired runtimes |

## Requirement trace

All ER requirements are mandatory at their applicable boundaries. Each has an accountable owner, implementation/qualification package and observable acceptance condition. Transport-specific realizations are conditional on EC-00; none may weaken domain semantics. The mapping is semi-formal requirements engineering, not a formal proof.

### ER-001 — scope

**Requirement:** Every internal machine interface has a unique inventory entry and explicit disposition.

**Trace:** G12 / F13; owner `agentops`; delivery EC-01 (agentops#2733), EC-21 (agentops#2754).

**Acceptance:** Reconcile repository discovery, configured deployments and observed consumers; unresolved/unknown entries prevent programme completion.

### ER-002 — scope

**Requirement:** Select one estate-wide canonical contract-authoring convention, with one source per domain package, after architecture qualification.

**Trace:** G12 / F13; owner `vuoro`; delivery EC-00 (vuoro#2734), EC-02 (vuoro#2735).

**Acceptance:** ADR compares shortlist on mandatory cases; no independently edited generated schemas; selected versions and exclusions are explicit.

### ER-003 — ownership

**Requirement:** Package and service boundaries follow domain state and authority ownership.

**Trace:** G12 / F13; owner `vuoro`; delivery EC-02 (vuoro#2735), EC-04 (vuoro#2737).

**Acceptance:** Ownership/import graph is acyclic; work, evidence, authority and UI responsibilities remain distinct; no generic execute(type,payload) authority bypass.

### ER-004 — identity

**Requirement:** Work, request, attempt, artifact, event and provider-reference identities remain stable and separately typed.

**Trace:** G04 / F04; owner `vuoro`; delivery EC-02 (vuoro#2735), EC-05 (sprintctl#2738).

**Acceptance:** A cross-provider continuation retains work identity while changing attempt; tenant/repository collisions and wrong-kind IDs are rejected.

### ER-005 — typing

**Requirement:** Missing, zero, empty, unknown, denied and unavailable retain distinct semantics across projections.

**Trace:** G07 / F07; owner `vuoro`; delivery EC-02 (vuoro#2735), EC-03 (agentops#2736).

**Acceptance:** Cross-language and JSON/binary tests exercise defaults, presence, unknown enums/fields, oneof/unions, nullability, integers beyond JS safe range, decimals, timestamps and bytes.

### ER-006 — validation

**Requirement:** Business constraints and operation preconditions are enforced by owners beyond generated type checks.

**Trace:** G07 / F07; owner `vuoro`; delivery EC-02 (vuoro#2735), EC-04 (vuoro#2737).

**Acceptance:** Well-typed invalid scope/range/state transitions fail; generated validators match server behavior and errors do not leak secrets.

### ER-007 — evolution

**Requirement:** Compatibility covers source clients, wire data, readable/tool projections and business behavior.

**Trace:** G12 / F13; owner `agentops`; delivery EC-03 (agentops#2736), EC-20 (acceptance-lab#2753).

**Acceptance:** Supported N/N-1 matrix is declared and passes; incompatible changes require a new version and rollout; removed field identities are never reused where applicable.

### ER-008 — generation

**Requirement:** Compilers, plugins, descriptors and packages are pinned, reproducible and independently verifiable.

**Trace:** G12 / F13; owner `agentops`; delivery EC-03 (agentops#2736), EC-11 (gitops-nixos#2744).

**Acceptance:** Clean builds regenerate byte-identical generated artifacts under declared environment; tampered plugin/artifact fails; clients install offline from retained artifacts.

### ER-009 — generation

**Requirement:** CLI/MCP and model-facing schemas derive from canonical contracts while staying readable and bounded.

**Trace:** G12 / F13; owner `agentops`; delivery EC-03 (agentops#2736), EC-09 (agentops#2742).

**Acceptance:** Same valid/invalid fixtures pass/fail across surfaces; unsupported schema constructs fail generation explicitly; no handwritten semantic shadow interface.

### ER-010 — transport

**Requirement:** Transport selection meets native, browser, proxy and local connection requirements without separate semantics.

**Trace:** G12 / F13; owner `vuoro`; delivery EC-00 (vuoro#2734), EC-04 (vuoro#2737), EC-08 (vuoro-cloud#2741).

**Acceptance:** Representative requests/events traverse actual supported ingress patterns; HTTP/JSON/gRPC/Connect alternatives are qualified only where selected.

### ER-011 — queries

**Requirement:** Queries define pagination, consistency, freshness and permission-scoped snapshots.

**Trace:** G02 / F02; owner `sprintctl`; delivery EC-05 (sprintctl#2738).

**Acceptance:** Concurrent mutation, expired cursor, revoked access and unavailable source produce explicit outcomes; no cross-tenant cursor leakage.

### ER-012 — errors

**Requirement:** Errors distinguish validation, stale revision, denial, unsupported capability, outage, limit and unknown effect.

**Trace:** G12 / F13; owner `vuoro`; delivery EC-02 (vuoro#2735), EC-04 (vuoro#2737).

**Acceptance:** Clients map typed errors consistently; transient failure is not absence; retry guidance never blindly repeats an uncertain effect.

### ER-013 — commands

**Requirement:** Mutations use expected revisions and scoped idempotency with declared retention.

**Trace:** G04 / F04; owner `sprintctl`; delivery EC-05 (sprintctl#2738).

**Acceptance:** Concurrent writers conflict; retry of identical operation returns original result; reused key with different payload fails; expired-key handling is explicit.

### ER-014 — delivery

**Requirement:** Events have stable IDs, ordering scope, cursors, deduplication and replay/reset semantics.

**Trace:** G04 / F04; owner `vuoro`; delivery EC-04 (vuoro#2737), EC-05 (sprintctl#2738), EC-09 (agentops#2742).

**Acceptance:** Disconnect/restart/duplicate/out-of-order/compacted cursor tests pass; resume cannot silently skip events; event delivery is not exactly-once effect execution.

### ER-015 — resilience

**Requirement:** Deadlines, cancellation and retries are explicit per operation.

**Trace:** G09 / F09; owner `vuoro`; delivery EC-04 (vuoro#2737), EC-10 (appservice#2743).

**Acceptance:** Timeout after commit yields reconcilable unknown effect; cancellation is not assumed rollback; non-idempotent effects are not automatically retried or hedged.

### ER-016 — limits

**Requirement:** Bound payloads, queues, concurrency, streams and resource consumption with backpressure.

**Trace:** G08 / F08; owner `appservice`; delivery EC-04 (vuoro#2737), EC-10 (appservice#2743), EC-20 (acceptance-lab#2753).

**Acceptance:** Slow client, oversized message, decompression expansion and overload tests remain bounded; recovery does not cause retry storms.

### ER-017 — capabilities

**Requirement:** Clients negotiate capabilities and supported contract versions without treating advertising as authority.

**Trace:** G12 / F13; owner `vuoro`; delivery EC-04 (vuoro#2737), EC-09 (agentops#2742).

**Acceptance:** Unsupported wake/stream/tool modes fail visibly; old clients cannot interpret unknown success states or gain scope through negotiation.

### ER-018 — security

**Requirement:** Authenticated transport identity is bound to actual principal, audience, workspace, resource and action.

**Trace:** G06 / F06; owner `cred-broker`; delivery EC-06 (cred-broker#2739), EC-08 (vuoro-cloud#2741).

**Acceptance:** Spoofed identity fields/forwarded headers, wrong audience and cross-tenant requests are denied by the owner; payload identity creates no grant.

### ER-019 — security

**Requirement:** Delegation, revocation and exact-operation acceptance survive the interface migration.

**Trace:** G06 / F06; owner `cred-broker`; delivery EC-06 (cred-broker#2739).

**Acceptance:** Expired/revoked/wrong-target/replayed grants fail; altered artifact or procedure cannot reuse acceptance; authority checks occur at the protected boundary.

### ER-020 — security

**Requirement:** Public coordination never gains a new push path into the protected horizon.

**Trace:** G06 / F06; owner `vuoro-cloud`; delivery EC-08 (vuoro-cloud#2741), EC-10 (appservice#2743).

**Acceptance:** Topology and negative tests prove protected consumers pull under local authority; generated clients cannot bypass existing custody/egress boundaries.

### ER-021 — privacy

**Requirement:** Logs, messages, diagnostics and exports enforce redaction, retention and owner entitlements.

**Trace:** G10 / F10; owner `vuoro-cloud`; delivery EC-07 (auditctl#2740), EC-08 (vuoro-cloud#2741), EC-10 (appservice#2743).

**Acceptance:** Secret fixtures and unauthorized workspace records are absent from tool/UI/trace outputs; deleted/revoked data behavior is specified and verified.

### ER-022 — evidence

**Requirement:** Signed or hashed meaning uses a versioned domain-specific representation, not generic serialization determinism.

**Trace:** G07 / F07; owner `auditctl`; delivery EC-02 (vuoro#2735), EC-07 (auditctl#2740).

**Acceptance:** Cross-language golden vectors cover map order, unknown fields, numeric edge cases and schema changes; altered meaning invalidates binding; original signed bytes remain retained.

### ER-023 — evidence

**Requirement:** Historical evidence identity, provenance and authoritative home remain intact.

**Trace:** G07 / F07; owner `auditctl`; delivery EC-07 (auditctl#2740).

**Acceptance:** Old records decode using retained schemas, retain original bytes/digests, and link to transformed views; reconciliation never restamps historical observations.

### ER-024 — artifacts

**Requirement:** Bulk artifacts use authorized immutable references, integrity checks and bounded transfer contracts.

**Trace:** G03 / F03; owner `vuoro`; delivery EC-04 (vuoro#2737), EC-07 (auditctl#2740), EC-12 (datacluster#2745).

**Acceptance:** Expired/unauthorized references fail; corruption is detected; large files are not forced into oversized control messages; portable export reconstructs references.

### ER-025 — operator

**Requirement:** The OA-01–OA-06 operator-action lifecycle is the first complete consumer of the selected foundation.

**Trace:** G12 / F12; owner `vuoro`; delivery EC-02 (vuoro#2735), EC-05 (sprintctl#2738), EC-08 (vuoro-cloud#2741).

**Acceptance:** Both runtimes publish current procedures; dead/shared/stale/partial requests and verification/attestation cases pass; TUI works without reopening chat.

### ER-026 — continuation

**Requirement:** Resolution continues only affected work through supported native runtime mechanisms.

**Trace:** G04 / F04; owner `agentops`; delivery EC-05 (sprintctl#2738), EC-09 (agentops#2742).

**Acceptance:** Duplicate delivery does not repeat operations; successor uses exact evidence; unsupported wake shows continuation-ready; no new estate scheduler.

### ER-027 — work

**Requirement:** Reference work-provider settlement and cross-project links retain semantics.

**Trace:** G01 / F01; owner `sprintctl`; delivery EC-05 (sprintctl#2738).

**Acceptance:** Reservations, releases, CAS and terminal decisions pass existing and new conformance; source receipt/completion event never substitutes for acceptance.

### ER-028 — context

**Requirement:** Context, knowledge, source corrections and permissions use versioned typed references.

**Trace:** G03 / F03; owner `vuoro`; delivery EC-04 (vuoro#2737).

**Acceptance:** Correction invalidates affected conclusions only; source/permission changes are visible; model confidence is not context authority.

### ER-029 — learning

**Requirement:** Outcome comparisons preserve cost, attention, denominator, uncertainty and revision provenance.

**Trace:** G11 / F11; owner `vuoro`; delivery EC-04 (vuoro#2737), EC-07 (auditctl#2740), EC-20 (acceptance-lab#2753).

**Acceptance:** Missing observations remain unknown; comparable cohorts reconstruct accepted outcomes; no model router or compiled agent profile is recreated.

### ER-030 — hosting

**Requirement:** Browser/TUI and hosted services use shared contracts with explicit tenancy and supported transport modes.

**Trace:** G12 / F13; owner `vuoro-cloud`; delivery EC-08 (vuoro-cloud#2741), EC-10 (appservice#2743).

**Acceptance:** Wrong tenant, browser reconnect, proxy buffering and authentication expiry tests pass; UI state cannot settle protected work.

### ER-031 — platform

**Requirement:** Deployment, discovery, ingress, health, telemetry and restore support mixed-version migration.

**Trace:** G09 / F09; owner `appservice`; delivery EC-10 (appservice#2743).

**Acceptance:** Disposable rollout/drain/rollback and whole-application restore prove configured RPO/RTO and retained decoding assets before live promotion.

### ER-032 — hosts

**Requirement:** Host packages reproduce supported compiler/client/runtime and local integration configurations.

**Trace:** G09 / F09; owner `gitops-nixos`; delivery EC-11 (gitops-nixos#2744).

**Acceptance:** Clean rebuild and offline recovery pass; supported versions are explicit; no hidden developer workstation dependency remains.

### ER-033 — compute

**Requirement:** Compute/capacity/cost observations map through typed adapters while providers retain native APIs.

**Trace:** G05 / F05; owner `datacluster`; delivery EC-12 (datacluster#2745).

**Acceptance:** Scope/region/retention, missing utilization and teardown results remain explicit; provisioning observation does not imply resource ownership or permission.

### ER-034 — inference

**Requirement:** Local inference boundaries preserve qualified arrangement metadata and privacy constraints.

**Trace:** G05 / F05; owner `local-inference`; delivery EC-13 (local-inference#2746).

**Acceptance:** Refused local-only data never falls through to cloud; engine/parser/model revisions, context/concurrency and fallback remain measurable.

### ER-035 — household

**Requirement:** Household commitment/publication/outcome interfaces preserve domain meaning.

**Trace:** G01 / F14; owner `homelab-analytics`; delivery EC-14 (homelab-analytics#2747).

**Acceptance:** Corrected source windows supersede appropriate evidence; estimates differ from measured effects; human acceptance and raw-data locality remain intact.

### ER-036 — writing

**Requirement:** Creative workspace integration preserves source revisions and human canon ratification.

**Trace:** G01 / F14; owner `scribectl`; delivery EC-15 (scribectl#2748).

**Acceptance:** Generated client can resume/export/correct work without silent canon promotion; original artifacts and acceptance remain reconstructible.

### ER-037 — physical

**Requirement:** Physical/cooperative outcomes retain explicit attestation and uncertainty.

**Trace:** G01 / F14; owner `frontier-weave`; delivery EC-16 (frontier-weave#2749).

**Acceptance:** Human-performed steps, unknown physical state and accepted evidence are distinguishable across restart and export.

### ER-038 — research

**Requirement:** Research evidence/decision boundaries retain assumptions and source provenance.

**Trace:** G01 / F14; owner `aligned-equity`; delivery EC-17 (aligned-equity#2750).

**Acceptance:** Correction, source version, missing data and accepted decision survive migration and export without converting hypotheses into facts.

### ER-039 — browser

**Requirement:** Browser/local bridge adapters preserve native execution and qualified language interoperability.

**Trace:** G12 / F13; owner `browser-workbench`; delivery EC-18 (browser-workbench#2751).

**Acceptance:** Actual Python/TS/Rust surfaces discovered are exercised with cancellation, auth loss, streaming limits and exact result links.

### ER-040 — coverage

**Requirement:** Smaller tools, plugins, batch jobs and scripts receive explicit owner migration or retirement decisions.

**Trace:** G12 / F13; owner `agentops`; delivery EC-01 (agentops#2733), EC-19 (agentops#2752), EC-21 (agentops#2754).

**Acceptance:** Bindery and every inventory-discovered consumer have owner tasks before cutover; zero unexplained legacy callers after a declared observation window.

### ER-041 — migration

**Requirement:** Each cutover has one authoritative writer, data reconciliation, consumer switch, rollback and adapter expiry.

**Trace:** G09 / F09; owner `agentops`; delivery EC-01 (agentops#2733), EC-04 (vuoro#2737), EC-20 (acceptance-lab#2753), EC-21 (agentops#2754).

**Acceptance:** Fault injection during each stage does not create competing authorities; rollback handles new records and unsupported old clients; no indefinite shim.

### ER-042 — storage

**Requirement:** Transport changes do not silently change persistence contracts or erase retention obligations.

**Trace:** G09 / F09; owner `auditctl`; delivery EC-07 (auditctl#2740), EC-10 (appservice#2743).

**Acceptance:** Storage migration is separately justified and tested; backups retain schemas/keys by existing policy; restored historical records retain meaning.

### ER-043 — quality

**Requirement:** Performance and reliability claims use representative predeclared workloads and baselines.

**Trace:** G07 / F07; owner `acceptance-lab`; delivery EC-00 (vuoro#2734), EC-20 (acceptance-lab#2753).

**Acceptance:** Report p50/p95 latency, CPU/RSS, payload size, reconnect/load behavior, generation/build time, maintenance effort and sample size; no fabricated speedup.

### ER-044 — quality

**Requirement:** Conformance spans languages, versions, transports, domain behavior and injected faults.

**Trace:** G07 / F07; owner `acceptance-lab`; delivery EC-20 (acceptance-lab#2753).

**Acceptance:** Supported matrix passes all mandatory negatives; a deliberately broken schema/authority/replay case fails the gate; real supplier swap and recovery are demonstrated.

### ER-045 — operations

**Requirement:** Humans can inspect typed traffic and reconstruct failures without exposing private payloads.

**Trace:** G12 / F13; owner `agentops`; delivery EC-03 (agentops#2736), EC-09 (agentops#2742), EC-20 (acceptance-lab#2753).

**Acceptance:** Readable redacted CLI views and trace IDs reconstruct requests/results/evidence; debug replay is isolated and cannot execute live effects.

### ER-046 — closure

**Requirement:** Rewrite completion requires removal of superseded internal paths and explicit retained external boundaries.

**Trace:** G12 / F13; owner `agentops`; delivery EC-21 (agentops#2754).

**Acceptance:** Inventory has no unresolved entries; removal PRs, consumer evidence, release/deployment observations and support/rollback/export handover are linked.

### ER-047 — supply

**Requirement:** Selected dependencies have viable licensing, maintenance, offline builds and upgrade/security response.

**Trace:** G10 / F10; owner `agentops`; delivery EC-00 (vuoro#2734), EC-03 (agentops#2736), EC-11 (gitops-nixos#2744).

**Acceptance:** Document version/runtime support and provenance; pin artifacts; rehearse upgrade/rollback; no required paid registry or hosted code generator without explicit sourcing decision.

### ER-048 — economics

**Requirement:** Estate rewrite remains accountable to useful outcomes and maintenance/attention burden.

**Trace:** G01 / F01; owner `agentops`; delivery EC-00 (vuoro#2734), EC-20 (acceptance-lab#2753), EC-21 (agentops#2754).

**Acceptance:** Measure workflow success, repeated prompts, stale requests, cost per accepted cohort and interface maintenance before/after; inconclusive evidence stays inconclusive.

## Delivery packages and dependency gates

Each package must inspect current source and observations, specify owner interfaces, implement/onboard, qualify normal and negative cases, perform only authorized rollout, observe outcomes, then remove superseded paths and document support/rollback/export. Detailed acceptance is the conjunction of its linked ER requirements, not merely producing code.

### EC-01 — Inventory every estate interface and assign migration disposition

**Owner/item:** `agentops` / **agentops#2733**. **Prerequisites:** current-state discovery.

Build producer/consumer/version/authority inventory from source plus owner observations; include internal APIs, CLI machine modes, MCP mappings, events, artifacts, plugins and scripts. Record replace/adapt/retain-external/retire per boundary; unknown consumers block retirement. Reconcile smaller projects and generated guidance.

**Acceptance requirements:** ER-001, ER-040, ER-041.

### EC-00 — Qualify architecture alternatives and record the stack decision

**Owner/item:** `vuoro` / **vuoro#2734**. **Prerequisites:** EC-01 (agentops#2733).

Use the landed architectural discovery to compare protobuf plus gRPC/Connect against TypeSpec/OpenAPI and scoped alternatives on identical operator-action cases. Record actual language/runtime/browser/proxy behavior, failure semantics, tooling burden and benchmarks. Select IDL, transports, versions and exception rules through an ADR before foundation implementation; estate-wide rewrite remains committed.

**Acceptance requirements:** ER-002, ER-010, ER-043, ER-047, ER-048.

### EC-02 — Define canonical domain contract foundation and package ownership

**Owner/item:** `vuoro` / **vuoro#2735**. **Prerequisites:** EC-00 (vuoro#2734).

Implement selected IDL package boundaries, identifiers, commands/queries/events, validation, compatibility policy, authority metadata, semantic hashing and domain ownership. Settle operator-request ownership with OA-01. No generic execute-payload escape or new universal runtime.

**Acceptance requirements:** ER-002, ER-003, ER-004, ER-005, ER-006, ER-012, ER-022, ER-025.

### EC-03 — Build reproducible contract generation and conformance toolchain

**Owner/item:** `agentops` / **agentops#2736**. **Prerequisites:** EC-02 (vuoro#2735).

Generate typed clients, validators, readable CLI/MCP schemas, fixtures and docs from one source; pin compiler/plugins/runtime matrix; test deterministic regeneration and lossy projections; package versioned artifacts for Python/TypeScript and discovered Go/Rust consumers.

**Acceptance requirements:** ER-005, ER-007, ER-008, ER-009, ER-045, ER-047.

### EC-04 — Migrate service composition and client transport contracts

**Owner/item:** `vuoro` / **vuoro#2737**. **Prerequisites:** EC-03 (agentops#2736).

Replace internal service/client/adapter-kit/schema-runtime interfaces with selected contracts; preserve compatibility discovery, context/knowledge, artifacts, effect and learning semantics. Qualify streaming, errors, pagination, overload, resumable reads and capability negotiation.

**Acceptance requirements:** ER-003, ER-006, ER-010, ER-012, ER-014, ER-015, ER-016, ER-017, ER-024, ER-028, ER-029, ER-041.

### EC-05 — Migrate work, request, release and continuation provider boundary

**Owner/item:** `sprintctl` / **sprintctl#2738**. **Prerequisites:** EC-04 (vuoro#2737).

Map reference work provider operations and durable identifiers; preserve CAS, reservations, terminal decisions, snapshots and cross-project dependencies. Implement operator request/continuation requirements with OA-01/OA-04 under settled ownership; qualify alternative provider conformance.

**Acceptance requirements:** ER-004, ER-011, ER-013, ER-014, ER-025, ER-026, ER-027.

### EC-06 — Migrate identity delegation and protected-operation interfaces

**Owner/item:** `cred-broker` / **cred-broker#2739**. **Prerequisites:** EC-03 (agentops#2736).

Adapt broker identity/session/capability APIs and protected consumers while retaining existing authentication, custody and policy owners. Verify spoofing, audience/resource scope, revocation, replay, unknown fields and exact-operation binding; no automatic grant widening.

**Acceptance requirements:** ER-018, ER-019.

### EC-07 — Migrate evidence ingestion and reconstruction interfaces

**Owner/item:** `auditctl` / **auditctl#2740**. **Prerequisites:** EC-03 (agentops#2736).

Replace publisher/ingest/query boundaries while preserving original event IDs, bytes, provenance, observation-vs-decision semantics and S4 authoritative home. Introduce versioned decoding and semantic signature/digest test vectors; no historical evidence restamping.

**Acceptance requirements:** ER-021, ER-022, ER-023, ER-024, ER-029, ER-042.

### EC-08 — Migrate hosted edge and prove operator-action vertical workflow

**Owner/item:** `vuoro-cloud` / **vuoro-cloud#2741**. **Prerequisites:** EC-04 (vuoro#2737), EC-05 (sprintctl#2738), EC-06 (cred-broker#2739), EC-07 (auditctl#2740), EC-09 (agentops#2742).

Implement chosen browser/HTTP/RPC edge and adapters, tenant isolation and generated UI clients; compose OA-01 through OA-06 as first end-to-end consumer. Preserve protected-side pull topology and distinct hosting/effect grants; verify actual proxy and browser paths.

**Acceptance requirements:** ER-010, ER-018, ER-020, ER-021, ER-025, ER-030.

### EC-09 — Migrate native runtime integrations and generated agent tools

**Owner/item:** `agentops` / **agentops#2742**. **Prerequisites:** EC-04 (vuoro#2737).

Replace Claude/Codex/local-native integration plumbing using generated readable tools; map provider work/session handles without pretending all providers support wake, cancel, tools or events. Qualify lost delivery, dead sessions and successor continuation; retain external native protocols at adapters.

**Acceptance requirements:** ER-009, ER-014, ER-017, ER-026, ER-045.

### EC-10 — Qualify deployment networking telemetry and disaster recovery

**Owner/item:** `appservice` / **appservice#2743**. **Prerequisites:** EC-08 (vuoro-cloud#2741).

Update service discovery, ingress/proxy/timeouts, identity, observability, deployment compatibility and backup/restore composition; test network faults and outage recovery using disposable environments before any separately authorized live rollout.

**Acceptance requirements:** ER-015, ER-016, ER-020, ER-021, ER-030, ER-031, ER-042.

### EC-11 — Package generated SDK toolchains and workstation integrations

**Owner/item:** `gitops-nixos` / **gitops-nixos#2744**. **Prerequisites:** EC-03 (agentops#2736).

Pin compiler/plugins/client runtimes in reproducible host packaging; exercise rebuild/offline restore, certificate/config discovery and user terminal integrations. Avoid a mandatory extra runtime or language without measured justification.

**Acceptance requirements:** ER-008, ER-032, ER-047.

### EC-12 — Migrate compute-provider and capacity observation interfaces

**Owner/item:** `datacluster` / **datacluster#2745**. **Prerequisites:** EC-04 (vuoro#2737).

Adapt resource discovery, provisioned compute handles, cost/usage and teardown observations through typed contracts; preserve missingness, provider-native APIs and region/retention boundaries. Bulk data remains in suitable referenced artifact formats.

**Acceptance requirements:** ER-024, ER-033.

### EC-13 — Migrate inference integration and local resource metadata

**Owner/item:** `local-inference` / **local-inference#2746**. **Prerequisites:** EC-11 (gitops-nixos#2744), EC-12 (datacluster#2745).

Adapt local model/harness/tool/environment metadata and native client integration; retain external inference protocol; verify context/privacy refusal, interruption, contention and rollback without introducing central model routing.

**Acceptance requirements:** ER-034.

### EC-14 — Migrate household publication and outcome integration

**Owner/item:** `homelab-analytics` / **homelab-analytics#2747**. **Prerequisites:** EC-05 (sprintctl#2738), EC-07 (auditctl#2740), EC-09 (agentops#2742).

Use generated contracts for commitment/publication/outcome references and freshness corrections; preserve household authority, evidence windows, human decisions and raw-data locality. Validate representative actual consumer workflows and export.

**Acceptance requirements:** ER-035.

### EC-15 — Migrate writing context and ratified outcome integration

**Owner/item:** `scribectl` / **scribectl#2748**. **Prerequisites:** EC-05 (sprintctl#2738), EC-07 (auditctl#2740), EC-09 (agentops#2742).

Replace machine boundaries for context/artifact/work/outcome links while preserving human creative ratification and source revisions; prove interruption, correction, export and no automatic canon promotion.

**Acceptance requirements:** ER-036.

### EC-16 — Migrate physical and cooperative project integrations

**Owner/item:** `frontier-weave` / **frontier-weave#2749**. **Prerequisites:** EC-05 (sprintctl#2738), EC-07 (auditctl#2740), EC-09 (agentops#2742).

Map project evidence, work and physical/human attestation boundaries; preserve domain-specific authority and uncertain physical outcomes; prove supported workflows and failure recovery with generated clients.

**Acceptance requirements:** ER-037.

### EC-17 — Migrate research evidence and decision integrations

**Owner/item:** `aligned-equity` / **aligned-equity#2750**. **Prerequisites:** EC-05 (sprintctl#2738), EC-07 (auditctl#2740), EC-09 (agentops#2742).

Map research sources, assumptions, provenance, evidence and accepted decisions without converting estimates into facts; preserve corpus revisions and export; qualify old/new client behavior and useful domain outcomes.

**Acceptance requirements:** ER-038.

### EC-18 — Migrate browser workspace and runtime adapter boundaries

**Owner/item:** `browser-workbench` / **browser-workbench#2751**. **Prerequisites:** EC-05 (sprintctl#2738), EC-07 (auditctl#2740), EC-09 (agentops#2742).

Generate supported browser and local bridge interfaces; qualify Python/TypeScript/Rust boundaries actually present, browser streaming restrictions, identity, cancellation and result links; retain browser/runtime-owned execution.

**Acceptance requirements:** ER-039.

### EC-19 — Reconcile remaining consumers and retire obsolete integration surfaces

**Owner/item:** `agentops` / **agentops#2752**. **Prerequisites:** EC-04 (vuoro#2737), EC-05 (sprintctl#2738), EC-07 (auditctl#2740).

Account for Bindery and every smaller tool/plugin/script found by EC-01, including historical kctl/actionq/outctl surfaces. Assign owner-specific implementation tasks before cutover; prove replace/adapt/external-retain/retire disposition. Retired components are not rebuilt merely because old schemas exist.

**Acceptance requirements:** ER-040.

### EC-20 — Run estate conformance recovery and supplier replacement campaign

**Owner/item:** `acceptance-lab` / **acceptance-lab#2753**. **Prerequisites:** EC-08 (vuoro-cloud#2741), EC-10 (appservice#2743), EC-11 (gitops-nixos#2744), EC-12 (datacluster#2745), EC-13 (local-inference#2746), EC-14 (homelab-analytics#2747), EC-15 (scribectl#2748), EC-16 (frontier-weave#2749), EC-17 (aligned-equity#2750), EC-18 (browser-workbench#2751), EC-19 (agentops#2752).

Run mixed-version/language/transport matrices and negative cases, operator overnight scenario, domain outcomes, whole-system recovery and actual provider swap. Measure bounded performance, maintenance and attention against baseline; no throughput benefit inferred from encoding.

**Acceptance requirements:** ER-007, ER-016, ER-029, ER-041, ER-043, ER-044, ER-045, ER-048.

### EC-21 — Close migration and delete superseded internal interfaces

**Owner/item:** `agentops` / **agentops#2754**. **Prerequisites:** EC-20 (acceptance-lab#2753).

Verify every inventoried boundary reaches target or an explicit retained external exception; remove temporary shims, duplicate schemas/endpoints/clients/configuration/docs, prove no hidden consumers, retain evidence/history and recovery assets. Record removal PRs and source/released/deployed/qualified distinctions.

**Acceptance requirements:** ER-001, ER-040, ER-041, ER-046, ER-048.

Cross-project dependencies are explicit documentary gates because the current tracker scope guard cannot enforce them. Same-owner edges are registered where supported. Existing active items and reservations are not reset. EC-20 additionally requires the OA-06 real operator pilot and AO-K02 measurement baseline. These are evidence gates, not dates or staffing promises.

## Backcast and cutover sequence

1. **Coverage and selection:** EC-01 inventory feeds EC-00 executable architecture qualification. Final ADR names canonical source, versions, boundary transports and retained exceptions.
2. **Foundation:** EC-02/03 establish semantics, ownership, generation, packages and rejecting conformance gates. Owner migration discovery may proceed in parallel; implementation binds to qualified decisions.
3. **First complete consumer:** EC-04–09 compose existing OA-01–06 work into a real operator-action workflow. Preserve readable model tools, exact authority and native continuation. Do not build an unrelated legacy inbox first.
4. **Estate migration:** EC-10–19 qualify host/platform/compute and every domain consumer, with bounded rollout and per-unit rollback. A failed unit blocks its dependants, not unrelated discovery.
5. **Proof and removal:** EC-20 demonstrates mixed-version/language/fault behavior, provider replacement and useful outcomes; EC-21 removes superseded internal paths and closes every inventory disposition.

Per migration unit: capture baseline and fixtures; release compatible reader/decoder and generated client artifacts; shadow only non-authoritative reads/projections; reconcile data with source IDs and counts; fence/drain the old writer and establish the new authoritative path; switch consumers with declared version policy; observe outcomes and unexpected callers; execute rollback or accept; remove adapters/endpoints/schemas/configuration after evidence-backed retirement. The ADR specifies handling of in-flight operations and data written after cutover. No dual authoritative writes, global exactly-once claim, or automatic irreversible database transformation is permitted by this plan.

## Obstacles, risks and resolving gates

| Obstacle | Resolving requirements / evidence |
|---|---|
| Hidden caller survives removal | ER-001/040/046 inventory, observation window and owner signoff evidence |
| Binary-compatible change breaks tools or meaning | ER-005/007/009 source/JSON/tool and behavioral conformance |
| Convenient new RPC layer creates another authority | ER-003/018–020 owner checks and topology negatives |
| Lost response duplicates protected operation | ER-012–015 idempotency, uncertain-effect reconciliation and fault tests |
| New encoding changes acceptance hash | ER-022/023 original bytes and domain-specific canonical meaning vectors |
| Browser/proxy or Python runtime cannot support chosen path | ER-010/030 and EC-00 executable path qualification |
| Temporary adapter becomes permanent architecture | ER-041/046 removal condition, unknown-caller handling and closure evidence |
| Rewrite replaces useful domain semantics with generic messages | ER-025–039 domain acceptance and first complete consumer |
| Infrastructure or language expansion increases burden | ER-043/047/048 measured operational and development cost |
| Offline restore lacks compatible decoder/toolchain | ER-008/031/032/042 retained artifacts, schema versions and recovery drill |

## Completion evidence and reassessment

A completion packet names the inventory population and uncovered boundaries (must be zero or explicitly retained external exceptions), each package's exact source/release/deployment/qualification evidence, supported client/version/transport matrix, tested failure classes, useful domain outcomes, operator attention and maintenance measures, original-evidence reconstruction, actual provider swap and whole-system restore. Removal commits and retired configuration/endpoints must be identifiable.

An ADR can select a better alternative to protobuf if it passes the same requirements. Refresh vendor/runtime facts at selection and upgrade. Unsupported or inconclusive cases are recorded and block claims for that boundary. No implicit permission is created to purchase, deploy, widen identity grants or expose new tenant surfaces.

## Source observations

The following manifest observations are sampled source facts, not a complete live interface census. Local HEAD and file digests make them reproducible even where a working tree differs from its remote. EC-01 must fetch canonical source and measure actual deployments before implementation decisions.

| Owner / source | Local HEAD observed | Manifest SHA-256 |
|---|---|---|
| vuoro / `pyproject.toml` | `aa5af4de351f011c1d4f795eaa72b692c5dfcb47` | `98a9abf9b8505268edd9019e290d83c8ea8d116abb1a804840851bb483633d0b` |
| vuoro-cloud / `pyproject.toml` | `47d49fec848ff3891ef0e49f43a5e071f67a39a5` | `476a3c391d305b2277b09bdccac1d7ce9bf20b2489e82ca17f2100d9df6f09a7` |
| vuoro-cloud / `flake.nix` | `47d49fec848ff3891ef0e49f43a5e071f67a39a5` | `e54887862a98c28f36a00932f2cf898528f37cf06f3eed2fe350351f2b9dcb67` |
| sprintctl / `pyproject.toml` | `16f121f1fc527f3238953b6f203b32530cdfb5bc` | `7577786be7bb627d8c45499c5aba60b370914f50a268a3e5be89c98d2a8a9a51` |
| cred-broker / `pyproject.toml` | `72b86d765f5e7386383cec2171b577c2af845839` | `e680487e404db3f8034f8a6b9d513154e7111fb99eee82ff2faba3de9dd1917b` |
| auditctl / `pyproject.toml` | `b3985a41c668a31366c87d0fc94a724c4b487d63` | `3d76476ad6a4b7279b1a28a1bb0da377af77a2ed9f4eee0cbd0a0ca076ce6508` |
| homelab-analytics / `pyproject.toml` | `c8379d7504f12dcc1a9e9d269e4fbb48741d7e8f` | `daa5cfc0e71c6217f5977d0d132b998b9245aabd28f75fe71e46c9c9181e44f1` |
| homelab-analytics / `apps/web/frontend/package.json` | `c8379d7504f12dcc1a9e9d269e4fbb48741d7e8f` | `a3e97c7f8165b6af4e08a47dd0b55b429953a93fed2c41cc704392026e8c57ea` |
| scribectl / `pyproject.toml` | `0eab88f3ddb925127c142d7572ccb6794982f241` | `61cc2f478432e4694404e7ea2a2117dbd83de5b15f0867957daaab6064f1c5a1` |
| browser-workbench / `pyproject.toml` | `8644736bec6e9bf3ae7f3298779c6553b5593f9e` | `0100c21041f16c159633154735f78559a575cf27324befd5956b2ea8f9a78d45` |
| browser-workbench / `package.json` | `8644736bec6e9bf3ae7f3298779c6553b5593f9e` | `25d72dc5e1727a575ef71fe75dcc7d04cce168951a8ecc718972e3d671163c1b` |
| browser-workbench / `Cargo.toml` | `8644736bec6e9bf3ae7f3298779c6553b5593f9e` | `38367223bafe2f88f6c2a19786c013f54c8cfac7dca475b443b9f648760113bd` |
| bindery-core / `go.mod` | `39645d9d263251c7179990718b966cc555b47624` | `3a9222d77c2cf36e6839e3210e786c9b3c61a8171fb84d176cb2e043502d4d5f` |
| gitops-nixos / `flake.nix` | `6f556ff715b1fb556bfab94bc3aa17edd01087d2` | `84f1c2af8e7a0b197ca5d8793209b09f979974e0a4859fc3616c96542b8c807f` |
