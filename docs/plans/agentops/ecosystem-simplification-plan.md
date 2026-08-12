---
doc_id: ecosystem-simplification
status: draft
proposed_by: operator
created_at: 2026-08-12
references:
  - vuoro-served-substrate-plan.md
  - agent-ops-substrate-plan.md
  - sprintctl/docs/plans/roadmap-reset.md
  - vuoro/docs/plans/architectural-simplification-alignment.md
  - actionq/docs/plans/vuoro-served-execution-alignment.md
  - sprintctl/docs/plans/vuoro-served-authority-alignment.md
  - kctl/docs/plans/vuoro-served-knowledge-alignment.md
  - auditctl/docs/plans/vuoro-served-audit-alignment.md
  - outctl/docs/MIGRATION_ROADMAP.md
---

# Ecosystem simplification and stated-goal refactoring plan

## Purpose

This plan coordinates cross-member simplification and refactoring so that the
ecosystem's code matches its stated goals. It supplements, but does not
replace, the per-member served-substrate alignment plans and the sprintctl
roadmap reset.

The single governing constraint is **state ownership decides repository
ownership**. No simplification may let a member acquire another member's
authority.

## Strategic objectives

1. **Align intent with code.** Resolve documented design mismatches so future
   development follows one mental model.
2. **Reduce structural duplication.** Unify duplicated backend, adapter, and
   schema machinery so parity bugs and drift disappear.
3. **Split god modules.** Decompose monolithic CLI, application, and daemon
   files so review, testing, and parallel ownership become practical.

## Phased program

### Phase 0 — Foundational cleanup (low risk, high clarity)

| # | Work item | Owner | Outcome |
|---|---|---|---|
| P0.1 | Remove stale `actionq/build/lib/` artifacts; enforce `build/` hygiene | `actionq` | Clean working tree |
| P0.2 | Eliminate `sys.path` mutation in tests/scripts; use `PYTHONPATH` or package installs | `agentops`, `actionq`, `actionq-dispatcher` | Test reliability |
| P0.3 | Inline duplicated canonical-JSON helpers in `outctl` into `serialization.py` | `outctl` | Reduced duplication |
| P0.4 | Merge `kubectl_guard.py` + `kubectl_readonly_guard.py` in `outctl` | `outctl` | Single policy implementation |
| P0.5 | Reconcile `actionq-contracts` workspace vs. PyPI dependency in `actionq` | `actionq` | Consistent packaging |
| P0.6 | Document current boundary resolutions for contention points in §4 | `agentops` | Single source of truth |

### Phase 1 — Critical-path intent alignment (strategic priority)

| # | Work item | Owner | Outcome |
|---|---|---|---|
| P1.1 | Deprecate `actionq-dispatcher` and absorb residual coordinator behavior into `actionq-daemon` | `actionq` + `agentops` docs | One execution authority |
| P1.2 | Decide and record Runner vs. ActionQ worktree ownership | `actionq` + `vuoro` | No ambiguity |
| P1.3 | Remove stale cockpit direct-SQL exception documentation; verify activation uses sprintctl command | `agentops` cockpit + `sprintctl` | No raw DB writes from UI |
| P1.4 | Decide recovery authority disposition per `vuoro/docs/plans/architectural-simplification-alignment.md` V-S2 | `vuoro` + `sprintctl` | Recovery has an owner |
| P1.5 | Add `outctl` to member enumerations consistently | `agentops` + `outctl` | Outctl treated as full member |

### Phase 2 — Structural duplication reduction

| # | Work item | Owner | Outcome |
|---|---|---|---|
| P2.1 | Extract backend-agnostic repository protocol; collapse mirrored `sprintctl/db.py`/`pg.py` | `sprintctl` | ~6,000 LOC duplicated logic removed |
| P2.2 | Extract shared central-schema runtime for `kctl`, `auditctl`, `actionq` | `kctl`/`auditctl`/`actionq` + `vuoro` packaging | Eliminates triplicated schema machinery |
| P2.3 | Extract shared Vuoro adapter base for JSON-schema builder/registration boilerplate | `vuoro` (library) + domain owners | Four adapters shrink and align |
| P2.4 | Remove direct cross-member internal imports from Vuoro verification scripts and kctl source | `vuoro` + `kctl` | Transport-only boundary restored |

