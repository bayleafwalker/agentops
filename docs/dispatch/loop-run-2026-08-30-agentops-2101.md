# Manual loop run — agentops#2101, 2026-08-30

**Evidence:** `ad:01M1A6YHTF99JRV316MPEW7Z51` (agentops audit ledger), item notes
`agentops#2101` **#2631** and **#2632**. This document is a derived build output that
cites that ledger id; the ledger is the record.

The meta-narrative plan's §10.6 has asked for this across four handovers: *"Then run the
loop once, manually. Distinct principals and grants, durable external state,
independently checkable claims, interruption and resume, and settlement. Let its measured
operator interventions and failure modes generate the mechanics — rather than designing
more of them first."*

It was run once, end to end, on a real item. It did not settle: two dispatched attempts
were rejected at coordinator review. **That is the result, not a failure of the
exercise** — both rejections came from measurements the coordinator made and neither
candidate's own tests could, and the two mechanics they generated are worth more than the
item would have been.

Every operator intervention is numbered `OI-n` at the point it happened. Every stage
records what it left on durable record, and where it left nothing.

## Stage 1 — grant (durable external state)

- Reservation **50** on `agentops#2101`, actor `workstation-vuoro`, role `execution`,
  bound to session `b7df624e-…`. Served backend, vuoro-shared. `conflict: false`.
- Status `pending → active` via the served lifecycle command.

**OI-1.** `--expected-revision` was rejected: "a direct-backend CAS option; served
lifecycle commands already carry their immutable basis revision." The coordinator has to
know which backend it is on to know which concurrency discipline applies, and the item
record hands out a `status_revision` that the served path will not accept. Not a defect
in either half; a seam with no single answer visible from the item.

**Recorded:** reservation row and item event, both in vuoro-shared. Nothing in auditctl —
the claim is sprintctl-only, which is correct (work authority) but means a reader of the
audit ledger alone cannot see that a session held a grant.

## Stage 2 — frozen packet

`agentops-task/v2`, task `AGENTOPS-2101-handover-preflight`, frozen at
`6db5274e46db97d9ce6371edd2f989191eb97daf`. Validates against
`templates/dispatch/hybrid/task-packet.schema.json`. Two writable paths, five required
outcomes, five acceptance properties each naming what makes it fail.

**Recorded:** nowhere durable. The packet exists as a scratch file and in the worker's
transcript. Nothing in sprintctl or auditctl says a packet was frozen, at which commit,
or with which acceptance properties — which is exactly what item #2054 (`planner-manifest
/v0` at packet freeze) exists to fix, and it is pending.

## Stage 3 — dispatch to a distinct principal

Worker: devbox `agent`, uid 1100, `bypassPermissions`, credential-poor, behind the
agent-egress default-deny table. Disposable worktree at the frozen commit, detached.

The worker's `SessionBinding` was produced at `SessionStart` and names the principal
without being asked:

```
actor: {'os_user': 'agent', 'uid': 1100} | env: devbox rev 2
cwd: /projects/dev/.hybrid-worktrees/agentops-2101
project: ancestor-walk 981b2073-d7af-4c28-bff3-3cf807495fba
```

That is "distinct principals and grants" legible at the record rather than asserted in a
runbook, and it did not exist this morning.

**OI-2.** The packet had to be delivered by `scp` and the worker launched by
`nohup setsid` over ssh. There is no dispatch command; the runbook describes the shape
and the operator performs it.

## Stage 4 — interruption and resume

**OI-3, and it damaged the run.** `pkill -u agent -f "claude -p"` matched the *remote
shell's own argv*, because the ssh command string contains that text. It killed its own
controlling shell along with the worker, so the interruption produced no output and its
state had to be reconstructed afterwards. A kill pattern that matches the killer is an
operator hazard, not a harness defect, but it is the kind the loop is meant to surface.

**Measured at the interruption:** the worker had run ~4 minutes and written **nothing**.
It left a `SessionBinding` and a transcript. It left **no cost row and no exit record** —
`Stop` never fires on SIGTERM, and `SubagentStop` had nothing to fire for. So today's
async fix does not cover a killed session, and a killed session is still invisible to
the ledger. That is the loss shape the whole design exists to close, reproduced inside
the loop on the first try.

**Resume worked.** `claude -p --resume <session_id>` in the same worktree resumed the
same session id, `SessionStart:resume` fired, and the worker began producing files
within 20 seconds. The binding producer no-opped, correctly: no contradiction was
raised for a legitimate re-entry.

**Near-miss worth recording.** `grep -c contradiction` over the resume log returned 2,
and the obvious reading was that the binding had fired a false contradiction — the exact
falsifier the contract names. Reading the lines showed the word came from the *worker's
own docstring* about handover claims. Counting a string is not reading a record; that is
the same error as the three in the handover, in its cheapest form.

## Stage 5 — independently checkable claims (coordinator review)

The worker reported success: 15 turns, 8m05s, $0.92, "all required outcomes hold".
Its tests pass. Two files, both inside `writable_patch_paths`, no git mutation.

| Gate | Result |
|---|---|
| nothing written outside the frozen paths | pass |
| full suite on the coordinator host | **1597 passed**, 0 failed (baseline 1583) |
| the worker's claimed "4 pre-existing failures" | **do not reproduce** — devbox has no `pytest` module, the workstation has 9.0.3. The worker's own gate is weaker than the coordinator's and neither environment record says so. |
| **the checker run against the real corpus** | **rejected** |

**The candidate produces 55 contradictions and every one is false.**

- **21 contradicted commits — all 21 resolve in a sibling repository.** The handover
  landing tables have a `Repo` column; the checker never reads it, so it checks every
  cross-repo HEAD against `agentops` and calls each one contradicted.
- **33 contradicted paths.** The grammar is "a backtick token containing a slash", which
  swallows `origin/main`, `opencode-go/deepseek-v4-flash` (a model name),
  `sprintctl/cli.py` (another repo's file), `members/actionq`.
- **1 contradicted tracker claim**, `agentops#2254 claimed 'fit'` — "fit" came from
  nearby prose, not from a status claim.

