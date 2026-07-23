# Output 1 — Semantic Register

One row per workflow semantic. Scores are 0–3 per the plan's scoring model:
**DI** decision impact · **RV** recovery value · **RC** reconstruction cost avoided ·
**DV** discovery value · **MC** maintenance cost · **XS** external substitutability
(0 = commodity, 3 = highly specific). Scores support the disposition; they are not summed.

Consequential-consumption evidence is preferred over raw reads throughout
(plan §Workstream 1). "Served" = shared PostgreSQL authority read 2026-07-23.

## Work domain (sprintctl)

| # | Semantic | Owner | Producers → Consumers | Authority | DI | RV | RC | DV | MC | XS | Evidence (consequential use) | Disposition |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Work-item status + transition machine (`pending→active→done/blocked`) | sprintctl `db.py:23,779` | agents/CLI → next-work, dispatch, handoff, cockpit | Yes | 3 | 2 | 2 | 1 | 1 | 0 | 939 items; transitions gate next-work selection and dispatch prompts; illegal transitions raise | **Retain and stabilize** (requirement is commodity-shaped; implementation need not be bespoke) |
| 2 | Dependency blockers (`dep`) | sprintctl mig.8 | operator/agents → `→active` gate, handoff conflicts | Yes | 2 | 1 | 1 | 2 | 1 | 1 | 115 deps; unresolved blocker blocks activation (`db.py:837`); `[dependency-blocked]` conflicts surfaced in real 2026-07-22 bundle | **Retain and stabilize** |
| 3 | Sprint container (status planned/active/closed, kind active/backlog/archive) | sprintctl | operator/agents → scoping, takeup, render | Yes | 2 | 1 | 1 | 0 | 1 | 0 | 138 sprints; in practice a batch/scope label (92 in homelab-analytics; July "verification" sprints opened+closed same day) | **Simplify** — sprint ≈ work batch; `kind` + multi-active add ceremony beyond observed use |
| 4 | Exclusive claims + claim tokens (proof = id+token) | sprintctl mig.2/4/6, `pg.py` | claim start/handoff → status-change gate, dispatch skills | Yes | 3 | 3 | 2 | 1 | 3 | 3 | Gates every mutation under claim (`db.py:806-845`); orchestrator-owned tokens kept from subagents (dispatch-build skill); 2026-07-08 recovery takeovers; 2 real token-exposure incidents drove transport redesign | **Retain and stabilize** — the single most load-bearing semantic; simplify lifecycle (see 5) |
| 5 | Claim heartbeat + TTL expiry | sprintctl | sessions → staleness display, (intended) sweep | Weak | 1 | 1 | 0 | 0 | 2 | 1 | **89/91 served claims expired-but-active**; nothing consequential has depended on heartbeat freshness; default TTL 300 s routinely outlived | **Add decay** — make expiry authoritative via server-side sweep; drop heartbeat as a client obligation or fold into command activity |
| 6 | Claim handoff (rotate/transfer) | sprintctl `cli.py:6228` | outgoing session → incoming session | Yes | 3 | 3 | 2 | 1 | 2 | 3 | 32 claim-handoff events Jul 8–21; ownership continuity across 10-agent batches; repeated "previous proof unavailable → explicit adopt" shows both use and friction | **Retain and stabilize**; fix proof-loss path (served recovery) rather than adding ceremony |
| 7 | Local claim-recovery sidecars | sprintctl `cli.py:376-433` | local mode only → `claim recover` | Yes | 2 | 3 | 1 | 0 | 1 | 3 | Local-mode only; superseded by served recovery path in flight | **Retain as provisional** until served equivalent proven, then remove |
| 8 | Session identity triple (runtime_session_id / instance_id / host+pid) | sprintctl | env detection → claim matching, takeup sweep | Yes | 2 | 2 | 1 | 0 | 1 | 2 | Enables `claim resume` matching and dead-session sweep | **Retain** as part of claims (not an independent semantic) |
| 9 | Worktree/branch/commit/PR advisory metadata on claims | sprintctl mig.4 | claim start → resume, cockpit worktree pane | No | 1 | 2 | 2 | 1 | 1 | 1 | Locates in-flight worktrees on resume; advisory by design | **Retain** (cheap, consumed); explicitly non-authoritative |
| 10 | Handoff bundle (summary, conflicts, recent decisions, next action, shutdown protocol) | sprintctl `cli.py:6682` | `handoff` → next session | No (projection) | 3 | 3 | 3 | 2 | 2 | 2 | 30 handoff-generated events; real 2026-07-22 bundle flagged `[unclaimed-active-work]` and prescribed next action; this is the reconstruction-avoidance mechanism itself | **Retain and stabilize; simplify contract** — 20+ top-level fields; `delta_since_last_handoff`, `freshness`, dual JSON/text parity have no observed consequential reader |
| 11 | `session resume` / `usage --context` contract | sprintctl `cli.py:4379,7270` | CLI → resuming agent | No | 3 | 3 | 3 | 1 | 2 | 2 | Prescribed resume path in every bundle; consumed by skills (sprint-resume, task-pickup) | **Retain and stabilize** |
| 12 | Append-only event log (decisions, notes, blockers…) | sprintctl `db.py:74` | agents → handoff recent-decisions, kctl extraction | Yes (append) | 2 | 2 | 2 | 2 | 1 | 1 | 402 decisions; recent-decisions consumed in every bundle; sole feed for kctl extraction | **Retain and stabilize** the log; **simplify the taxonomy** (see 13) |
| 13 | Free-form `event_type` taxonomy | sprintctl (unconstrained) | agents → (mostly nothing) | No | 1 | 0 | 0 | 1 | 2 | 0 | 33 distinct types; near-duplicates (lesson/lesson-learned, pattern/pattern-noted, decision/verdict/design_note/architecture); one-offs; only ~8 types consumed anywhere | **Simplify** — constrain to consumed set (decision, blocker, verification, claim-handoff, handoff-generated, lesson-learned, coordination-failure, sprint-boundary); everything else = tags in payload |
| 14 | Refs (`pr/issue/doc/other/file/glob/manifest`) | sprintctl mig.7/10 | agents → work context, reconcile skill | No | 1 | 1 | 1 | 1 | 1 | 0 | 317 refs, 303 = `doc`; `pr`/`issue` types unused | **Simplify** — refs ≈ doc links; collapse type enum, keep scope refs only if dispatch scoping consumes them |
| 15 | Takeup / release (sprint occupancy events) + sweep | sprintctl `cli.py:3607-3990` | sessions/daemon → occupancy display, dead-session sweep | Yes (weak) | 1 | 2 | 1 | 1 | 2 | 2 | 8 taken-up / 5 released events (all July); sweep cross-checks live actionq sessions — the sweep is the valuable part; occupancy duplicates claim semantics at sprint level | **Demote** — keep the liveness sweep, fold occupancy into claims or drop the separate event pair; cockpit pane replaceable |
| 16 | Authority-command journal + remote decisions | sprintctl `authority.py` | (opt-in, mode=off everywhere) | Intended | 0 | 0 | 0 | 0 | 2 | 3 | `authority_decision` table: **0 rows**; mode off in every repo marker | **Remove or retain as provisional with expiry** — speculative capability; +4,907-line arbitration commit has no operational record yet (migration-dataset caveat: built for the served cutover; give it a review date, not permanence) |
| 17 | Capability receipts (drafted→accepted, sha256-pinned artifacts) | sprintctl `contracts.py` + skills | sprint-close skill → operator ratification | Intended | 1 | 0 | 0 | 1 | 2 | 3 | 4 `capability-receipt-drafted` events, single day (2026-07-14); actual ratification happens as git doc commits ("ratify" commits in agentops) | **Demote to projection** — ratification-by-doc-commit is the working mechanism; receipts add a parallel ceremony with one exercise |
| 18 | Aggregate UUIDs / repository identity | sprintctl mig.9-ish, `pg.py` | migration + cross-repo joins | Yes | 1 | 0 | 0 | 0 | 1 | 0 | Required by shared authority (multi-repo keying) | **Retain** (essential constraint of shared substrate) |
| 19 | Outbox / dual-write / shadow pilot / projection-reads / pilot cutover evidence | sprintctl (multiple modules) | migration machinery | No | – | – | – | – | 3 | – | Migration dataset by definition | **Migration-temporary** — must carry explicit sunset at cutover completion (plan Gate 3) |
| 20 | Sprint snapshots / `render` documents | sprintctl | render → committed docs | No | 1 | 1 | 1 | 1 | 1 | 0 | Committed phase snapshots; rebuildable | **Internal** (rebuildable projection) |

