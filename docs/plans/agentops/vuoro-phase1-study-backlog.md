---
doc_id: vuoro-phase1-study-backlog
status: draft
drafted_at: 2026-07-22
scope: vuoro-phase1-comparison-study
method_refs:
  - vuoro-phase1-study-corpus.md
  - vuoro-phase1-study-prompt-template.md
---

# Vuoro phase-1 comparison study — item backlog

This is the enumerated work backlog for the phase-1 comparison study defined
in [`vuoro-phase1-study-corpus.md`](vuoro-phase1-study-corpus.md) (which
system/reading goes with which capability slice) and
[`vuoro-phase1-study-prompt-template.md`](vuoro-phase1-study-prompt-template.md)
(how to run one investigation). It is a research/documentation workstream —
no code, schema, or deployment changes are in scope. It is independent of the
Vuoro served-substrate implementation backlog in
[`vuoro-backlog-enablement-2026-07-21.md`](vuoro-backlog-enablement-2026-07-21.md);
the two should not be conflated or cross-claimed.

Full corpus coverage: every primary investigation, reference read, domain
reading assignment, cross-cutting item, and explicit exclusion from the
corpus appears below with a stable ID.

## sprintctl registration: deferred

sprintctl item creation is currently blocked in this workstation —
`SPRINTCTL_BACKEND=local` is invalid against this repo's `remote` marker and
no `SPRINTCTL_URL` is configured (`sprintctl doctor` confirms
`backend-config-invalid`). This is the same environment boundary documented
in
[`vuoro-continuation-blockers-2026-07-22.md`](vuoro-continuation-blockers-2026-07-22.md)
(Blocker A) — the fix is an operator-authorized endpoint, not a workstation
database connection, and this study does not change that.

The IDs below (`P#`, `R#`, `D#`, `X#`, `E#`) exist so that once the remote
endpoint is available, each item can be registered as a native sprintctl item
with a `ref` back to `vuoro-phase1-study-backlog.md#<id>`, without renumbering
anything here. Suggested shape for that later registration: one native item
per `P#` (the only tier substantial enough to warrant claim/status tracking),
titled `Phase-1: {system} — {capability}`, owner `agentops` (research), no
dependency edges except where a `P#` needs a same-slice sourcing item done
first (see Tier 1b below). `R#`/`D#`/`X#`/`E#` stay doc-only — too light to
carry sprintctl overhead.

## Tier 1 — primary investigations (full phase-1 doc)

One item per {system, capability} pair from the corpus's **Primary** line.
Each is a full phase-1 doc per the template: frontmatter, sections A–G,
annex, ≤2 pages main body. Dispatch by filling the four template variables
and handing the result to an agent with repo access.

### Tier 1a — ready now (local evidence available)

| ID | Slice | System | Capability | Evidence |
| --- | --- | --- | --- | --- |
| P02 | 1. Session identity and continuity | Vuoro/sprintctl | Identity that stays stable across context resets, and how it's scoped | `/projects/dev/sprintctl` — pin commit at investigation start; source, schema, tests |
| P04 | 2. Session handoff | Vuoro/sprintctl | Tier-2 scribe reconciliation: how one session ends and the next resumes with sufficient context | `/projects/dev/sprintctl` — pin commit; see `session-mechanization-plan.md` for prior art on the mechanism, but investigate the shipped behavior, not the plan |
| P06 | 3. Exclusive claim / assignment | Vuoro/sprintctl | Claims require remote consensus, no offline buffering | `/projects/dev/sprintctl` — pin commit; note this item is currently blocked from *running* against a live remote in this workstation (Blocker A) — investigate as-shipped from source/tests, do not require a live remote claim to complete the doc |
| P09 | 4. Ready-work determination | Vuoro/sprintctl | Readiness determination (`next-work` and related) | `/projects/dev/sprintctl` — pin commit; source, tests |
| P11 | 5. Concurrent-edit convergence | Vuoro/sprintctl | Observational events merge idempotently; claims don't | `/projects/dev/sprintctl` — pin commit; source, tests |
| P13 | 6. Knowledge claim lifecycle | Vuoro/kctl (+ doc-refs lifecycle) | draft → ratified → superseded, human ratification | `/projects/dev/kctl` — pin commit; source, schema, tests |
| P14 | 7. Durable evidence emission at transitions | Vuoro/auditctl | Uncontested — examination, not competition | `/projects/dev/auditctl` — pin commit; source, schema, tests |

