# Output 6 — Reduced Workflow Specification (Clean-Room Handoff)

Status: **DRAFT-FOR-FREEZE**. Freeze blockers (per the 2026-07-23 review
reconciliation): (1) five timed resume observations during normal work,
recorded per the README's template, including at least one multi-agent
resume and one after a meaningful idle gap — these also test H9; (2) one
successful actionq queue-volume inspection — **completed 2026-07-23**
(read-only via CNPG pod exec; outcome: effectively no real usage; R5
split applied below). The only remaining blocker is (1). Paired blinded
shadow reconstructions would strengthen the sample but are not required
to complete the planned gate. Per Gate 5,
this document must be frozen before external tools are studied in detail,
and must not be modified during the comparison — including in response to
attractive features or awkward gaps found in candidate tools.

Only requirements that survived the assessment appear here. Each uses the
plan's template. "Current Vuoro implementation" names code for reference
only — implementation details are explicitly not requirements.

Environment constraints that any solution must respect (from RQ5, verified
real): trust separation between devbox and workstation; restricted production
access; resumable unattended agent work; concurrency and claim ownership
across ~10 concurrent agents; durable audit-quality history of decisions;
long idle periods (months) without state rot.

## Five cold-resume observations (observational status toward Gate 4)

These observations are evidence-backed from the 30–60 day retrospective but
only one instance currently has a comparable timed next-action metric.
Until four additional normal-work *timed* observations are collected, the freeze
is explicitly blocked.
Task #1216 re-review confirms this remains unchanged: five candidate resume
incidents are identified, but only one includes a defensible assisted timing band.
No remaining incident has complete assisted-versus-manual timing fields.