## Execution domain (actionq / dispatcher)

| # | Semantic | Owner | Producers → Consumers | Authority | DI | RV | RC | DV | MC | XS | Evidence | Disposition |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 21 | Action lifecycle (`pending→claimed→terminal`) + priority queue claim (`SKIP LOCKED`) | actionq `db.py:599` | enqueue/daemon → execution | Yes | 3 | 2 | 1 | 0 | 1 | 1 | Admission control (rate limits, chain depth); mutual exclusion for unattended dispatch | **Retain and stabilize** |
| 22 | Claim renew fencing (`claimed_by` check) + sweep requeue | actionq `db.py:661,899` | workers/timer → lease authority | Yes | 3 | 3 | 1 | 0 | 1 | 2 | Only fenced op; sweep is the liveness authority; systemd timer shipped | **Retain and stabilize**; document (or fix) the known unfenced-terminal-transition gap explicitly in the spec |
| 23 | Fingerprint idempotency (sha256 args+basis, replay/conflict) | actionq `application.py:60-347` | served mutations | Yes | 3 | 1 | 1 | 0 | 1 | 2 | Duplicate-mutation prevention with durable decision refs | **Retain and stabilize** |
| 24 | Session events / heartbeat projection | actionq `db.py:136-268` | daemon → cockpit claims pane, takeup sweep | No | 1 | 1 | 1 | 0 | 1 | 1 | Explicitly informational; claims are the liveness authority | **Internal** (projection; correct as designed) |
| 25 | Worktree-per-dispatch isolation + ACL + diff validation | dispatcher/actionq | daemon → safe unattended edits | Yes | 3 | 2 | 1 | 1 | 2 | 2 | scope-iterate prompt + ACL enforced; prevents agent escape/overlap | **Retain and stabilize** (re-homing dispatcher→actionq is migration work) |
| 26 | Trusted-caller + model-alias routing (verified providers, no implicit cross-provider fallback) | actionq/agentops routing | config → harness selection | Yes | 2 | 0 | 0 | 0 | 2 | 2 | Routes real dispatches; canonical model-routing.json | **Retain as provisional** — policy churns with model market; keep data-driven |
| 27 | Evidence exhaust (git evidence, session capsules, usage-limit tails) | actionq | daemon crash paths → forensics | No | 1 | 2 | 1 | 1 | 1 | 2 | Fails open; consumed in stale-session recovery messages | **Retain as internal** |

