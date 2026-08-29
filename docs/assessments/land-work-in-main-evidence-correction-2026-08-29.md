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

---

## Addendum: blast radius of the `ci-not-on-main` observation

The practice's "land on `main` and let CI catch issues" has an unmet
precondition, recorded as observation `ci-not-on-main`. Surveying every
`.github/workflows/` under `/projects/dev` bounds it: **three workflows, in
three repos, trigger on `pull_request` only.**

| Workflow | Assessment |
|---|---|
| `homelab-analytics/verify.yaml` | **The real gap.** A full verify suite (`verify-fast`) that never runs on `main`. This is the one confirmed empirically — a push of `7894ef8` produced no Verify run. |
| `agentops/protected-paths.yml` | **Newly load-bearing.** A protected-paths gate that only fires on PRs never fires at all once work lands directly. Under the old PR-default this was adequate; under `land-work-in-main` it is a gate that has stopped gating. |
| `appservice/placeholder.yaml` | Already addressed by `appservice` #1559, which removes it and gates automerge on Offline Validate. That PR is deliberately held open for human review. |

Everything else already triggers on `push`. Notably `aligned-equity/verify.yaml`
carries `push: branches: [main]`, which is why landing 23 commits there
directly on 2026-08-29 did exercise CI rather than bypassing it.

**Sequencing — do not fix this by adding push triggers yet.** The
`git.apps.kotona.app` runner move comes first. Adding `push` triggers on
hosted runners pays for the policy in GitHub Actions minutes, which is spend
that was already decided against. The correct order is: move the runners,
then add push triggers, then the practice's precondition is met.

Until then the honest statement of the practice is narrower than its wording:
*land on `main` and let CI catch issues — in the repos where CI actually runs
on `main`.* Two repos are currently outside that set. The contradiction is
correctly recorded rather than resolved.
