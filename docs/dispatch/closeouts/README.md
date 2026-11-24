# Outcome closeout records

One `outcome-closeout-record/v1` JSON per delegated outcome under the
[active dogfood practice](../model-routing.md#active-dogfood-practice-2026-11-04)
([schema](../../../schemas/outcome-closeout-record.v1.schema.json)). Copy
[TEMPLATE.json](TEMPLATE.json) to `<closed_on>-<outcome_id>.json` in the same
change as the closeout.

It joins the fields the practice says to assess (observed route, coordinator
effort, elapsed time, review findings, repairs, cost) into one record per
attempt. Every measurement has a `basis` of `measured`, `estimate` or
`unknown`; leave a value `null` rather than guess. Set
`review.same_tier_as_worker` honestly: a review on the worker's own tier does
not support a comparative-quality claim.

This is a record, not infrastructure: no producer, hook or service reads it.
`scripts/tests/test_outcome_closeout_records.py` validates every file here
against the schema.

| Record | Outcome |
|---|---|
| [2026-11-04-outcome-routing-pr485.json](2026-11-04-outcome-routing-pr485.json) | routing practice guidance (backfilled; effort and elapsed unknown) |
| [2026-11-10-lanectl-delivery-020.json](2026-11-10-lanectl-delivery-020.json) | Native landing, PR reconciliation, unattended integration and conservative abandoned-runner recovery. |
| [2026-11-10-lanectl-specification-020.json](2026-11-10-lanectl-specification-020.json) | Independent intent drafting, adversarial review, recurring maintenance intake and isolated local native provider. |
| [2026-11-10-lanectl-coordination-020.json](2026-11-10-lanectl-coordination-020.json) | Owner-coordinated native execution and atomic served lane events, with optional immutable service composition. |
| [2026-11-20-worldwindow-kernel-m1.json](2026-11-20-worldwindow-kernel-m1.json) | WorldWindow kernel rework M1: painting-first core at v3b parity, accepted after the human A/B. |
| [2026-11-20-worldwindow-kernel-m2.json](2026-11-20-worldwindow-kernel-m2.json) | WorldWindow kernel rework M2: fast review loop (preview, review package, promote). |
| [2026-11-21-worldwindow-kernel-ec-1b.json](2026-11-21-worldwindow-kernel-ec-1b.json) | WorldWindow kernel effect classes EC-1b: shared procedural primitives, accepted by the independent EC-A suite. |
| [2026-11-21-worldwindow-kernel-ec-a.json](2026-11-21-worldwindow-kernel-ec-a.json) | WorldWindow kernel EC-A: independently authored effect-class acceptance suite, accepted after adversarial review; one repair after acceptance (PR #39). |
| [2026-11-21-worldwindow-kernel-ec-0.json](2026-11-21-worldwindow-kernel-ec-0.json) | WorldWindow kernel EC-0: effect-class consumer assets (imports, shared maps, ritual patches, storm foregrounds), accepted with named limits. |
| [2026-11-21-worldwindow-kernel-ec-1a.json](2026-11-21-worldwindow-kernel-ec-1a.json) | WorldWindow kernel EC-1a: effect-class contract and gates (typed maps, foreground layers, signals, native-size fringe, motion floor), accepted by the independent EC-A suite. |
| [2026-11-22-worldwindow-kernel-ec-0-rework.json](2026-11-22-worldwindow-kernel-ec-0-rework.json) | WorldWindow kernel EC-0 follow-ups: protect crossings, shared storm outdoor mask, repaired unlit-sigil patch (PRs #61, #63, #66); a second attempt record linked to the EC-0 record. |
| [2026-11-22-worldwindow-kernel-ec-1a-seam-floor.json](2026-11-22-worldwindow-kernel-ec-1a-seam-floor.json) | WorldWindow kernel EC-1a addendum: the seam no-motion floor leaves out events and flicker layers (PR #54, with EC-A's criterion PR #47); a second attempt record linked to the EC-1a record. |
| [2026-11-22-worldwindow-kernel-ec-a-family-kit.json](2026-11-22-worldwindow-kernel-ec-a-family-kit.json) | WorldWindow kernel EC-A addendum: the effect families' shared acceptance kit eca/family.py (PR #45); a second attempt record linked to the EC-A record. |
| [2026-11-22-worldwindow-kernel-oracle-pipeline-strategy.json](2026-11-22-worldwindow-kernel-oracle-pipeline-strategy.json) | WorldWindow kernel oracle pipeline-strategy plan and draft ADR-0011 (PR #58), accepted after an independent review with 8 blocking findings. |
| [2026-11-22-worldwindow-kernel-ec-4.json](2026-11-22-worldwindow-kernel-ec-4.json) | WorldWindow kernel EC-4: fire@1 and the storm fire study, with a wave-1 rework; accepted (budget signed off on a quiet box 2026-11-23). |
| [2026-11-22-worldwindow-kernel-ec-7.json](2026-11-22-worldwindow-kernel-ec-7.json) | WorldWindow kernel EC-7: thunder@1 and the storm thunder study; accepted (budget signed off on a quiet box 2026-11-23; sky_flash_ev 1.8 against the plan's 2.5, plan note pending). |
| [2026-11-23-worldwindow-kernel-ec-3.json](2026-11-23-worldwindow-kernel-ec-3.json) | WorldWindow kernel EC-3: rain@1 in air and glass modes and the rain and glass studies, with a wave-1 rework (PRs #56, #68). |
| [2026-11-23-worldwindow-kernel-ec-6.json](2026-11-23-worldwindow-kernel-ec-6.json) | WorldWindow kernel EC-6: neon@1 and the ritual neon study, accepted after two independent look reviews; a scope-check failure repaired by landing EC-0's patch separately. |
| [2026-11-22-worldwindow-kernel-ec-a2.json](2026-11-22-worldwindow-kernel-ec-a2.json) | WorldWindow kernel EC-A2: independently authored acceptance criteria for EC-2 (atmospherics) and EC-3 (rain, air and glass) with stand-in studies, calibration and the coordinator's rulings (PRs #40, #42, #50, #52). |
| [2026-11-23-worldwindow-kernel-ec-2.json](2026-11-23-worldwindow-kernel-ec-2.json) | WorldWindow kernel EC-2: clouds@1, mist@1, steam@2 and the storm atmospherics study, with a wave-1 maps-and-parameters rework and a scud-edge fix (PRs #55, #70); budget signed off 2026-11-23. |
| [2026-11-23-worldwindow-kernel-ec-4-clip-repair.json](2026-11-23-worldwindow-kernel-ec-4-clip-repair.json) | WorldWindow kernel EC-4 addendum: fire rolls off the light it adds so flame cores no longer clip flat, passing criterion 20 (PR #74, merged by the coordinator after EC-4 hit a usage limit); a second attempt record linked to the EC-4 record. |
| [2026-11-24-worldwindow-kernel-ec-a4.json](2026-11-24-worldwindow-kernel-ec-a4.json) | WorldWindow kernel EC-A4: independently authored acceptance criteria for EC-4 to EC-7, the clipping oracles (PR #71) and the wave-2 criteria for wander, own patch, re-strike variety and strike timing (PR #77), with the rulings. |