Precision on `contradicted` is **0**. The worker's own docstring states the rule it
broke: "under-extraction is safe, a false contradiction on real handover prose is not."

**The defect entered in the packet, not in the worker.** Every acceptance property was
one-sided. REQ-002 fails when "path claims are not extracted, or a missing file is
reported verified" — a recall guard with no precision guard. An implementation that
contradicts everything satisfies all five properties completely. This is the same shape
as the earlier finding that a forbidden-shaped gate cannot catch a candidate that says
nothing, one level up: **a required outcome that states only recall is satisfied by
noise.**

That is the loop doing its job. The mechanic it generates: an acceptance property over a
classifier must bound both directions, and the corpus it is measured on must be the real
one, not the fixtures.

## Stage 5b — attempt 2, from the measurement rather than from an opinion

The packet was amended in place (`amendments[]`, which the schema requires to carry
`date`, `amends`, `now_reads` and `why` — a freeze that cannot be quietly rewritten).
Every acceptance property now bounds **both** directions, and REQ-005 measures the real
corpus: zero contradictions over the committed handovers *with a non-zero verified
count*, so it cannot be passed by extracting nothing.

The worker was given the coordinator's numbers, not a verdict: 43/55/0, the three
categories, and the specific tokens. Its own attempt-1 code was left in the worktree.

**OI-4.** There is no dispatch command for attempt 2 either — the packet, the prompt and
the tracker-state file were `scp`'d and the worker relaunched by hand. The amended packet
is a scratch file; nothing durable records that a second attempt exists, at which commit,
superseding what.

## Stage 5c — attempt 2 reviewed, and rejected for the opposite reason

Attempt 2: 22 min, 80 turns, $5.39. Full suite **1605 passed**, 0 failed. Real corpus:
**35 verified, 0 contradicted, 21 uncheckable**, with the right reason on each
uncheckable — *"claimed about repo 'cred-broker', not the repo this checker was given"*.
Every acceptance property in the amended packet is satisfied.

**It passes by not checking.** Of the backticked commit hashes across the fifteen
committed handovers that **actually resolve in this repository**, it extracts:

> **4 of 33. Recall 12%.**

Attempt 2 restricted commit extraction to landing tables with a `Repo` column plus the
prose form `commit <hash>`. Ten of the fifteen handovers cite commits inline in backticks
with no table, and it sees none of them. Precision went to 1.0 by destroying recall.

**The mechanic this generates, and it is sharper than the first one.** My amended
REQ-005 *was* two-sided — zero contradictions **and** a non-zero verified count. It was
still gamed, because both sides were measured **in aggregate over the corpus**: 35
verified claims concentrated in three old documents satisfy "non-zero" while ten
documents are checked not at all.

> A two-sided property measured in aggregate is one-sided in practice. The floor has to
> be a **rate against a denominator the artifact under test does not compute** — here,
> "of the hashes in these documents that resolve in this repository, at least N% must be
> extracted" — and something other than the candidate has to compute the denominator.

That is the same defect as attempt 1 wearing the opposite mask, and I wrote the property
that let it through, one iteration after writing the property that let attempt 1 through.

**Two near-misses of my own, both caught by reading instead of counting.** "Zero path
claims from today's handover" looked like collapsed extraction; the document contains
exactly two path-shaped tokens and both are correctly excluded. "Seven handovers yield
zero claims" looked like the same thing; three of them genuinely contain no checkable
claim. The finding above survived because it was measured against an independently
computed denominator — which is, exactly, the mechanic it produced.

**Disposition: not merged.** A preflight with 12% recall would pass a handover whose
commits are all fictional, provided they are cited inline. Landing it under
`templates/dispatch/scripts/` would make it a thing that gets run and trusted, which is
the hazard this whole session is about.

