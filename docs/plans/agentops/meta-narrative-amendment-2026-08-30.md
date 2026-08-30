---
doc_id: meta-narrative-amendment-2026-08-30
status: active
created_at: 2026-08-30
owner: agentops
amends: meta-narrative-plan-2026-08-29
---

# Meta-narrative plan — amendment, 2026-08-30

Amends `meta-narrative-plan-2026-08-29.md` (rev. 2). Its intent, its role
classification and its scenario families stand. **§10 First moves does not**, and
the reason it does not is worth more than the corrections themselves.

Rev. 2's own closing section lists four claims it had to retract, every one of
them *inherited or inferred and stated without measurement*. This amendment adds
four more of the same kind, produced by the plan itself in the twenty-four hours
since. A plan that ranks work by unverified status is a plan that misranks work.

---

## 1. §10 measured, item by item

Each row was read at file and line, or queried against the store, on 2026-08-30.

| # | First move | Plan's premise | Measured |
|---|---|---|---|
| 1 | Register `SubagentStop`, emit `session.exit` with `terminal_reason` | not built | **Built, registered, and it does not fire.** See §2. |
| 2 | Export `AUDITCTL_ARTIFACTS_ROOT` | required for writes | **Superseded.** The requirement was removed in 0.1.4. See §3. |
| 3 | Encode a failing resume scenario | not written | **Written, run twice, one FAIL and one PASS on record.** The PASS was weaker than it looked. See §4. |
| 4 | Pin scorer revisions in acceptance-lab | "a present, verified defect" | **Already fixed** before the plan was written. A different, unlisted defect was live. See §5. |
| 5 | Extract the consumer proof from `bindery-core` | not started | Unchanged. Still the highest-value unexamined thing here. |
| 6 | Run the loop once, manually | not started | Unchanged. |

Two rows were wrong in the pessimistic direction and two in the optimistic one,
which is the useful part: the error is not a bias toward under- or over-claiming.
It is the absence of a check.

---

## 2. Why the producer does not fire, and what it cost

The `SubagentStop` hook is registered at
`/projects/dev/.claude/settings.local.json:130-142` and symlinked to this
repository's template. Fed a synthetic event by hand it writes a correct record.
It has never written one in anger: both `dispatch.exit` rows in
`/projects/dev/.auditctl/auditctl.db` carry `session` values of `test-1` and
`probe-live-1`.

**Project settings load from the session's primary working directory only** —
documented behaviour, confirmed against the Claude Code settings reference. This
session's primary directory is `_projects/vuoro-dispatch-ready/`, a materialized
project folder with no `.claude/` at all. `SubagentStop` fires for background
subagents regardless of how they were launched, so the event was raised and
nothing was listening.

The consequence is exact and worth stating plainly: **a session launched from a
dispatch-ready project folder — the object this workspace materializes precisely
in order to dispatch from — inherits none of the workspace's telemetry or guard
hooks.** Not the subagent-exit record, not the gate log, not the pre-tool guard,
not the sprint context. Only the user-scope `Stop` hook, which is user-scope for
exactly this reason and is the precedent that settles where the fix belongs.

`SubagentStop` is now registered in `~/.claude/settings.json` beside it, and **the
registration alone was not the fix.**

The script was mode **644**. Invoked by bare path — which is how a settings file names a
hook — the harness's shell answers `Permission denied` and exits **126**, before the
script reads a byte of stdin. I verified that script this morning by running
`bash <path>`, reported "the hook works when invoked", and moved on. Running a script
through an interpreter is precisely what hides a missing exec bit: it proves the script
works and says nothing about whether the registration does.

Two things kept it invisible. `core.fileMode` is `false` in agentops, so git never
recorded that someone had chmod'd the working copies — the workstation's hooks were 755
on disk and 644 in the index, and that difference never appears in `git status`. And
devbox's `/projects/dev` is an independent clone, so it received the **tracked** mode for
every one of them.

