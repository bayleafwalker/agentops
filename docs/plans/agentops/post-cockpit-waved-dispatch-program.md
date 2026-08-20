---
doc_id: cockpit-and-post-cockpit-waved-dispatch-program
status: superseded
created_at: 2026-08-01
owner: agentops
tracker_item: agentops#2070
superseded_at: 2026-08-20
superseded_by: native-runtime-federation-realignment-2026-08-20.md
---

# Cockpit convergence and post-cockpit waved dispatch program

> **Superseded 2026-08-20.** This remains the historical 2026-08-01 backlog
> reconciliation and wave design. It does not override live Sprintctl state and
> is no longer a dispatch recipe. The current execution boundary is
> [`native-runtime-federation-realignment-2026-08-20.md`](native-runtime-federation-realignment-2026-08-20.md).

## 2026-08-20 migration disposition

- Preserve the reasoning-unit, same-repository serialization, independent
  verification, owner-API, and separate deployment-authorization rules.
- Replace exclusive claims and proof transport with Sprintctl `origin/main`
  v0.3.0 advisory reservations and expected-revision CAS. Overlap is visible,
  not prevented, and a reservation grants no mutation authority.
- Do not create ActionQ actions/attempts to realize a wave. Start work through
  the selected native runtime and register its external execution reference and
  actual binding-assurance level in the ActionQ federation surface.
- Do not implement the deferred ActionQ external-runtime backend in Wave 6.
  It preserves the execution-plane ownership that ActionQ's newer deletion plan
  removes.
- Treat `_orchestration#1366` in active sprint `_orchestration#437`
  (dispatcher-meta sequential handoff) as **do not dispatch** until its tracker
  owner records supersession or a native-runtime /
  immutable-predecessor-reference re-scope. This document makes no Sprintctl
  mutation.
- Outctl is not a member or a future wave. Native harness evidence targets
  standard OpenTelemetry plus the selected Langfuse or Phoenix/object-storage
  path.

All dates, item readiness statements, dependency corrections, and wave tables
below are retained as historical evidence. Re-read live Sprintctl state and
owner plans before scheduling any successor work.

This is the cross-repository execution projection for cockpit convergence and
the goal inventory that follows it. The filename retains the destination's
short name, while Waves 0 and 1 explicitly clear and execute the cockpit
prerequisite. Sprintctl owns live item state and dependency edges; owner-local
plans own semantics; this document owns only reasoning-unit boundaries,
concurrency, entry gates, and review topology. Re-read every item and owner
plan before dispatch. A dated status here never overrides Sprintctl.

The target state is one owner-mediated operation path per domain, observable
owner resources, immutable released composition, explicit publisher and policy
authority, replayable execution evidence, and removal of transitional direct
access. Vuoro remains transport and composition, not a queue, policy engine,
recovery authority, or generic event store.

## Governing constraints

- Dispatch one dependency-cleared reasoning unit at a time per repository.
  Independent repositories may run concurrently. Same-repository units use
  separate accountable build contexts but integrate sequentially.
- Contract, test-oracle, compatibility, authority, security, migration,
  recovery, publication, and deletion decisions are coordinator-owned.
- Reviewed bulk implementation is admitted only after interfaces, acceptance
  semantics, writable paths, and discriminating executable gates are frozen.
- An independent reviewer gates every unit before publication or dependent
  clearance. A shared contract failure opens the same-repository circuit
  breaker and stops later units.
- Deployment, image publication, Flux, Kubernetes, and production
  reconciliation remain separately authorized in `appservice`.
- Cross-repository dependencies that Sprintctl cannot encode are structured
  blocker notes. Their absence from `deps` never implies readiness.

## Reconciled baseline

The 2026-08-01 reconciliation made these authoritative backlog corrections:

- AgentOps #1280 now names its real completed prerequisite, #1279, rather than
  nonexistent #1213.
- Sprintctl #1238 formally blocks #1234 because `interrupted` recovery status
  and token removal must exist before the atomic recovery record.
