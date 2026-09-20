# Authoring cloud routines (claude.ai Routines / RemoteTrigger)

This is the guidance for anyone writing or editing a prompt for a **cloud
routine**: a scheduled or run-once Claude Code session that Anthropic hosts
(created and edited via the `schedule` skill / `RemoteTrigger` API, visible at
`claude.ai/code/routines`). It is not local `cron`, and it is not a Vuoro
maintenance lane job. See TS-16 in
[`../plans/2026-09-17-target-state.md`](../plans/2026-09-17-target-state.md)
for the accepted boundary this rule enforces.

## The rule: a cloud routine's judgement must land as a GitHub artifact

**A cloud routine whose job is to produce a judgement, finding, or review
verdict must end every run by opening a GitHub PR that carries that output as
a file — even when the run found nothing to flag.** A read-only review is not
exempt: "read-only" means it does not push to the code it is reviewing, not
that it may skip writing its own report.

**Why:** the routine's cloud session transcript is not a durable store and is
not reachable from the workstation or from `sprintctl`. There is no API this
identity holds that lists cloud session transcripts or resumes one by ID from
a workstation session (`claude agents --json` lists only local sessions). If a
routine's only output is its transcript, a human must manually open
`claude.ai/code` to read it, and a workstation session — attended or
unattended — has no way to tell "the routine ran and found nothing" apart
from "the routine did not run" or "the routine failed silently." Both look
like empty search results from `gh pr list` / `gh issue list` / `gh api
.../comments`.

Concretely (agentops#2471, 2026-09-20): the 2026-09-20 11:00 UTC
`weekly-lanes: independent review of slice PRs` routine
(`trig_01E5rGrQvzeTQ3JajA4yexGX`) fired, ran read-only, and produced a
transcript with real verdicts — and nothing else. No PR, issue, or comment
existed anywhere in agentops/vuoro/sprintctl/appservice after it ran. The
other four routines in the same batch were not read-only and each left a
GitHub PR (vuoro #95, #96, #97, #101); those were the only harvestable
outputs. This is TS-16's gap one layer up: a runtime the operator does not
host did real work the record cannot see, and it failed silently rather than
erroring.

## What "landing a judgement as a GitHub artifact" means in practice

End the routine's prompt with an explicit final step:

1. Write the finding/report to a dated file. For an agentops review routine,
   that is `docs/assessments/<topic>-<date>.md`; pick the analogous
   `docs/assessments/`-style path in whichever repo the routine's report
   belongs to.
2. Commit only that file on a fresh branch, push the branch, and
   `gh pr create` against the repo's default branch.
3. Do this unconditionally — including the "nothing to report" case. State
   that plainly in the report body ("0 branches found", "N reviewed, 0
   findings") instead of skipping the PR. A silent, correct "nothing found"
   run must be indistinguishable in the record from a loud one, and both must
   be distinguishable from a run that never fired or crashed before its final
   step.

Do not rely on the routine posting only into its own session, and do not
treat "the transcript has the verdict" as done. Validate a routine you just
wrote or edited by checking `gh pr list --state all --search <marker>` (or
the repo-appropriate equivalent) after its next fire, not by reading its
transcript at `claude.ai/code`.

## What must never be added to close this gap

**Do not give a cloud routine a forge or served credential.** The cloud can
reach GitHub (that is how the PR in step 2 above gets opened); it cannot
reach served `sprintctl` or Forgejo, and must not be made to. Per TS-16: intent,
coordination and evidence may cross to a runtime the operator does not host;
effects and credentials may not. The GitHub PR *is* the crossing — an
unmergeable branch and a queued intent that a homelab-side identity later
reads, acts on, and signs. Widening a cloud routine's credentials (a
served sprintctl token, a Forgejo token, direct write access outside its own
report file) to "solve" reachability would cross that boundary instead of
using the sanctioned crossing point, and must not be done even as a
convenience.

## Editing an existing routine's prompt

Cloud routine definitions are edited with `RemoteTrigger` (`action: "get"`
then `action: "update"`, `trigger_id: "trig_..."`) — see the `schedule`
skill. They are not stored in this repo. If you cannot reach or edit a
routine's cloud-side definition in a given session (no `RemoteTrigger`
access, or the update call is refused), say so explicitly rather than
reporting the routine as fixed; a change to this guidance document alone does
not change what the cloud routine will do on its next fire, only a
`RemoteTrigger` `update` (or a human repointing it at claude.ai/code) does
that.
