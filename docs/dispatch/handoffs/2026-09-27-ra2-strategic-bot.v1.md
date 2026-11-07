# Handoff 2026-09-27-ra2-strategic-bot.v1

<!-- Rendered from the canonical JSON beside this file. Do not hand-edit:
     `agentops handoff validate` and `ack` read the JSON, never this. -->

**Objective.** Close the residual review items on the RA2 strategic bot (feat/strategic-bot in /projects/dev/_wt/bindery-ra2-bot), refresh the stale results tables, push and open the PR to main. The operator checks up on 2026-09-28 and merges.

**Next action.** cd /projects/dev/_wt/bindery-ra2-bot && git status && git log --oneline -1 (expect 24754e2 + the uncommitted map edit). Then: (1) finish/prove/commit the mirror-symmetry edit; (2) walk every item in /projects/dev/agentops/docs/dispatch/handoffs/2026-09-27-ra2-strategic-bot-data/residual-items.json against HEAD, fixing still-open ones failure-first; (3) clean Release build 0 warnings, both test projects, CI arena smoke, ci/verify-no-assets.ps1 via nix shell nixpkgs#powershell; (4) rerun the final tournament and refresh the results docs; (5) git push origin feat/strategic-bot and gh pr create --base main (do not merge); (6) write /projects/dev/agentops/docs/dispatch/handoffs/2026-09-27-ra2-strategic-bot-data/codex-report.md: per-item table (item, status fixed/already/open, commit, test), test counts, PR URL, anything left open.

## Predecessor

- harness: claude-code
- session: 78fca569-75ab-48b7-89eb-b3f8e360e1c0
- model: claude-opus-5-5
- context used: unknown%
- transcript: unknown
- origin: `workstation:/projects/dev/agentops/docs/dispatch/handoffs/2026-09-27-ra2-strategic-bot.v1.json` (authoritative copy; an ack from another host goes through it)

Read-only after transfer: once a successor acks, the predecessor makes no
edits and takes no external actions. It stays consultable.

## Constraints

- Work only in /projects/dev/_wt/bindery-ra2-bot on branch feat/strategic-bot. Never touch the main checkout /projects/dev/bindery-ra2-adapter (it stays on main).
- dotnet only via: nix shell nixpkgs#dotnet-sdk_8 -c dotnet <args>. TreatWarningsAsErrors is on. Parallel dotnet runs are allowed.
- No live Anthropic credential on this host: LLM arms use --llm-fake. Never claim live-LLM results.
- Every fix needs a test that you ran and saw FAIL before the fix and PASS after. Never weaken invariant tests (fog, late-discard, single ownership, validator-sanitised intent).
- No proprietary game files in the repo (ci/verify-no-assets.ps1).
- Held-out maps and held-out opponents are for final evaluation only; never tune on them.
- Commits: fix(bot)/feat(bot)/docs(bot) style, SPDX GPL-3.0-or-later headers, file-scoped namespaces. Commit trailer: Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com> is NOT yours; use the Codex attribution your harness gives, or none.
- Push feat/strategic-bot and open the PR to main with gh. Do NOT merge; the operator's checkup merges.
- Do not edit /projects/dev/.claude, ~/.claude, /projects/dev/agentops (except writing your report into /projects/dev/agentops/docs/dispatch/handoffs/2026-09-27-ra2-strategic-bot-data and acking the handoff).

## Decisions