That is the entire explanation for devbox recording nothing: not only was nothing
registered there, nothing registered there could have run. Six hooks named as commands
were tracked 644, and a seventh was found by the test rather than by inspection —
`forge-credential.sh` is executed with arguments by `forge-context.sh`, which swallows the
failure as `PROBE FAILED`, so on every fresh clone the credential probe has been reporting
a failure that was really a permission error.

### Proven, on both hosts

A live session on each host, spawning a real subagent through the Task tool, in a
disposable git repository:

| Host | Result |
|---|---|
| devbox (`agent`) | `dispatch.exit`, `terminal_reason: completed`, real `agent_id` and transcript path |
| workstation | `dispatch.exit`, `terminal_reason: completed`, real `agent_id` |

Both carry `completed` rather than `crash-inferred`, which is itself the evidence that a
real transcript existed and was read — the probes earlier in the day could only ever
produce `crash-inferred`.

So the contract this session bound in the morning now has a producer that fires, on both
hosts, measured at the artifact. **Declared, selected, invoked, evidenced.** That is the
first time any item in §5's table has completed the whole arc.

### And the control that ran beside it found a larger gap

`SubagentStop` fires for a headless (`claude -p`) session. **`Stop` does not** — measured
on both hosts, with the workstation as its own control: 83 `session-costs.jsonl` entries
today from interactive sessions, and **zero** from either headless run. Not a threshold
effect; the devbox run made tool calls and still produced nothing.

That inverts a recommendation taken today. `log-session-cost.sh` was registered for the
devbox `agent` identity on the reasoning that devbox is where the spend happens and
records none. The premise is right and the fix does not reach it: that identity exists
*precisely* to run headless — its own deployed `$comment` says so — so the hook it now
carries will not fire for the work it was registered to measure. Harmless, and it will
fire if someone works interactively there, but the gap it was meant to close is still
open.

**Dispatched and headless work records no cost anywhere.** That is a candidate cause for
the capture-rate figure in §3 that is worth more than the one already retired there, and
it is measurable rather than inferred: every `workflow.session` row on record comes from
a session a human was sitting in front of.

`materialize_project.py` emits no `.claude/` for the folders it creates, and
`MANAGED_RUNTIME_PATHS` does not admit one. Whether a project folder should carry
its own hook registration, or whether hook scope should simply never have been
directory-shaped, is an owner decision this amendment does not take.

---

## 3. First move 2 was written against a false statement in the code

`auditctl.paths.require_artifacts_root` raised *"AUDITCTL_ARTIFACTS_ROOT is
required for audit writes."* It has not been true since 0.1.4:
`resolve_audit_context` defaults the root to the resolved repository root, and an
explicit value may only *confirm* that root, never redirect it. The function was
imported by `cli.py`, called nowhere, and its only caller was its own test — which
passed, because **a test that exercises only dead code always passes.**

So the plan's second first-move exists because a retired requirement was still
stated in the code and read as current. Removed in auditctl `fb8ee82`.

The capture-rate figure the item was built on needs re-deriving from scratch
rather than adjusting. One input to it: `AUDITCTL_ARTIFACTS_ROOT` is exported by
two `.envrc` files, and **direnv refuses to load this repository's** — it was
denied and then edited, so the allow-hash no longer matches. There is no
`/projects/dev/.envrc`, and every settings `env` block in the workspace is empty
but for `EDITOR` and `VISUAL`. The variable is therefore unset in every context
observed today. Under 0.1.6 that is now the *correct* state, not the defect.

Running `direnv allow` is an operator trust decision, not a cleanup, and the
previous deny looks deliberate. Left for the owner, with the file read: it exports
four variables and sources an optional gitignored local file. No secrets.

---

## 4. What the `resume-and-settle` PASS actually established

