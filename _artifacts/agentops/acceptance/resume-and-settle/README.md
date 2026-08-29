# `resume-and-settle` — recorded runs

`events.db` is the authority here; the Markdown files are projections of it and can be
rebuilt (`acceptlab report --db events.db --run-id <id>`). It is committed rather than the
reports alone because acceptance-lab's own rule is that the event log is authoritative and
projections are disposable, and keeping only the projection inverts that.

| Run | Scenario | Status | Score | What it says |
|---|---|---|---|---|
| `762d7235` | 1.0.0 | FAIL | 0.694 | The first run. Failed `served-surfaces-only` on the probe's own arrange-phase writes — the gate was mis-stated, not the platform. Kept rather than rescored. |
| `15f82e69` | 1.0.1 | FAIL | 0.722 | The corrected gate passes. Three hard gates still fail, all on one thing: the checkpoint and its exact revision do not survive an interruption. |
| `46ba1aac` | 1.0.1 | **PASS** | 1.000 | After the deploy. All eight hard gates and the soft gate. Recovery cost 1.35s. |
| `d7fc543e` | 1.0.1 | FAIL | 0.722 | The same pre-deploy candidate output, re-scored once acceptance-lab pinned scorer revisions. |
| `e7876b67` | 1.0.1 | **PASS** | 1.000 | The same post-deploy candidate output, re-scored under pinned scorers. This is the citable one. |

## Why the last two runs exist

The first three were scored by an unversioned set of thirteen scorer callables, so
nothing in them says which judgement produced the verdict — a settlement citing that
PASS would cite a moving target. acceptance-lab now records a revision per scorer and
one for the evaluation harness, and refuses to compare runs whose revisions differ.

The last two re-score the *same candidate outputs*, byte for byte, under the pinned
build. No probe was re-run and no event was rewritten: the log is append-only and still
carries all five runs. The verdicts are identical to the unpinned ones — 0.722 FAIL and
1.000 PASS — which is the expected result, because the scorers did not change; only
their identification did.

`comparison-before-after.md` is the before/after delta, and it exists only because both
sides are pinned. Asking for the same comparison across the original runs is refused:

    Runs were scored by different scorer revisions and are not comparable:
    checkpoint-recovered: baseline=unrecorded candidate=unrecorded; ...

Unknown is not equal, so two runs that are both silent about their scorers are not
comparable either. That refusal is the point of the pin, not an inconvenience around it.

Same scenario version across the last two runs, so the verdict moved because the platform
did, not because the bar did.

## What changed between them

sprintctl 0.3.4 → vuoro-service 0.1.55 → appservice `cd32a254`. Two defects:
`work.read.handoff` failed outright for any sprint holding an active reservation — the
state an interrupted session leaves behind — and the handoff record discarded the
checkpoint it was given, so a session's position died with its process.

## One correction to the probe, and why it did not manufacture the pass

Between `15f82e69` and `46ba1aac` the probe was taught to read `last_checkpoint` rather
than `git_context`. `git_context` is what the *calling* process observes, which for a
resumer with no worktree is null by construction; `last_checkpoint` is what the *previous*
session recorded. The probe had been asking the wrong process where its predecessor was.

That correction could not have rescued the earlier run. Pre-deploy, the bundle had no
`last_checkpoint` field at all and no 40-character revision anywhere in it — checked
directly at the time — so the corrected reader would have found strictly less, not more.
The first `46ba1aac` attempt, before the correction, still recovered the revision, but by
scraping a sha out of the response blob rather than by reading a field that means
"checkpoint". That is why the fallback now marks what it finds as scraped: a probe that
cannot tell a lucky grep from a recovery will eventually report one as the other.
