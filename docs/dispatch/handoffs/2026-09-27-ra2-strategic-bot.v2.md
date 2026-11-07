# Handoff 2026-09-27-ra2-strategic-bot.v2

<!-- Rendered from the canonical JSON beside this file. Do not hand-edit:
     `agentops handoff validate` and `ack` read the JSON, never this. -->

**Objective.** Close ALL 18 residual review items on the RA2 strategic bot (feat/strategic-bot, PR #2 open, not merged), prove the mirror-symmetry fix with matches, rerun the final tournament and refresh the results docs, then correct PR #2's description. The operator merges after checkup.

**Next action.** cd /projects/dev/_wt/bindery-ra2-bot && git status && git log --oneline -1 (expect c80c935, clean, in sync with origin). Then: (1) mirror-match proof for c80c935; (2) all 18 residual items, failure-first; (3) clean Release build 0 warnings, both test projects, CI arena smoke, ci/verify-no-assets.ps1; (4) tournament rerun + docs; (5) git push origin feat/strategic-bot, gh pr edit 2 --body with an accurate summary (do not merge); (6) write /projects/dev/agentops/docs/dispatch/handoffs/2026-09-27-ra2-strategic-bot-data/codex-terra-report.md: 18-row table (exact title, status, commit, test that fails on revert), mirror-match table, test counts, tournament headline, anything left open with reason.

## Predecessor

- harness: codex
- session: 9fce7d53-8d3c-4971-9ff6-0e0611a844fd
- model: gpt-5.6-luna
- context used: unknown%
- transcript: unknown
- origin: `workstation:/projects/dev/agentops/docs/dispatch/handoffs/2026-09-27-ra2-strategic-bot.v2.json` (authoritative copy; an ack from another host goes through it)

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
- PR #2 (https://github.com/bayleafwalker/bindery-ra2-adapter/pull/2) is already open. Push to feat/strategic-bot and edit PR #2's description with gh pr edit so it states exactly what is done and what is open. Do NOT merge.
- Do not edit /projects/dev/.claude, ~/.claude, /projects/dev/agentops (except writing your report into /projects/dev/agentops/docs/dispatch/handoffs/2026-09-27-ra2-strategic-bot-data and acking the handoff).
- Every one of the 18 items in residual-items.json (14 rejected_claims + 4 not_fixed) gets its own row in the report, matched by exact title. 'open' is only allowed with a concrete reason why it cannot be done on this host; 'already fixed' needs the commit AND a test you ran that fails if that commit's change is reverted (revert in a scratch copy or with a temporary edit, never committed).
- Contract changes are in scope: ObservationFrame allegiance, QueuesKnown/CreditsKnown/PowerKnown handling in the planner, ActiveRole in StrategistContext, CacheCreationTokens in ProposalCost + failed-request costs summed in BotArenaAgent. Keep all invariants.
- Do not stop early. Do not open or describe work as done that is not done.

## Decisions

- **Bot lives in bindery-ra2-adapter: src/Bindery.Ra2.Bot, .Sim, .Claude; tools/Bindery.Ra2.Bot.Arena, .Tune, .Baseline; tests/Bindery.Ra2.Bot.Tests.** — Repo owns the RA2 telemetry seam; bot is engine-agnostic and builds on Linux.
- **Hardening run wf_09897313-9c6 landed 42 commits (2321cb6..33d5ce0): independent ai-* opponents, frozen baseline for pinned styles, strength work, CMA-ES tuner (tuned set NOT adopted: no gain), completeness gaps, 25 post-review fixes, final tournament and docs. Pushed.** — Record in docs/architecture/strategic-bot-results.md.
- **Its 8 area fixers were blocked (snip rewrite + isolation guard refused git). Residual run wf_e273b932-542 used hand-made worktrees: 129 findings -> 110 fixed, 15 already fixed, 4 not fixed; merged at 8e92463 (tests green at merge, 0 warnings, CI arena smoke passed).** — Per-area reports: /projects/dev/agentops/docs/dispatch/handoffs/2026-09-27-ra2-strategic-bot-data/area-fix-reports.json; merge: /projects/dev/agentops/docs/dispatch/handoffs/2026-09-27-ra2-strategic-bot-data/merge-report.md.
- **2 skeptics per claim (250 checks) rejected 14 distinct claims. The repair step then made 10 commits 8e92463..24754e2 (f3b10c5 income warm-up, e854d6b army swing, eec8fad culture test, 7b9d6a5 base-threat pin, 4b9e99e unreported production debt + QueuesKnown/CreditsKnown/PowerKnown, db06023 expansion field, 8b70473 extra factory by queue, 56c0775 counters rows, a497b6f base-threat prompt, 24754e2 renewal folding) and was mid-way through the twin-valley/open-steppe mirror fix when the session ended.** — Those 10 commits are unverified by skeptics; the map edit is uncommitted in the worktree.
- **snip-hook-defer.sh now skips harness-isolated worktrees (agentops PR #252, merged 95fa9f3), operator-approved.** — Isolated workflow agents can use git again.
- **Codex Luna successor (v1, session 9fce7d53) committed the mirror-symmetry edit as c80c935, pushed, opened PR #2; bot tests 769/770 (1 live-LLM skip), adapter 95/95, verify-no-assets pass.** — Its report: /projects/dev/agentops/docs/dispatch/handoffs/2026-09-27-ra2-strategic-bot-data/codex-report.md. It checked the map fix only with 16 SimMapsTests (no mirror matches), walked 11 of 18 residual items without verifying them, did not rerun the tournament, and PR #2's description overstates (claims findings closed and docs refreshed).

## Rejected

- **Workflow worktree isolation from the main checkout without a reset** — Worktrees start at main 82b4e62 (no bot code); agents must reset to feat/strategic-bot. Fixed hook now allows that.
- **Adopting the tuned parameter set** — Worse than defaults on fresh training seeds (177 vs 180 of 198) and no held-out gain.
- **Reinforcements joining a running attack as a group; turtle threshold 0.9** — Measured regressions or no change (strength report).

## Repo state

Digest definition: v4 (see the handoffs README).

| path | branch | head | dirty | unpushed | diff_sha256 |
|---|---|---|---|---|---|
| `/projects/dev/_wt/bindery-ra2-bot` | feat/strategic-bot | `c80c935ec6b4` | no | 0 | `e3b0c44298fc1c14…` |

## Unresolved

- Prove c80c935 with mirror matches: selector vs frozen/pinned mirror opponents on twin-valley, river-crossing and open-steppe with sides swapped, enough seeds for a 95% interval; west-start share must be near 50% (it was 37/48 on twin-valley, 48/48 on river-crossing before).
- All 18 items in /projects/dev/agentops/docs/dispatch/handoffs/2026-09-27-ra2-strategic-bot-data/residual-items.json. Repair commits 8e92463..24754e2 likely close several (f3b10c5 income warm-up, e854d6b army swing, eec8fad culture, 7b9d6a5 base threat, 4b9e99e production debt, db06023 expansion field, 8b70473 extra factory, 56c0775 counters, a497b6f base-threat prompt, 24754e2 renewal folding) — prove each against the skeptics' objections in the file. Known genuinely open: bridge unknown queues/credits/power, ActiveRole in StrategistContext, inference cost cache-creation + failed requests, allegiance for non-self owners; suspects: TwoSpeed event-deferral test, operations objectives consumer coverage, culture in IntentValidator messages.
- Final tournament rerun as docs/architecture/strategic-bot-results.md describes (all arms, all maps split training/held-out, all opponents, 6 seeds, contested + standard); refresh the tables and docs/architecture/strategic-bot.md. The results doc also has a retail-telemetry paragraph that rode along in c80c935 — keep it only if accurate for HEAD.
- Live LLM arms still need ANTHROPIC_API_KEY (operator).

## Evidence

- artifact: `/projects/dev/agentops/docs/dispatch/handoffs/2026-09-27-ra2-strategic-bot-data/residual-items.json`
- artifact: `/projects/dev/agentops/docs/dispatch/handoffs/2026-09-27-ra2-strategic-bot-data/area-fix-reports.json`
- artifact: `/projects/dev/agentops/docs/dispatch/handoffs/2026-09-27-ra2-strategic-bot-data/merge-report.md`
- artifact: `/projects/dev/_wt/bindery-ra2-bot/docs/architecture/strategic-bot-results.md`
- artifact: `/projects/dev/_wt/bindery-ra2-bot/docs/architecture/strategic-bot-proposal.md`
- session: `78fca569-75ab-48b7-89eb-b3f8e360e1c0`
- artifact: `/projects/dev/agentops/docs/dispatch/handoffs/2026-09-27-ra2-strategic-bot-data/codex-report.md`
- artifact: `/projects/dev/agentops/docs/dispatch/handoffs/2026-09-27-ra2-strategic-bot-data/codex-run.log`

## sprintctl bundle

- none (sprintctl unavailable or produced no bundle)

## Successor

- session: 7053f58b-7b26-4d68-8272-0891b701381c
- acknowledged: 2026-09-27T06:10:23Z