Five scored runs over two candidates: the pre-deploy candidate FAILs at 0.722, the
after-deploy candidate PASSes at 1.000 on all eight hard gates. The deploy
genuinely fixed two defects — `work.read.handoff` errored for any sprint holding
an active reservation, which is exactly the state an interrupted session leaves,
and the handoff record discarded the checkpoint it was given.

That is real. It is not "resumability is proven". Adversarially, of the outcome's
five elements: one (through the served backend) is genuinely exercised; two (fresh
process, no local cache) were partly exercised while the probe contradicted the
scenario's own `deliberately_not_carried` list; one (after interruption) is
simulated and inert — nothing about the world changes across the boundary; and the
recovery of the four facts was exercised as *reads of records*, not as recovery of
capability.

Four gates passed for reasons weaker than their names. The sharpest:
`revision-is-exact` could not distinguish a checkpoint read from a lucky grep —
the fallback set `revision_was_scraped` and **nothing ever read it**, so the
identifier appeared exactly once in the file.

Hardened in `7e164e3` to scenario 1.0.2. Provenance now reaches the scored facts;
the recover phase builds its environment from an 8-name allowlist and measures the
leak rather than asserting isolation; session identity refuses rather than picking
an arbitrary active claim; and the citations name what they actually derive from.

**The verification that matters:** the candidate that scored a clean sweep now
scores 0.000 on `revision-provenance-is-declared`. A scenario that cannot fail
proves nothing, and this one could not.

One finding from that work generalises past this scenario. Adding a *forbidden*
gate did not make the old artifact fail — a not-denied gate cannot catch a
candidate that says nothing. Requiring provenance **positively** is what bit.

`changes-carry-receipts` is still wrong and is recorded as a known gap rather than
fixed: every effect in the trajectory comes from the arrange phase, so the gate
certifies the pre-interruption session's writes, not a recovered session's. The
fix needs a live write to `vuoro-shared` that cannot be rehearsed without
performing it.

---

## 5. The defect class, and the falsifier that already names it

Five instances measured today, in five different repositories, all the same shape:

| Instance | Declared | Produced |
|---|---|---|
| `ACTIONQ_TERMINAL_REASON_CODES` | validator live since before 2026-08-22 | its only writer retired that day; zero events validated since |
| `SubagentStop` hook | built, registered, tested | two rows, both tests |
| `session-capsule.schema.json` | schema, 3 skills, 5 scripts, 81 test functions | never emitted an instance |
| `.auditctl-id` | implemented, documented | zero instances in the fleet |
| `require_artifacts_root` | a stated requirement, with a passing test | called by nothing |

This is not five bugs. It is one habit — the contract and its test are built
first, and nothing anywhere asks whether a producer ever arrived. Each instance
was individually invisible because **the test passes either way.**

Vuoro's own direction document already states it as falsifier 11:

> Every ledger contract names the lifecycle events its transitions emit, and those
> events are observed in auditctl. A Vuoro object that emits no lifecycle events is
> not an object, it is a name — `vuoro-dispatch-ready` is the counterexample
> already on record.

The falsifier is right and was unmechanized, which is why it caught none of the
five. Mechanizing it is the class-level fix and is the one piece of new machinery
this session builds.

`check_producers.py` is that machinery, and its first run says the class is
larger than the five instances that prompted it:

```
no-instance=5   examples-only=14   produced=11   cannot-determine=7
```

over 8 audit stores, 15 shards, 2118 event records and 980 JSON files.

**The largest class is `examples-only` — fourteen contracts whose only instances
are their own committed fixtures.** `test-context` has 69 of them and
`verification-result` 48. A shape without a writer is indistinguishable from a
working contract until something asks, and nothing did.

Two results are worth more than the counts.

`skill-lock.v1.schema.json` was **unparseable** — two unclosed braces, committed
in `cb03365`, never loaded by anything, because its producer validates
`schema_version` and an `isinstance` by hand instead of against the schema. It is
the purest instance of the class: not merely unproduced but syntactically broken
for months, beside a producer that never looked at it. Repaired; nothing validates
against it yet, and the census now says so.

