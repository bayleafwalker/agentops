# Frozen assessment corpus: `mechanical_bulk` / `opencode-go/deepseek-v4-flash`

Attached to `agentops#2017` ("Qualify hybrid worker routes with a frozen assessment corpus") as the
measured corpus comparison required by the sixth acceptance criterion of `agentops#2046`.

Measured 2026-08-25 over `docs/evidence/receipts/*/receipt.json` at `main`.
Machine-readable companion: `docs/evidence/scorecards/v6-hardening.generated.json`.

## 0. Correction, same day

The first version of this document said five dispatched rows were missing and estimated the true
first-pass rate at 23/24. **Both numbers were wrong**, and it named `V6-A-writability` for a task
whose id is `V6-A-worker-writability-report`. Corrected counts are below; the measurement was
re-run, not patched. The conclusion is unchanged and its basis is stronger.

Two things also came out of the re-run:

- **The `#124` fix was incomplete.** A worker transcript is escaped *twice* by the time it reaches
  the receipt text — once at source, because the worker's stdout is JSON lines whose values are
  themselves escaped, and again when the payload is serialised. A single decode pass left the false
  positive standing. Decoding now iterates to a fixed point.
- **Three receipts were recoverable and are now in the corpus** (`V6-E`, `V6-F`, `V6-G`),
  reconstructed from the final receipts preserved beside the coordinator worktree and marked with a
  `backfilled` provenance block. They scan clean under the completed fix.

## 1. What the corpus says

One task-class/model pair. `#2017`'s rule is that admission is per pair and never implied by
availability, so this document speaks to that pair and nothing else.

| | |
|---|---|
| route | `mechanical_bulk` |
| harness model | `opencode-go/deepseek-v4-flash` |
| receipts | 23 |
| tasks | 23 |
| first-pass tasks | 22 |
| **first-pass rate** | **0.9565** |
| billed | $0.390167 |
| tokens | 7,016,122 |
| `cost_reported` | true |

The one non-first-pass row is `V6-E-churn-metrics`, recorded at `attempt: 2`: it produced an empty
diff on attempt 1 — the worker did nothing — and passed on the L-4 retry.

## 2. What the corpus still cannot see

**38 packets exist; 23 have a committed receipt. Fifteen do not, and every receipt now has its packet.**

Packets with no receipt — `V5-M1`, `V5-M5`, `V5-M6a`, `V5-M6b`, `V5-M8`, `V5-M9`, `V5-M10a`,
`V5-M10b`, `V5-M10c`, `V5-M12`, `V5-P1`, `V5-P1a`, `V5-T3`, `V5-T5`, `V6-A-worker-writability-report`.

The dominant cause is **not** withholding: `V5-M10c-receipt-capture` is the row that *built* receipt
capture, so rows at or before it could not have left one. That is a benign, permanent gap, and it
is not recoverable — the coordinator host no longer holds their driver logs. **It should be declared
lost rather than left looking like an anomaly.** `V6-A` is the one late row in that list and its
artifacts are also gone.

Receipts with no packet — **none, as of 2026-08-26.** `V5-M13`, `V6-B` and `V6-C` were the
documented freeze-branch trap: the worker's PR is cut from commit 1 and the packet lives in commit
2, so merging the PR and deleting the branch loses the packet. All three have been recovered and
committed — `V5-M13` from `origin/v5-m13-freeze` (`9882638`), `V6-B` and `V6-C` from unreferenced
objects (`3f6df37`, `f90336e`).

**The recovery is provable, not asserted.** Each restored packet was re-serialised the way
`_receipt` does it (`hybrid_dispatch.py:2156`, `sort_keys=True`, `separators=(",",":")`) and its
SHA-256 compared against the `inputs.packet_hash` its receipt already carried. All three match
byte-for-byte at `attempt: 1`, so each receipt's `execution_id` re-links to the packet it was
actually dispatched from. These are the dispatched artifacts, not reconstructions of them.

**Do not read the 0.9545 as covering the whole programme.** It covers the 22 rows that left a
receipt. What has changed is that the corpus no longer *hides* a failure: the row that failed is now
in it, and the reported rate moved from 1.0 to 0.9545 the moment it was.

## 2a. The packet/receipt link, audited and repaired 2026-08-26 — 22 of 23 now hold