### Tier 1b — blocked on sourcing (no local checkout)

Each needs a confirmed repo/URL before dispatch. None of these are
architecturally blocked (unlike Blocker A above) — they just need sourcing.

| ID | Slice | System | Capability | Repo status |
| --- | --- | --- | --- | --- |
| P01 | 1. Session identity and continuity | td | Session identity scoped branch+agent, stable across context resets | Not sourced. The prompt template's own example invocation names `https://github.com/marcus/td` — unverified, confirm before use |
| P03 | 2. Session handoff | td | Done/remaining/decision/uncertain structure, enforced review separation | Same td repo as P01 — source once, use for both |
| P05 | 3. Exclusive claim / assignment | Beads | Atomic claim, multi-writer server mode | Not sourced — no candidate URL known, locate before dispatch |
| P07 | 4. Ready-work determination | Beads | `bd ready`, auto-ready detection | Same Beads repo as P05 |
| P08 | 4. Ready-work determination | td | `next`, `critical-path` | Same td repo as P01/P03 |
| P10 | 5. Concurrent-edit convergence | Dolt (merge docs, as consumed by Beads) | Cell-level merge, branch semantics, conflict tables | Not sourced. **Investigate Dolt's own merge documentation, not Beads' Go code** — the corpus is explicit that Beads' storage layer is the actual primary source here, so this item's evidence is Dolt docs, independent of whether the Beads repo (P05/P07) is sourced |
| P12 | 6. Knowledge claim lifecycle | Graphiti/Zep | Temporal knowledge graph; edge validity intervals; new facts invalidate rather than overwrite | Not sourced — locate before dispatch |

Sourcing checklist to clear Tier 1b: confirm the td repo (or replace with the
correct one if `marcus/td` is wrong), locate Beads, locate Dolt's merge
documentation, locate Graphiti and/or Zep. Do this once — P01/P03/P08 share
one repo, P05/P07 share another.

## Tier 2 — reference reads (claims-annex only, no full doc)

Lighter pass: produce just the tagged-claim annex material for the
adopt/adapt/interoperate/differentiate classification later, not a full A–G
doc. Best dispatched alongside the Tier-1 item for the same system where one
exists.

| ID | Slice | System | Why it's reference, not primary |
| --- | --- | --- | --- |
| R01 | 1. Session identity and continuity | Beads | Agent identity is weaker/assignee-string — the contrast with td/Vuoro is the finding |
| R02 | 1. Session identity and continuity | Claude Code session/resume semantics | Runtime-side counterpart; public docs at docs.claude.com, not a repo |
| R03 | 3. Exclusive claim / assignment | td | Assignment exists but single-writer local — the interesting bit is what it *doesn't* need |
| R04 | 4. Ready-work determination | Airflow/Dagster | Mature version of the readiness-under-dependencies problem |
| R05 | 5. Concurrent-edit convergence | Git merge semantics | The mental model everyone imports, correctly or not |
| R06 | 5. Concurrent-edit convergence | Automerge/CRDT docs | Reference CRDT design, not sourced locally |
| R07 | 6. Knowledge claim lifecycle | Letta memory blocks | Agent-attached shared memory — the contrast that justifies kctl's decoupling |
| R08 | 6. Knowledge claim lifecycle | Wikidata statement model | Ranks/qualifiers/deprecated-rank — ratification at scale with humans in the loop |

Slices 2 and 7 have no reference tier (corpus: td is the strongest handoff
artifact and needs no contrast; auditctl's evidence-emission slice is
uncontested).

## Tier 3 — domain reading (calibrates sections D and F)

One grouped item per slice, matching the corpus's own bullet grouping. Not
agent-dispatchable investigations — reading/vocabulary calibration, to land
before or alongside finalizing that slice's D (Authority) and F (Failure
semantics) sections.

