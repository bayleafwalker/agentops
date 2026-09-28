# Routing evaluation — agentops, 2026-09-28

Can TypeSafe Jev route dispatch work better than what already exists? This
evaluation scores Jev's tier choice against hindsight labels on 100 agentops
sprintctl items. It compares Jev with the Haiku triage in `vuoro-dispatch-build`
and with a keyword heuristic.

Rerun with `python3 jev/eval/compare.py jev/eval/agentops-2026-09-28`.

## Method

**Items.** The first 100 items from `sprintctl item list` in agentops, all `done`.
They are split by position into a tuning half (0–49) and a held-out half
(50–99); see `split.json`.

**Hindsight labels.** Each label is `bounded`, `standard`, `hard`, `needs_planning`
or `insufficient_evidence`. A judge assigns it after seeing the item's full history:
events, notes, decisions, refinements, coordination failures, and whether the item
was later retired.
- Opus labelled all 100 items (`labels-opus.jsonl`).
- Sonnet independently labelled items 0–24 and 50–74 (`labels-sonnet.jsonl`).
- Neither judge saw any router's answer.

**Routers.** Each router saw only the item title and description:
- `jev-route-v1.jsonl`: Jev, model `jev-1.13.0`, using the committed `route-v1` bundle.
- `jev-route-v2.jsonl`: Jev with reworded tier criteria (`route-v2-not-adopted.json`), tuned on the tuning half.
- `haiku-triage.jsonl`: Haiku 4.5 with the workflow's triage rubric, verbatim. `dispatch_ready=false` is read as `needs_planning`.
- `heuristic.jsonl`: keyword rules (`heuristic.py`).

## Results

The two judges agree on 70% of items (κ 0.59). That is the practical ceiling for
any router.

| Gold labels | n | Haiku | Heuristic | Jev v1 | Jev v2 |
|---|---|---|---|---|---|
| Opus, all | 100 | 0.50 | 0.41 | 0.48 | 0.51 |
| Opus, held-out | 50 | 0.56 | 0.54 | **0.64** | 0.56 |
| Sonnet, all | 50 | **0.44** | 0.32 | 0.30 | 0.42 |
| Both judges agree | 35 | **0.57** | 0.34 | 0.34 | 0.49 |

Values are exact agreement. Kappa and the error directions are in the `compare.py` output.

- **No router is reliably better than Haiku triage.** Rankings change with the judge. Jev v1 led on Opus's held-out half, but was the weakest model router against Sonnet and on the items both judges agree on. At n ≤ 50 these differences are within noise.
- **The routers fail in different directions.**
  - Haiku marked 58 of 100 items not dispatch-ready, against 34 by hindsight, so it sends ready work to planning.
  - Jev v1 dispatches work that needed planning, and under-tiers `standard` work as `bounded`: it chose `standard` once in 100 items.
  - v2 fixed the under-tiering but not the planning misses.
- **Many `needs_planning` labels can only be known in hindsight.** The item was later retired or superseded by a strategic decision, and no text-only router can see that coming.
- **Jev's confidence carries signal.** Against Opus, v1 was right on 63% of answers at confidence ≥ 0.8 and 25% below 0.6.
- **Cost and speed:** about 1.4k tokens and 5 s at the median (10.6 s p95) per Jev call, with no agent startup.

## Caveats

- One repository only, and a small n.
- The judges are LLMs, not outcome measurements.
- Some descriptions were edited after completion. That leaks outcome text to every router equally.
- The real Haiku triage also reads the repo's `AGENTS.md`, its dispatch manifest and the live item. Here it saw text only.

## Consequences

- **Kept:** `vuoro-dispatch-build` records each unit's routing decision as a `dispatch.route.decision` event. Before this, triage decisions were not persisted at all, and they are the labels any future comparison needs.
- **Not kept:** an online Jev call in the dispatch path. Jev scoring stays offline (`jev_shadow.py score`) until recorded decisions support a clear result.
- **Not adopted:** `route-v2`. Its effect depends on the judge and the evidence is inconclusive, so `route-v1` remains the pinned bundle.
