---
doc_id: vuoro-phase1-study-corpus
status: source-material
authored_by: operator
recorded_at: 2026-07-22
recorded_from: ~/Downloads/phase1-comparison-corpus.md
---

# Comparison corpus for the Vuoro phase-1 study

Per capability slice: primary systems get a full phase-1 investigation; reference designs get a claims-annex read (no full doc); domain materials calibrate the schema sections — mainly D (authority) and F (failure).

---

## 1. Session identity and continuity
- **Primary:** td (session identity scoped branch+agent, stable across context resets); Vuoro/sprintctl (origin_session_id).
- **Reference:** Beads (agent identity is weaker/assignee-string — the contrast is the finding); Claude Code session/resume semantics as the runtime-side counterpart.
- **Domain:** Terry et al., *Session Guarantees for Weakly Consistent Replicated Data* (read-your-writes, monotonic reads — the formal vocabulary for the remote-feeding-local cursor cache); DDIA ch. 5.

## 2. Session handoff
- **Primary:** td (done/remaining/decision/uncertain structure, enforced review separation); Vuoro/sprintctl Tier-2 scribe reconciliation.
- **Reference:** none needed — td is the strongest artifact in the space.
- **Domain:** clinical handover protocols, esp. SBAR (situation/background/assessment/recommendation — decades of evidence on structured vs free-text handoff); UK HSE guidance on shift handover (post-Piper Alpha ops literature); Google SRE workbook on on-call handoffs. This slice's prior art is human-factors, not software.

## 3. Exclusive claim / assignment
- **Primary:** Beads (atomic claim, multi-writer server mode); Vuoro/sprintctl (claims require remote consensus, no offline buffering).
- **Reference:** td (assignment exists but single-writer local, so the interesting bit is what it *doesn't* need).
- **Domain:** Gray & Cheriton, *Leases* (1989); Kleppmann, *How to do distributed locking* (fencing tokens — the canonical argument for your stale-actor rejection); Postgres `SELECT ... FOR UPDATE SKIP LOCKED` queue pattern (directly relevant — actionq is Postgres); Kafka consumer-group epoch fencing / zombie fencing (the production analog of origin_seq discipline); SQS visibility-timeout semantics as the at-least-once baseline.

## 4. Ready-work determination
- **Primary:** Beads (`bd ready`, auto-ready detection); td (`next`, `critical-path`); Vuoro/sprintctl.
- **Reference:** Airflow/Dagster scheduling semantics (readiness under dependencies + time + sensors — the mature version of the problem).
- **Domain:** build-system DAG scheduling (Bazel action graph); critical-path method (CPM/PERT) — td's `critical-path` is a direct lift, know the original.

## 5. Concurrent-edit convergence
- **Primary:** Beads-as-shipped — which means **Dolt's merge documentation is the primary source**, not beads' Go code (cell-level merge, branch semantics, conflict tables); Vuoro/sprintctl (observational events merge idempotently; claims don't).
- **Reference:** Git merge semantics (the mental model everyone imports, correctly or not); Automerge/CRDT docs.
- **Domain:** Shapiro et al., *CRDTs* (2011) — for the vocabulary of what converges without coordination; DDIA ch. 5 conflict-resolution section; the standard "LWW is silent data loss" argument. The study question: which Vuoro state is CRDT-shaped (events) and which is consensus-shaped (claims) — you've already made this call; this literature is the check.

## 6. Knowledge claim lifecycle (creation → ratification → supersession)
- **Primary:** Graphiti/Zep (temporal knowledge graph; edge validity intervals; new facts invalidate rather than overwrite); Vuoro/kctl + doc-refs lifecycle (draft→ratified→superseded, human ratification).
- **Reference:** Letta memory blocks (agent-attached shared memory — the contrast that justifies kctl's decoupling); Wikidata's statement model (ranks, qualifiers, deprecated-rank — ratification/supersession running at scale with humans in the loop).
- **Domain:** bitemporal modeling — valid time vs transaction time (Snodgrass; Fowler's bitemporal articles; XTDB docs as a clean modern treatment). Ratification is exactly a transaction-time event over a valid-time claim; this vocabulary will sharpen kctl's schema more than any product will.

## 7. Durable evidence emission at transitions
- **Primary:** Vuoro/auditctl (uncontested — the exercise is examination, not competition).
- **Reference:** td `action_log` + `git_snapshots`; Dolt cell-level history (evidence as a database property).
- **Domain:** W3C PROV data model (entity/activity/agent; acted-on-behalf-of = coordinator delegation); in-toto attestation structure (subject+predicate+signature — adopt only if a second believer ever exists); Kubernetes audit policy (capture discipline: which transitions, what verbosity, which stage); OpenTelemetry GenAI semantic conventions (the observability/evidence boundary — what auditctl is *not*); Rekor/CT transparency logs (tamper evidence — note explicitly out of scope for a single operator).

---

## Cross-cutting shelf (whole-substrate, no slice)
- **Kleppmann, DDIA** ch. 5, 8, 9 — the general text for sections D and F across every investigation.
- **Transactional outbox pattern** (microservices.io) + Kafka idempotent-producer/exactly-once docs — external validation of the (origin_session_id, origin_seq) design.
- **CQRS / event sourcing** (Young, Fowler) — projection plane; also the discipline of not confusing the event log with the audit log.
- **A2A protocol task lifecycle** (submitted/working/input-required/completed/canceled/failed) and **MCP tasks** — the emerging cross-agent work-item state machines; prior art for what Vuoro's API exposes to foreign runtimes at the interoperate boundary.
- **Temporal** — durable execution; the canonical thing Vuoro should *not* become; read only enough to draw the boundary.
- **Jepsen analyses** (any two, e.g. Postgres and Kafka) — not for content but as method: the exemplar for how section F should be written.

## Deliberately excluded, with reason
- Jira / Linear / GitHub Issues — human-tracker domain models; use only as the null baseline Beads' FAQ already argues against.
- CrewAI / AutoGen / LangGraph-as-framework — orchestration and runtime, declared non-core; LangGraph checkpointing stays a one-page appendix.
- OpenHands — execution environments; boundary already drawn.
- Foundry-style agent-substrate management — acknowledged out of product scope.