| ID | Slice | Reading |
| --- | --- | --- |
| D1 | 1. Session identity and continuity | Terry et al., *Session Guarantees for Weakly Consistent Replicated Data* (1994); DDIA ch. 5 |
| D2 | 2. Session handoff | SBAR clinical handover protocol; UK HSE shift-handover guidance (post-Piper Alpha); Google SRE workbook, on-call handoffs |
| D3 | 3. Exclusive claim / assignment | Gray & Cheriton, *Leases* (1989); Kleppmann, *How to do distributed locking* (fencing tokens); Postgres `SELECT ... FOR UPDATE SKIP LOCKED`; Kafka consumer-group epoch/zombie fencing; SQS visibility-timeout semantics |
| D4 | 4. Ready-work determination | Bazel action graph (build-system DAG scheduling); CPM/PERT critical-path method |
| D5 | 5. Concurrent-edit convergence | Shapiro et al., *CRDTs* (2011); DDIA ch. 5 conflict-resolution section; the "LWW is silent data loss" argument |
| D6 | 6. Knowledge claim lifecycle | Bitemporal modeling — Snodgrass; Fowler's bitemporal articles; XTDB docs |
| D7 | 7. Durable evidence emission at transitions | W3C PROV data model; in-toto attestation structure; Kubernetes audit policy; OpenTelemetry GenAI semantic conventions; Rekor/CT transparency logs (explicitly out of scope for a single operator — read to confirm the boundary, not to adopt) |

## Tier 4 — cross-cutting shelf (whole-substrate, no single slice)

| ID | Reading | Applies to |
| --- | --- | --- |
| X1 | Kleppmann, DDIA ch. 5, 8, 9 | General text for sections D and F across every investigation |
| X2 | Transactional outbox pattern (microservices.io) + Kafka idempotent-producer/exactly-once docs | External validation of the (origin_session_id, origin_seq) design |
| X3 | CQRS / event sourcing (Young, Fowler) | Projection plane; keeping the event log distinct from the audit log |
| X4 | A2A protocol task lifecycle + MCP tasks | Cross-agent work-item state machines; prior art for Vuoro's interoperate-boundary API |
| X5 | Temporal (durable execution) | Read only enough to draw the boundary — the thing Vuoro should *not* become |
| X6 | Jepsen analyses (any two, e.g. Postgres and Kafka) | Method exemplar for how section F should be written, not content |

## Excluded, with reason (not work items — do not re-propose)

| ID | Excluded | Reason |
| --- | --- | --- |
| E1 | Jira / Linear / GitHub Issues | Human-tracker domain models; null baseline only, per Beads' own FAQ |
| E2 | CrewAI / AutoGen / LangGraph-as-framework | Orchestration/runtime, declared non-core; LangGraph checkpointing stays a one-page appendix at most |
| E3 | OpenHands | Execution environments; boundary already drawn |
| E4 | Foundry-style agent-substrate management | Acknowledged out of product scope |

## Suggested execution order

1. **P02, P04, P06, P09, P11, P13, P14** (Tier 1a, 7 items) — dispatchable
   today, local evidence, no external dependency. Pair each with its Tier-2
   reference item where one exists (R01/R02 alongside P02; R05/R06 alongside
   P11; R07/R08 alongside P13).
2. **Sourcing checklist** — confirm/locate td, Beads, Dolt, Graphiti/Zep
   (blocks P01, P03, P05, P07, P08, P10, P12, and reference items R03, R04).
3. **P01, P03, P08** (td, once sourced) and **P05, P07** (Beads, once
   sourced) — 5 items, two repos.
4. **P10** (Dolt merge docs) and **P12** (Graphiti/Zep) — 2 items,
   independent of each other and of step 3.
5. **Domain reading (D1–D7) and cross-cutting shelf (X1–X6)** — run in
   parallel with the above; each D# should land before its slice's primary
   investigation(s) finalize sections D/F, not necessarily before dispatch.

Total: 14 primary + 8 reference + 7 domain + 6 cross-cutting = 35 items,
plus 4 explicit exclusions on record.
