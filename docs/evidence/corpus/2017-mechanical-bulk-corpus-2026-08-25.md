# Frozen assessment corpus: `mechanical_bulk` / `opencode-go/deepseek-v4-flash`

Attached to `agentops#2017` ("Qualify hybrid worker routes with a frozen assessment corpus") as the
measured corpus comparison required by the sixth acceptance criterion of `agentops#2046`.

Measured 2026-08-25 over `docs/evidence/receipts/*/receipt.json` at `main`.
Machine-readable companion: `docs/evidence/scorecards/v6-hardening.generated.json`.

## 1. What the corpus says

There is exactly **one** task-class/model pair in the corpus. `#2017`'s rule is that admission is
per pair and never implied by availability, so this document can speak to that pair and to nothing
else.

| | |
|---|---|
| route | `mechanical_bulk` |
| harness model | `opencode-go/deepseek-v4-flash` |
| receipts | 19 |
| tasks | 19 |
| first-pass tasks | 19 |
| **first-pass rate** | **1.0** |
| billed | $0.318435 |
| tokens | 5,446,953 |
| `cost_reported` | true |

## 2. Why that 1.0 must not be used as-is

**The corpus is missing five dispatched rows, and the only row that needed a retry is one of them.**

Withheld receipts were never written at all (the defect closed in #124), so `worker_totals` — which
reads receipts — cannot count a run that left no file. Absent from `docs/evidence/receipts/`:

- `V6-A-writability`
- `V6-D-validate-dispatch-manifest`
- `V6-E-churn-metrics`
- `V6-F-gate-tiers`
- `V6-G-defect-seeds`

`V6-E-churn-metrics` went **red on attempt 1** (empty diff — the worker did nothing) and passed on
the L-4 retry. It is excluded. Every excluded row is excluded for the same reason — a secret-scan
false positive on JSON-escaped transcript text — and that reason is **uncorrelated with whether the
row passed**, except that the one failure happens to be inside the excluded set.

So the measured rate is not merely uncertain, it is **biased upward**, and the direction is known:

- measured over the corpus: **19/19 = 1.0**
- including the five excluded rows, using the dispatch logs: **23/24 ≈ 0.958**

The scorecard nonetheless reports `cost_reported: true` and `total_reliable: true`, because every
receipt it *can* see reported its cost. **A corpus with a hole in it produces a reliability flag
that is true and a rate that is wrong.** That is the failure mode recorded as debt and now
demonstrated on a live artifact rather than predicted.

## 3. Containment evidence

New this session, and thin on purpose — it is stated as what it is.

`exact_execution_proven` was computed against the raw transcripts of the four rows dispatched today
and held on **4 of 4**: each ran its granted command with the exact registered string, and three of
the four additionally attempted a foreign `ls` that the harness refused (`ungranted_completed: 0`
throughout).

That measurement is **not yet in the receipts**. The wiring (#129) landed after the last dispatch,
so `command_evidence` appears in **0 of 19** receipts and `churn_metrics` in **1 of 19**
(`V6-H-command-evidence`). The containment claim above therefore rests on transcripts held outside
the committed corpus, and does not survive a cold audit of this repository alone.

## 4. Recommendation

**Do not admit the pair on this corpus.** Not because the evidence is bad — 23/24 with a known,
explained failure is a good result — but because the artifact that would be audited does not
contain it. Three specific gaps:

1. **Five rows are missing.** Fixed forward by #124, which writes a stub receipt on a withholding.
   The five historical rows can be backfilled from the dispatch logs, or declared lost; either is
   fine, but the corpus must state which.
2. **No receipt yet carries `command_evidence`.** The next dispatched row will be the first. One
   row is not a corpus.
3. **`frontier` is all zeros** in the generated scorecard — the Stop hook writes per turn, and a
   scorecard generated inside the session it measures has nothing to read. Read it as "not
   measured", never as "free".

**The cheapest thing that would settle it:** dispatch the next few rows normally and re-measure. The
receipts will then carry churn and command evidence by construction, and the withholding path now
leaves a countable stub, so the same script produces a corpus that can be audited cold.

**Falsifier for this recommendation:** if a re-measure after those rows shows `command_evidence`
present on every new receipt, no `ungranted_completed > 0` anywhere, and a first-pass rate computed
over a corpus with no missing rows, then the pair qualifies on its own evidence and this document's
objection is spent. The objection is about the corpus, not about the model.

## 5. What is explicitly not claimed

- Nothing about `bindery_external_runtime_w0`. It has zero packets; there is no evidence either way.
- Nothing about other repositories. Six repos opt into the route name; none of their receipts are
  in this corpus.
- No comparison against a frontier-only control. The corpus has no control arm, so "cheaper than
  doing it directly" is unmeasured here and remains an open question for `#2017`.
