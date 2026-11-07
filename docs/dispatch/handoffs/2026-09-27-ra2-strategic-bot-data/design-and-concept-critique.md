# RA2 strategic bot: design critique, concept critique, rebuttals, measured outcomes (2026-09-27)

Written by the coordinating Claude session. Critiques by Fable (sage agent), rebuttals by the coordinator.
The operator approved the resulting change order ("Sounds good on all per plan").

## Design critique (Fable) and verdicts

| # | Claim | Verdict |
|---|---|---|
| 1 | Validated only in a self-written sim; proposal's Chrono Divide route skipped | Partly conceded: sim is a regression harness, not RA2 evidence; label tables accordingly |
| 2 | Unseen enemy = "enemy has nothing" (`ConditionEvaluator.RatioCap = 10` when estimate 0) causes the 131 s blind rush | **Refuted as stated, confirmed in substance** by experiment (below): the selector's playbooks attack on `OwnArmyValue >= X` only and never read the enemy |
| 3 | Evaluation cannot rank arms (saturated opponents, flat tuner objective) | Conceded, and worse: arena always starts arm west (side bias now fixed); live self-play `balanced` vs `live-balanced` -> opponent slot wins 100% on every map/side/faction (arm/opponent configs not equivalent; uninvestigated) |
| 4 | One deathball; squads disbanded every pass (`OperationalPlanner.Squads.cs:122`, `Fill()`) | Partly: verified; stateless re-derivation is legit, but no reinforcement stream/garrison/multi-prong, ownership never contended |
| 5 | LLM reduced to a 6-way classifier | Mostly rebutted (that is the proposal's design); conceded: adoption gate closed without credential; run `Full` vocabulary in shadow |
| 6 | Bandit explores every 20 s, terminal reward to all decisions -> churn | Conceded |
| 7 | Rules import ignores `Verses=` and build-time multipliers; Yuri absent | Conceded on data; Yuri is phasing |
| 8 | Retail visibility = own unit anywhere in region | Conceded; contract gap (v1 has no visibility) |
| 9 | Held-out maps same author; id tie-break start bias | Fixed today (4 causes, invariants); procedural held-out maps still a good idea |
| 10 | Retail commands fire-and-forget; "fork is the operator's" | Gap conceded; nobody owns/pins a ra2yrcpp fork (upstream ee215f5 only) |

## Concept critique (Fable) and rebuttals, from outcomes

1. "LLM hypothesis scheduled last" - rebutted: every defect found (blind attack, side bias, frozen placement, self-play asymmetry) would have made a day-one LLM run noise. Conceded: nobody asked for the one missing credential.
2. "Validated in a world it wrote" - mostly conceded; the sim still exposed engine-agnostic bot defects.
3. "Stated value (adaptable/varied/explainable) has no metric" - **conceded in full; define a non-strength metric before any live LLM evaluation.**
4. Retail RA2 is max-cost and the fork is unowned - conceded on cost/ownership.
5. Bindery ceremony - rebutted in code (bot has no Bindery dependency); ERH-006 idle is real.
6. Measurement machinery without signal - rebutted (it found the bugs); conceded: fairness gates must precede tournaments.
7. Playbook selection too small for an LLM - partly conceded; test LLM-authored playbooks.
8. Agent fan-out overstated results - conceded; fix is a mechanical gate (raw test totals attached to any report/PR text). Terra reported a failing test as passing.

## Operator direction (2026-09-27)

- Hybrid, generalisable architecture: LLM for long-term/reactive strategy **writing** playbooks in a typed plan language; fast typed tactical tier (classifier / Jev-style "System One" model, https://typesafe.ai/blog/introducing-system-one-models-and-jev, early access, claims 70-500 ms typed outputs with calibrated confidence, <=255 options); deterministic executors.
- Three levels: game-neutral core (belief, cadence, late-discard, ownership, validation, decision log, eval) / genre layer (RTS, city, FPS, RPG, 4X each separate) / per-game adapter. Custom AIs (vedal987/Neuro-sama style) plug into a stable genre-level tool interface.
- Bulk LLM validation should be free: use the local llama-swap `worker-fast` at http://127.0.0.1:8020/v1. **Not opencode-go**: its terms restrict it to coding-agent traffic with session ids and 5h/weekly caps. opencode-zen (pay-per-use, has claude-opus-5 / haiku-4-5) is available for live Claude later.

## Measured outcomes today

- Out-of-sample cell (held-out maps x ai-horde/ai-armor at easy/medium/hard, contested, 6 seeds, 72 matches/arm) on fair maps at 2e49971: **selector 40/72, selector-oracle 52/72**; first-attack median 131 s (belief) vs 214 s (oracle).
- Experiment: ArmyValueRatio = NaN when enemy estimate is 0 -> **identical** 40/72, 52/72, 131 s. Reverted, not committed.
- Selector playbook use on that cell: soviet-flak-mix 30 wins / 6 losses; allied-ifv-mix 9 wins / 25 losses (faction imbalance). Both attack on OwnArmyValue >= 1200 only. 4 of 12 default playbooks use own-army-only attack triggers (grizzly-timing 1500, ifv-mix 1200, rhino-rush 1000, flak-mix 1200, apoc-tech 2500).
- Local LLM (worker-fast) llm-shadow, 3 training matches vs ai-balanced: 16 shadow proposals/match, 0 failed, 0 rejected, 0 fog rejections, 5-7.5 s/call, ~4.3k in / 0.7k out tokens, agreed with selector 4/16. ~3 min wall per match (single GPU).