| # | Date | Context | Resume surface | Evidence of value | Timing |
|---|---|---|---|---|---|
| 1 | 2026-07-08 | homelab-analytics recovery after lost claude-agent sessions (items #730–#734) | claim records + `claim resume` | 5 rotate recoveries completed with ownership continuity; conflict duplication avoided | Assisted timing only (`<5 m` rotate ops); manual baseline not captured in-band |
| 2 | 2026-07-14 | sprintctl ops-upgrade wave (~20 claim handoffs across ~8 actors; repeated "previous proof was unavailable; explicit adopt") | claim handoff + bundles (6 handoffs) | Proven proof-loss recovery and transfer continuity in active multi-actor work | **not timed in-band; no protocol timing fields recorded** |
| 3 | 2026-07-21 | sprintctl/vuoro 10-agent dispatch batch (`942` tool calls) | orchestrator-owned claims, done-from-claim, kctl capture | Batch-scale claim continuity preserved across orchestrator chains | **not timed in-band; no protocol timing fields recorded** |
| 4 | 2026-07-22 | sprintctl #1195 end-of-day handoff into next-session continuation | `handoff-1195-served-backend-2026-07-22-eod.txt` / bundle | Deterministic next action produced; conflicts surfaced (`[unclaimed-active-work]`, dependency block) and bundle-correct decisions prevented wrong branch | Assisted timing: `<5 min` (from in-band band in source artifact); manual comparison: `15–60 min` reconstruction counterfactual in `02-workflow-economics.md` |
| 5 | 2026-07-19→23 | ecosystem cold resume into #1195 continuation after idle period | sprint list + continuation-blockers plan + bundle | Multi-day gap did not lose operational continuity; remaining proof-channel risk stayed explicit | **not timed in-band; no protocol timing fields recorded** |

### Task #1216 protocol coverage

| # | Resume timing evidence | Source |
|---|---|---|
| 1 | Assisted only (`<5m`) with no paired manual clock | `02-workflow-economics.md` (§2 incidents 1–5), incident claim records in `.sprintctl` |
| 2 | No assisted timing field; no manual-comparison timing | `06-reduced-workflow-specification.md` row 2, `handoff-407` chain context |
| 3 | No assisted timing field; no manual-comparison timing | 10-agent dispatch session (`.agents/sessions/2026-07-21-vuoro-served-substrate-codex-dispatch.md`) and 06 row 3 |
| 4 | Assisted `<5m` band; manual comparison band `15–60m` | `handoff-1195-served-backend-2026-07-22-eod.txt`, `02-workflow-economics.md` counterfactual detail |
| 5 | No assisted timing field; no manual-comparison timing | `README` evidence source list + `06` row 5 |

Result: **1 of 5 resumptions has any defensible timed metric; none are protocol-complete with all fields.**

Freeze condition result:

* **Valid observed resumes:** 5
* **Valid timed observations:** 1
* **Gate-4 status:** **BLOCKED** pending 4 additional timed observations with idle-gap and multi-agent coverage.

Current claim: no R1–R8 wording changes are made from these observations until
the protocol-complete timed set closes.

## Requirement vs mechanism confidence

The eight requirements are not equally established. Confidence in the
*problem* (that it must be solved) and confidence in the *current mechanism*
(that Vuoro's present solution shape is the demonstrated one) are scored
separately; the clean-room comparison must weigh candidates against the
left column, not the right.

The model-sensitivity column resolves H8 at freeze: it records which
requirement weights should be re-evaluated when agent runtime capabilities
materially change (longer context, longer-running sessions). During the
clean-room comparison these weights are frozen; H8 is not a lever for
amending requirements after candidate tools are examined.

| Requirement | Requirement confidence | Current mechanism confidence | Model sensitivity (H8) |
|---|---|---|---|
| R1 lifecycle | High | High | Low |
| R2 claims | High | Medium-high | Medium |
| R3 resume | High | High | High |
| R4 decision log | High | High after taxonomy reduction | Medium |
| R5 unattended execution safety | High for the safety envelope (isolation + ACL + admission); the queue *form* is not requirement-grade | Low-medium — direct inspection 2026-07-23: 23 live actions, 3 completions, zero sweep/requeue/idempotency firings; the queue-specific design is unproven in live use (R5 split applied) | Low |
| R6 cross-machine authority | High | Medium for a unified single Vuoro service | Low |
| R7 durable knowledge transfer | Medium-high | Medium (KB context-loading proves distribution, not per-entry decision impact) | Medium-high |
| R8 composed operator view | Medium | Low-medium (no usage telemetry; 15 deployed versions demonstrate development, not operator dependence) | Medium |

---

## R1 — Work registry with gating lifecycle

```text
Requirement: A per-repo registry of work items with a small status lifecycle
  (pending → active → done/blocked) whose transitions are validated, plus
  blocking dependencies that prevent activation until blockers are done.
Problem solved: Work selection and "is this finished" arbitration for both
  humans and agents; prevents starting blocked or already-done work.
Evidence of repeated use: 939 items, 766 completed across 12 repos;
  transitions gate next-work selection and dispatch prompts; 115 dependencies;
  dependency-blocked conflicts surfaced in live bundles.
Consequence if absent: Work selection falls back to memory/docs; duplicated
  and out-of-order execution observed risk in multi-agent batches.
Minimum acceptable behaviour: CRUD + validated transitions + dependency
  block on activation + list/filter by status; scriptable (JSON out).
Current Vuoro implementation: sprintctl db.py:23-36, 779-845.
Implementation details that are NOT requirements: SQLite/Postgres choice;
  sprint "kind" taxonomy; multi-active sprints; priority integer; tracks.
Maturity: Stable.
```

## R2 — Exclusive execution claims with transferable proof

```text
Requirement: An agent can take an exclusive, provable claim on a work item;
  mutations of claimed items require the proof; claims can be transferred
  (handoff) or recovered after session loss; proofs are never exposed to
  delegated subagents or logs.
Problem solved: Two agents editing the same scope; ownership continuity
  across session death; safe delegation in multi-agent batches.
Evidence of repeated use: 91 claims; 32 handoffs in July; 5 recovery
  takeovers 2026-07-08; orchestrator-owned-token invariant in every dispatch
  skill; 2 real token-exposure incidents drove a transport redesign.
Consequence if absent: Duplicated/conflicting edits in every multi-agent
  batch (the dominant operating mode in bursts).
Minimum acceptable behaviour: claim(item) → proof; mutation gate; release;
  transfer with proof rotation; recovery path for lost proofs; an
  authoritative invalidation-and-recovery policy for dead claims — any
  time-based expiry, if present, is authority-enforced, never client- or
  presentation-enforced. Whether time-based liveness is needed at all
  remains open (H7); the evidence rejects client heartbeat upkeep, not
  event-driven invalidation.
Current Vuoro implementation: sprintctl claims (mig.2/4/6, pg lease_epoch),
  claim start/handoff/resume/recover.
Implementation details that are NOT requirements: heartbeat as a client
  obligation (89/91 claims show it isn't maintained and nothing depended on
  it); claim_type enum beyond exclusive-execute; hostname/pid capture;
  300-second default TTL.
Maturity: Stable (proof transport across hosts: Provisional until
  invocation/v2 has operating history).
```

## R3 — Deterministic resume bundle

```text
Requirement: One command/artifact that renders, for a repo: state summary,
  active/ready/blocked work, detected conflicts (unclaimed active work,
  dependency blocks, staleness), recent decisions, and a single recommended
  next action; consumable by a cold agent without other context.
Problem solved: Session resumption after interruption, delegation, or idle
  gaps — the core reconstruction-avoidance claim, which held under
  counterfactual analysis (≤5 min vs 15–60 min with residual ambiguity).
Evidence of repeated use: 30 bundle generations; committed bundles; the
  2026-07-22 #1195 resume worked example; every dispatch skill's resume path.
Consequence if absent: 10–60 min reconstruction per resume across ≥3
  sources, plus wrong-next-action risk (blocked scope attempted).
Minimum acceptable behaviour: The seven blocks above, deterministic given
  state, text output sufficient. Conflict detection is the non-negotiable
  part — it is what git cannot provide.
Current Vuoro implementation: sprintctl handoff (cli.py:6682) + session
  resume (cli.py:4379).
Implementation details that are NOT requirements: the 20+-field bundle
  contract; delta_since_last_handoff; freshness block; JSON/text dual parity;
  50-event tails; shutdown-protocol prose.
Provisional input surface (not a requirement): session-note/v1 — authored,
  non-authoritative session context for resume cases not adequately
  represented by work state or decision events. Candidate supplement to
  this requirement only; promotion is gated on H9 (does an authored note
  repeatedly resolve information gaps not representable in R3/R4?), tested
  during the five timed resume observations. Until then the scope fence
  holds: no kctl ingestion, no cockpit pane, no new note kinds, no stable
  served cross-machine transport, no mutation of authoritative work state.
Maturity: Stable.
```

## R4 — Append-only decision log with constrained taxonomy

```text
Requirement: Item- and repo-scoped append-only events for a small consumed
  vocabulary: decision, blocker, verification, lesson, coordination-failure,
  claim/handoff lifecycle, sprint boundary. Free-form detail lives in the
  payload, not new types.
Problem solved: Decision recall on resume (bundles), and the sole feed for
  knowledge distillation (R7).
Evidence of repeated use: 402 decision events consumed by every bundle;
  kctl extraction watermark over the event stream.
Consequence if absent: Decisions re-derived or lost; knowledge pipeline
  starves.
Minimum acceptable behaviour: append + list by item/type/time; type
  vocabulary is closed (extension = deliberate schema act).
Current Vuoro implementation: sprintctl event table (free-form type — 33
  observed types, ~8 consumed).
Implementation details that are NOT requirements: the open taxonomy (it is
  an observed defect); source_type actor/daemon/system split.
Maturity: Stable (vocabulary closure is the one change from current).
```

## R5 — Execution queue with fenced leases, idempotency, and isolated workspaces

```text
Requirement: A durable action queue for unattended agent execution:
  admission control (rate/chain limits), exclusive claim with fenced renew,
  sweep-based requeue of dead claims, idempotent mutation with duplicate
  replay, and per-dispatch isolated git worktrees under an enforced tool/path
  ACL with post-run diff validation.
Problem solved: Safe unattended execution; crash recovery without manual
  triage; duplicate-suppression for retried commands.
Evidence of repeated use: Deployed actionq-server + daemon; smoke configs
  against real projects; crash-evidence recovery paths; systemd sweep timer;
  ACL denies (push/merge/curl/kubectl) standing.
Direct queue inspection (2026-07-23, read-only via CNPG pod exec — closes
  the assessment's access gap): 23 live actions total, all scope-iterate
  (18 in a 5-project pilot burst 2026-05-08→14; 5 on 2026-07-18). Outcomes:
  3 completed, 4 failed, 10 admission-rejected (validation working), 6
  cancelled — 2 of them "superseded by direct completion", i.e. the work
  bypassed the queue. 17 claims by 13 distinct daemon/dispatcher identities
  across vscode-shell and devbox. Zero requeue/sweep/expire/replay/
  duplicate/conflict events: the fenced-renew, sweep-requeue, and
  idempotency machinery has never fired on live data. Plus 6 single-action
  "demo" daemon schemas (2026-07-21, migration dataset) and 28 test schemas.
Consequence if absent: Unattended agents cannot be trusted with write access;
  the multi-agent operating mode collapses to supervised-only.
Minimum acceptable behaviour: the six capabilities above. Known accepted
  gap to carry verbatim: terminal transitions are not fenced (only renew is);
  any rebuild must either reproduce or consciously close this.
Current Vuoro implementation: actionq db.py/application.py; dispatcher
  worktree+ACL machinery (being re-homed into actionq).
Implementation details that are NOT requirements: session-event projection
  shape; heartbeat cadence; tmux supervision; harness adapter roster.
Maturity: **Split per the 2026-07-23 queue inspection** (the "effectively
  no real usage" branch of the review's decision rule). The demonstrated
  requirement is safe unattended/delegated execution with isolated
  worktrees + enforced ACL — that operating record is real and stays High.
  The particular actionq lease/fencing/idempotency design is Provisional:
  deployed and design-complete, but exercised only in pilot smoke runs,
  with no live firing of its safety machinery. Clean-room candidates are
  judged against the safety envelope, not this queue design.
```

## R6 — Cross-machine authority service with server-resolved identity

```text
Requirement: Domain state (R1–R5, R7) reachable from multiple machines
  across a trust boundary through authoritative served interfaces,
  optionally composed behind one client surface or gateway, where: identity
  is resolved server-side (never client-asserted), operations carry required
  authorities, catalog/compatibility is versioned and additive, secrets are
  never persisted/logged in transit, and schema migration authority is
  separated from runtime authority. One physical service is not required;
  the current unified Vuoro service is the reference implementation, not an
  acceptance criterion (this keeps H1–H3 genuinely open).
Problem solved: Devbox vs workstation trust separation with one source of
  truth; the pre-served alternative (per-machine SQLite) produced the
  recurring WAL/concurrency defect class (≥7 incidents) and cutover
  ceremony.
Evidence of repeated use: Live shared Postgres authority since 2026-04-29;
  workstation .envrc secret derivation; migration mid-flight by design.
Consequence if absent: Machine-local stores fork truth; credential handling
  ad hoc; the token-exposure incident class returns.
Minimum acceptable behaviour: served CRUD for the kernel domains + identity/
  authority gating + additive versioning + credential non-persistence +
  migration/runtime role split — whether provided by one service or by
  composed domain authorities.
Current Vuoro implementation: vuoro-service/-client, invocation v1/v2.
Implementation details that are NOT requirements: single-service topology;
  FastAPI/httpx; ETag catalog mechanics; operation aliases; adapter-wheel
  packaging; the full four-domain catalog breadth (serve what has
  consumers).
Maturity: Stable (concept + v1); Provisional (v2 transient credentials,
  days old).
```

## R7 — Knowledge distillation with bounded output

```text
Requirement: A pipeline from work events to a curated, rendered knowledge
  artifact that agents load by default (via AGENTS.md or equivalent):
  extract candidates from the decision log, one review-and-publish decision
  at the work boundary, supersession-based compaction under a size budget,
  and a 30-day decay on coordination-class candidates unless recovery-linked
  or promoted.
Problem solved: Cross-session/cross-month transfer of lessons — the only
  channel by which April lessons demonstrably reached July sessions.
Evidence of repeated use: 275 candidates, 173 published; review <1 day in
  168/195 cases; 1,010-line KB in every homelab-analytics session context.
Consequence if absent: Lessons decay with context windows; repeated
  mistakes (the recorded coordination-failure patterns) recur unrecorded.
Minimum acceptable behaviour: extract → single review+publish step →
  rendered artifact + machine-readable export; size budget; coordination
  decay per Output 4.
Current Vuoro implementation: kctl (with two-step approve→publish and no
  compaction — both changed by this spec).
Implementation details that are NOT requirements: the durable/coordination
  dual-stream schema; category enum; central body-free replication; the
  exact extract→review→render mechanism (substitutable — the requirement
  is durable lesson transfer, not this pipeline shape).
Maturity: Stable (local pipeline); Provisional (central/served layer).
  Requirement confidence Medium-high: KB context-loading proves
  distribution, not that particular entries changed decisions.
```

## R8 — Thin operator projection with owner-contract writes

```text
Requirement: A read-only composed view of the kernel domains (the two
  proven joins: sessions⋈items, dispatches⋈costs, plus lists), where any
  mutation is submitted through a domain-owner contract and the surface
  itself holds no authority.
Problem solved: Batch supervision (many agents, one glance) without a
  second write path to defend.
Evidence of repeated use: Deployed cockpit through 15 versions; write-
  surface policy held (only sprint-activate direct, executor disabled).
Consequence if absent: Operator falls back to N CLI invocations —
  tolerable solo, costly during batches.
Minimum acceptable behaviour: the joins + lists + dispatch submission;
  no authority.
Current Vuoro implementation: agent-cockpit (see Output 5 for pane-level
  retain/remove list).
Implementation details that are NOT requirements: Next.js; pane roster
  beyond Output 5's retained set; MCP endpoint; headroom panel.
Maturity: Provisional pending H5 (the CLI-only batch supervision test);
  the write-surface policy (no authority in the surface) is Stable. The
  15 deployed versions demonstrate development, not operator dependence —
  R8 is not an established kernel peer of claims and resume.
```

---

## Explicit non-requirements (Gate 2 — the requirement set no longer assumes these survive)

- Authority-command journal / remote decision arbitration (0 rows; review date or removal)
- Capability-receipt machinery (ratification-by-doc-commit is the accepted step)
- Audit central ingest + observation envelope (no consumer; repo-local NDJSON suffices)
- Audit event types that mirror other stores (`knowledge.landed`)
- Takeup occupancy events (keep only the dead-session sweep, folded into claims)
- Open event-type taxonomy; ref-type enum beyond doc/scope
- Claim heartbeat as client obligation; inspect/review/coordinate claim types
- Sprint kinds, multi-active sprints
- Operation aliases in the served catalog; `*.schema.compatibility` as client ops
- Cockpit: takeup pane, audit pane, MCP endpoint (pending decision), reconciliation executor (pending smoke target)
- All migration scaffolding: outbox, dual-write, shadow pilot, projection-reads flags, pilot cutover-evidence, ingest cursors — must carry sunset dates at cutover completion