And the mirror, which is the more actionable half: **auditctl declares no
event-type vocabulary at all.** `validate_event_object` accepts any non-empty
`type` string. So the census also reports the inverse — 46 event types observed in
the stores, every one a producer with no contract. `workflow.session`, the
most-written type on record at 1747 rows, is a free-form string in a shell hook.
The workspace has contracts without producers *and* producers without contracts,
and neither side had a way to notice.

One correction to §5's own table, from that run: `TERMINAL_REASON_CODES` is not
enforced against zero events. `crash-inferred` has two instances — both of them
the SubagentStop probe rows above. The other six codes have never been written
anywhere. 14% of the vocabulary is exercised, which is a worse finding than
unproduced because it is measurable and was not being measured.

The check exits 0 always. A gate over the standing inventory has no admission
subject and would fail 26 of 31 schemas at once, which is how `dispatchable` died
(rev. 2 §2). `--fail-on` exists for a caller that *does* carry a subject — a schema
added by one change. It also reports `cannot-determine` on 7 contracts, and a
measurement that admits it could not look is not sound enough to block on.

`.auditctl-id` is the instance that resolves *differently*, and it is worth
separating so the class does not swallow it. Its zero instances are not a defect:
measured on this host, worktrees already resolve to their main repository root, so
a declared id would change nothing today. It becomes load-bearing on a rename or a
relocation, not now. The handover offered "write the files or delete the
mechanism"; the measured answer is neither.

One divergence found while measuring it, unrelated and real: the `kotona.app`
worktree resolves its repository root to
`/mnt/truenas/storage_layer/projects/dev/kotona.app`, the legacy NFS copy, while
`/projects/dev/kotona.app` is the local one. Same `repo_id`, two filesystems.
`AGENTS.md` forbids NFS as a writable Git workspace. Neither root has an
`.auditctl/` store yet, so nothing has been misrouted — which is why it is worth
recording before something is.

---

## 6. Corrections this session owes

Stated in the same form rev. 2 used, because the pattern is the finding.

| Claim | Reality |
|---|---|
| "nobody has run the resumability outcome" | Two candidates, five scored runs and a before/after comparison were on disk. Inherited from §1 of the plan, restated by me without opening `_artifacts/`. |
| "the scorer-pinning defect is present" | Fixed before the plan was written: versioned `ScorerSpec`, a lock file, a digest and a drift test. The plan measured a defect it had already closed. |
| "the fix for capture is a settings `env` block" | The requirement it served had been removed two releases earlier. I reasoned to a fix for a problem that no longer existed, which is the same error one layer down. |
| "the event-type mismatch is the reason no records exist" | True and not the cause. The hook was in the wrong settings scope; it would have written nothing under either type. I found the smaller defect first and would have shipped it as the fix. |
| "the restamp question is an owner call" | Derivable, and derived in §7 from a rule auditctl already states about itself. Escalating it was the 2026-08-26 memo's own failure -- a resolved action presented as an open question. The owner call is one level up and was already written down. |

The last one is the one to keep. A correct diagnosis that is not the *operative*
one is more expensive than no diagnosis, because it closes the investigation.

---

## 7. Landed

| Repo | Commit | What |
|---|---|---|
| auditctl | `c094ad4` | terminal-reason contract bound to the event type, not to its first writer's name |
| auditctl | `fb8ee82` | `require_artifacts_root` retired |
| acceptance-lab | `add5ca1` | an empty subject is not a pass; three scorer revisions bumped, three deliberately not |
| agentops | `eee9c4f` | one publisher resolver; silent failure now leaves a trace |
| agentops | `7e164e3` | `resume-and-settle` 1.0.2, able to fail again |
| gitops-nixos | `1596fc7` | `.auditctl/` ignored; the tree can read clean |
| cred-broker | `bf81ee1` | `.sprintctl/` ignored |

