All 8 fix branches are merged into `feat/strategic-bot` and the cross-area requests are applied. The results doc tables were not rerun and are out of date. Release build has 0 warnings, all tests pass, and the CI arena smoke passes. HEAD is **8e9246335a41580aaa6f7116de3dd6fa05f90e80** in `/projects/dev/_wt/bindery-ra2-bot`. Nothing was pushed.

**Merged branches** (each with `--no-ff`, in the order given; every one had commits beyond 33d5ce0): fix/ra2-sim-arena (13 commits), fix/ra2-bridge-ci (8), fix/ra2-belief-features (8), fix/ra2-strategy (3), fix/ra2-arbitration-runtime (4), fix/ra2-operations-tactics (7), fix/ra2-claude (8), fix/ra2-rules-playbooks (5).

**Conflicts and resolutions**
- No textual conflicts.
- One semantic conflict. The strategy branch's test `Two_speed_sends_the_request_an_event_deferred_to_the_slow_strategist` expected a late discard. After arbitration-runtime, a severe event cancels the unusable in-flight request at once instead (`proposal_failed` reason `superseded`).
- I updated the test's assertions and kept its intent: the event-triggered request goes to the slow strategist, never the fast one. Commit f4dc0ee.

**Cross-area changes** (commit 8e92463):
- **Squads (sim-arena 1):** squads attack only contacts seen this frame; a fogged contact gets an attack-move to its last-seen cell. Artillery holds its stand-off cell while the defence it besieges is in fog. This is the controller code, so the RA2 bridge path gets the same rule.
- **Docs (sim-arena 2, arbitration 4, rules 3):** `strategic-bot.md` has a new section covering every item listed, plus updated metrics definitions.
- **Factories (sim-arena 3):** new `UnitRule.Produces` field. The importer fills it from `Factory=`, the fixtures declare it, and the sim uses the declared factories. In the fixture, Kirovs come from the war factory, so the Soviet `ai-air` wave test now allows 1100 s.
- **Shadow datasets (sim-arena 4):** `DatasetFilter.ShadowOnly` / `IncludeShadow`. Shadow records now log the features the shadow strategist was asked with.
- **Missing queues, credits, power (bridge-ci, belief 1):** `ObservationFrame` gains `QueuesKnown`, `CreditsKnown`, `PowerKnown` and `Enemies`.
  - Belief keeps the last sampled credits and power and skips owners that are not enemies.
  - The planner does not treat an unreported queue as free. It orders into it at most once per the ordered item's build time plus 5 s.
  - The assembler reports queues as unknown, and credits and power as unsampled until the first sample. When given non-hostile owners, it fills `Enemies`. The sim fills `Enemies` too.
- **Sim economy and events (belief 2–5):** the sim debits production as it builds and refunds what was paid on cancel. Oracle events go through the same per-player filter. A kill's `GameEvent.Owner` is the killer everywhere, including the assembler. Both contract docs are fixed.
- **Strategy (strategy 1–3):** `StrategistContext.Trigger`, and two-speed sends every `event:*`/`replan:*` request to the slow strategist. `intent_activated` records carry `mode`. The arena tags datasets with the arm's mode, refuses an oracle dataset for the belief distilled arm, trains an oracle distilled arm in oracle mode, and credits the bandit's last decision.
- **Culture formatting (strategy 4):** already fixed before this merge; no change.
- **Dataset frames (arbitration-runtime 1):** examples take their frame and snapshot version from the features the strategist saw.
- **Planner credits (arbitration-runtime 2):** the planner subtracts what queued production still owes (new shared `ProductionDebt`, new `OperationalOptions.ProductionChargedWhileBuilding`).
- **Retail setting (arbitration-runtime 3):** `StandardBot.SimulatorOptions` now also charges while building, so the retail caveat no longer applies.
- **Repair and placement (operations-tactics 1–2):** new `UnitRule.Repairs`, read from `UnitRepair=`; `RepairController` uses it. The sim repairs only within 3 cells of an own depot, and rejects overlapping placement within 2 cells. The scripted AI now keeps 2 cells between its buildings. Fogged-attack rejection was already in fd95829.
- **Claude (claude 1–6):**
  - The prompt marks a fallback or emergency intent as a placeholder with no commitment window, uses the arbiter's clock (`ActiveRole`/`ActiveSince`), and states the yield rule.
  - Cost counts cache writes and prices each billed attempt at its own model's rate.
  - Arena cost tallies the models that served replies separately and counts unpriced requests instead of pricing them at 0.
  - The scheduler drops a refinement whose intent ended while it was in flight.
  - The attack condition now follows `attackArmyValue` for the bandit and tuner too (`AttackArmyThreshold` moved to the bot library).

**Tests**
- Bot tests: 741 passed, 1 skipped, 0 failed. Adapter tests: 95 passed, 0 failed.
- I checked failure-first in a throwaway worktree at f4dc0ee: all 5 behavioural tests that compile against the old API failed there. The other new tests use new API, so they fail to compile on the old code.

**Smoke**
- Arena smoke run exactly as in `ci.yml`: exit 0, 6 matches, 6 wins, 0/640 differing frames, 0 fog-violation frames.
- I also ran the CI tune smoke: exit 0.

**Not done**
- **Results doc rerun:** not rerun. The last full run was two `--llm-fake` tournaments, about 1 h of compute on the shared machine, and the doc's tables would need rewriting from the output. `strategic-bot-results.md` now opens with a note that its tables predate the merge; the rerun commands are in its Setup section, unchanged.
- **MCV expansion:** producing an MCV, escorting it to a distant expansion and deploying it is a new feature.
- **`harvesterTarget` gate:** the attack does not wait for the harvester target; the description already states what the planner does.
- **Callers:** no production code passes `nonHostileOwners` or the player's country yet.
- **Outside the repo:** the native telemetry source changes are documented in `Ra2BotTelemetryContract`.
- **Two-speed routing by source:** the optional `ActiveIntent.Source` check was not added, because the existing ownership check already covers it.
- **Frozen Baseline:** untouched. Its own simulator options still assume full payment on order, so it now misjudges its credits in the sim and plays somewhat differently.

**Worktrees:** all 8 `/projects/dev/_wt/ra2-fix-<area>` worktrees are removed and the `fix/ra2-*` branches deleted, each only after checking it was merged.