# `land-work-in-main` — evidence correction

**Date:** 2026-08-29
**Corrects:** the survey cited as basis in commits `ca422b1` and `9865215`
**Effect on the claim:** none — the policy stands, and the corrected evidence
is stronger than the evidence it replaces.

## What the original survey reported

The 2026-08-29 survey of `/projects/dev` that motivated the `land-work-in-main`
skill changes reported two findings:

1. Eight repos sitting ahead of `main` on unlanded branches.
2. **Zero open PRs anywhere** — from which it concluded that the failure mode
   was not "a PR nobody reviews" but work that was never proposed at all.

## What was actually true

Finding (1) was correct. Finding (2) was an artifact of the measurement.

`gh` and forge API calls fail **silently** inside the Claude Code tool
sandbox: no error, exit 0, empty output. The survey's PR query never reached
GitHub. Re-run with the sandbox disabled, the same query returned **six open
PRs**, four of them substantive:

| Repo | PR | State | Reviewers |
|---|---|---|---|
| `kctl` | #8 | ready, CLEAN, checks green | 0 |
| `appservice` | #1559 | draft, checks green | 0 |
| `vuoro` | #62 | draft, checks green | 0 |
| `agentops` | #140 | draft, checks green | 0 |
| `actionq` | #40 | draft, **CONFLICTING** | 0 |

Two `ha-elisa-kotiakku` dependabot PRs make up the remaining six.

Two of the eight "unlanded" branches were also mis-read: `actionq-dispatcher`
and `cluster-alignment-mvp` were reported as existing only on local disk and
therefore at risk against the 7-daily snapshot window. Both had in fact been
squash-merged upstream nine days earlier and their remote branches deleted.
The `[gone]` tracking ref plus a stale local `main` produced a false
"1 ahead, not pushed" reading. `git diff <branch> origin/main` was empty in
both.

## Why the claim is strengthened, not weakened

The original reasoning was: *the failure isn't an unreviewed PR, it's work
that never became visible at all.* The corrected evidence shows **both**
failure modes running simultaneously — and the PR half is the more exact
illustration of the policy. Every one of those PRs had `reviewers: 0` and no
review decision. Four were parked as drafts. One had already decayed into
merge conflict during the week it sat there.

That is precisely what `pr-handoff-summary` now forbids: a PR opened for a
reader who was never named. The survey did not find an absence of that
pattern; it found six instances of it and could not see them.

## The second-order finding

The survey's own failure is the same defect shape the policy exists to
catch — a step reporting success while doing nothing. An empty result and an
unreachable endpoint are indistinguishable from the output alone, so
"returned nothing" was read as "there is nothing". This is recorded as a
standing verification rule in `/projects/dev/AGENTS.md` § *Empty is not
absent*: state absence only when the channel demonstrably answered.

## Disposition

All eight branches and five of the six PRs are now resolved. `appservice`
#1559 remains open by owner decision — it changes CI automerge gating and is
held for human review, which is a *named* action and therefore a legitimate
reason for a PR to stay open under this policy.