- AgentOps #2039 records Sprintctl #1164 as its sole remaining external gate;
  Sprintctl #2038, ActionQ #2031-#2035, and Vuoro #2037 are complete.
- Vuoro #2028 records pending ActionQ #2027 as its owner-semantics gate.
- Vuoro #2045 records the missing immutable Kctl owner release as its gate.
- ActionQ #1445 remains parked behind explicit runtime selection and the
  AgentOps #2061 replay-complete corpus gate.
- Vuoro #2060 remains ratification-only until its human evidence-security
  decisions are frozen.
- Sprintctl #1983 is reconciliation-only: the owner plan records Kctl commit
  `2187c5c` as landed, but the pending item lacks owner verification evidence.
- Vuoro #2047 is done from retained passing disposable fake-runner evidence.

No dependency was removed and no cycle was found.

## Immediate readiness pool

These items are live-ready now. Their placement in a later program wave is a
scheduling preference or same-repository integration order, not an additional
dependency:

- AgentOps lane: #2053, #1280, and coordinator/human ratification #2062;
- Sprintctl lane: #1164 and #1235, integrated sequentially;
- Vuoro lane: #2041, #2042 decision, #2043 contract, #2048 configuration,
  #2050 verification profiles, #2051 publisher boundary, and #2059 policy
  assessment. #2060 may run only as its human decision session.

Only one implementation unit per repository integrates at a time. A
coordinator may reorder ready units within a repository after rereading their
current revisions; the tables below must not be interpreted as unrecorded
dependency edges.

## Dispatch topology

The waves below are release trains. A lane may advance when its own entry gate
passes; it does not wait for unrelated lanes in the same numbered wave. The
wave number expresses the earliest safe dispatch point, not a global barrier.

### Wave 0 — reconcile and clear the cockpit gate

Maximum cross-repository concurrency: 3.

| Unit | Repository/item | Posture | Entry | Exit gate |
|---|---|---|---|---|
| W0-S1 | Sprintctl #1164 | coordinator-only compatibility removal | all eleven owner-ledger gates and operator decision remain pinned green | full suite; served/local recovery; stale-client guidance; catalog/CLI parity; independent removal review |
| W0-A1 | AgentOps #2053 | coordinator schema/validator, then reviewed-bulk examples/docs | current packet schema and gate hash baseline pinned | missing and duplicate IDs fail; valid packet behavior unchanged; hash break versioned; dispatch suite and artifact validator |
| W0-V1 | Vuoro #2041 | coordinator boundary refactor | request-shape and optional-dependency fixtures frozen | client/service suites, both wheels, boundary tests, byte/error parity |

Circuit breaker: any disagreement among the #1164 owner ledger, live served
catalog, deployed compatibility evidence, and repository source stops W0-S1
and keeps AgentOps #2039 held. W0-A1 and W0-V1 may continue because they do not
consume that boundary.

### Wave 1 — converge cockpit paths while independent owner work proceeds

Maximum cross-repository concurrency: 3. AgentOps units integrate sequentially.

| Unit | Repository/item | Posture | Entry | Exit gate |
|---|---|---|---|---|
| W1-A1 | AgentOps #2039 | coordinator train | W0-S1 done; exact Sprintctl removal and ActionQ/Vuoro catalog revisions pinned | old/new fixtures cover allowed and rejected writes, tenant/auth isolation, pagination and degradation; `npm test`; `npm run build`; consumer search proves no fallback; clean-install and historical-config review |
| W1-S1 | Sprintctl #1235 | coordinator mutation/concurrency semantics | current revision vocabulary pinned | stale CAS has no row/event effect on both backends; matching CAS applies once; two-connection Postgres race has one winner; full suite |
| W1-V1 | Vuoro #2042 | coordinator decision only | all recovery producers, consumers, retention, and evidence refs inventoried | explicit retain-local/remove-service or durable-owner route; independent review rejects in-memory authority |

