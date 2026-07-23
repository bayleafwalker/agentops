# Vuoro Pre-Clean-Room Assessment — Results

Status: complete (retrospective execution, 2026-07-23)
Plan: [../../plans/Vuoro-Pre-Clean-Room-Assessment-Plan.md](../../plans/Vuoro-Pre-Clean-Room-Assessment-Plan.md)

## Method and evidence base

The plan's 30–60 day observation window was executed retrospectively against the
full operating record rather than prospectively. Evidence sources:

| Source | What it provided |
|---|---|
| Served PostgreSQL authority (sprintctl-pg, read-only) | 12 repos, 939 work items, 1,134 events, 91 claims, 317 refs, 115 deps; full event/claim/ref/dep distributions and monthly write activity 2026-03 → 2026-07 |
| Frozen local snapshots (`.sprintctl.db.frozen-*`, 2026-04-29 cutover) | Pre-cutover steady-state usage: homelab-analytics 78 sprints / 492 items / 282 events / 69 claims (2026-03-28 → 2026-04-26) |
| Live kctl stores (5 DBs) | 275 knowledge candidates, 173 published entries, review-lag distribution, stream (durable/coordination) outcomes |
| Live auditctl stores (4 DBs + `_artifacts` NDJSON) | 101 audit events total; type distribution; central-layer non-use |
| Real resume artifacts | `handoff-1195-served-backend-2026-07-22*.txt`, committed `handoff-*.json` bundles, claim-handoff event payloads, `.agents/sessions/2026-07-21-vuoro-served-substrate-codex-dispatch.md` (10-agent batch, 942 tool calls) |
| Full commit ledgers, 90-day window | sprintctl 99, agentops 97, appservice 57 (filtered), actionq 36, kctl 19, auditctl 14, vuoro 12, actionq-dispatcher 8 commits, with per-commit file/line stats and issue clustering |
| Source-level semantic inventory | All five tool repos plus vuoro service/client and cockpit, at file:line granularity |

Known gaps: no *timed* with/without resume measurements exist; the
Workstream 2 counterfactual is analytical (see economics report §2).
Only one candidate incident has an explicit assisted resume timing band and no
candidate has a full assisted-versus-manual paired timing capture with protocol
fields.
The actionq CNPG LoadBalancer (5432) is filtered from assessment hosts,
but the queue authority was inspected read-only via CNPG pod exec on
2026-07-23, closing the original queue-volume gap — results under
"Path to freeze" below and in the spec's R5.

**Migration separation (plan requirement, confirmed by operator mid-assessment):**
invocation/v2 and the served-substrate cutover are days old and mid-flight.
All served-but-not-yet-consumed catalog surface, pilot/outbox/shadow/dualwrite
scaffolding, and the July commit surge are classified as **migration dataset**,
not steady-state. Steady-state conclusions rest on 2026-03 → 2026-06 plus
non-migration July work.

## Outputs (plan §Required outputs)

1. [Semantic register](01-semantic-register.md)
2. [Workflow economics report](02-workflow-economics.md) (includes Workstream 2 session-reconstruction results)
3. [Architecture-tax report](03-architecture-tax.md) (Workstreams 4 + 5)
4. [kctl retention recommendation](04-kctl-retention.md) (Workstream 6)
5. [Cockpit disposition](05-cockpit-disposition.md) (Workstream 7)
6. [Reduced workflow specification](06-reduced-workflow-specification.md) — the clean-room handoff
7. [Open hypotheses](07-open-hypotheses.md)

## Headline findings

1. **A real kernel exists and is small.** Eight capabilities carry essentially
   all observed consequential decisions: item lifecycle + dependency gating;
   exclusive claims with proof tokens; the deterministic resume/handoff bundle;
   the append-only decision log; queue admission with fenced renew + sweep +
   worktree isolation; idempotency fingerprints; the cross-machine authority
   service with server-resolved identity; and the knowledge distillation
   pipeline whose rendered output is consumed via AGENTS.md every session.
   (Post-assessment caveat: the 2026-07-23 queue inspection found the
   queue-specific machinery — fenced renew, sweep, idempotency — unexercised
   in live use; R5 is split accordingly. See "Path to freeze".)

2. **Usage is bursty and substantially self-referential.** Served-backend
   activity: Mar 210 events, Apr 277, May 6, Jun 1, Jul 640. The May–June
   trough shows the ecosystem operated ~2 months with almost no state writes.
   homelab-analytics (531 items) is the only large non-toolchain consumer;
   most other backlogs track the toolchain building itself.

3. **Claim value concentrates at acquisition and transfer, not upkeep.**
   89 of 91 served claims are expired-but-active; heartbeat/TTL hygiene is
   not maintained and nothing consequential has depended on it. Claim-start
   conflict gating and handoff/recovery are repeatedly consequential
   (2026-07-08 recovery takeovers; orchestrator-owned claims in 10-agent
   batches; two real token-exposure incidents driving the transport redesign).

