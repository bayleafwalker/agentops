# Output 3 — Architecture-Tax Report

Covers Workstream 4 (change-origin classification) and Workstream 5
(blast radius). Dataset: full commit ledgers for the 90-day window
(2026-04-24 → 2026-07-23), which for every repo except appservice equals the
full history: sprintctl 99, agentops 97, appservice 57 (path-filtered),
actionq 36, kctl 19, auditctl 14, vuoro 12, actionq-dispatcher 8 = **342
commits** examined. appservice Renovate/homelab-ops bulk excluded.

## 1. Migration separation (Gate 3)

Migration dataset (served-substrate): all 12 vuoro commits; sprintctl ~15
(served routes, work adapter, authority identity, ingest cursors, schema
split); kctl ~13 (central schema, knowledge adapter, artifact exports);
auditctl ~8 (central ingest, observation adapter); actionq ~11 (schema
authority #1196, execution adapter #1197); dispatcher 2; agentops ~15
(ratifications, rollout materials, routing); appservice ~30 (vuoro-dev/shared
namespaces, schema gates, egress, role splits).

**≈106 of 342 commits (~31%) are migration**, and they dominate July
(the 640-event July surge in the authority is the same phenomenon).
Steady-state analysis below excludes them.

## 2. Workstream 4 — Change-origin classification (steady-state)

Remaining ~236 commits, classified by the plan's eight categories
(counts approximate; one commit may carry two categories — dominant chosen):

| Category | ≈Count | Representative evidence |
|---|---|---|
| 1. External-workflow pain | **~10 (4%)** | Native priority #1175; item description edit; render project-name default; takeup remote fix (b429e9a — the *only* tool change homelab-analytics forced in May–June) |
| 2. Essential environment constraint | ~25 | Trusted-caller routing; credential handling; runtime/migration role split; network policies; tmux supervision; backup/restore drills |
| 3. Defect correction | ~35 | WAL-busy retries ×3 repos; serialize claim admission / event-id admission / schema bootstrap; worktree-clean false positives; pg NDJSON round-trip |
| 4. Process-semantic expansion | ~40 | Remote command arbitration (+4,907 lines, unused so far); capability receipts (+1,879 + 2,165 template lines); session-capsule/reconciliation-proposal contracts; observation envelope; takeup protocol; Tier-0/Tier-1 context packets |
| 5. Vuoro-induced maintenance | ~30 | Client/wheel pin bumps; skill/template sync commits (33–55 files); "align/link" doc-pairs ×4 repos; render-guidance sync ×5 repos; kctl migration-6 drift repair |
| 6. Platform migration | (separated above) | — |
| 7. Operator surface | ~45 | Cockpit build-out (~25 agentops commits) + 10 appservice image bumps + headroom/layout/map/site work |
| 8. Speculative capability | ~15 | Authority-command journal; capability-receipt machinery; MCP endpoint (shipped disabled); reconciliation executor (shipped disabled); copilot harness stub; audit central ingest ahead of any consumer |

### The key test (automate / remove / accept)

The striking result is the **~4% share of category 1**. Stated precisely:
only ~10 steady-state commits had immediate consumer-project pain as their
dominant classified subject; most immediate change scope was
ecosystem-internal. This is a commit-subject classification, not a causal
effort measure — commit counts do not weigh effort, value, or causal
ancestry (one painful incident can spawn a long implementation chain), so
it should not be read as "only 4% of development was caused by workflow
pain." Even so read conservatively, the change budget is spent
overwhelmingly on the system itself (semantic expansion, operator surface,
self-induced maintenance) rather than on pain arriving from consumer
projects. For the externally-triggered features that do exist, the
automate-vs-remove-vs-accept hearing mostly favors the automation taken
(priority, description edit are cheap and consumed). But for category 4/8 the
hearing repeatedly favors *accept-the-step*:

- **Capability receipts**: the operator already ratifies via git doc commits
  ("docs(vuoro): ratify …"). Accepting that step (a doc commit) would have
  avoided ~4,000 lines of receipt machinery exercised once.
- **Authority-command journal**: 0 rows after landing; the arbitration
  decision it encodes is currently made by the operator synchronously.
- **Audit central ingest**: no consumer reads audit events; the repo-local
  NDJSON already satisfies the durable-record need at ~1% of the machinery.

## 3. Workstream 5 — Blast radius

### Group A — semantically trivial changes

| Change | Repos touched | Footprint | Verdict |
|---|---|---|---|
| Cockpit image bump | appservice only | 1 file, 1 line (×10 occurrences) | Healthy |
| Headroom display (% / reset times) | agentops only | 1–2 files | Healthy |
| Polling gate (pollAll) | agentops only | 6 files | Healthy |
| New knowledge category / render tweak | kctl only | 1–3 files | Healthy |
| Cockpit reads kctl knowledge | agentops + kctl contract doc | 10 files + artifact contract | Acceptable (contract was the right call vs scraping) |
| **Native priority adoption** | sprintctl + agentops + template tree | feature 8 files, then skill-sync 3 files ×2 repos | **Tax**: skill/template sync gives presentation-level conventions a multi-repo footprint |
| **"vuoro project guidance" render sync** | 5 repos, same commit replicated | 1–2 files each | **Tax**: generated-doc convention forces N-repo commits for one sentence |
| **Sprint activation from cockpit** | agentops + sprintctl (+250-line domain handler) | 2 repos | Defensible (authority boundary demanded domain ownership), but shows any cockpit write ≈ cross-repo contract work |

### Group B — inherently difficult changes

| Change | Repos | Footprint | Verdict |
|---|---|---|---|
| Claim-proof transport (#1195 + invocation/v2) | sprintctl (4 commits, 33 files, ~4.5k lines) + vuoro (2 commits, ~1k lines) + agentops ratification + pin bump | 3 repos | Proportionate: cross-host secret transport across a trust boundary is essential complexity; incident-driven (2 real token exposures) |
| Schema authority / migration gates (#1196) | actionq 37 files ~3.2k lines + appservice role gates | 2 repos | Proportionate |
| Authority migration per domain (#1197/#1199-#1202) | 1 domain repo + appservice each | 2 repos each | Healthy fan-out: no issue spanned >2 repos; adapters kept domain-owned |
| Ingest cursor scoping fix | sprintctl 22 files | 1 repo | Migration machinery gravity — acceptable if outbox/cursor layer is sunset post-cutover |
| Offline/recovery (daemon sweep, crash evidence) | actionq(+dispatcher) | 1–2 repos | Healthy |

### Interpretation (per plan matrix)

Narrow Group A (mostly) + broad-but-bounded Group B = **the expected healthy
pattern**, with two named exceptions:

1. **Template/skill sync gravity.** The shared skill tree turns any workflow
   convention change into an N-repo mechanical commit wave. This is
   architectural gravity for presentation-layer material. Candidate fixes for
   the clean-room spec: skills fetched at dispatch time from one canonical
   root (no per-repo copies), or accept version skew.
2. **Generated-guidance replication.** Deterministic per-repo rendered docs
   (project guidance) trade drift-detection for commit fan-out. The
   render+hash mechanism works; the question for the reduced spec is whether
   per-repo materialization is a requirement or an implementation detail.

The recurring concurrency-defect class (WAL/serialization, ≥7 incidents,
fixed independently per repo) is a third, quieter tax: it is the price of
five separate local-first stores. The served substrate should retire it —
**verify post-cutover that this defect class actually disappears**; if it
does not, the substrate's chief economic justification weakens.
