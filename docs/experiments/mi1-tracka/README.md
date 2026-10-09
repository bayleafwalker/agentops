# MI-1 Track A: bounded comparison protocol

Status: frozen preparation snapshot (2026-10-09). Served item 2616 remains open.

Current execution status, checked 2026-10-09: the manual workflow was installed
by [PR321](https://github.com/bayleafwalker/agentops/pull/321), merge
`074e5c29c8a539f98f9e018c041675d6f16e4bf3`. Both isolated native cases have
executed and their report PRs remain open drafts, held outside the default
branch until the hosted cases finish. No hosted comparison run has started:
the GitHub Actions secrets API still reports zero repository secrets, so the
required `ANTHROPIC_API_KEY` is unavailable. These observations do not establish
comparative quality, operator time, total cost or a kill-rule decision. The
common task and input protocol stays frozen at
`5b309b9003327b1cfdf25bf3b702c4abc9e4a75e` for both paths.

The preparation record below describes what was verified before execution;
its statement that the companion is only a template is historical. The active
manual workflow now lives at `.github/workflows/mi1-tracka.md` with its compiled
lock file. Its installation does not schedule or dispatch any session.

This packet supplies common inputs and a rubric for two real repository review
cases. It contains no comparative results. The companion workflow is a template
outside `.github/workflows`; committing it does not enable execution.

## Verified prerequisites and capabilities

GitHub Agentic Workflows compiles Markdown plus frontmatter into Actions YAML.
Its standard agent job is read-only; declared safe outputs apply GitHub writes
in separate jobs. A draft report PR fits the same proposal/review boundary as
the native path. This is a vendor execution path, not a new Vuoro driver.
See the [official overview](https://docs.github.com/en/copilot/concepts/agents/about-github-agentic-workflows),
[workflow structure](https://github.github.com/gh-aw/reference/workflow-structure/)
and [safe outputs](https://github.github.com/gh-aw/reference/safe-outputs/).

The measured latest release was `v0.89.21`, published 2026-09-23, at source
`c35393777e5604a63721d09512263b1383301d4f`. The Linux AMD64 compiler was downloaded
to a session-local directory and matched the published checksum
`1c74ff5fc28b1891d32b67f4348a9b7f750946b6d4a721e909187a848868016b`.
Checksum agreement alone is not a provenance attestation. Release-specific
[authentication](https://github.com/github/gh-aw/blob/c35393777e5604a63721d09512263b1383301d4f/docs/src/content/docs/reference/auth.mdx),
[PR outputs](https://github.com/github/gh-aw/blob/c35393777e5604a63721d09512263b1383301d4f/docs/src/content/docs/reference/safe-outputs-pull-requests.md)
and [cost](https://github.com/github/gh-aw/blob/c35393777e5604a63721d09512263b1383301d4f/docs/src/content/docs/reference/cost-management.md)
were read, so website changes do not silently redefine the prepared candidate.

The actual GitHub API reported Actions enabled, repository owner type `User`,
and **zero Actions secrets** for `bayleafwalker/agentops`. No installed `gh aw`
extension was found. The released documentation requires `ANTHROPIC_API_KEY`
for this Claude template, or a separately configured Anthropic WIF rule.
It explicitly does not support Claude subscription OAuth tokens. Its keyless
Copilot route requires organization subscription and centralized billing;
that documented prerequisite is absent for this personal repository. No
inference run has been attempted and no subscription outage is inferred.
Existing workstation credentials have not been exported or repurposed.

## Cases and common inputs

[cases.json](cases.json) freezes the source revisions and tasks. `receipt-audit`
reviews the actual public MI-1 receipt packet merged in PR319. `ci-diagnosis`
uses the actual failed public workflow run 36913128176, head
`343bb1bd10e575b90eb36a8cb7bbb0a9d599bbe1`, and failed job 110540455279.
[The copied public log](inputs/ci-failure.log) retains the fetched bytes and its
SHA256 is in the ledger. It is input evidence, not a new experiment run.

Freeze the final protocol commit before launching either path. Give both the
same case task, source revisions and ledger. Record the actual engine, model,
build, configuration, instruction digest and input digests for every attempt;
provider omissions remain unknown. Do not compare a native session with
private diagnostic context against a hosted session lacking that context.
The current coordinator therefore cannot act as the isolated native comparator.

Each path proposes one report PR per case. Neither may change historical
evidence, owner state, workflow policy or source behavior. A separate reviewer
checks source citations, factual accuracy, reproducibility and absence of
invented authority. Passing requires all four; a useful no-findings report
can pass. Record each failure and correction rather than replacing an attempt.
The reviewer identifies their prior knowledge; this is not a blinded study.

## Measurements and decision

Record operator active seconds separately for setup, instruction, review and
recovery, using an explicit timer or operator-provided measurements. Agent wall
time and time spent waiting are separate fields. An unmeasured human interval
is unknown, never zero. Record correction count, first-pass rubric outcome,
accepted final quality and recovery actions for each case and path.

Capture engine usage and Actions job durations from original run artifacts;
retain native usage snapshots with their cumulative/session semantics. Label
`gh aw` AI-credit cost as an estimate and provider invoice cost separately.
Include setup and recovery costs; unknown invoice or subscription allocations
remain unknown. A token total alone is not a total-cost comparison. If a report
PR created with `GITHUB_TOKEN` does not trigger CI, record that limitation and
the actual coordinator action required; do not quietly introduce another token.

The candidate has only a manual trigger, a 15-minute inference-step timeout, 12 agent turns,
100 AI credits (a $1 estimate cap, not a billing guarantee), one draft report PR
and a one-file/32-KB output limit. No automatic schedule or merge is proposed.
Before execution, review the compiler-emitted jobs and immutable action pins,
verify inference authentication, and obtain delegation for the bounded sessions.
Do not configure or run provider credentials just to make compilation pass.

Released compiler validation of the template passed with no final warnings.
The emitted agent job has only `contents: read`; its inference step is limited
to 15 minutes within a 60-minute job wrapper. Threat detection has a separate
10-minute limit and the safe-output job has a 45-minute limit. The vendor's
safe-output and conclusion jobs request `contents`, `issues` and
`pull-requests` write permissions; the declared output is still only the report
PR. Automatic failure-issue reporting is disabled. Every emitted external
action reference is pinned to a full commit SHA. These are inspected compiler
outputs, not observed runtime enforcement or a whole-workflow 15-minute limit.
The [compilation receipt](compilation.json) binds this exact template to the
session-local generated YAML. Installing it at a different workflow path
requires recompilation and review of that output.

Apply the milestone kill rule only after both cases have comparable measured
results on operator time, accepted quality, recovery effort and total cost.
If GitHub Agentic Workflows meets this GitHub-contained need, adopt it for that
scope and add no dispatch machinery. A failed prerequisite is not evidence of
inferior quality or cost, and this protocol establishes no Track A completion.
