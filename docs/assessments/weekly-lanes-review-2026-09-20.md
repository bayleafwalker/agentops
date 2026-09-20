# Weekly lanes: independent review (2026-09-20)

Independent, read-only review of the work the 2026-09-20 implementation run was
scheduled to produce against the 2026-09-19 weekly-lanes synthesis
(`vuoro docs/plans/2026-09-19-agent-systems-weekly-lanes.md` rev 2,
`2026-09-19-weekly-lanes-work-items.yaml`, `2026-09-19-weekly-lanes-slices.md`,
all on `vuoro main`; the `claude/weekly-lanes-synthesis` branch no longer exists,
having merged as vuoro #97).

This review pushed no commit to `vuoro`, `sprintctl`, `auditctl`, `actionq` or
`kctl`, and touched no served sprintctl or Forgejo credential.

## Summary

**0 `claude/wl-*` branches found, in any of the six repos. 2 weekly-lanes PRs
reviewed (both found under a different branch prefix). 6 findings, none of them a
correctness bug.**

The branch-naming assumption in this review's own brief did not hold, so the
result is stated two ways:

- **Literal target set — `claude/wl-*`: zero branches.** `git ls-remote origin
  'refs/heads/claude/*'` returns nothing in `vuoro`, `agentops`, `sprintctl`,
  `auditctl`, `actionq` or `kctl`. All six remotes fetch `+refs/heads/*`, so this
  is a real absence, not a refspec artifact. There are also **zero open PRs** in
  any of the six repos.
- **Actual target set — weekly-lanes work landed today: two PRs.** Both in
  agentops, both from a `wl-*` prefix without `claude/`, which is why the literal
  search missed them:
  - **#219**, *"hooks: record guard-hook deny/ask decisions into the gate log
    (WL-D1)"*, from `wl-d1-decision-row-2434` (branch deleted; on `main` as
    `74267d7`).
  - **#224**, *"ExperimentRecord for weekly-lanes C1 outcome-collateral rescore
    (#2436)"*, from `wl-c1-2436-experiment-record` (on `main` as `ab75806`).
    Opened 12:16:39Z and merged 12:17:11Z — **32 seconds** — which is one minute
    after this review's own org-wide PR search ran. It did not exist to be found;
    it is reviewed below because it belongs to the target class, and a reader of
    this report would otherwise never learn it landed.

The scheduled implementation run itself opened **no branches and changed no
code**, and said so: its report (vuoro #101, `docs/evidence/2026-09-19-weekly-lanes/implementation-report.md`)
records a per-item disposition for all twelve work items and concludes the
size-S, dependency-satisfied set was empty by the time it started. Spot-checks
of that report are in the last section; its central claims held up.

agentops #219 is **not** the scheduled run's work. It was created at 11:23 UTC,
47 minutes *after* the run's report merged (10:44 UTC), and carries
`Co-authored-by: dev <semper425@gmail.com>` with no `Claude-Session:` trailer —
the signature of an attended workstation session, not the unattended cloud run.

## PR review 1 of 2: agentops #219 — WL-D1

| | |
|---|---|
| **Repo / branch** | `bayleafwalker/agentops`, `wl-d1-decision-row-2434` (deleted; merged as `74267d7`) |
| **Plan item** | WL-D1, *Guard-hook decision rows plus rework_rounds kind filter*, host item agentops#2434, lane W1-2, size S |
| **Diff** | 8 files, +319/−10 |
| **State** | Created 2026-09-20T11:23:42Z, **merged 11:31:33Z** (8 minutes), 0 reviews |
| **Verdict** | **fix-then-land** on the code — except it already landed, and the fixes below are now follow-up work. The merge itself is the finding. |

### What it does

Adds `hooks/lib/emit-decision.sh`, a sourced `emit_decision <hook> <rule_id>
<tool> <deny|ask>` helper that appends one `{"kind":"decision", ts, hook,
rule_id, tool, policy_decision}` row to the same `gates-$SESSION.jsonl` that
`gate-log.sh` writes, and wires it into the five deny/ask points across the four
guard hooks. `hooks/log-session-cost.sh` splits `kind == "decision"` rows out
before computing `gates` and `rework_rounds` and publishes them under a sibling
`decisions` key.

### Verification I ran myself

Everything below is my own run in this container, not a restatement of the PR's
claims.

**agentops hooks suite** — 12 of 13 pass, including the new
`test-decision-row.sh`. The one failure is environmental and pre-existing:

```
test-sprintctl-maintain-check.sh   FAIL
  mktemp: failed to create directory via template
  '/projects/dev/.claude/sprintctl-hook-test.XXXXXX': No such file or directory
```

It hardcodes a workstation path absent from this container and touches no WL-D1
file.

**agentops scripts suite** — `python3 -m pytest -q scripts/tests`:
`829 passed, 17 skipped, 1000 subtests passed in 67.93s`.

**Independent behaviour-preservation check.** The riskiest edit in the diff is
in `bounded-read-guard.sh:35-41` and `nfs-workspace-guard.sh:43-49`, where
`exec python3 /dev/fd/3` becomes `OUT="$(printf '%s' "$EVENT" | python3 /dev/fd/3 ...)"`
so bash regains control after python exits. The PR asserts byte-identical
behaviour; I re-derived it rather than trusting it. Diffing pre-change
(`181dffa`) against post-change output and exit code over identical events:

- `nfs-workspace-guard.sh`, 12 cases (6 denies — Edit/Write/NotebookEdit under
  the sealed prefix, `git -C <prefix> commit`, `cd <prefix> && git push`, plain
  `git commit` with cwd under the prefix; 3 allows; 2 fail-open cases —
  malformed and empty event JSON; 1 deny with no `session_id`): **0 diffs.**
- `forge-sandbox-guard.sh`, 4 cases (2 network denies, 2 allows): **0 diffs.**

Decision rows were emitted correctly in every deny case, and correctly *not*
emitted for the deny with no `session_id`.

**Session-id and gate-dir resolution** are consistent across the three writers —
`AGENTOPS_GATE_LOG_DIR` falling back to `/projects/dev/.claude/state`, and
`.session_id` off the event: `gate-log.sh:19,37`, `log-session-cost.sh:34,38`,
`emit-decision.sh:39,42`. Decision rows land in the file the Stop hook drains.

**The new `decisions` key does not trip auditctl validation.**
`auditctl/validation.py:143-152` accepts any JSON object as metadata, and the
strict path at `:155-165` activates only for `type == "session.exit"` with
`source == "actionq-daemon"` and a non-null `dispatch_result_ref` /
`dispatch_result_digest`. `decisions` is not a trigger key. Worth stating
because `test-decision-row.sh` publishes through an **auditctl stub**, so the
test alone could not have told us this.

### Acceptance criteria

| Criterion | Met | Evidence |
|---|---|---|
| Four guard hooks append the decision row on deny and on ask | **yes** | 5 call sites; `bounded-read-guard.sh:316`, `nfs-workspace-guard.sh:276`, `forge-sandbox-guard.sh:28`, `gate-check.sh:36,40`. `bounded-read` and `nfs-workspace` only ever emit `deny` (`:73`, `:107`), so their deny-only grep is complete, not a gap. |
| `secret-read-guard.sh` not created or referenced; exactly four hooks touched | **yes** | 4 guards + the helper + `log-session-cost.sh` (required by the item's own `outputs`) + 2 tests = 8 files. The lone `secret-read-guard` mention is a pre-existing comment at `bounded-read-guard.sh:22`, outside the diff. |
| `rework_rounds` unchanged on an interleaved replay fixture | **yes** | `log-session-cost.sh:83-85` splits before the rework computation; `test-decision-row.sh:117-127` asserts parity against the plain fixture. Verified by running it. |
| `gates` documented as mixed, or split into a sibling `decisions` key | **yes** | Split; `log-session-cost.sh:71-76,133` and the commit message say which. |
| No OTel GenAI schema version pinned | **yes** | No `otel` / `opentelemetry` / `schema_url` token anywhere in the diff. |

No acceptance criterion is claimed-but-unmet, and I found **no correctness bug**
in the diff.

### Findings

**F1 — Merged against its own stated instruction, with no review.
Severity: high. Process, not code.**
`agentops` PR #219 body, final paragraph: *"Do not merge — a reviewer takes it
from here per the item's own instructions; agentops#2434 stays `active`."* It
was merged 8 minutes after it opened with **zero reviews** (`get_reviews` returns
`[]`). WL-D1 is the one item the lane loop deliberately re-tiered from
`fast-build` to `frontier-plan (attended session)`
(`docs/assessments/lane-loop/refine-2026-09-19T1655Z.md`, notes 3135/3136), and
`docs/plans/2026-09-17-target-state.md:33` carries TS-4's guard-hook clause as
**`proposed`**, not accepted — an unsettled enforcement boundary.

In fairness: the commit's `Co-authored-by: dev` trailer and absent
`Claude-Session:` trailer indicate an attended workstation session, so the
*attended-session* tier was plausibly satisfied. What was not satisfied is the
handoff the PR itself asked for — a second pair of eyes on an enforcement-surface
change before it landed. This review is that second pair of eyes, arriving after
the fact.

**Fix:** treat this review as the retrospective handoff. Confirm agentops#2434's
status is correct now that the work is on `main` (the PR expected it to stay
`active`; I could not check served sprintctl state from here, and did not try).
If the project wants the gate to bind mechanically rather than by convention,
the enforceable version is a branch-protection rule requiring one approving
review on paths under `hooks/`.

**F2 — Two of the four guard hooks have no committed test, including the one
carrying the riskiest edit. Severity: medium.**
`hooks/tests/` references `bounded-read-guard` and `gate-check` only; grepping
the whole directory for `nfs-workspace-guard` and `forge-sandbox-guard` returns
nothing — before this PR and after it. `test-decision-row.sh:69-86` drives
`bounded-read-guard.sh` (deny) and `gate-check.sh` (deny and ask), which is 3 of
the 5 call sites. `nfs-workspace-guard.sh:276` and `forge-sandbox-guard.sh:28`
are unexercised — yet `nfs-workspace-guard.sh` received the same `exec`→capture
rewrite as `bounded-read-guard.sh`. Both are correct today (I verified, above),
but nothing in CI holds them there.

**Fix:** extend `test-decision-row.sh`'s fixture with the two missing hooks. A
deny for `nfs-workspace-guard.sh` needs only an `Edit` event whose `file_path` is
under `/mnt/truenas/storage_layer/sealed/projects/...`; one for
`forge-sandbox-guard.sh` needs a `Bash` event with a network command. Both then
assert 5 decision rows instead of 3. Roughly ten lines.

**F3 — No committed falsifier for the behaviour-preservation claim.
Severity: medium.**
The PR's central safety claim — deny/ask/allow stdout and exit code are
byte-identical before vs after — was established by a before/after harness that
lives only in the PR description. Nothing in `hooks/tests/` asserts that a guard
hook's `hookSpecificOutput` and exit code are what they are. A later edit inside
the `OUT="$(...)"` capture block in either python-backed hook — a stray `echo`,
a lost `printf '%s\n'` at `bounded-read-guard.sh:315`, a dropped `exit "$RC"` —
would change what the harness sees a hook decide, and every test in the repo
would still pass.

**Fix:** commit the harness. Golden-output assertions for the five deny/ask
points and at least one allow path per hook, checking exact stdout and exit
code, in `hooks/tests/`. This is the falsifier the item is missing: the existing
tests can only tell you the *recording* is right, never that the *decision* still
is.

**F4 — Decision rows are silently dropped when `session_id` is absent, where
gate rows are not. Severity: low. Deliberate and documented; recording it so the
asymmetry is a known one.**
`emit-decision.sh:38-40` returns without writing when `.session_id` is
absent/empty/null, with the reasoning at `:30-32` ("an unattributable decision
row would be worse than no row at all"). `gate-log.sh:37` instead falls back to
the literal `"unknown"` and writes to `gates-unknown.jsonl`. So in a session
without a `session_id`, the Stop hook still publishes gate rows from
`gates-unknown.jsonl` but zero decisions — denials become invisible in exactly
the sessions whose provenance is already weakest. I confirmed this path: the
no-`session_id` deny in my differential produced correct stdout and no row.

**Fix:** none required if the asymmetry is intended — but it deserves a line in
whatever documents the `decisions` key, so a later reader does not read an empty
`decisions` array as "no denials occurred" when it means "no session id".

## PR review 2 of 2: agentops #224 — WL-C1

| | |
|---|---|
| **Repo / branch** | `bayleafwalker/agentops`, `wl-c1-2436-experiment-record` (merged as `ab75806`) |
| **Plan item** | WL-C1, *local-inference outcome-class rescore*, host item agentops#2436, lane W1-3, size S — **the plan's designated first experiment slice** |
| **Diff** | 1 file, +157 (`_projects/exp-2026-09-local-inference-outcome-collateral/README.md`) |
| **State** | Created 2026-09-20T12:16:39Z, **merged 12:17:11Z** (32 seconds), 0 reviews |
| **Verdict** | **fix-then-land** — the record is good work, but it is landed as `status: implemented` on evidence no one else can reach. Already merged, so F5 is now follow-up. |

### What it does

Lands the ExperimentRecord for agentops#2436: hypothesis, baseline, challenger,
task sample, measures, falsifier evaluation, limitations, rollback and evidence
for splitting local-inference's run outcome into `{completed,
completed_with_collateral_change, incomplete}` instead of
`accepted = tests_pass(dest)`.

This item is why the earlier implementation run stood down — it recorded WL-C1 as
*"skipped: repo out of scope"*, `local-inference` being unavailable to it. That
disposition is now partly overtaken: the **record** is in agentops, while the
**code** it describes is not in any repository at all (F5).

### What I could and could not verify

**The falsifier evaluation is internally sound — I checked the logic.** The stated
falsifier is *"retire the outcome field if the rescore surfaces zero
`completed_with_collateral_change` rows, **or** if per-arm rankings are unchanged
**and** no row was previously invisible under the TAMPER convention."* Against the
record's own numbers: 2 collateral rows surfaced, so the first disjunct is false;
per-arm rankings are unchanged (all three arms 6/6 `completed`), but the two rows
*were* previously invisible to `scorecard.csv`, so the second disjunct's
conjunction is false. Neither disjunct holds, so "keep the field" follows. The
reasoning is valid and the record does not overclaim — it says plainly that the
outcome field and the TAMPER note agree 100% wherever both are computable, and
that the value added is surfacing rows that never reached the TAMPER-bearing
pipeline at all.

**The Limitations section is unusually honest** and I found nothing to add to it:
two positive rows called a smoke signal rather than a rate; `arm=profile` flagged
as a naming choice rather than a fact recovered from a log; the
`--add-outcome-column` reconstruction flagged as lossy in the general case.

**But I could verify none of the underlying numbers**, and neither can anyone
else. See F5.

### Findings

**F5 — The record is landed as `implemented` on evidence that exists in no
repository. Severity: high.**
The Evidence section cites local-inference commit
`4d06fb006be14443fae63797eb43ba179d566332` on branch `wl-c1-rescore-2436`, made
*"in a fresh worktree/clone off `master` … the branch exists in a separate clone,
not yet fast-forwarded onto local-inference's real `master`."* I confirmed the
surrounding claim independently: `local-inference` is **not among the 50
repositories on this account** (`list_repos`), so it has no GitHub remote and the
cited sha is unreachable from anywhere but the disk that made it. Every number in
Measures, the 14 passing tests, and the `scorecard.csv` byte-equality check
therefore rest on an artifact that cannot be fetched, re-run, or audited — and
that disappears with that working copy. The record's own header already says
`status: implemented`, which reads as stronger than the evidence supports.

To be fair to it: the record is candid about exactly this, names note #3286 as the
reason, and calls the remaining step mechanical rather than a design decision. The
problem is not concealment — it is that an ExperimentRecord is change memory, and
this one currently remembers a commit nobody can open.

**Fix:** fast-forward `wl-c1-rescore-2436` onto local-inference `master` on the
workstation, then amend the record's Evidence section with the resulting `master`
sha. Until that happens, the header should read `implemented (workstation-local;
evidence not yet reachable)` rather than plain `implemented`, so a later reader is
not misled by a status line into thinking the slice is closed. If local-inference
is meant to stay remote-less, then the record should carry the artifact it needs
to survive independently — at minimum the `derive_outcome` function body and the
rescore counts as committed text in agentops, not only a pointer.

**F6 — Merged in 32 seconds with no review, on the plan's designated first
experiment slice. Severity: medium. Same pattern as F1.**
Opened 12:16:39Z, merged 12:17:11Z, zero reviews. It is documentation only, which
lowers the blast radius — but the content is a **falsifier evaluation that keeps a
contract alive**: "Decision: keep the outcome field and the enum", explicitly so
WL-C2 (`#2433`) can reuse it. A retire/keep call on the first experiment slice is
the single decision in this plan most worth a second reader, and it got none. Two
of the two weekly-lanes PRs that landed today were merged within 8 minutes and 32
seconds of opening, neither reviewed; that is a pattern, not two coincidences.

**Fix:** as F1 — if the gate should bind mechanically, it is branch protection,
not convention. At minimum, a falsifier evaluation that concludes "keep" should
not merge unreviewed.

### Goal-state check for #224

- **`_projects` as a store — raised and dismissed.** TS-14
  (`docs/plans/2026-09-17-target-state.md:43`) says project-instance folders
  `_projects/*` are *"derived work folders, never a store"*, and an
  ExperimentRecord is a §5.1 core ledger object, so landing one into `_projects/`
  looks at first like a contract violation. It is not: the weekly-lanes plan
  explicitly assigns *"`_projects` ExperimentRecords"* to agentops in its
  `repositoryOwnership` block, and WL-C4 is literally *"`_projects`
  ExperimentRecord over Delivery unit F"*. The plan sanctions this pattern by
  name. Recording the tension because it is real and a future reader will hit it,
  not as a finding against this PR.
- **§1.2 non-goals, §5 contracts — clean.** No new execution machinery, no new
  noun: `ExperimentRecord` is an existing §5.1 object and the outcome enum is a
  field on an existing results row.
- **Scope creep — none.** One file, and the record declines to widen: granularity
  beyond a `tests/`-only boolean is explicitly deferred to WL-C2.

### One correction to the earlier run's scope claim

The implementation report states that `appservice` and `local-inference` were both
outside its access scope. For `local-inference` that holds — it is on no remote at
all. For **`appservice` it does not**: `bayleafwalker/appservice` exists as a
private repository on this account and is attachable. WL-C3 (Delivery unit F,
appservice-owned) was set aside as out-of-scope-by-access when it was really
out-of-scope-by-size (`M`, not `S`) — the size reason was also given and is the
sound one. Worth correcting so a future run does not skip appservice work on a
false access premise.

## Goal-state check for #219

Against `vuoro docs/plans/2026-08-22-long-term-direction.md` §1.2 and §5, and
`agentops docs/plans/2026-09-17-target-state.md`:

- **§1.2 non-goals — clean.** No execution control plane, runner, queue, worker
  supervisor or model router. The change records a decision a hook has already
  made; it adds no scheduling or dispatch. No centralized evidence ownership
  shift: rows stay in the per-session gate log and ride the existing Stop-hook
  publication.
- **§5 contracts — no new noun.** `decisions` is a key on an existing auditctl
  metadata payload, alongside the existing `gates`. It introduces no v4
  capability contract and no object in §5.1/§5.2. The item's own acceptance
  criterion explicitly sanctioned either a mixed array or this sibling key.
- **TS-4 — this is the sensitive one.** `:33` keeps local guard hooks as operator
  enforcement, status `proposed` for the guard-hook clause. #219 changes what the
  hooks *record*, not what they *enforce* — no deny path added, no scope widened,
  no `.claude/gates.json` or credential touched, and I verified the decisions
  themselves are byte-identical. The scope claim holds on the merits. The
  governance issue is F1, which is about *how it landed*, not what it does.
- **Scope creep — none found.** The diff is the item's `outputs` list and
  nothing else.
- **Approval gate — see F1.** This is the one place the weekly-lanes work
  touched a gate, and the gate did not hold as written.

## Spot-checks of the implementation run's own report (vuoro #101)

The run's deliverable was a disposition report, so its claims are what there is
to review. I checked the two that carry the most weight.

- **WL-A1 (`accepted_without_evidence`, sprintctl) — "already done" confirmed,
  with one deviation the report itself flags.** `sprintctl/sprintctl/unbound.py:57-62`
  carries the fourth `CATEGORIES` entry; the derivation is at `:138-141`. The
  work-items YAML asks for the row to be *"split by `rationale == ""` (alias
  path) versus non-empty rationale"*; the implementation instead splits on
  presence of the `item-decided` event (`unbound.py:28-33`). That is a literal
  deviation from the acceptance text. I agree with the report that it is the
  stronger signal — a rationale can be empty on an explicit decide — and the
  both-paths fixture the criterion demands does exist and does pass
  (`tests/test_served_decisions.py:338-375`). Recording it as an accepted
  deviation rather than an unmet criterion.
- **sprintctl test run** — `python3 -m pytest -q tests/test_releases.py
  tests/test_decisions.py tests/test_served_decisions.py`: **97 passed, 2
  skipped.** Full suite: **1455 passed, 326 skipped in 51.55s**. But the
  criterion also names `tests/pg/test_releases.py`, and all **25 of its tests
  skip** without a PostgreSQL server, which this container has none of. Since
  `unbound.py:39-47` documents real PostgreSQL/SQLite divergence in how `->>`
  yields text versus a native value, dual-backend parity for the new category is
  **unverified here** — not failing, unrun. Worth one CI run against PG before
  that criterion is called closed.
- **WL-D1's disposition in the report is now stale.** The report records WL-D1 as
  deliberately not implemented. It landed 47 minutes later, in a different
  session. The report was accurate when written; the evidence directory now
  needs the follow-on noted, or a later reader will conclude WL-D1 is still open.

## Coverage: what was searched

| Repo | `claude/wl-*` branches | Open PRs | Weekly-lanes PRs reviewed |
|---|---|---|---|
| `vuoro` | 0 | 0 | — (docs-only: #101 report, spot-checked above) |
| `agentops` | 0 | 0 | **#219 (WL-D1)**, **#224 (WL-C1)** |
| `sprintctl` | 0 | 0 | — (WL-A1/A2b landed pre-run via the lane loop) |
| `auditctl` | 0 | 0 | — |
| `actionq` | 0 | 0 | — |
| `kctl` | 0 | 0 | — |

Method: `git fetch origin --prune` then `git ls-remote origin 'refs/heads/claude/*'`
per repo (all six confirmed fetching `+refs/heads/*:refs/remotes/origin/*`),
`list_pull_requests state=open` per repo, and an org-wide
`search_pull_requests` for `WL-` over `created:2026-09-19..2026-09-21`, which is
what surfaced #219 despite its non-matching branch name.

A caveat on that coverage: #224 opened at 12:16:39Z, about ten minutes *after*
that search ran, and merged 32 seconds later. It was caught only because this
report's own PR was still open and a later check-in re-read the base branch. A
one-shot review is structurally blind to whatever lands while it is writing — a
second reason to key the next run to merged PRs in a date window, and to re-check
that window once before closing out.

## Recommendation

Two notes for whoever picks this up.

**The branch-naming premise this review runs on is wrong**, and will silently
return "0 branches" every week until it is fixed. The implementation work uses a
bare `wl-*` prefix and deletes branches on merge, so a scheduled review keyed to
live `claude/wl-*` branches finds nothing even on a week when work landed. Key the
search to merged PRs in a date window instead — that is how both #219 and #224
were found.

**Weekly-lanes PRs are merging unreviewed, fast.** Both of today's landed within
8 minutes and 32 seconds of opening with zero reviews — one against its own
written "Do not merge", the other carrying a keep/retire call on the plan's first
experiment slice (F1, F6). Neither turned out to contain a correctness bug; I
looked hard at #219 in particular. So this is not a plea to slow down on the
merits. It is that the review step is currently producing no signal at all, which
means the next PR that *does* carry a bug lands exactly the same way. If these are
meant to be reviewed, branch protection on `hooks/` and `_projects/` is the
mechanism. If they are meant to merge unreviewed, the item tiering that says
otherwise should be retired, so the record stops claiming a gate that is not
operating.