All verified at the canonical remote, not at the push output.

**auditctl 0.1.7 is released** — `af96357`, verified at the installed artifact.

It was blocked for part of the session, and the block was mine: I raised *"does a
version bump restamp the existing verification result, or produce a new one?"* as
an owner call. It is not one. auditctl's own boundary rule settles it — a ledger
**records what was observed and never states what should be** — so an observation
is never rewritten, and the answer is to record a new one. Presenting a derivable
question as a decision is the failure the 2026-08-26 decisions memo diagnoses, and
this is another instance of it.

The root cause was measurable and is now fixed. `pyproject.toml` is inside
`CENTRAL_IMPLEMENTATION_PATHS`, so a version bump changes the digest of an
implementation that did not change — `git diff 5f45f12..HEAD` over all seven
digested paths is empty, and the sole difference is the version literal. The digest
assertion named **one** packet, so the only route back to green was to falsify it.
It now requires that *some* result for the context was observed against the packaged
tree: the guarantee that what ships is verified is kept, the singularity is dropped,
and observations accumulate instead of overwriting each other.

`central-observation-ingest-item-2329.json` records this run and deliberately does
not restate item-1201's fault enumeration or history count, which this run did not
instrument. `item-1201` is left untouched — including its restamped
`implementation_sha` from the 0.1.6 release, because correcting that would be the
same act again.

Evidence taken at the artifact rather than the report: installed `__version__`
0.1.7; `validate_dispatch_exit_metadata` present in the installed tree and
`require_artifacts_root` absent from it; and the installed CLI, run in a disposable
repository, rejects `terminal_reason: "ran-out-of-vibes"` with the seven safe codes,
rejects a `dispatch.exit` carrying no reason at all, and accepts `usage-limit`.
Declared is not invoked and invoked is not evidenced, so all three were run.

Commissioned by `agentops#2329`, closed with note `#2629`. auditctl has no local
sprintctl; its items are tracked in agentops scope, per the `#2063` precedent —
which also revealed that the item ids named by three of the four result filenames
(1201, 1202, 1207) resolve in no repo scope reachable today. Only 2063 does. Left
as found.

**The genuinely upstream question is already on record** and is the one to put to
the owner: the vuoro direction doc §14 lists, under open architecture decisions,
*where each ledger object is canonically stored — which bound provider owns
`EvidenceSet` and `Decision`.* `verification/results/` and acceptance-lab's
`campaigns/` are both standing in for a durable evidence record that has no declared
home, which is why each improvises whether it is a **record** or a **build output**,
and why the gate guarding each improvises to match.

That is the same defect as §5, one level up. Declared-versus-produced is contracts
with no writer; stored-versus-derived is artifacts with no declared kind. The
four-objects contract classifies Project, Workspace, Environment and Session — and
classifies no evidence artifact at all.

---

## 8. Open, in dependency order

1. ~~Prove the dispatch-exit producer fires.~~ **Done**, on both hosts — see §2. The
   remaining half is the vocabulary: six of the seven terminal reasons have still never
   been written anywhere, and `usage-limit`, the code the incident that commissioned all
   this actually needed, is one of them. A producer that only ever emits `completed` has
   not yet been tested against the case it exists for.
2. **Declare where evidence objects live** (§7) — direction doc §14, already open.
   Until it is answered, every evidence artifact improvises its own kind and its own
   gate. Nothing is blocked on it today; the next thing that touches a stored record
   will be.
3. **Re-derive the capture rate** from scratch (§3), rather than adjusting a figure
   whose stated cause has been retired. Start from the measured fact in §2: `Stop` does
   not fire headlessly, so every session that was never sat in front of is missing by
   construction, and no amount of fixing the publisher recovers it.