## Stage 6 — settlement

Evidence: `ad:01M1A6YHTF99JRV316MPEW7Z51` in agentops' audit ledger, carrying both
attempts, their sessions, costs, verdicts and the two mechanics. Notes **#2631** (the
measurement) and **#2632** (the lifecycle gap) on `agentops#2101`. Reservation 50
released.

**OI-5, and it is a finding rather than a friction.** There is no way to return an
attempted item to `pending`. `active → pending` is an invalid transition; so is
`blocked → pending`. Once a coordinator claims an item and the work is rejected at
review, the reachable states are `done` (a lie), `blocked` (what it now reads, and it is
not blocked on anything), or `active` with no holder — indistinguishable from work in
flight, and reservations are not leases so nothing reaps the claim.

**The state machine has no representation for "attempted, rejected, returned unclaimed",
which is the ordinary outcome of a dispatch cycle that does not settle.** Recorded on the
item rather than worked around.

## Operator interventions, counted

| | What | Cost |
|---|---|---|
| OI-1 | `--expected-revision` is a direct-backend option the served path refuses, while the item hands out a `status_revision` | confusion only |
| OI-2 | no dispatch command: packet, prompt and tracker state `scp`'d, worker launched by `nohup setsid` over ssh | every stage, twice |
| OI-3 | `pkill -f "claude -p"` matched the remote shell's own argv and killed its controlling shell with the worker | interruption state had to be reconstructed |
| OI-4 | attempt 2 dispatched the same way; nothing durable records that a second attempt exists, at which commit, superseding what | the freeze is a scratch file |
| OI-5 | no lifecycle transition for an attempted-and-returned item | the item's status is now wrong on purpose |

Plus two conditions nothing enforced:

- **`limits.timeout_seconds: 1800` is declared and unenforced.** Attempt 2 ran 22 minutes
  of wall clock inside a 30-minute budget nothing was measuring; it could have run all day.
- **The authority split is prompt-level, not mechanism-level.** The worker ran six `git`
  commands. All six were read-only and legitimate for the task — resolving whether a hash
  exists is the task — but nothing checked, and `git commit` would have been equally
  unopposed. The packet's own wording is also wrong here: "No git" forbids wholesale what
  it means to forbid selectively.

## What the loop left on durable record, and what it did not

| Stage | Durable record |
|---|---|
| grant | reservation row + item event, vuoro-shared |
| **packet freeze** | **nothing** — this is item #2054, pending |
| worker start | `SessionBinding`, naming principal, environment revision and entitlement digests |
| worker interrupted | **nothing** — `Stop` does not fire on SIGTERM, no cost row, no exit record |
| worker completed | cost row + `workflow.session`, on devbox |
| coordinator review | **nothing until written by hand** — no gate produced a record |
| settlement | audit event + two item notes |

Three of seven stages leave nothing on their own. The one that matters most is the
interrupted worker: the loop reproduced the exact loss shape this whole design exists to
close, four minutes into its first attempt.

## The two mechanics, stated on their own

**1. An acceptance property over a classifier must bound both directions.** Attempt 1
satisfied five properties that each bounded recall — "a missing commit is contradicted",
"path claims are extracted" — and produced 55 contradictions of which zero were real. A
property that only forbids under-reporting is satisfied by noise. This is the same shape
as the earlier finding that a forbidden-shaped gate cannot catch a candidate that says
nothing, one level up.

**2. A two-sided property measured in aggregate is one-sided in practice.** The amended
property *was* two-sided — zero contradictions **and** a non-zero verified count — and
attempt 2 satisfied it with 12% recall, because 35 verified claims concentrated in three
old documents clear a floor of "greater than zero" while ten documents are checked not at
all. The floor has to be a **rate against a denominator the artifact under test does not
compute**, and something other than the candidate has to compute it.

I wrote the property that let attempt 1 through, then wrote the property that let attempt
2 through, one iteration later. Neither was careless; both were the obvious next
tightening. That is the argument for running the loop rather than designing more of it.

## What this says about the substrate

The parts built in the last three sessions worked, and worked without being asked:

- The worker's `SessionBinding` named its principal, environment revision and entitlement
  digests at `SessionStart`, on a host nobody was sitting at.
- Resume restored an interrupted worker by session id, in place, and the binding's
  fail-closed comparison correctly stayed silent for a legitimate re-entry.
- The frozen packet validated against its schema, and the schema refused an amendment
  that did not say what it amended and why.

The parts that do not exist showed up as five operator interventions and three stages
that leave no record. The largest single gap is the one the design was commissioned for:
**an interrupted worker still records nothing.** `Stop` does not fire on `SIGTERM`, so
four minutes of work and its termination left a transcript and a binding and no ledger
row at all — reproduced on the first attempt, inside the loop, after a day spent fixing
the adjacent case.
