# Output 2 — Workflow Economics Report

Covers Workstream 2 (session reconstruction) and Workstream 3 (state economics).
Time estimates use the plan's bands: <5 m · 5–15 m · 15–60 m · 1–4 h · >4 h.

## 1. Activity baseline

Served-authority write activity (events / item updates per month):

| Month | Events | Item updates | Character |
|---|---|---|---|
| 2026-03 | 210 | 190 | homelab-analytics steady work + sprintctl bootstrap |
| 2026-04 | 277 | 405 | Peak steady-state: homelab-analytics delivery + tool phases |
| 2026-05 | 6 | 32 | Trough — ecosystem essentially idle |
| 2026-06 | 1 | 0 | Trough |
| 2026-07 | 640 | 312 | Served-substrate migration (migration dataset) |

Interpretation discipline: the May–June trough means **the workflow system was
not needed for two months and nothing broke** — state kept, no reconciliation
debt accrued on resume in July. That is simultaneously evidence that (a) the
durable store survives disuse gracefully (a real benefit over memory), and
(b) steady-state carrying cost must be judged against long idle periods, not
continuous use.

## 2. Workstream 2 — Session reconstruction (retrospective sample)

12 documented resumption incidents were identified from event payloads,
committed bundles, and session notes. No timed with/without pairs exist
(Gate 4 is Partial); counterfactual estimates are analytical, derived from
counting the sources a cold session would need without the resume surface.

### Sample