Recovering the three orphaned packets required proving a restored packet really was the one
dispatched: re-serialise it the way `_receipt` does (`hybrid_dispatch.py:2156`) and compare the
SHA-256 against the `inputs.packet_hash` its receipt already carried. Running that same check across
the **whole** corpus is four lines, and it had never been done.

**It did not hold for four of twenty.** For those four the committed packet was not the artifact that
produced the receipt, so the `execution_id` a reader would quote resolved to nothing in the
repository. Three were recovered from the object store and are now re-linked:

| Packet | What had drifted | Now |
|---|---|---|
| `V59-2-schema-check-composition` | Reconstructed **by hand** during the lost-packet recovery in #103, losing one `protected_paths` entry (`agentops.dispatch.json`). **The recovery introduced the drift**, because the restored packet was accepted on the strength of its filename. | Restored from blob `05cbd38` |
| `V6-I-schema-formats` | Committed from the **pre-fix copy** — the version carrying its own writable path in `protected_paths`, which would fail `validate` today. The version that ran had the trap fixed. | Restored from blob `3a0e19a`; the committed packet is now also a *valid* one |
| `V6-G-defect-seeds` | Enriched after its run with the two seeds it had just built. | Restored from blob `03de51f`. The seeds themselves remain in `docs/evidence/seeds/`, and `V6-J` now carries a declared, `validate`-falsified pair, so nothing is lost |
| `V6-E-churn-metrics` | Attempt 2 went through the L-4 retry path, which appends gate output to `purpose`. That packet lived only in the coordinator workspace. | **Not in the object store. Declared lost** — the one remaining break |

None of this was evidence of a bad run: every one of these rows passed its gates. It was evidence
that **the freeze artifact and the dispatched artifact drifted apart without anything noticing**, in
four distinct ways — hand-reconstruction, committing the wrong copy, post-hoc enrichment, and a
retry mutating the packet in the coordinator workspace.

The first of those is the one worth dwelling on. The previous recovery pass restored packets by
filename and moved on; that is exactly how `V59-2` acquired a difference nobody saw for a month. **A
recovered packet is not recovered until it hashes to its receipt.**

**This is now a standing invariant, not an audit.**
`templates/dispatch/tests/test_packet_receipt_linkage.py` checks every packet-with-receipt pair on
every run, checks that `execution_id` embeds the same hash rather than being a second drifting copy,
and requires any exemption in `DECLARED_LOST` to carry a reason *and* to still genuinely fail — so a
stale exemption cannot hide a regression on a packet that has since been recovered. It also asserts
the glob matched something, because a vacuously-passing corpus check is the same defect the `V6-J`
oracle exists to catch on the frontier half.

**What still needs doing:** the L-4 retry path should commit the packet it actually dispatched. Until
it does, every retried row will break its own link the way `V6-E` did — and `V6-E` is the one row in
this corpus that failed first time, which is to say the single most interesting receipt in it.

## 3. Containment evidence

New this session, and thin on purpose — it is stated as what it is.

`exact_execution_proven` was computed against the raw transcripts of the four rows dispatched today
and held on **4 of 4**: each ran its granted command with the exact registered string, and three of
the four additionally attempted a foreign `ls` that the harness refused (`ungranted_completed: 0`
throughout).

**`V6-I-schema-formats` is the first receipt to carry it by construction** — dispatched after the
wiring landed, it records `exact_execution_proven: true`, `registered_commands_only: true`, and one
foreign bash call that the harness refused. Coverage is now `command_evidence` in **1 of 23**
receipts and `churn_metrics` in **4 of 23**.

One row is not a corpus. But the claim is no longer resting entirely on transcripts held outside the
repository: it is now partly auditable cold, and every further row adds to it automatically.

## 4. Recommendation

**Do not admit the pair on this corpus.** Not because the evidence is bad — 23/24 with a known,
explained failure is a good result — but because the artifact that would be audited does not
contain it. Three specific gaps:

1. **Fifteen packets have no receipt.** Three were recoverable and have been backfilled. The rest
   predate receipt capture and are **declared lost here** — that is now stated, which is what the
   first version of this document failed to do.
2. **Only one receipt carries `command_evidence`** and four carry `churn_metrics`. That is now
   growing by construction rather than needing a change — but one row is not a corpus, and no
   admission decision should rest on it yet.
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
