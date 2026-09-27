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

## Record the run through the Vuoro connector

The PR shows that the routine ran and what it concluded. It does not show what
produced the verdict or which evidence it rests on. Since generation 47 the
Vuoro connector grants the record tools (`vuoro:evidence.record`:
`register_run`, `append_evidence`, `write_session_note`), so every routine
also leaves a run record, and its PR names that record. In a routine session
the tools appear as `mcp__Vuoro__register_run` and so on.

1. **At start, before any other work, call `register_run`** with the
   RunManifest fields:
   - `harness_id`: `claude-code`.
   - `harness_build`: the output of `claude --version` in the session.
   - `model_id`: the model id the session runs as.
   - `recipe_id`: `<owner>/<repo>:<prompt path>@<blob>`, where `<blob>` is
     `git rev-parse HEAD:<prompt path>`. Keep the routine's real instructions
     in a versioned file in the report repository (`docs/routines/<slug>.md`
     in `bayleafwalker/vuoro`). The prompt stored in the Routine is a short
     stub that says to follow that file.
   - `observed_profile`: `{"instruction_digest": "sha256:<sha256sum of the
     prompt file>", "skill_digests": []}`.
   - `idempotency_key`: `routine.<slug>.<YYYYMMDDTHH>`, where the timestamp is
     the UTC hour in which the session started (`date -u +%Y%m%dT%H`). A
     retry within the same hour reuses the key and gets the same `run_id`
     back, so one fire stays one run. The coverage funnel counts retries once
     per expected invocation either way.

   Keep the returned `run_id` for the rest of the session.
2. **For each finding, call `append_evidence`** with `kind: "finding"`,
   `ref: "<report path>#<finding id>"`, `digest: "sha256:<hex>"` of the
   finding's text, `collector: "<slug>"`, `validity: {"basis":
   "until_inputs_change", "valid_from": "<now, ISO 8601>"}` and
   `idempotency_key: "<run key>.f<n>"`. A run that finds nothing records no
   findings, but it still records step 3.
3. **After writing the report file and before committing it, call
   `append_evidence` for the report itself** with `kind: "report"`,
   `ref: "<report path>"` (repository-relative, with no `#fragment`),
   `digest: "sha256:<sha256sum of the file>"` and
   `idempotency_key: "<run key>.report"`. Do not edit the file after this
   call: the coverage funnel checks the digest against the file in the PR.
4. **End the PR body with the line `Vuoro-Run: <run_id>`** on a line of its
   own. Do not wrap the key in bold; backticks around the value are
   tolerated.
5. **After opening the PR, call `write_session_note`** with a short summary
   of the verdict, the PR URL and the same `Vuoro-Run: <run_id>` line
   (`idempotency_key: "<run key>.note"`).
6. **If a record tool is missing or refused** (the connector was not
   re-authorized after the grant widened, or a tool returned an error), still
   open the PR required above. Write `Vuoro-Run: unavailable (<error code or
   "tools not listed">)` in the PR body and in the report. The conformance
   check then fails with that reason instead of the run going silently
   unrecorded.

**Check a routine PR** from the trusted side:

```sh
agentops routine-pr-conformance <pr-number> --records <export.json>
```

The command exits 0 only if the PR's `Vuoro-Run` trailer resolves to a run
whose RunManifest fields are non-empty and which has at least one evidence
item. It exits 1 for a non-conformant PR, including a PR with no trailer, and
2 when its inputs cannot be read. The records export is JSON produced by
`agentops vuoro-run-records --sql [--since <date>]`, run against the tenant
runtime's database through the operator's backend-inspection path (a bounded
`psql` over the private Kubernetes API; vuoro-cloud
`docs/runbooks/operator-access.md`). To run the query directly, pass
`--records-cmd "<that psql command>"` instead of `--records`: the SQL goes to
the command on stdin. The export is needed because the served read path
resolves a run only for the exact binding that registered it. A workstation
identity is not the Routine's binding, and no cross-binding `describe_run`
operation exists yet.

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

The Vuoro connector's record tools are not an exception to this rule. They
carry evidence and coordination, which TS-16 lets cross: the operator
consents to the connector's OAuth grant in claude.ai, and the grant is bound
to one client, principal and workspace. The routine never holds a token it
could reuse elsewhere, and a run record is not an effect.

## Editing an existing routine's prompt

Cloud routine definitions are edited with `RemoteTrigger` (`action: "get"`
then `action: "update"`, `trigger_id: "trig_..."`) — see the `schedule`
skill. They are not stored in this repo. A routine that follows the record section
above keeps its real instructions in the report repository
(`docs/routines/<slug>.md`), so changing the file changes the next fire, and
the run's `recipe_id` and `instruction_digest` show which revision ran. The
Routine's own prompt stays a stub that points to that file. If you cannot reach or edit a
routine's cloud-side definition in a given session (no `RemoteTrigger`
access, or the update call is refused), say so explicitly rather than
reporting the routine as fixed; a change to this guidance document alone does
not change what the cloud routine will do on its next fire, only a
`RemoteTrigger` `update` (or a human repointing it at claude.ai/code) does
that.