### Phase 3 — God-module decomposition

| # | Work item | Owner | Outcome |
|---|---|---|---|
| P3.1 | Split `sprintctl/cli.py` into `commands/` subpackage | `sprintctl` | Reviewable command modules |
| P3.2 | Split `sprintctl/application.py` into service classes | `sprintctl` | Testable services |
| P3.3 | Split `actionq/daemon.py` into lifecycle/runner/routing/audit/claim-client modules | `actionq` | Daemon maintainable |
| P3.4 | Split `actionq/application.py` into enqueue/claim/complete/groups/outbox services | `actionq` | Clear boundaries |
| P3.5 | Split `kctl/application.py` and `agentops` orchestration scripts | `kctl`, `agentops` | Parallel ownership |

### Phase 4 — Test and release ergonomics

| # | Work item | Owner | Outcome |
|---|---|---|---|
| P4.1 | Merge sprintctl SQLite/PG test files via backend fixture parametrization | `sprintctl` | One test source |
| P4.2 | Split oversized integration tests by domain/operation | `sprintctl`, `actionq`, `kctl` | Faster, focused tests |
| P4.3 | Replace git-SHA pins of `vuoro-client` with released tags | `sprintctl`, `kctl` | Stable releases |
| P4.4 | Remove transitional feature flags once migrations complete | `actionq`, `sprintctl` | No dead toggles |

### Phase 5 — outctl migration support

outctl's W0–W8 Rust migration remains a separate owner-local plan
(`outctl/docs/MIGRATION_ROADMAP.md`). This plan tracks only outctl's
ecosystem-level obligations: consistent membership, no authority acquisition,
and a clean Vuoro discovery contract.

## Batch 1 — Immediate work

Batch 1 resolves the design-intent contention points that block clean future
development. It is scoped for maximum strategic clarity with minimal
structural risk.

| # | Work item | Rationale | Success criteria |
|---|---|---|---|
| B1.1 | Document boundary resolutions for contention points in §4 | Prevents repeated design debates during later refactoring | `boundary-resolutions.md` ratified |
| B1.2 | Deprecate `actionq-dispatcher` and absorb residual coordinator behavior into `actionq-daemon` | Single execution authority; unblocks P3.3 | `dispatcher-once` is a thin launcher; no queue/worktree logic remains |
| B1.3 | Decide and record Runner vs. ActionQ worktree ownership | Unblocks portable-execution architecture and P2.4 | ADR in `actionq` or `vuoro` docs; affected plans updated |
| B1.4 | Remove stale cockpit direct-SQL exception documentation | The code already calls sprintctl; the exception text is outdated | `write-surface-policy.md` exception removed |
| B1.5 | Add `outctl` to member enumerations consistently | Prevents accidental exclusion from cross-member work | `project.context.json`, AGENTS tables, and generated guidance include `outctl` |

Suggested order: B1.1 → B1.5 → B1.2 → B1.3 → B1.4.

## Critical-path contention points

These design-intent mismatches must be resolved before large-scale code moves.

| Contention | Current state | Decision needed | Proposed resolution |
|---|---|---|---|
| Execution authority | `actionq-dispatcher` docs describe a coordinator; current AGENTS says it is only a launcher; `actionq-daemon` is absorbing the old role | Who owns one-shot vs. daemon execution? | `actionq` owns all execution lifecycle; `actionq-dispatcher` is a deprecated compatibility shim |
| Worktree/runner materialization | ActionQ claims worktree prep; portable-execution doc assigns it to a separate Runner | Is Runner a separate repo or an ActionQ internal package? | Decide in B1.3; if separate, define its home and contract; if ActionQ, update `portable-execution.md` |
| Cockpit write surface | `write-surface-policy.md` still documents a grandfathered direct-SQL exception, but the code now calls sprintctl | Remove stale exception documentation | Exception text deleted; activation confirmed as domain-owned command |
| Recovery authority | Service-side in-memory reconciler has no durable owner | Who owns recovery records and reconciliation? | Per V-S2: either remove service reconciler and keep local client export, or route recovery to a durable sprintctl/auditctl adapter |
| outctl membership | Outctl exists but is not consistently represented in member tables | Is outctl a full substrate member? | Yes; enumerate consistently and respect its local-only, non-authoritative contract |