| # | Date | Project | Incident | Vuoro surface used |
|---|---|---|---|---|
| 1–5 | 2026-07-08 | homelab-analytics | 5 recovery takeovers after a lost claude-agent session (items #730–#734), `mode=rotate` | claim records + `claim resume` |
| 6 | 2026-07-14 | sprintctl | Ops-upgrade wave: ~20 claim-handoffs across ~8 actors incl. repeated "previous proof was unavailable; explicit adopt"; 6 handoff bundles same day | claim handoff + bundles |
| 7 | 2026-07-17 | sprintctl | Remote-availability / lifecycle verification sprints; 4 bundles | handoff + sprint status |
| 8 | 2026-07-21 | sprintctl/vuoro | 10-agent codex dispatch batch (942 tool calls, 4 independent verification rounds); claims #155–#157 closed items #1185–#1206 | orchestrator-owned claims, done-from-claim, kctl capture |
| 9 | 2026-07-22 | sprintctl (#1195) | End-of-day handoff, next session resumed served-route work | `handoff-1195-served-backend-2026-07-22-eod.txt` |
| 10 | 2026-04 (1–13) | homelab-analytics | 31 handoff-generated events during peak delivery | bundles |
| 11 | 2026-04-23 | homelab-analytics | claim-recovery directory activity (crash recovery) | local recovery sidecars |
| 12 | 2026-07-19→23 | ecosystem | Cold resume after documentation/backlog work into #1195 continuation | sprint list + continuation-blockers plan + bundle |

### Counterfactual detail (incident 9, worked example)

```text
Project: sprintctl (#1195 served-backend cutover)
Session type: end-of-day handoff → next-morning resume
Vuoro-assisted resume: read one bundle (54 lines): summary 24/22/1/1, active item,
  2 conflicts ([unclaimed-active-work], [dependency-blocked]), 5 recent decisions
  (incl. "7 remaining served routes reconciled into 4 groups, 3 buildable now,
  claim-proof channel cross-repo blocked"), explicit NEXT ACTION. Band: <5 min.
Manual reconstruction: git log across sprintctl + vuoro + agentops (group A/B
  commits landed same day); agentops continuation-blockers + ratification docs;
  no single artifact states which group remains or that the claim-proof channel
  is blocked cross-repo. Sources ≥3 repos, ≥6 artifacts. Band: 15–60 min, with
  residual ambiguity about remaining scope and blocker status.
Confidence difference: high vs medium (manual risks re-doing group B or
  attempting the blocked claim-proof group).
Available only through Vuoro: conflict detection (unclaimed active item),
  decision trail linking scope groups to buildability.
Presented but not action-affecting: freshness block, delta-since-last-handoff,
  most of the 50-event tail.
Errors/ambiguities: none observed in the bundle; item counts matched git.
```

### Counterfactual detail (incidents 1–5)

Without claim records, a recovering operator/agent must inspect worktrees and
branches to find five in-flight items and guess ownership; the risk is not
mainly time (15–60 min) but **duplicated or conflicting work** — precisely
what claims exist to prevent. The recovery takeover completed as five rotate
operations (<5 min each) with ownership provable throughout.

### An additional honest datapoint

This assessment itself is a cold-agent reconstruction: establishing ecosystem
state from raw repos took ~2 h of wall time *with six parallel discovery
agents*; the served sprint list + one bundle yielded current operational state
in minutes. That asymmetry is the product's core claim, and it held.

### Workstream 2 conclusions

- Resume value is real and concentrated in three artifacts: the **bundle**
  (conflicts + decisions + next action), **claims** (ownership + in-flight
  location), and the **sprint/item lists**. Everything else in the resume
  surface was not observed to change a decision.
- The counterfactual gap widens with (a) number of concurrent agents and
  (b) time since last activity. Single-agent, same-day resumes could plausibly
  be served by git + an EOD note (the two `handoff-1195-*.txt` files are
  nearly that); multi-agent and post-trough resumes could not.
- Friction finding: the claim-proof loss path ("previous proof unavailable")
  recurred ~8× on 2026-07-14 — the ceremony cost of proof transport predates
  its served fix. This is a defect-shaped cost, not a semantic-shaped one.

## 3. Workstream 3 — Ledger

### Costs (evidence-backed)

| Cost | Evidence | Band (per occurrence) | Frequency observed |
|---|---|---|---|
| Capture during work (claim/note/done/handoff) | Skill flows; event volumes (~1,100 events over ~80 active days) | <5 m | Continuous during active work |
| Stale-state repair | 89 expired-active claims (unrepaired — cost avoided by ignoring, which itself argues heartbeat is non-load-bearing); stale-claim triage lines in bundles | <5 m | Occasional |
| Claim-proof loss ceremony | ~8 forced adopt/rotate cycles 2026-07-14 | 5–15 m each | Burst; addressed by served recovery + v2 transport |
| Schema maintenance | ~30 schema versions ecosystem-wide (sprintctl sqlite 11 + pg 3 + outbox 1; kctl 7 + central 3; auditctl 2 + 2; actionq 1; vuoro protocol/envelopes); kctl migration-6 drift needed a repair migration | 1–4 h per migration incident | ~Monthly in steady state; weekly during migration |
| Recurring concurrency-defect class | Same WAL-busy/serialization fix landed independently in sprintctl (×2), auditctl, kctl-adjacent outbox; plus serialize claim admission, event-id admission, schema bootstrap | 1–4 h each | ≥7 incidents in window |
| Cross-repo presentation coupling | Skill/template syncs (935ccbf 33 files; 050a192 55 files), "align/link" doc-pairs ×4 repos, render-guidance sync ×5 repos | 15–60 m each | Per convention change |
| Unused-surface carrying cost | authority-command journal, capability receipts, audit central ingest, MCP endpoint, reconciliation executor (disabled) | — | Standing (tests + docs + review attention) |
| Documentation drift repair | CHANGELOG lag, version 0.1.0/0.2.0 drift, cockpit nav drift, stale screenshots | 5–15 m each | Ongoing low level |

### Benefits (evidence-backed)

| Benefit | Evidence | Band (per incident) | Frequency |
|---|---|---|---|
| Duplicated/conflicting work prevented | Claim gating in 10-agent batch (incident 8); `[unclaimed-active-work]` conflict surfacing; exclusive-claim admission serialization | 15–60 m per prevented collision (unbounded worst case: corrupted parallel edits) | Every multi-agent batch |
| Interrupted-session recovery | Incidents 1–5, 11; recovery sidecars; rotate takeovers | 15–60 m avoided each + error avoidance | ~Weekly during active work |
| Deterministic resume | Incidents 6–10, 12; bundle counterfactual above | 10–60 m avoided per resume | Most sessions after gaps |
| Handoffs without re-analysis | 32 claim-handoff events; orchestrator→verifier chains 2026-07-14/21 | 5–15 m each | Per delegation |
| Discovery: missing/blocked work | Conflicts block in bundles (2 real flags 2026-07-22); dependency-blocked surfacing; `maintain carryover` (38 events) | 5–15 m each; occasionally prevents wrong next action | Per resume |
| Knowledge reuse | 1,010-line rendered KB in AGENTS.md context (homelab-analytics); 173 published entries; 12 committed KB publication commits | Diffuse; the only channel by which April lessons reached July sessions | Every session (passive) |
| Unsafe-action blocking | Transition machine rejections; dispatch ACL denies (push/merge/reset/curl/kubectl); admission rate limits | Unbounded worst case | Standing |
| Survived the 2-month trough | July resume found consistent state; no reconciliation debt on re-entry | 1–4 h avoided (est.) | Once observed |

### Balance judgment

- **During multi-agent bursts** the ledger is clearly positive: capture costs
  are minutes; each burst shows multiple prevented-collision and handoff
  events whose reconstruction alternative is 15–60 m *plus error risk*.
- **During single-agent steady work** the ledger is approximately neutral:
  bundles help across day boundaries; much of the event capture (33-type
  taxonomy, receipts, audit mirrors) is write-only.
- **The net-negative pockets** are precisely the compression set of Output 1:
  unused authority/receipt/audit-central machinery, taxonomy sprawl, and the
  recurring local-store concurrency defect class (an architecture cost the
  served substrate is expected to retire — verify post-cutover).