W1-A1 is entirely coordinator-owned with the current manifest. It is itself
sequential: consumer/operation inventory → contract freeze →
owner operation additions → cockpit rewire → compatibility window evidence →
old-path deletion → independent cross-repository review. A future coordinator
may register a self-contained cold cockpit test/build command and then
reassess mechanically frozen `apps/web` plumbing for reviewed bulk; the
existing commands do not falsify cockpit behavior.

### Wave 2 — build observable and reusable mechanics

Maximum cross-repository concurrency: 3. Same-repository order is mandatory.

| Lane/unit | Repository/item | Posture | Depends on | Exit gate |
|---|---|---|---|---|
| W2-Q1 | ActionQ #2027 | coordinator owner semantics/oracle | owner item readiness | observable owner lifecycle proof and falsifying histories; no Vuoro-owned state |
| W2-A1 | AgentOps #1280 | coordinator freeze, then reviewed-bulk tooling | #1279 done; live-ready now | cross-repo latest/supersedes, redaction, reconciliation-boundary and round-trip tests; dispatch review |
| W2-V1 | Vuoro #2043 | coordinator compatibility/composition | live-ready now; program-sequenced after #2041 only because of shared Vuoro integration surfaces, not a tracker dependency | locked-to-installed identity, explicit constructors, credential separation, both wheels, boundary/full suite |

After W2-Q1 passes, dispatch Vuoro #2028 as W2-V2: coordinator freezes
`resource-reference/v1`, catalogs, observation authority, cursor and timeout
semantics, and the oracle. Only frozen polling/reconnect/client mechanics are
reviewed-bulk eligible. Required gates cover authorization independence from
opaque refs, cursor expiry, reconnect, at-least-once deduplication, response
loss, visible transport selection, and separation from output streams.

### Wave 3 — harden released composition and verification

Maximum cross-repository concurrency: 2. Vuoro integration is strictly
sequential because these units share catalog, packaging, and compatibility
surfaces.

| Order | Repository/item | Posture | Entry/exit |
|---:|---|---|---|
| 1 | Vuoro #2050 | coordinator-only profile semantics and CI implementation | live-ready now; exact current package suites and protected paths pinned; prove named superset profiles and forced full escalation; extend profiles when #2028 lands rather than treating #2028 as a hidden blocker |
| 2 | Vuoro #2051 | coordinator-only identity/security | prove only the trusted publisher can write; execution/composition fails closed when given write credentials |
| 3 | Vuoro #2052 | coordinator end-to-end canary | #2050 and #2051 done; compile, execute, integrate, independently verify, and deterministically republish one disposable wave |
| 4 | Vuoro #2045 | coordinator-only adapter promotion | immutable Kctl wheel evidence exists; clean install matches lock and registration/compatibility fail closed |
| 5 | Vuoro #2048 | coordinator-only configuration | live-ready now; pin the exact released ActionQ catalog/config contract selected at dispatch; executable config-load tests pass |

Vuoro #2048 does not authorize daemon enablement or an `appservice` rollout.
Catalog drift, wheel/source mismatch, historical-profile incompatibility, or a
publisher-identity violation stops the entire Vuoro composition train.

### Wave 4 — ratify authoritative records, policy, and evidence boundaries

These are coordinator/human decisions, not bulk implementation. AgentOps #2062
and Vuoro #2059 are live-ready and may start immediately in independent
repository contexts. Vuoro #2060 may join only as a human decision session.

| Unit | Repository/item | Required decision |
|---|---|---|
| W4-A1 | AgentOps #2062 | ratify/reject/defer D1-D7; enumerate each authoritative record owner, durable form, export/rebuild state, retention/security class, and loss consequence; classify roadmap surfaces |
| W4-V1 | Vuoro #2059 | assign policy schema/version/precedence and admission ownership; decide only the narrow released-capability composition seam |
| W4-V2 | Vuoro #2060 | assign CLI compaction ownership; freeze bytes, ordering, signals, permissions, evidence export, retention/redaction/deletion, and A/B oracle |