## Worktree, branch, and review practice

- **Worktrees:** Each batch gets its own worktree or per-member feature
  branches; no direct commits to `main`.
- **Branch naming:** `refactor/<batch>-<short-desc>` per member, e.g.
  `refactor/b1.4-cockpit-sprint-activation`.
- **Cross-member coordination:** Use `agentops` `_orchestration` repo-id with
  parent/child claims; each child claim references this plan.
- **CI gating:** Each PR must pass member-local CI plus
  `validate_verification_artifacts.py --root .` where applicable.
- **Release pinning:** No refactor enters a pinned release version until it has
  passed CI, review, and at least one canary cycle on `main`.
- **Backwards compatibility:** Where a shared library is extracted (P2.x),
  old imports remain shimmed for at least one release cycle.

## Success criteria

The program is complete when:

1. Every contention point in §4 has a ratified decision record.
2. No member imports another member's internal modules directly (except
   explicitly authorized test fixtures).
3. `sprintctl` has one backend-agnostic storage layer.
4. `kctl`, `auditctl`, and `actionq` share a central-schema runtime.
5. God modules identified in Phase 3 are split into submodules/services.
6. `actionq-dispatcher` is either retired or documented as a deprecated shim.
7. Cockpit does not perform raw sprintctl DB writes.
8. Transitional feature flags and git-SHA pins are removed.
9. `outctl` is consistently represented as a member.

## Progress log

### P2.1 — sprintctl `db.py`/`pg.py` backend unification (2026-08-13)

Nine increments landed on the sprintctl dispatch-ready branch, each behind a
shared `sprintctl/<table>core.py` module (a `Conn` protocol implemented by a
thin per-backend adapter class), tested against the full SQLite suite after
every commit and, for the full chain, against a live disposable PostgreSQL
instance (124/124 `test_pg_integration.py`, and the broader `-m pg` suite at
169 passed against the same 8 pre-existing failures documented before this
work started — zero regressions):

- `rows.py` — claim/row serialization (landed before this session)
- `sprintcore.py`, `trackcore.py`, `refcore.py`, `depcore.py` — CRUD-shaped
  table sections
- `workitemcore.py` — work-item CRUD, plus relocating `validate_priority`/
  `effective_priority`/`validate_work_item_description` out of `db.py` so
  `pg.py` stops depending on `db.py` for backend-agnostic logic
- `eventcore.py` — event CRUD and the takeup/payload helpers, converging
  three previously-inconsistent payload-decode call sites
- `claimcore.py` — claim read-paths (4a), heartbeat/release (4b), handoff
  (4c)

**Two real SQLite/PostgreSQL behavioral drifts were found and fixed** while
extracting the read-then-emit-event logic, which had been copy-pasted
between the two backends since it looked backend-agnostic already:

1. `release_claim`'s rejection event on pg.py always used
   `["claims", "coordination", "release"]` tags, silently dropping the
   `ambiguity`/`legacy` tags db.py used for claims with no `claim_token`.
2. `handoff_claim`'s pg.py UPDATE bumped `lease_epoch` on rotation/adoption;
   db.py's never did. `lease_epoch` is a fencing token consumed by
   `terminal_recovery_server.py` and `authority.py` — the SQLite gap meant a
   session holding a pre-handoff epoch could still pass a fencing check
   after ownership changed hands. No existing test caught this on either
   backend; three regression assertions were added.