## Knowledge domain (kctl) — see also Output 4

| # | Semantic | Owner | Producers → Consumers | Authority | DI | RV | RC | DV | MC | XS | Evidence | Disposition |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 28 | Candidate pipeline (extract→review→publish), durable stream | kctl | sprint events → knowledge entries | Yes | 2 | 0 | 2 | 3 | 2 | 2 | 275 candidates across stores; 168/195 reviewed <1 day; published output consumed via AGENTS.md context load | **Retain; simplify ceremony** (merge approve+publish; see Output 4) |
| 29 | Coordination knowledge stream (`candidate_kind=coordination`) | kctl mig.5/6 | claim/coordination events → review | Yes | 1 | 1 | 0 | 1 | 2 | 3 | 22 coordination candidates ecosystem-wide, 55–62% rejected, 4 published | **Add decay** (30-day expiry unless promoted; Output 4) |
| 30 | Supersession links (acyclic, immutable retries) | kctl | publish → KB compaction (unused so far) | Yes | 1 | 0 | 0 | 1 | 1 | 1 | Mechanism exists; no compaction consumer yet | **Retain** — becomes the compaction primitive (Output 4) |
| 31 | knowledge-artifact/v1 export + rendered KB | kctl | export/render → cockpit, AGENTS.md | No | 2 | 0 | 2 | 2 | 1 | 1 | 1,010-line KB referenced by AGENTS.md → in-context every session | **Retain and stabilize** (with size budget, Output 4) |
| 32 | Central review schema + Vuoro knowledge adapter | kctl `central_schema.py` | (migration) | Yes | – | – | – | – | 2 | – | Never exercised live; body-free central design is sound | **Migration-provisional** — admit as Provisional with usage telemetry |

