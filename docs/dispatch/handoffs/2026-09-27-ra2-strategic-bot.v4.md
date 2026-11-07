# Handoff 2026-09-27-ra2-strategic-bot.v4

<!-- Rendered from the canonical JSON beside this file. Do not hand-edit:
     `agentops handoff validate` and `ack` read the JSON, never this. -->

**Objective.** Finish the operator-approved RA2 strategic-bot change order on PR #2 (bandit fix, then Full-vocabulary local-LLM shadow pass with a pre-defined non-strength metric), then correct PR #2's description, rerun the documented tournament, refresh docs/architecture/strategic-bot-results.md and push to feat/strategic-bot so the operator can merge.

**Next action.** cd /projects/dev/_wt/bindery-ra2-bot && git status && git log --oneline -1 (expect clean, a23294f, 4 commits ahead of origin/feat/strategic-bot). Check /tmp/bandit-base/results.json exists (else rerun: nix shell nixpkgs#dotnet-sdk_8 -c dotnet run --project tools/Bindery.Ra2.Bot.Arena -c Release -- run --arms bandit,selector --maps training --opponents training --seeds 8 --benchmark contested --no-decisions --out /tmp/bandit-base). Then implement the bandit fix test-first in src/Bindery.Ra2.Bot/Strategy/ContextualBanditStrategist.cs per the recorded design, measure on training only, commit with raw test totals.

## Predecessor

- harness: claude-code
- session: 164ee96b-82fc-4ce1-9b26-b8ac4d6536d7
- model: claude-opus-5-5
- context used: unknown%
- transcript: unknown
- origin: `workstation:/projects/dev/agentops/docs/dispatch/handoffs/2026-09-27-ra2-strategic-bot.v4.json` (authoritative copy; an ack from another host goes through it)

Read-only after transfer: once a successor acks, the predecessor makes no
edits and takes no external actions. It stays consultable.

## Constraints

- Work only in /projects/dev/_wt/bindery-ra2-bot on branch feat/strategic-bot (PR #2 open, NOT merged; operator merges). Never touch /projects/dev/bindery-ra2-adapter.
- dotnet only via: nix shell nixpkgs#dotnet-sdk_8 -c dotnet <args>, with Bash dangerouslyDisableSandbox (pre-approved). Parallel dotnet runs are fine. TreatWarningsAsErrors.
- Every fix: a test seen to FAIL before and PASS after. Never weaken invariant tests (fog, late-discard, ownership, validator, SimMapsTests mirror/numbering, MirrorMatchTests incl. the new live-slot guard).
- Any report, commit or PR text quotes raw dotnet test totals (two Codex successors overstated results).
- tools/Bindery.Ra2.Bot.Baseline stays frozen.
- Bulk LLM work: local endpoint only (--llm-endpoint http://127.0.0.1:8020/v1 --llm-model worker-fast). Never opencode-go for the bot. opencode-zen (paid) only for an explicit live-Claude run.
- Held-out maps/opponents are evaluation only; tune on training only (arena --knob applies tuning knobs to arms only). Pre-register criteria in docs/experiments/ BEFORE each held-out or LLM evaluation run; one held-out run per change, no retuning after it.
- No sprintctl writes without operator permission; Codex launches need the operator's launch permission.
- Pushing to feat/strategic-bot (the open PR branch) is in scope for 'correct PR #2'; do not merge. 4 commits are currently unpushed.
- Use seeds that are a multiple of 4 for arena runs (side x faction balance; report warns otherwise).

## Decisions

- **Enemy-aware attack gating committed at afa6ff6: launch needs own army / upper enemy bound >= ratio sliding 1.2 (no evidence) -> 0.8 (fresh sighting); unseen enemy = prior 12/s after 75 s capped 1600 (training p75); a recent look at a known enemy base counts as evidence.** — Pre-registered (docs/experiments/2026-09-27-enemy-aware-gating-preregistration.md). Held-out 6 seeds: selector 40/72 -> 55/72 (+19/-4, sign p 0.0026); oracle 52 -> 49/72 (misses >=50 by one, p 0.375); median first attack unchanged 127.5 s (predicted: the ~124 s attack passes the gate by construction).
- **Arena start side rotates by seed at 8a56aa0 (seeds 1-2 west, 3-4 east...; MatchRunner.ArmStartsEast/Oriented), report has As west/As east columns and a side-mix warning, distinct-game key includes side.** — Arm always started west. With 8 seeds held-out selector wins 36/48 west and 36/48 east.
- **No player-slot asymmetry exists; guard MirrorMatchTests.Live_mirror_matches_do_not_favour_either_slot added.** — Expert subagent: live-balanced vs live-balanced slot 0 = 24/48 on each of 4 maps; combat applies damage simultaneously. The old 'opponent always wins' was frozen `balanced` arm vs live stack. Remaining real asymmetry: Soviet wins every Standard-benchmark mirror (documented in BenchmarkSettings; contested benchmark handicaps Allied).
- **Rules import at 3936348: per-unit Verses row (UnitRule.Verses) drives Effectiveness by defender armor; build seconds = cost x [General] BuildSpeed x BuildTimeMultiplier; [General] MultipleFactory carried and applied by the sim (sqrt(n) kept when absent).** — Critique #7. Embedded fixture has neither, so arena numbers are unchanged.
- **Persistent attack membership + batched reinforcements at a23294f; ReinforceSquadTargetSize (was unused) = batch size, default 2, now a tuning knob.** — Pre-registered (docs/experiments/2026-09-27-reinforcement-batching-preregistration.md). Training sweep 1/2/4/6 -> selector 287/294/291/281 of 336. Held-out 8 seeds: selector 72 -> 74/96, oracle 64 -> 68/96 (within noise, criteria pass).
- **Current reference numbers at a23294f (contested, 8 seeds): held-out selector 74/96, oracle 68/96; training selector 288/336, oracle 310/336. Tests: Bindery.Ra2.Bot.Tests Failed 0, Passed 813, Skipped 1, Total 814; Adapter.Tests 95/95.** — Baseline for the next steps and for the refreshed results doc.
- **Bandit fix design (not yet implemented): explore (UCB width) only when committing at episode start; within a match switch playbook only if another arm's mean exceeds the committed arm's mean by BanditOptions.SwitchMargin (~0.2); credit CompleteEpisode once per contiguous playbook segment, not once per renewal.** — Critique #6: explores every ~20 s proposal and credits the terminal reward to every renewal. File: src/Bindery.Ra2.Bot/Strategy/ContextualBanditStrategist.cs (Settle adds every settled renewal to `episode`).

## Rejected

- **ArmyValueRatio = NaN when the enemy is unseen, as the blind-rush fix** — Measured no effect (40/72, 52/72, 131 s); the playbooks attack on OwnArmyValue only.
- **Uncapped linear unseen-enemy prior** — Reached ~15000 by 900 s; FullMatchTests vs ai-turtle failed. Capped at 1600 (training plateau).
- **Gate ratio 1.2 regardless of evidence (v1)** — Training sweep: Seen ratio 1.2 cost the oracle arm 3 wins vs 0/0.8; v1 held-out oracle 46/72.
- **Treating an empty freshly-scouted enemy base as no evidence** — Army confidence is 0 with no army contact, so the prior dominated and the bot never attacked ai-turtle; fixed by base-scouting evidence.
- **Reinforcement batch 4 or 6** — Training: oracle 304 and 297/336 vs 308 at batch 2.
- **Side rotation as a new report dimension (both sides per seed)** — Would break replay manifests, file names and pairing keys; seed-derived rotation keeps them.
- **opencode-go as bulk LLM backend; trusting Luna/Terra reports without rerunning tests** — Terms (coding-agent traffic only); both overstated results.

## Repo state

Digest definition: v4 (see the handoffs README).

| path | branch | head | dirty | unpushed | diff_sha256 |
|---|---|---|---|---|---|
| `/projects/dev/_wt/bindery-ra2-bot` | feat/strategic-bot | `a23294f17a1a` | no | 4 | `e3b0c44298fc1c14…` |

**Running:**

- Background arena run (bandit baseline) writing /tmp/bandit-base at a23294f; finishes within minutes and needs no action beyond reading results.json/report.md.

## Unresolved

- Bandit fix: implement test-first (churn test: after the episode's first decision, lower the committed arm slightly so UCB would switch -> must not switch; credit test: 5 renewals of one playbook -> CompleteEpisode returns 1). Baseline for comparison is being written to /tmp/bandit-base (arena --arms bandit,selector, training, contested, 8 seeds); if missing, rerun it at a23294f before changing code. Measure churn by per-match `activations` and `postureFlips` in results.json.
- Non-strength metric (variety/explainability) must be defined and pre-registered before judging any LLM arm (concept critique #3).
- Full-vocabulary LLM shadow pass with worker-fast (arms llm-shadow / llm-t0..t3 'tiers'); ~3 min wall per match on one GPU, so keep the cell small and pre-register thresholds.
- Held-out: the belief selector beats the oracle arm (74 vs 68/96); uninvestigated.
- Faction imbalance: selector as Allied 34/48 vs Soviet 40/48 held-out at a23294f (was 10/36 vs 30/36 before the gate).
- Bot spending model treats N factories as N parallel items (FeatureCompiler.Economy), unlike RA2 and the sim; follow-up.
- Latent: SkirmishSimulation.cs ~985 spawn fallback uses StartRegions[0] for any player (edge case, no measured effect).
- PR #2 description overstates (claims all 18 items closed); results tables stale. Rerun the documented tournament and refresh docs/architecture/strategic-bot-results.md, then push.
- Stale auditctl #2315/#2316/#2317 and sprintctl #2110 need sprintctl write permission (operator).
- ADR for the three-level architecture / typed plan language not drafted; live Claude run via opencode-zen untested.

## Evidence

- artifact: `/projects/dev/_wt/bindery-ra2-bot/docs/experiments/2026-09-27-enemy-aware-gating-preregistration.md`
- artifact: `/projects/dev/_wt/bindery-ra2-bot/docs/experiments/2026-09-27-reinforcement-batching-preregistration.md`
- artifact: `/projects/dev/agentops/docs/dispatch/handoffs/2026-09-27-ra2-strategic-bot-data/design-and-concept-critique.md`
- artifact: `/projects/dev/_wt/bindery-ra2-bot/docs/architecture/strategic-bot-results.md`
- artifact: `/projects/dev/agentops/docs/dispatch/handoffs/2026-09-27-ra2-strategic-bot.v3.json`
- session: `164ee96b-82fc-4ce1-9b26-b8ac4d6536d7`

## sprintctl bundle

- none (sprintctl unavailable or produced no bundle)

## Successor

- session: 12b54b2a-2ada-4812-b58b-541e0f4682af
- acknowledged: 2026-09-27T17:00:45Z
