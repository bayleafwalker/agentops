<!-- Generated 2026-09-19 by workflow backlog-goal-state-reconcile (95 agents: a Sonnet assessor per item, an Opus refuter for every non-keep disposition, a Sonnet report). Read-only assessment: no sprintctl writes were made. Refine ticks of the devbox lane loop apply the upheld dispositions. -->

> **Coordinator notes (2026-09-19):**
> - The report's retire rows for #2214 and #1286 contradict each other: #2214 cites #1286 as its successor, but #1286 is itself retired. Treat #2214 as retire_goal_state with no successor. The Beads option survives only through dossier §15 trigger 8.
> - #2194 (POL-004) was not verified on its own. The verified siblings #2195 and #2196 fold it into their reject batch, so apply retire_goal_state (TS-1) together with #2193, #2195, #2196 and #2212.
> - #1281 (session-note hook wiring) is listed as keep, but the target-state path S4 retires session mechanization, which is the same reason #1262 is retired. Implement ticks must not take #1281. A refine tick re-decides it against S4 (expected outcome: retire_goal_state).
> - Per-item raw assessments and verifier verdicts: `2026-09-19-backlog-reconciliation.items.json`.

# Backlog Reconciliation Report — 2026-09-19

*Disposition = verifier's `corrected_disposition` where verifier did not uphold; otherwise assessor's disposition. All statuses are sprintctl live-state as read by the assessor/verifier pairs, not re-verified here.*

## RETIRE — superseded / goal-state (sprintctl write only, no build)