## Audit domain (auditctl)

| # | Semantic | Owner | Producers → Consumers | Authority | DI | RV | RC | DV | MC | XS | Evidence | Disposition |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 33 | Repo-local audit log (SQLite + NDJSON shards) | auditctl | git hooks, sprintctl publisher → `list/render` only | Append | 1 | 1 | 1 | 0 | 1 | 1 | 101 events; 87 = `knowledge.landed` duplicating kctl; **no automated consumer anywhere**; homelab-analytics logged 7 events in 3 months | **Simplify** — keep the cheap local append log; drop event types that mirror other stores unless a consumer appears |
| 34 | Observation envelope (origin stream/seq, event-id, causation) + central ingest (gap detection, global admission, receipts) | auditctl mig.2 + central | (never run live) | Yes | 0 | 0 | 0 | 0 | 3 | 3 | Design-complete, unexercised; all live DBs at schema v1 with bare events | **Retain as provisional with expiry** — freeze further investment until a consumer (or compliance need) is named; candidate **remove** at review date |

## Serving substrate (vuoro) — classified under the admission policy

| # | Semantic | Class | Evidence | Disposition |
|---|---|---|---|---|
| 35 | Handshake / catalog (ETag, stale-catalog 409) / invocation-v1 envelopes / error vocabulary | **Stable** | Only in-tree consumer is sprintctl, but every served route depends on it; additive-compat policy enforced by tests | **Retain and stabilize** |
| 36 | Server-resolved identity, env binding, authority membership, deny-all default | **Stable** | Real trust constraint (devbox vs workstation); enforced in dispatch order | **Retain and stabilize** |
| 37 | invocation/v2 transient-credential transport | **Provisional** | Landed 2026-07-23; adversarial redaction tests; driven by 2 real token-exposure incidents | **Retain as provisional** with telemetry + promotion criteria (per admission policy) |
| 38 | Domain adapter catalogs (work/execution/knowledge/audit operations) | **Provisional** | Much of catalog served-but-not-consumed — expected mid-migration | **Retain as provisional**; require consumer evidence per operation before Stable promotion |
| 39 | Operation aliases (`execution.claim` vs `execution.action.claim`, `knowledge.read/review`, `work.read.next-work` vs `work.project.next-work`) | Internal | Duplicate surfaces; DeprecationMetadata exists | **Remove** (deprecate before any external consumer appears — cheapest moment is now) |
| 40 | `*.schema.compatibility` ops, `work.pilot.cutover-evidence` | Internal / migration | No client callers; composition-time use only | **Demote to internal**; pilot op is migration-temporary |
| 41 | Runtime-role vs migration-role DSN separation; pinned checksum-verified adapter wheels | **Stable** | Enforced in deploy + composition verification | **Retain and stabilize** (essential constraint) |

## Operator surface — see Output 5 for per-pane dispositions.

---

### Reading the register against Gate 1/2

**Kernel (Gate 1):** rows 1, 2, 4, 6, 10, 11, 12 (with 13 simplified), 21, 22, 23, 25, 28, 31, 35, 36, 41.

**Compression set (Gate 2):** rows 3, 5, 13, 14, 15, 16, 17, 24 (already internal), 29, 33, 34, 39, 40 — plus the migration-temporary scaffolding in row 19, which the requirement set must not assume survives.
