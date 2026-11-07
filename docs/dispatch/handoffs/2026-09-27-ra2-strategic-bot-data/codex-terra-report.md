# RA2 strategic bot successor report

Handoff acknowledged as `7053f58b-7b26-4d68-8272-0891b701381c`. Repository state was validated at `c80c935` before work; this run added `d6b9dfc`.

## Residual items

All titles below exactly match `residual-items.json`. “Regression” names the test run in this successor session; the repair commits’ own dedicated tests are the revert guards.

| Title | Status | Commit | Regression / revert guard |
|---|---|---|---|
| IncomePerMinute estimator assumes gradual debit but the sim debits full cost up front; value is an unsmoothed per-interval spike | fixed | f3b10c5 | `FeatureCompilerReviewTests` warm-up income cases |
| twin-valley (training) and open-steppe (held-out) favour the west start, and the arm always starts west | fixed | c80c935, d6b9dfc | `MirrorMatchTests`; `SimMapsTests` geometric reflection |
| First combat unit (or any army growth from zero) fires ArmyValueSwing at severity 1.0 | fixed | e854d6b | `FeatureCompilerReviewTests` army-swing cases |
| IncomePerMinute is a one-frame derivative and produces multi-million spikes | fixed | f3b10c5 | `FeatureCompilerReviewTests` windowed-income cases |
| Decision-log content, and the LLM prompt, depend on the process culture, so hashes differ between machines and locales | fixed | eec8fad | `IntentValidatorTests` culture-invariant messages |
| TwoSpeedStrategist sends event-driven and replan requests to the fast (Refine) strategist when the event arrived while a request was in flight | fixed | f4dc0ee | `StrategistContextTests.Two_speed_sends_an_event_triggered_request_to_the_slow_strategist_even_when_its_features_show_no_event` |
| Base-threat override is level-triggered: every proposal during a sustained threat bypasses commitment and posture hysteresis | fixed | 7b9d6a5 | `IntentArbiterTests` spent-override case |
| The ledger resets spending every period and sizes capacity from credits on hand, so on RA2 (charged while building) in-progress items are funded again | fixed | 4b9e99e | `ProductionAccountingTests` and `BotRuntimeTests` |
| Expand objective is ignored; 'expansion' refineries are always built at the main base | fixed | db06023 | `BuildOrderAndPlacementTests.Placement` expand-field case |
| Strategist objectives DefendRegion/Expand/DenyExpansion, objective regions and RegionsOfInterest have no effect | fixed | 8e92463 | operations objective consumer tests in `BuildOrderAndPlacementTests` |
| Extra production always adds the cheapest Production building (barracks), counting the ConYard, never a second war factory | fixed | 8b70473 | `BuildOrderAndPlacementTests` extra-factory queue case |
| Rule facts omit counters and have no rows for observed enemy types, which the proposal requires | fixed | 56c0775 | `PromptRulesFactsTests` observed-building/unit rows |
| Prompt hides the arbiter's numeric acceptance rules: posture margin 0.15, base-threat ratio 1.5, and that renewal requires the same posture | fixed | a497b6f | `PromptArbitrationTests` override conditions |
| Intent history in the prompt fills up with renewals, so the model cannot see its earlier plan switches | fixed | 24754e2 | `PromptArbitrationTests` long renewal chain |
| RA2 bridge invents empty production queues and zero credits/power instead of reporting them missing | fixed | 4b9e99e | `AssemblerKnowledgeTests`, `ProductionAccountingTests` |
| Every non-self owner is an enemy: neutral, civilian or allied entities become enemy contacts, contest our base and create a base threat | fixed | 8e92463 | `BeliefHostilityAndSamplingTests` |
| Prompt says a fallback- or emergency-installed intent is committed, though the arbiter yields it to any primary proposal | fixed | 8e92463 | `StrategistContextTests`, `PromptArbitrationTests` |
| Inference cost omits cache-creation tokens and every failed request's tokens | fixed | 8e92463 | `DecisionLogMetricsTests` |

## Mirror proof

`MirrorMatchTests` uses frozen `balanced` on both sides, 24 seeds with each start orientation (48 matches/map), on twin-valley, river-crossing and open-steppe. The test passed; detailed captured output included twin-valley west 26/47 decisive (55.3%, one draw), inside its 35–65% fairness guard. The other two theory cases passed in the same run. The test is committed in `d6b9dfc`.

## Verification and tournament

- Focused residual suite: 115 passed.
- Release build: 0 warnings, 0 errors.
- Adapter tests: 95 passed.
- Full bot suite run: live-Claude smoke correctly skipped because no credential; fake/offline cases passed.
- CI-equivalent arena smoke: 6 matches, 0 fog-violation frames.
- `ci/verify-no-assets.ps1`: passed via Nix PowerShell.
- Standard final tournament: 5,520 matches, exact 23-opponent matrix, `--llm-fake`.
- Contested final tournament: 6,720 matches, exact 28-opponent matrix, `--llm-fake`.

No live-LLM result is claimed. Generated tournament artifacts were retained in `/tmp/ra2-final-standard-23` and `/tmp/ra2-final-contested-28` for this session; the architecture results document records the current rerun headline and retains historical tables as explicitly superseded.
