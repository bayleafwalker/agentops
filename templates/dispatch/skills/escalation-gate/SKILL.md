---
name: escalation-gate
description: Run before telling the owner that something is theirs to decide, and before writing any document that presents open decisions. Converts "this needs a ruling" into a resolved action, a ratification, or one narrowly framed policy question.
---

# Escalation gate

Use this whenever you are about to write "this is your call", "awaits your
ruling", "the open owner decisions", or any variant. Also use it before filing a
plan, findings or handover document that contains such a section.

## Why it exists

On 2026-08-26, two separate sessions escalated four items each. Re-measured, the
real counts were **zero and one**. The owner's assessment of the first:

> zero to one of the four required fresh human judgment... the human was mostly
> being used as a very expensive Enter key.

Every false escalation had the same shape: **a rule's rationale was recalled
correctly and its scope wrongly, and the recollection was then treated as the
constraint.** The governing text was on disk every time.

The sharpest example is worth carrying, because it looked airtight. The claim was
that handover §2a's two-kinds doctrine made subagent usage an owner decision.
Checked against the code rather than the prose: `release_scorecard.py` names the
field `usage_equivalent_usd`, and the guarded invariant is
`total_billed_usd == worker_billed_usd`. §2a separates *imputed from metered* —
it says nothing about which imputed usage counts. Subagent tokens are the same
kind as frontier tokens, so counting them moves the frontier figure and leaves
billed money untouched, which is exactly what the invariant permits. There was
no doctrine to reopen. It was an undercount, and an undercount is a defect.

Note that prose guidance already existed and did not hold: the failure recurred
within one working day of being documented. That is why this skill ends in a
mechanical check.

## The three axes

Ask them in order. They are independent, and **only the third is an escalation.**

**1. Can the answer be derived?** Usually yes. Derive it. If it needs a
measurement you have not taken, *take the measurement* — "unscoped" is not a
finding, it is an unfinished task you are handing to someone with less context
than you.

**2. May you perform the resulting action?** An authorization gate — a human
acceptance event, a deploy, dropping someone's stashes, spending budget — is
**ratification, not deliberation.** Bring a resolved action for signature, not a
question. A permission prompt or a refused tool call is a gate of this kind; it
is *not* evidence that the underlying choice is the owner's.

**3. Is a new value choice necessary?** Only this is a real escalation, and only
when the choice is **new policy** rather than **applying policy the project has
already stated**. If the governing text settles it and you are merely predicting
which reading is more convenient, that is policy application.

## Before you assert axis 3, do this

For each item you believe is genuinely the owner's:

1. **Open the governing text and quote it.** Not from memory. Cite it as
   `file:line`, `§n`, or `Rule n`. If you cannot point at it, it is not a
   constraint — it is a recollection.
2. **Read the quote for scope, not for gist.** The recurring failure is a rule
   whose *reason* you have right and whose *reach* you have wrong. Ask
   specifically: what does this rule range over? A class, a route, a kind, a
   window, a path? Does the thing in front of you fall inside that range?
3. **Check whether the brief already answers it.** Handover §1: *"This document
   is the whole brief. Read the files it names; do not re-derive them from
   chat."* Several past escalations were answers already written down, restated
   as questions.
4. **Check Rule 4's enumeration.** The owner touchpoints are: the release
   boundary, freeze amendments, anything the admission policy names
   coordinator-only (oracle design, authority plane, migration, recovery), and
   the v5.9 refactor pass. If your item is not one of these, the default is that
   it is not an escalation.
5. **Re-measure any record you are relying on.** A stale or overstated record is
   never an owner decision — correct the record and the decision usually
   evaporates. Precedent: a debt entry claiming 179 commits behind and 23 dirty
   files was, when measured, 29 behind and clean.

## The output

The default output of a planning or review cycle is **an execution packet of
resolved actions**, plus **at most one narrowly framed policy question**.

Classify every item explicitly in the document, using the words *derivable*,
*ratification*, or *new value choice*, and cite the governing text. This is not
a style preference — `check_decision_briefs.py` enforces it over
`docs/plans/agentops/*.md`, because prose guidance demonstrably did not survive
a single working day.

## Format

Follow `docs/plans/agentops/2026-08-26-open-owner-decisions.md`: Background →
Options with their implications → Recommendation → **and a re-measurement of
whether the item is genuinely gated at all.** That last step is the one that
changes the answer; in the pass that document records, it removed three of four.

## Verify

```
python templates/dispatch/scripts/check_decision_briefs.py
```