4. **Semantic expansion has outrun consumption.** 33 free-form event types
   (heavy near-duplication) vs ~8 consumed by any downstream surface; the
   `authority_decision` journal has 0 rows; capability receipts were exercised
   once (4 drafts, one day) while actual ratification happens via git doc
   commits; audit central ingest machinery (2 schema layers, crash-safe
   sequencing, global admission) has never processed live data; 303 of 317
   refs are plain doc links.

5. **auditctl is currently a write-only mirror.** 101 events, 87 of them
   `knowledge.landed` duplicating kctl state; no automated consumer anywhere.
   Its sophisticated central-ingest contract is design-complete but
   unexercised.

6. **Blast radius is mostly healthy** (narrow trivial / broad difficult), with
   two exceptions: the skill/template sync mechanism and replicated
   "align/link" doc-pairs give presentation-level changes multi-repo
   footprints; and a recurring defect class (SQLite WAL/busy + concurrency
   serialization repaired independently in ≥4 repos) is architecture-shaped
   cost of local-first stores under concurrent agents.

7. **kctl's problem is not retention of candidates** (168/195 reviewed <1 day)
   but publish ceremony (10 approved : 1 published centrally) and monotonic
   growth of published output with no compaction.

## Decision-gate status

| Gate | Status |
|---|---|
| 1 — Kernel definition | **Passed** — evidence-backed kernel list in the reduced spec |
| 2 — Compression decisions | **Passed** — dispositions marked in the semantic register |
| 3 — Migration normalization | **Passed** — migration dataset separated throughout |
| 4 — Counterfactual established | **Partial** — retrospective sample of 12 documented resumption incidents (5 reviewed in [`06`](06-reduced-workflow-specification.md#five-cold-resume-observations-observational-status-toward-gate-4), none protocol-complete, only 1 with any timing at all and that timing is analytical/retrospective) + **2 genuinely live, protocol-complete timed observations** recorded 2026-07-23 (Observation 1: delegated shape, 3h30m idle gap; Observation 2: solo shape, 4h22m idle gap, first with a fully instrumented wall-clock — see [`08-resume-observations.md`](08-resume-observations.md)). Observation 1 and the retrospective audit's one timed incident describe **the same underlying event** (the 2026-07-22 #1195 EOD handoff into this session) — see `08`'s cross-reference note for the resulting timing discrepancy. Net: 2 of 5 live timed rows; the solo requirement is now satisfied. Still needed: a multi-agent-batch resume, and enough more to reach five — none may be retrospective reconstructions. |
| 5 — Clean-room input frozen | **Draft-for-freeze** — spec is complete; freeze after Gate 4 completes (the actionq volume inspection completed 2026-07-23; R5 split applied) |

## Path to freeze (per 2026-07-23 review reconciliation)

Two substantive evidence gates remain; two freeze-discipline edits are
already applied in the spec (H8 model-sensitivity tags; session-note/v1
classified as a provisional R3 input surface with H9 recorded).

**1. Five timed resume observations** during normal work, each recording:

```text
repo · idle duration · session shape (solo/delegated/multi-agent) ·
resume surface used · time to confident next action · conflicts or
blockers surfaced · other sources consulted · ambiguity remaining ·
H9: did an authored session note change/accelerate the next action?
```

Include at least one multi-agent resume and one resume after a meaningful
idle gap — five same-day solo resumptions do not satisfy the gate. Paired
blinded shadow reconstructions (a cold agent reconstructing the same
point-in-time state without bundle access) would strengthen the sample
but are optional, not required.

**2. actionq queue-volume inspection — COMPLETED 2026-07-23** (read-only
via CNPG pod exec; the LoadBalancer's 5432 is filtered from assessment
hosts but the Kubernetes API is not). Findings: 23 live actions ever, all
`scope-iterate` — 18 in a five-project pilot burst 2026-05-08→14, 5 on
2026-07-18. Outcomes: 3 completed, 4 failed, 10 admission-rejected, 6
cancelled (2 "superseded by direct completion" — the work bypassed the
queue). 17 claims by 13 distinct daemon/dispatcher identities. Zero
requeue/sweep/expire/replay/duplicate events: the fenced-renew, sweep,
and idempotency machinery has never fired on live data. Six single-action
"demo" daemon schemas (2026-07-21, migration dataset) and 28 test schemas.
Per the decision rule this is the **effectively-no-real-usage** branch:
the demonstrated requirement (safe unattended execution with isolated
worktrees + ACL) is split from the particular actionq lease/idempotency
design, which drops to Provisional. Applied in the spec's R5 and
confidence table.

After the resume observations complete: freeze Output 6 and only then begin the clean-room
comparison. Do not amend the frozen spec because a candidate tool has an
attractive feature, lacks claim proof, or makes a requirement
inconvenient — that inconvenience is what the comparison is meant to
reveal.