The numbered order is the preferred synthesis order, not a dependency chain:
#2062 may inventory facts alongside owner proofs, while its final ratification
must label unavailable evidence rather than assume it. Vuoro #2059 and #2060
integrate sequentially because they share a repository, but neither is made
dependent on cockpit or composition work by this document. Each ratification
may create separately scoped owner-repository implementation items. Do not fold
those implementations into the decision item or infer them before
ratification. Unresolved ownership or record-of-truth questions stop the lane.

### Wave 5 — Sprintctl reservation and recovery train

This is a serial compatibility/migration train, not bulk parallel work:

Formal same-repository live edges:

```text
#1235 completed as W1-S1 → #1236 → #1237
#1237 → Sprintctl #1244 → #1238
#1164 + #1237 → #1238
#1238 → #1239
#1237 + #1238 → #1240
#1238 → #1234
#1239 + #1240 + #1234 → #1241
```

Structured cross-repository gates and program handoffs, which Sprintctl cannot
represent as formal dependency rows:

```text
Sprintctl #1237 done → Vuoro #1243
Sprintctl #1241 done → AgentOps #1242
```

Wave 5 continues from W1-S1; it must not redispatch #1235. The graph above is
the live claimability graph, including the audited #1238 → #1234 edge. It does
not solve a contradiction in the owner release plan: live dependencies require
#1238 to complete before #1239/#1240 can be claimed, while safe merge order
requires #1239/#1240 behavior before #1238's schema commit. Before dispatching
any of #1238-#1240, the Sprintctl owner must revise the item/dependency boundary
or freeze one coordinator-owned release-train protocol that can be executed
without bypassing claim rules. Until then, the three-item train is **not
dispatch-ready**. Every unit remains coordinator-owned because it changes
mutation, claim, migration, recovery, or compatibility semantics.

The shared gate is disposable SQLite/Postgres parity plus the focused protocol
history, full repository suite, verification-artifact validator, and an
independent reviewer. Lost-update counterexamples, row-count drift, a
non-atomic recovery record, stale-client ambiguity, or a mixed catalog/schema
version stops the train.

Sprintctl #1983 is excluded from this train. Kctl owner verification must attach
the landed commit, served event-read/watermark tests, and explicit evidence for
the expected absent-`maintain.check` preflight behavior. A successful served
`kctl doctor` is not required because that command does not exist. The owner
then closes or supersedes the item; implementation must not be redispatched.

### Wave 6 — deferred external runtime

> **Retired 2026-08-20:** do not dispatch this wave. Native runtimes are the
> execution boundary; ActionQ records/reconciles external references and must
> not invoke a runtime as its backend.

ActionQ #1445 remains parked. It becomes dispatch-plan eligible only after an
operator selects an external runtime and the AgentOps #2061 corpus contains
content-addressed normal, denial, cancellation, and abrupt-failure scenarios.
Any implementation remains coordinator-owned and must preserve ActionQ as the
only claim/retry/cancellation-settlement/verification/publication authority.

## Bulk-dispatch admission table

“Bulk” here means review-gated implementation behind a coordinator-owned
oracle, never bulk authority.

| Item | Bulk-admissible slice | Freeze required first |
|---|---|---|
| AgentOps #2053 | examples and documentation migration | schema, uniqueness validator, schema version and gate-hash oracle |
| AgentOps #1280 | bounded script/skill mechanics | note contract, member discovery, kind rule, redaction and reconciliation oracle |
| Vuoro #2028 | client polling/reconnect mechanics | resource schemas, cursor/timeout/authority semantics and fixtures |
| Vuoro #2041 | internal deduplication mechanics | exact invocation/profile interface and byte/error fixtures |

AgentOps #2039 remains coordinator-only until a separately reviewed manifest
change registers a cold command that falsifies cockpit test and build behavior.
Vuoro #2050 remains coordinator-only because its CI workflow surface is hybrid
protected. All other listed units are coordinator-only or deferred. A rejected bulk
candidate returns to the coordinator; it is not retried without a materially
revised packet and oracle.

