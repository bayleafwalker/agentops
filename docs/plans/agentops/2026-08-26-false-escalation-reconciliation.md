# The eight escalations of 2026-08-26 — reconciled

Prepared 2026-08-26, after the gate landed. Two sessions escalated four items
each. Re-measured, the true counts were **zero** and **one**. The gate that came
out of that (`templates/dispatch/skills/escalation-gate/SKILL.md`, and
`templates/dispatch/scripts/check_decision_briefs.py`) stops the *next* one. It
does nothing about the eight already in the record, or about anything derived
from them.

This document is that half. A repository can be repaired while its active
decision state stays poisoned, so the question here is not "was the gate built"
but "is anything still live that should not be".

## 0. Classification of this document

Per the three axes. **Everything below is derivable and already derived.** No
item in this document is a new value choice; the two that remain the owner's are
named in §4 and are neither re-opened nor re-argued here. Governing text:
`docs/dispatch/handover-2026-08-23-metanarrative-v5.md` Rule 4, which enumerates
the owner touchpoints, and §2a, which defines the two kinds of cost.

## 1. The failure shape, stated once

Every one of the eight had the same shape:

> a rule's **rationale** recalled correctly and its **scope** recalled wrongly,
> then the recollection treated as the constraint.

The governing text was on disk each time. That is why the gate's operative step
is *open the governing text and quote it with a citation, and read it for scope
rather than gist* — not *think harder*.

## 2. Session one — the four in `2026-08-26-open-owner-decisions.md`

Ruled and executed the same day; that document carries the outcomes table. Their
classification, restated against the axes:

| # | Claim as escalated | Governing text | Actual scope | Correct classification | Disposition |
|---|---|---|---|---|---|
| 1 | Accept `agentops#2046`? | the designated human acceptance event | the *event* is the owner's; the six criteria were already verified at file and line | **ratification** — bring a resolved action | Accepted (B); notes #2538, #2539; item `done` |
| 2 | `#2100`: are route and authority one axis or two? | the 2026-08-23 ruling: *"a green evidence gate **on this class** disposes candidate"* | the ruling already says authority attaches to a **class**; `self_candidate_class` looked it up by `route` | **derivable** — policy application, not policy making | `action_class` landed; `#2100` closed (note #2544); successor `#2306` |
| 3 | devbox checkout disposal | none — bounded maintenance | the recorded debt said 179 commits behind and 23 dirty files; measured, 29 behind and clean | **derivable**, after re-measurement | Fast-forwarded, inspected, disposed |
| 4 | Should `format: "uuid"` start biting? | the manifest schema | all 18 manifests were already checked before the question was asked | **derivable** — a review-derived fix | `validate_manifest_identity` + 13 regression tests |

Three of the four had *already been derived* before the document was written and
were presented as open questions anyway. The owner's assessment — *"the human was
mostly being used as a very expensive Enter key"* — is the record of that.

One correction that survived and matters: decision 3 called the stashes twenty
minutes of tidying. `stash@{1}` would have reverted `overlay_hash` to sorted keys
and deleted the test pinning the property. An old branch can carry a reversal of
a decision made after it, so "old branch, main moved on" is not a safe default.

## 3. Session two — the four in `2026-08-26-measurement-instrument-findings.md`

| # | Claim as escalated | Governing text | Actual scope | Correct classification | Disposition |
|---|---|---|---|---|---|
| 5 | Global hook registration | the goal itself | a permission prompt was read as a policy question; a gate is not a deliberation | **ratification**, at most | Registered via `sync-devbox.sh --apply` |
| 6 | Subagent scoping | none | reported "unscoped" when the correct action was to go and scope it; unscoped is an unfinished task, not a finding | **derivable** | Measured: +9.1% overall, +23% across the T-series window |
| 7 | The resume-truncation bug | none | unfinished diagnosis filed as a handoff | **derivable** (diagnosis), still at hypothesis stage | Labelled hypothesis; repro named; resumed rows treated as lower bounds |
| 8 | **Finding E** — subagent spend uncounted | handover §2a | §2a separates *imputed from metered*; it says nothing about which imputed usage counts | **new value choice** — genuine | **Open.** Recommendation B (sibling `subagent_totals`) stands |

Finding E is the one true escalation in either session, and it did not appear on
either list of "what's yours to decide" — it surfaced only after reading the
process docs that should have been read first.

## 4. The live owner surface, asserted

Swept across `docs/plans/agentops/`, `docs/dispatch/handover-*.md` and the
receipts. **Exactly two items are live:**

1. **Finding E** — subagent spend. Options A/B/C and recommendation B stand as
   written in `2026-08-26-measurement-instrument-findings.md` §Finding E.
2. **The audit-ledger disposal** — the 424 fixture events, §6 of
   `2026-08-26-v6k-remainder-plan.md`. Planner's reading C.

None of the eight above remains live. Items 1–4 are ruled and executed with the
landing artifacts named; 5–7 are executed or correctly reclassified in place; 8
is item 1 of this list.

## 5. What was appended, not rewritten

The prior documents keep their original text. `2026-08-26-open-owner-decisions.md`
already carries its correction as a header block above the unchanged original,
and this document adds to the record rather than editing either source. That
choice is not only hygiene: §6 of the remainder plan is precisely the open
question of whether an append-only store may be rewritten at all, and a
reconciliation that rewrote history would pre-empt the ruling it is waiting on.

## 6. What this became mechanically

The eight are behavioral fixtures, not prose, in
`templates/dispatch/tests/test_check_decision_briefs.py`:

- the **unclassified escalation** shape (items 1–7) must be caught;
- **Finding E's** shape — a genuine new value choice, classified and cited —
  must be *left alone*. A gate that only ever fires is as useless as one that
  never does, and over-escalation is the failure this project has, so the
  positive case is the one worth pinning.

The gate cannot tell whether a classification is *correct*; nothing mechanical
can. It enforces that the question was asked in writing, because in all eight
cases it never was.