4. **Extract the consumer proof from `bindery-core`** — unchanged from rev. 2 §10.5,
   and now the highest-value item nobody has opened. 17% of measured spend, the only
   complete accept/reject/merge cycle on record, absent from every plan.
5. **`changes-carry-receipts`** (§4) needs a recovered session that writes.
6. **The scorer lock has a hole**: `scorer_digest` closes over each scorer's source
   but not over the helpers it calls, so editing `_ratio` would change what ten
   scorers measure while every digest stayed green. Recorded in `_ratio`, not fixed;
   closing it needs the digest to cover the call graph.
7. **The entitlement question** is unchanged and still first in principle: the record
   answers where a write came from, not who set the context and what entitled them.
   Its concrete shape is now visible — `AuditContext` instantiates the *write-scoped*
   half of the resolved-context invariant, and the *session-scoped* half has no
   producer. `session-capsule.schema.json` is that producer's schema, and it is
   instance number three in §5's table.

---

## 9. Later the same day: the producer emits the right code for the wrong reason

§8 item 1 said the remaining half of the dispatch-exit work was the vocabulary —
`usage-limit` had never been written, and a producer that only ever emits `completed`
has not been tested against the case it exists for. Testing it produced a worse
finding than a missing code.

**The classifier was reading prose.** `subagent-exit.sh` took the last three assistant
text blocks and matched `session limit` / `rate limit` / `usage limit`, then `timed
out` / `timeout`, then `cancelled`. Run unchanged over every subagent transcript on
this host — 353 of them — it returns **76 non-`completed` verdicts where the records
carry 19**:

| Verdict | Text match | Records | Spurious |
|---|---|---|---|
| `usage-limit` | 33 | 19 | 14 |
| `timeout` | 38 | 0 | **38** |
| `cancelled` | 5 | 0 | **5** |
| `completed` | 277 | 334 | — |

Zero false negatives in either direction. Every spurious verdict came from a subagent
that **completed** and whose final report discussed rate limiting, timeouts or
cancellation — a research subagent reporting on a queue design says "retries,
concurrency/rate limits"; one reporting on a WAF says "rate limiting is
in-application". Prose about a failure is indistinguishable from the failure, so this
is structural, not a threshold to tune.

It would have got the commissioning incident right, by coincidence: those three
transcripts end with text that happens to contain "session limit".

**§7b of the plan is wrong on its second bullet, and the correction is usable.** No
`Retry-After` arrived — that part holds. But the terminating record is not only prose.
It carries `isApiErrorMessage: true`, `apiErrorStatus: 429`, `error: "rate_limit"`,
and since roughly 2026-08 a `quotaLimits` object whose `resetsAt` is an **exact epoch
second**: `1787952600` on `agent-a5d642b86112f09ec.jsonl`, which is
`2026-08-29T00:30:00` Europe/Helsinki — precisely what the string rendered. The plan's
requirement that a policy "key on whether a reset instant was successfully derived, and
record how" was written believing derivation was impossible. It is not; it is a field
read.

**What changed.** The hook now classifies from the terminal record and keeps the text
only as `raw_tail`, for a reader. It selects the last *conversational* record rather
than the last line, because a parent's `file-history-snapshot` and `queue-operation`
rows follow the final turn. `reset_at` is published when `quotaLimits.resetsAt` is
present, with `reset_source` naming the field; the seven older limit deaths on this
host carry no such field and keep `unparsed-local-string`, which is now an honest
statement about one transcript rather than a claim about the format.

Re-run end to end over the same 353 transcripts, through the hook itself with a stub
publisher: **334 `completed`, 19 `usage-limit`, nothing else** — equal to the records,
with 12 exact reset instants and 7 declared underivable.

