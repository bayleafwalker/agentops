# Reduced Vuoro Profile — Sufficiency Study

## Determination

The reduced profile is sufficient as a **retained-core operating hypothesis**:
the ten locked corpus obligations still pass when its non-required surfaces are
not invoked. It is not yet sufficient to establish that Vuoro is *reduced
enough* operationally, or to award `keep-bespoke-reduced` under the frozen
threshold.

The profile is currently an invocation discipline over the same implementation,
not an independently enforced deployment shape. It therefore cannot by itself
show that background dependencies, services, operator work, or carrying cost
actually decreased.

## Functional check

The immutable sprintctl fixture at
`f22132c21ca17ad79d347ca1f43df8b3fe636c66` ran all ten locked obligations
twice from its disposable clone using `pytest -p no:cacheprovider`:

| Variant | Result | Observed wall time | Interpretation |
| --- | --- | ---: | --- |
| Current retained-core command | 10 passed | 0.284 s | Core authority, recovery, resume, and served-transport obligations remain functional. |
| Reduced retained-core command | 10 passed | 0.241 s | Same core obligations remain functional while no profile-excluded operation is invoked. |

The runs are warm, component-level checks. Their timing is not a performance or
cost comparison and must not be averaged or used to claim a reduction.

## Why the profile is not yet sufficient

1. Both variants execute the same source revision and the same retained core;
   the profile does not remove or disable a service, route, storage path, or
   background process.
2. No run proves that omitted heartbeat upkeep, authority-command journal,
   capability receipts, audit ingest, takeup events, cockpit panes, or
   cutover scaffolding would remain unused across S-SOLO, S-BATCH, and
   S-RESUME.
3. There is no scenario-segmented operator-time, setup, maintenance, or idle
   carrying-cost measurement.
4. S-DORMANT has not matured, and the current/reduced variants have not run
   comparable live multi-actor or simplification scenarios.

## Minimum next test

Treat the reduced profile as sufficient only after a run can prove all of the
following:

- a command-level trace or explicit feature gate shows every omitted surface is
  absent from the selected scenario;
- retained R1–R8 behavior remains functional under S-SOLO, S-BATCH,
  S-RESUME, and a fourteen-day S-DORMANT;
- current and reduced have per-scenario operator/setup/maintenance records;
- any omitted surface discovered as a background dependency is counted as a
  reduction failure, not silently restored.

Until then, retain the profile as a conservative design direction, not a
validated cost-reduction result.

## Evidence

- [Reduced operating profile](../contract/reduced-vuoro-operating-profile.yaml)
- [Current corpus evidence](../runs/2026-07-23-lane-b-current-corpus/evidence/test-results.md)
- [Reduced corpus evidence](../runs/2026-07-23-lane-b-reduced-corpus/evidence/test-results.md)
- [Segmented cost status](segmented-cost-inputs.yaml)