| id | title | reason | next action |
|---|---|---|---|
| 1261 | Execute accepted reconciliation proposals via sprintctl authority | Host (agent-cockpit) + dep #1187 both deleted (aa555d6, appservice#1647); TS-1/TS-2 | local: close retired |
| 1262 | Live session-mechanization dogfood / P3 cutover | S4 retires session mechanization outright; nothing ran | local: close retired w/ 1261 |
| 1275 | Isolated vuoro-dev + same-digest promotion | vuoro-dev app+db deleted (2d8c7471, 890a8781); disposition-register vuoro-dev row | local: close retired |
| 1277 | Human-only doc ratification gate | model/README.md removes `ratified` state; templates/dispatch deleted (0baa680/31a2e3f) | local: close retired |
| 1286 | Stage-2 Beads+Restate fork/projection slice | Dossier §7.3 keeps sprintctl authority; §15 preserves option behind trigger 8 (not fired) | local: close retired; reopen only if trigger 8 fires |
| 1287 | Enforce reduced-profile deployment shape + cost records | Owner decision D1 settled it; target-state S2-S5 deletes surfaces outright; TS-7 makes cost a derived query | local: close retired |
| 1288 | 14-day S-DORMANT observation | Candidate state moved 138/165/74 commits during the "untouched" window — observation invalid by its own precondition, not by TS-1/TS-2 | local: close retired (`retire_invalidated`); do not re-seed (no path step needs it) |
| 1289 | Collect 5 resume observations | Superseded by TS-8 (ledger handoff) + S8 resume-probe reuse, not Gate-4 duplication | local: close retired; stamp resume-observations-log.md abandoned-series |
| 1290 | Update cross-repo reservation-model docs | Already done across agentops/sprintctl-bootstrap-template/vuoro (a2d55c8, f397d97+, d72e827) | local: close **done** |
| 2017 | Qualify hybrid worker routes w/ frozen corpus | No control arm exists (event 2539); hybrid dispatch tooling deleted | local: close retired |
| 2039 | Converge cockpit network paths on owner-mediated Vuoro | Cockpit deleted (aa555d6), not converged; note post-cockpit W1-A1 wave doc still points here | local: close retired, flag wave doc |
| 2054/2055/2056 | Planner-manifest emit / PLANNER_GAP pass / keep-or-delete measure | Hybrid packet substrate deleted (0baa680); zero consumers | local: close all 3 together; keep #2053 done; review siblings 2057/2058 separately |
| 2057 | Independent scope reconstruction from artifacts | Same hybrid task-packet schema, now deleted | local: close retired |
| 2058 | Randomized trial: scope declaration control | Same deleted substrate (task-packet.schema.json, hybrid_dispatch.py) | local: close retired |
| 2062 | Ratify market-absorption/export-boundary ADR | Superseded by owner-decision D1 + TS-1/5/6/9/11 | local: close retired; **residual D4 (ActionQ) / D6 (Auditctl) re-file only if a live consumer appears** |
| 2115 | Gate OpenCode scaling on verified lifecycle | All 3 blockers done; PR-B already deleted templates/dispatch/hooks; TS-1/TS-2/TS-11 | local: close retired ("remain retired" per TS-2) |
| 2143 | Role-scoped model fitness/routing evidence (future) | Consumer tooling deleted; TS-2 excludes cross-provider routing | local: close retired |
| 2144 | Ecosystem simplification program | Its own plan doc marked `superseded` 2026-08-20; sub-items 2145-2149 all done | local: close retired |
| 2151/2152/2153/2154 | VUORO-CP FND-001..004 (hybrid control-plane ADR, IdentitySchema, protocol compat, ownership) | Source plan (2026-08-15) itself `superseded`/`retired` 2026-08-22; TS-1/TS-2 exclude runner/host architecture | local: close all 4 together |
| 2181 | CRED-000 assess cred-broker vs target contracts | **Not simply retired** — dossier §13 marks it "Absorbed into S7 grant integration" | local: close as **absorbed**; carry inventory scope (STEP_UP reuse, principal minting, grant evidence fields) into S7 work |
| 2193 | POL-003 author baseline Rego | No Rego exists anywhere; TS-1/TS-2 exclude a Vuoro/agentops policy engine; §1.2 non-goal | local: reject Decision citing TS-1/TS-2 (see conflict note on 2194) |
| 2196 | POL-006 promote families to enforcement | Same chain, retired plan; fail-closed intent already carried by surviving EffectGrant | local: close together with 2193/2194/2195/2212 |
| 2203 | AUT-007 cross-host builder-test-review pilot | Runner/lease pilot excluded by TS-1/TS-2; useful part (cross-host continuity) covered by TS-8/S8 | local: close retired; re-triage #2214 separately |
| 2209 | OPS-006 distributed failure-injection suite | Assumes owned runner/broker/OPA control plane, excluded; resilience proof is S8 rehearsal | local: close retired **together with dependent #2213** |
| 2211 | OPT-001 measure RTK as shadow projection | Its own prereq (ACP-005/#2179) already rejected; RTK is harness-native, outside Vuoro/agentops | local: close retired |
| 2212 | OPT-002 evaluate ToolHive | Dossier: "CUT ... no trigger exists"; empty MCP fleet | local: close retired together with #2195 |
| 2213 | OPT-003 evaluate DBOS vs named ActionQ failure | ActionQ execution domain itself is being deleted (dossier §13); no failure to name | local: close retired; DEPEND-durable-execution stays a preserved option only via the concurrency/cost tripwire, as a *new* item if it fires |
| 2214 | OPT-004 evaluate Beads vs named task-layer failure | Duplicates live item **#1286** (clean-room comparison track); dependency #2203 also retiring | local: close retired, cite #1286 as successor |
| 2216 | Resolve ActionQ execution.enqueue identity blocker | Whole canary-dispatch subsystem deleted (31a2e3f/174268b) | local: close retired; flag dormant `execution_provenance.py` (vuoro-service) for separate cleanup, no consumer |
| 2306 | Adopt action_class across packets/repos | Extends deleted hybrid_dispatch.py; TS-2 | local: close retired; note leftover `routing.action_classes` check in validate_verification_artifacts.py goes with S6 manifest retirement |
| 2407 | Hetzner S3 lifecycle rule for langfuse/ | Operator decision (event 2862) already superseded scope: no shared-bucket rule, dedicated credential instead | local: close retired; **fold surviving intent into #2395 (WP6) and #2394/#2398 teardown**; do not provision a new Hetzner project until pilot manifests are ready |

**Flagged conflict — item 2194 (POL-004, "Run observation mode over a full backlog")**: its own (unverified) assessment says **keep/implement**, but the verified dispositions on siblings 2195 and 2196 explicitly fold 2194 into the same reject batch ("record the reject through one Decision object that covers 2195 ... 2193, 2194, 2196, 2212"). No verifier pass exists for 2194 itself. Recommend treating this as **retire_goal_state** per the verified sibling consensus, but this is the one item in the set where the recorded per-item assessment and the cross-checked consensus actually disagree — worth a one-line operator note rather than a silent override, since it's a judgment call about whether "observe without blocking" is inside or outside TS-1's negative clause.

## DONE ALREADY (record only)

| id | title | reason | next action |
|---|---|---|---|
| 2254 | v5 P-1/P-3 two-way telemetry measurement | Scorecard already shipped (docs/evidence/scorecards/v5-p1-two-way.json, commits 463753b/1365b25/01b66e9) | local: **release stale reservation #33 first**, then mark done |

## KEEP — rescope (real correctness gaps, implement)

| id | title | reason | next action |
|---|---|---|---|
| 2074 | Audit/refactor doc portfolio | PR#19 delivered only the ledger/freeze; item's own 2026-08-09 decision said to refreeze packets and run correction waves — not done | local: refreeze doc packets against 2026-09-17 target state, run owner-local correction waves, keep item active |
| 2101 | Handoff must never outrank live tracker state | Shipped handoff/v1 only re-checks git basis, never re-queries live sprintctl tracker state, and never checks evidence[] file existence/hash — the exact bug class the item names | local: implement (a) mandatory/flagged tracker-watermark re-check in `handoff validate`, (b) existence+hash check for evidence refs; drop retired dispatch-loop claim-extractor spec |
| 2102 | Worktree-aware gh cleanup + PAT preflight | Live-used `gh pr merge --delete-branch` conflates merge success with cleanup failure (used daily per landing guidance); no rule exists in AGENTS.md today | local: add landing-guidance rule (treat merge/cleanup as separate outcomes, check PR state before retry); drop PAT-preflight half, superseded by credctl capability/lease model |

## KEEP — pending implementation, not blocked (dispatch candidates)

| id | title | next action |
|---|---|---|
| 1281 | Session-note hook wiring (inject/stop-gate/coverage) | local/cloud: implement per session-note-contract-plan.md, unblocked (#1280 done) |
| 2393 | WP4: Alloy OTLP receiver + redaction pipeline | local/cloud: implement manifest changes; cluster rollout is operator-only |
| 2394 | WP5: Langfuse deployment manifests | local/cloud: rework to D2-D8 (chart pin, single-replica, no CNPG backup, dedicated cred, SOPS exception, no external OTLP, storage-linter allowlist already landed); cluster deploy operator-only |
| 2395 | WP6: Langfuse/OTLP credentials + deploy | ClickHouse operator install + Authentik provider = local/cloud now; SOPS secret values/backup + Hetzner S3 lifecycle rule = operator-only (no admin creds on this host) |
| 2396 | WP7: session/subagent span adapter + rate-limit gauges | cloud (expert tier): unblocked, WP2/WP3 done |
| 2397 | WP8: host telemetry enablement (Claude Code + Codex OTel) | local: gitops-nixos change, cred-broker gap has a documented workaround (SOPS file + otelHeadersHelper), no operator block |
| 2398 | WP9: live acceptance + retention drill | local: run once WP8 lands; Hetzner S3 lifecycle sub-check is operator-only if still unresolved |
| 2399 | WP1: NFS consumer inventory + cockpit doc fix | cloud/local: pure docs task, unblocked (#2390 done) |
| 2414 | D11: automate DinD publish-runner stop conditions | local (needs repo+cluster write): extend runner-config-revision-guard.py |
| 2417 | Reissue external review packet (four-axis model) | cloud/local: doc synthesis, all prereqs (D12-D17) done |
| 2428 | Dated checks: pgdump Object-Lock cutover drills | local, date-gated (2026-09-20 / 10-03 / 10-05); pull 5 commits first (clean fast-forward) |

---

### (a) Executable now, ranked by value

1. **2396** — WP7 span adapter/rate-limit gauges (expert tier, unblocked, real telemetry gap)
2. **2101** — handoff tracker-precedence + evidence-hash hardening (real correctness bug, live risk)
3. **2393** — WP4 Alloy OTLP pipeline (unblocks WP6/WP7/WP9 evidence chain)
4. **2397** — WP8 host telemetry enablement (workaround exists, unblocks WP9)
5. **2394** — WP5 Langfuse manifest rework to D2-D8
6. **2102** — landing-guidance fix for `gh pr merge --delete-branch` outcome conflation (small, prevents recurring daily-use failure)
7. **2395 (partial)** — ClickHouse operator install + Authentik proxy provider sub-scopes
8. **2417** — reissue external review packet (prereqs done, pure synthesis)
9. **2399** — NFS consumer inventory docs (small, fast)
10. **2414** — D11 automate stop conditions for publish-runner
11. **1281** — session-note hook wiring
12. **2074** — refreeze doc packets + correction waves
13. **Batch sprintctl closes** — all 29 RETIRE-group items above (one pass of terminal-decision writes; low individual value, high backlog-cleanliness value; resolve the 2194 conflict as part of this pass)

### (b) Retire/merge actions to apply (single batch, cite refs above)

Close as retired/superseded/absorbed/done, in one or a few Decision-object writes:
1261, 1262, 1275, 1277, 1286, 1287, 1288, 1289, 1290(done), 2017, 2039, 2054, 2055, 2056, 2057, 2058, 2062, 2115, 2143, 2144, 2151, 2152, 2153, 2154, 2181(absorbed), 2193, 2194(resolve conflict → retire), 2196, 2203, 2209, 2211, 2212, 2213, 2214, 2216, 2254(done, release reservation #33 first), 2306, 2407(fold into #2395/#2394/#2398).

### (c) Blocked items — real vs not

| id | blocker | real? |
|---|---|---|
| 2395 (SOPS secret values + backup confirmation, Hetzner S3 lifecycle rule) | no S3/console admin access from this host | **Real** — operator-only |
| 2398 (S3 lifecycle sub-check) | same Hetzner access gap, if still open by drill date | **Real** — operator-only |
| 2393/2394 (final cluster rollout step) | cluster deploy convention reserved for operator | **Real**, but only the deploy step — code/manifest work is not blocked |
| 2398 (overall item) | sequencing behind WP8 (#2397) | **Not real** — ordering only, not an approval gate |
| 2151/2152/2153/2154 dependency chain | blocked_by each other | **Not real** — all retiring together, chain collapses |
| 2209/2213 | 2213 blocked_by 2209 | **Not real** — retire together |
| 2194 vs 2195/2196 | conflicting dispositions on same chain | **Not an external blocker** — internal data conflict, needs a one-line reconciliation call, not operator time |
| 2407 | previously thought to need operator Hetzner project | **No longer applies** — decision already superseded scope; folds into #2395 |