- **Bot lives in bindery-ra2-adapter: src/Bindery.Ra2.Bot, .Sim, .Claude; tools/Bindery.Ra2.Bot.Arena, .Tune, .Baseline; tests/Bindery.Ra2.Bot.Tests.** — Repo owns the RA2 telemetry seam; bot is engine-agnostic and builds on Linux.
- **Hardening run wf_09897313-9c6 landed 42 commits (2321cb6..33d5ce0): independent ai-* opponents, frozen baseline for pinned styles, strength work, CMA-ES tuner (tuned set NOT adopted: no gain), completeness gaps, 25 post-review fixes, final tournament and docs. Pushed.** — Record in docs/architecture/strategic-bot-results.md.
- **Its 8 area fixers were blocked (snip rewrite + isolation guard refused git). Residual run wf_e273b932-542 used hand-made worktrees: 129 findings -> 110 fixed, 15 already fixed, 4 not fixed; merged at 8e92463 (tests green at merge, 0 warnings, CI arena smoke passed).** — Per-area reports: /projects/dev/agentops/docs/dispatch/handoffs/2026-09-27-ra2-strategic-bot-data/area-fix-reports.json; merge: /projects/dev/agentops/docs/dispatch/handoffs/2026-09-27-ra2-strategic-bot-data/merge-report.md.
- **2 skeptics per claim (250 checks) rejected 14 distinct claims. The repair step then made 10 commits 8e92463..24754e2 (f3b10c5 income warm-up, e854d6b army swing, eec8fad culture test, 7b9d6a5 base-threat pin, 4b9e99e unreported production debt + QueuesKnown/CreditsKnown/PowerKnown, db06023 expansion field, 8b70473 extra factory by queue, 56c0775 counters rows, a497b6f base-threat prompt, 24754e2 renewal folding) and was mid-way through the twin-valley/open-steppe mirror fix when the session ended.** — Those 10 commits are unverified by skeptics; the map edit is uncommitted in the worktree.
- **snip-hook-defer.sh now skips harness-isolated worktrees (agentops PR #252, merged 95fa9f3), operator-approved.** — Isolated workflow agents can use git again.

## Rejected

- **Workflow worktree isolation from the main checkout without a reset** — Worktrees start at main 82b4e62 (no bot code); agents must reset to feat/strategic-bot. Fixed hook now allows that.
- **Adopting the tuned parameter set** — Worse than defaults on fresh training seeds (177 vs 180 of 198) and no held-out gain.
- **Reinforcements joining a running attack as a group; turtle threshold 0.9** — Measured regressions or no change (strength report).

## Repo state

Digest definition: v4 (see the handoffs README).

| path | branch | head | dirty | unpushed | diff_sha256 |
|---|---|---|---|---|---|
| `/projects/dev/_wt/bindery-ra2-bot` | feat/strategic-bot | `24754e2410ab` | yes | 76 | `ac17c90347e0fc4d…` |

## Unresolved

- Uncommitted mirror-symmetry edit in the worktree (SimMaps.cs twin-valley/open-steppe, SkirmishSimulation.cs, ScriptedSkirmishAi.cs tie-break, BuildPlacement.cs, Contracts/World.cs, SimMapsTests.cs, results doc): finish, prove with mirror matches (skeptic measured west start 37/48 before), commit.
- 14 rejected claims + 4 not_fixed items in /projects/dev/agentops/docs/dispatch/handoffs/2026-09-27-ra2-strategic-bot-data/residual-items.json: re-check each against HEAD (the 10 repair commits likely close most); remaining suspects: strategy TwoSpeed test does not exercise the event-deferral case; operations objectives (DefendRegion/Expand/DenyExpansion/RegionsOfInterest); not_fixed: bridge unknown queues/credits/power, prompt claims fallback intent committed (needs ActiveRole in StrategistContext), inference cost omits cache-creation + failed-request tokens (ProposalCost contract + BotArenaAgent), non-self owners treated as enemies (allegiance in ObservationFrame).
- Results doc tables are stale since 33d5ce0: rerun the final tournament as the doc describes and update docs/architecture/strategic-bot-results.md + strategic-bot.md.
- Live LLM arms still need ANTHROPIC_API_KEY (operator).

## Evidence

- artifact: `/projects/dev/agentops/docs/dispatch/handoffs/2026-09-27-ra2-strategic-bot-data/residual-items.json`
- artifact: `/projects/dev/agentops/docs/dispatch/handoffs/2026-09-27-ra2-strategic-bot-data/area-fix-reports.json`
- artifact: `/projects/dev/agentops/docs/dispatch/handoffs/2026-09-27-ra2-strategic-bot-data/merge-report.md`
- artifact: `/projects/dev/_wt/bindery-ra2-bot/docs/architecture/strategic-bot-results.md`
- artifact: `/projects/dev/_wt/bindery-ra2-bot/docs/architecture/strategic-bot-proposal.md`
- session: `78fca569-75ab-48b7-89eb-b3f8e360e1c0`

## sprintctl bundle

- none (sprintctl unavailable or produced no bundle)

## Successor

- session: 9fce7d53-8d3c-4971-9ff6-0e0611a844fd
- acknowledged: 2026-09-27T05:48:06Z