**Update (2026-08-13, same day):** the WorkItem CAS functions are done. A
second [planning pass](#p21-planner-assessment-2026-08-13) produced an
execution-ready design for the transaction-scaffold abstraction
`create_claim` needs, prototyped first on `update_work_item_description`
(the smaller of the two CAS functions) and then reused on
`set_work_item_status` in the same session to confirm it generalizes.
`WorkItemConn` gained `begin_txn`/`commit`/`rollback`/`for_update_of`/
`lock_for_update`/`execute`/`insert_event`. The abstraction deliberately
does not paper over a real concurrency-model difference: SQLite's
`begin_txn` takes a whole-DB write lock (so two CAS writers on *different*
items still serialize, unchanged from before this work), while
PostgreSQL's `lock_for_update` locks only the row in question. What both
backends must guarantee identically — and what a new SQLite-side
`threading.Barrier` regression test now proves, mirroring the PostgreSQL
one that already existed — is that two writers racing the *same* item
produce exactly one accepted write and one conflict. Verified against both
the full SQLite suite and the live disposable-PostgreSQL suite with zero
regressions.

**Deferred, not attempted:** `create_claim` (sub-increment 4d), still the
highest-risk piece in this section — PostgreSQL arbitrates admission with
an advisory lock *and* a row lock for two distinct concerns (repo-wide
capability arbitration vs. per-item exclusivity), where SQLite's single
`BEGIN IMMEDIATE` does both jobs at once, plus a claim-token collision
retry loop and a coordinate-claim delegation branch. The planning pass
that designed the WorkItem CAS work explicitly recommended `create_claim`
get its own fresh characterization pass rather than being folded into the
same session, even with live PostgreSQL validation now available: real
concurrent *processes* (not pytest threads in one process) could still
hide a lock-ordering risk in the two-tier lock that functional tests won't
catch.

**LOC estimate correction:** a planning pass over the four already-landed
CRUD-shaped increments (before this session added workitemcore/eventcore/
claimcore) measured *net +507 lines* — extracting straightforward
query-shape duplication into a Protocol/adapter split adds boilerplate that
outweighs the SQL text removed for thin CRUD tables. The `~6,000 LOC`
figure in the P2.1 row above is very unlikely to be sprintctl's slice
alone; it most likely refers to the cross-repo P2.x total. Whoever owns
this plan should correct or re-scope that estimate so P2.1's tracked
outcome isn't read as under-delivered once sprintctl's portion lands.

#### P2.1 planner assessment (2026-08-13)

A Plan-agent pass (before `workitemcore`/`eventcore`/`claimcore` existed)
produced a full section-by-section classification of WorkItem/Event/Claim
into query-shape (movable), pure-Python (movable, no protocol), and
transactional/locking (must stay backend-specific) logic, a recommended
extraction sequence, and named risk points. Sub-increments 1–3 of that
sequence (WorkItem reads, Event reads/writes, Claim 4a/4b/4c) are done;
sub-increment 4 (`create_claim`) and the WorkItem CAS step explicitly need
the transaction-scaffold prototyping step this plan has not yet done. The
full assessment is preserved in this session's transcript; it should be
copied into a standalone doc under `sprintctl/docs/plans/` before the next
session picks up `create_claim`, rather than re-derived from scratch.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Sprintctl backend unification breaks SQLite/PG parity | Keep exhaustive parity tests; introduce backend fixture before collapsing code |
| Shared library extraction creates coupling | Shared packages contain only generic plumbing, never domain authority |
| `actionq-daemon` consolidation destabilizes one-shot path | Maintain `dispatcher-once` as a launcher until daemon parity is proven |
| Cockpit sprint-activation migration changes UX | Preserve CLI-equivalent semantics; test both paths |
| Cross-member work diverges | Use `agentops` `_orchestration` claims and batch-end sync reviews |

## Open questions

- Should the shared central-schema runtime live in `vuoro`, `agentops`, or a
  new minimal member? (Decision deferred to P2.2)
- Does the Runner become a separate member or an ActionQ internal package?
  (Decision deferred to B1.3)
