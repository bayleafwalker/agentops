# Workflow Artifact: vuoro next-wave dispatch (post project-scoping)

- **Date:** 2026-07-21
- **Source session note(s):** none -- compiled live from conversation context, workflow progress metadata, and per-agent result payloads (no separate `.agents/sessions/` note was kept during the session).
- **Workflow(s) used:** `agentops/.claude/workflows/vuoro-dispatch-build.js`, invoked twice (wave 1: run `wf_23c6772b-cd3`; wave 2: run `wf_ae25ba4f-157`), plus one standalone `Agent` call (not a Workflow) for a rework/re-verify cycle on sprintctl#1160.
- **Repos touched:** sprintctl, actionq.

## Scenario

With the vuoro substrate (project-scoping) track fully closed (#1177-#1184), this session picked up the next planned wave of union backlog: 9 ready items across 4 tracks. Two (agentops#1172, actionq#975) were appservice-dependent and handed over via `item note --type blocker` rather than attempted. The remaining 7 were prioritized and dispatched in two waves through the tiered claim->build->independent-verify->close pipeline, respecting one real cross-repo dependency (actionq#1116 needs sprintctl#1160's code, not just its item status) that the backlog tooling itself cannot see.

## Suitability assessment

The pipeline shape (same-repo sequential build, independent-repo parallel, separate verify agent gating close) worked as designed and caught a real bug (see below) that would otherwise have shipped. Two things did not go smoothly and are worth flagging for future runs:

1. **Missing project-scoped skills caused friction on every single agent.** The build/verify/close prompts unconditionally call `Skill("dispatch-build")`, `Skill("code-change-verification")`, `Skill("item-done")`. These skills exist as real `SKILL.md` files under `agentops/templates/dispatch/skills/` and are materialized (symlinked from `.agents/skills/`) into `sprintctl/.claude/skills/` -- but never into `actionq/`, `kctl/`, or `agentops`'s own `.claude/skills/`. Every actionq agent (5 build/verify/close calls) and even some sprintctl agents hit "Unknown skill" and fell back to manual procedure, each burning a wasted tool call and some model reasoning to self-correct. **Fixed this session:** both workflow scripts now treat these Skill calls as best-effort/conditional instead of assumed-present (commit `f08759f`). **Not fixed this session (recommendation only):** actionq/kctl/agentops still don't have these skills materialized locally; that's a separate, slightly bigger piece of repo-process work (decide symlink-from-`.agents/skills` vs. some other materialization approach, then do it consistently across repos).
2. **A verify-gate agent stalled twice waiting on a backgrounded full-suite pytest run** during the sprintctl#1160 rework cycle (see below) instead of using a bounded/targeted check. Required two manual `SendMessage` nudges to reach a verdict. Future verify prompts should say explicitly: run full-suite regression checks in the foreground with a timeout, not backgrounded-and-polled.

## Item-level outcomes

| Item | Tier | Build tokens/calls | Verify tokens/calls | Verdict | Closed? | Rework? |
|------|------|---------------------|----------------------|---------|---------|---------|
| sprintctl#1160 | hard | 240,445 / 200 (shared build agent w/ #1163) | 71,300 / 98 | issues_found -> then confirmed after fix | yes (after rework) | yes -- see below |
| sprintctl#1163 | hard | (shared, above) | 55,651 / 44 | confirmed | yes | no |
| actionq#970 | hard | 244,761 / 142 (shared build agent w/ #976,#1115,#1117) | 34,926 / 17 | confirmed | yes | no |
| actionq#976 | hard | (shared, above) | 48,452 / 26 | inconclusive | no | n/a -- environment gap, not a code defect |
| actionq#1115 | standard | (shared, above) | 51,265 / 13 | confirmed (with a disclosed non-blocking concern) | yes | no |
| actionq#1117 | hard | (shared, above) | 53,309 / 23 | confirmed | yes | no |
| actionq#1116 | hard | 178,663 / ~74 (wave 2, own build agent) | included in wave-2 total | confirmed | yes | no |

Close-stage cost (per item, all confirmed-path unless noted): #970 33,852/21; #976 20,882/6 (left-open path); #1115 23,648/12; #1117 31,606/19; #1160 20,588/6 (left-open path, first pass); #1163 25,165/14; #1116 included in wave-2 total.

## What required rework

**sprintctl#1160** was the one real defect this batch caught. The independent verifier (first pass) confirmed scope and all 27 shipped tests passed, but manually explored the new `context-candidates` command and found: a not-found `--item-id` explicit target was still added to the internal truncation-counting pool, so `sprintctl context-candidates --item-id 999999 --json` on an empty pool reported `"truncated": true` with zero real candidates -- a false signal that could mislead a Tier-1 consumer into retrying with a larger `--limit` for no reason. The verifier also flagged a missing docs entry (item description listed docs as in-scope; none shipped). Verdict: `issues_found`, left open rather than closed.

Rather than dispatch a fresh build agent, I (main session) read the ~5-line bug directly, fixed it (`sprintctl/context_candidates.py`, gating both the `pool_ids.add` and the `_add` call on `explicit_found`), added two regression tests, and wrote the missing docs section, then committed (`ce24a41`) and pushed. A **fresh** independent verify-gate agent (never saw the first pass's reasoning, only the claim) then cold-reproduced the original bug scenario against the fix, reran the full suite, and confirmed no new regressions before closing the item.

Cost of the rework+re-verify cycle: the verify-gate agent needed 3 resume segments (52,057/45 calls/322s; 53,244/49/358s; 66,440/63/608s = **171,741 tokens / 157 tool calls / ~21.5 min wall-clock**) because it twice self-suspended waiting on a backgrounded full-suite pytest run instead of running a bounded/targeted check -- required two manual nudges from the orchestrator to reach a verdict. The actual fix diff was small (~80 lines including tests+docs); the verification overhead here was disproportionate to the defect size, driven by the stalling pattern rather than the check itself.

**actionq#1115** also surfaced a minor issue that was *not* treated as rework: the commit's stated rationale ("extract shared git-evidence plumbing instead of reinventing it") was only half-true -- `actionq/session_wrapper.py` kept its own near-identical private implementation instead of being refactored onto the new shared module, so duplication was added at a second call site, not removed. The verifier judged this a scope-honesty/documentation gap, not a functional defect (both implementations are in sync and independently tested), and confirmed the item rather than blocking it. Flagged here as a candidate for a small follow-up cleanup item, not actioned this session.

## What was validated vs. not

**actionq#976** (usage-limit pause/resume) is the one item left open for a reason other than a code defect. All 69 non-Postgres tests passed cold, including all 13 new/changed tests, and the diff scope was clean -- but the commit's headline verification claim was a real disposable-schema Postgres drill via the actual `actionctl` CLI (pause -> fail -> re-dispatch -> `session.resumed` with event-history correlation), and this sandbox has no `ACTIONQ_TEST_URL` / disposable Postgres instance reachable (only a shared/production-labeled `ACTIONQ_URL`, which the repo's own `AGENTS.md` says must never be used for mutating integration tests). The verifier correctly returned `inconclusive` rather than guessing pass/fail, and the item was left open with a note recommending a follow-up pass once a disposable Postgres schema is available. This is an environment-capability gap, not a rejection of the work.

## Cost summary

- Wave 1 (6 items, 2 repos, 14 agents): 955,850 subagent tokens, 641 tool calls, ~54.4 min of summed agent duration (parallel across repos, so wall-clock was shorter than the sum).
- Wave 2 (1 item, 1 repo, 3 agents): 225,135 subagent tokens, 105 tool calls, ~11 min.
- sprintctl#1160 rework+re-verify (1 agent, 3 resumes): 171,741 subagent tokens, 157 tool calls, ~21.5 min.
- **Total this session's dispatch work:** ~1,352,726 subagent tokens, 903 tool calls, 18 subagent invocations, ~87 min of summed agent time. (Excludes the main-loop/orchestrator's own tokens for planning, the manual bug fix, and this write-up.)

Tier-assignment note: every item except actionq#1115 was tiered `hard`. In hindsight #1115 ("standard") was reasonably scoped -- its build+verify+close cost was comparable to the `hard`-tier items, and it still surfaced a real (if non-blocking) finding, so `standard` was not obviously underpowered here. No item's outcome suggests a `hard` item should have been downgraded to `standard`/`mechanical`; the one real defect (#1160) was a subtle logic bug that a "hard" tier with a thorough independent verifier still needed a *second* independent pass to catch on rework -- tier alone does not substitute for the adversarial-verify gate.

## Follow-up changes named

1. **Fixed this session:** stale unconditional `Skill()` calls in both dispatch workflow scripts, and a wrong `claim release --claim-id` flag (should be `--id`) -- commit `f08759f` on agentops.
2. **Recommended, not actioned:** materialize the `dispatch-build` / `code-change-verification` / `item-done` (and siblings) skills into `actionq/.claude/skills/`, `kctl/.claude/skills/`, and `agentops/.claude/skills/` the same way `sprintctl/.claude/skills/` already symlinks them from `.agents/skills/`. Left as a recommendation since it's a separate scope decision (which repos, which skills, symlink vs. copy) rather than part of this dispatch batch.
3. **Recommended, not actioned:** actionq#976's Postgres-backed pause/resume drill needs a follow-up verification pass once a disposable `ACTIONQ_TEST_URL` schema is available in whatever environment runs it next.
4. **Recommended, not actioned:** a small cleanup item to actually extract `actionq/session_wrapper.py`'s duplicate git-evidence logic onto the new `actionq/git_evidence.py` module from #1115, closing the drift risk its own commit message claimed to close.
5. **Process note for future verify-gate prompts:** tell verifiers explicitly to run full-suite regression checks in the foreground with a bounded timeout rather than backgrounding and polling -- the #1160 rework cycle lost real wall-clock to a stalled background wait.