## Executable verification profiles

Each dispatch source has exactly one `command_id`. For a bulk packet, that one
registered cold command must falsify every packet requirement. Broader commands
below belong to coordinator and independent verification when they cannot be
represented by the worker's single command. At selection time, confirm the
registered command and the broader gate still cover:

- AgentOps: dispatch tests and
  `validate_verification_artifacts.py --root .`; cockpit units additionally
  run `npm test` and `npm run build` from `apps/web`.
- Vuoro: focused package tests, both wheel builds, boundary tests, full suite,
  and released-artifact smoke where composition changes.
- Sprintctl: focused protocol/recovery tests on both backends, full suite, and
  verification-artifact validation.
- Kctl: focused and full tests, served event-read/watermark behavior, expected
  absent-`maintain.check` preflight behavior, and artifact validation.
- ActionQ: focused contract/coordinator histories, disposable PostgreSQL where
  lifecycle is involved, full suite, and artifact validation.

The cross-repository gate pins old and new revisions and exercises rejected
writes, tenant/authorization isolation, pagination/degradation, clean install,
historical configuration, catalog compatibility, and consumer searches. A
review based only on a green per-repository suite is insufficient for a
cross-boundary unit.

## Compiling a cleared wave

`dispatch-plan/v1` deliberately does not encode backlog dependencies,
unresolved decisions, deployment authorization, or circuit-breaker predicates.
Those remain in Sprintctl and this program. Never compile the whole portfolio
as one plan.

For each dependency-cleared reasoning unit:

1. Re-read the item and formal dependencies. Resolve every structured external
   blocker note and pin its evidence.
2. Read exact `selected_revision` and a fresh `observed_revision`; they must
   match.
3. Pin credential-free repository URLs and exact 40-character commits.
4. Freeze registered `command_id`, repository-relative `allowed_paths`, sorted
   capabilities/gates, worker profile, topology, integration lane, and review
   profile.
5. Author one `dispatch-plan-source/v1` for the cleared wave and run:

   ```bash
   python templates/dispatch/scripts/compile_execution_plan.py compile \
     --source <wave-source.json> --output <wave-plan.json>
   python templates/dispatch/scripts/compile_execution_plan.py check \
     --source <wave-source.json> --output <wave-plan.json>
   ```

6. ~~Create ActionQ actions, establish or claim attempts under ActionQ
   authority, then bind and realize the group.~~ **Retired 2026-08-20.** Start
   the selected native runtime deliberately and record/reconcile its external
   execution reference plus assurance level through the ActionQ federation
   contract when available.
7. Run the independent gate once per reasoning unit. Publish or clear a
   dependent only after `PASS` and immutable evidence attachment.

Compiler inputs are intentionally produced just in time. Committing placeholder
revisions or mutable branch heads would make the portfolio look dispatchable
while defeating drift detection.

## Canonical owner plans

- AgentOps architecture:
  `docs/assessments/vuoro-architecture-implementation-plan-2026-07-25.md`
  and
  `docs/assessments/vuoro-substrate-simplification-refactoring-assessment-2026-07-26.md`.
- AgentOps packet and session mechanics:
  `docs/plans/agentops/execution-scope-declaration-pilot.md` and
  `docs/plans/agentops/session-note-contract-plan.md`.
- Vuoro observable resources and simplification:
  `docs/architecture/observable-resources.md` and
  `docs/plans/architectural-simplification-alignment.md`.
- Vuoro composition and integration:
  `docs/plans/kctl-served-hardening-promotion.md` and
  `docs/plans/repository-integration-ci-alignment.md`.
- Vuoro ratification inputs: `docs/plans/Policy_Contract_layer.md` and
  `docs/plans/vuoro-market-absorption-handoff.md`.
- Sprintctl cutover and v3:
  `docs/plans/1164-gate-evidence-ledger.md`,
  `docs/plans/v3-reservation-model-plan.md`, and
  `docs/plans/served-mode-gaps-plan.md`.