**What this says about the vocabulary, which is the part that outlives the fix.** The
corpus contains exactly two terminal outcomes. `cancelled`, `timeout`, `process-exit`,
`start-failed` and `crash-inferred` have never occurred on this host — `crash-inferred`
has been *written*, but only by a probe pointed at a path with no transcript. So the
honest statement is not "the vocabulary is 14% exercised"; it is that four of seven
codes have no observed instance and the instrument that appeared to produce three of
them was producing artifacts of its own reading. **A producer that infers can
manufacture coverage of a vocabulary that nothing has ever exercised**, which is the
§5 defect class seen from the other side: there, a contract with no producer; here, a
producer whose output was not evidence of anything.

The regression that guards it is `tests/test_subagent_exit_terminal_reason.py`. Its
fixtures are shaped like the real records, and its last case runs the hook against
every real subagent transcript on the host and requires the verdicts to equal the
records — skipped, never silently passed, where there is no corpus.

---

## 10. `Stop` does fire headlessly. It was never awaited.

§2 measured that `SubagentStop` fires for `claude -p` and `Stop` does not, and §8 item 3
built on it: every unattended session missing by construction, no publisher fix able to
recover it. That is wrong, and the correction is one key.

Four headless runs of `claude -p "Reply with exactly: OK"`, same directory, same prompt:

| Registration | `session-costs.jsonl` |
|---|---|
| `--settings` naming `log-session-cost.sh`, synchronous | **row written** |
| the same file with `"async": true` added | no row |
| no `--settings`, user settings carrying `"async": true` | no row |
| no `--settings`, after removing `async` from user settings | **row written** |

The only variable is the flag. An async hook is not awaited; a headless process exits the
moment the turn ends, and the write loses the race. An interactive session outlives its
own hook and always wins it — which is the entire explanation for 83 rows a day from
sessions a person was sitting in front of and none from either headless host. `Stop`
fired every time. Nothing waited for it.

`SubagentStop` survives the same flag only because a subagent ends *mid*-session, with a
parent still running. That is luck, not design, and the last subagent of a headless run
does not have it. Both are synchronous now, in the user settings here and in the
NixOS-declared settings devbox deploys. `PostToolUse` keeps `async`: it fires mid-session
with the process guaranteed to outlive it, which is the one place the flag buys
something.

**The cost of synchrony, measured rather than assumed.** `log-session-cost.sh` takes
134 ms against the largest transcript on this host (8.8 MB); `subagent-exit.sh` takes
38 ms. That is the price of the record, per turn, in the worst case here.

**Making it synchronous exposed the other half of the same defect.** At `Stop` the
assistant turn is not on disk yet — measured at 109 ms behind the hook. The first four
synchronous runs wrote `assistant_msgs: 0, in: 0, out: 0, cost_usd: 0`. A row that exists
and says nothing is the async loss wearing the opposite mask, and it is *worse*, because a
missing row is visibly missing while a zero row aggregates as a free session. The hook now
waits, bounded, for the last conversational record to be a closed assistant turn; the
verified headless row carries `assistant_msgs: 1`, its tokens, its cost and its model.

**What this does to the capture rate, which §8 item 3 asked for.** The rate cannot be
re-derived from the old figure *or* from §2's, because both were computed against a cause
that was not the cause. What is now known: headless capture was 0%, it was never a
property of the harness, and both hosts capture from the next session onward. The number
worth having is a forward one, and it needs a day of headless runs before it means
anything.

The guard is `tests/test_session_end_hooks_are_awaited.py`: no `Stop`, `SubagentStop` or
`SessionEnd` hook in any settings file this workspace declares may carry `async: true`,
and the cost row must carry a turn that lands after the hook starts. It was confirmed to
fail on both counts before it was made to pass.

**Method note, since this is the third instance in two days.** §2 verified that the hook
worked by running it through `bash`, which hid mode 644. This section's predecessor
verified that `Stop` did not fire by observing that no row was written, which hid a hook
that fired and was abandoned. Both measured a real thing adjacent to the claim. The
distinguishing move here was the *control*: same hook, same prompt, one flag changed.
