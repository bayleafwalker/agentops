# Handover — the loop that rejected itself twice

Supersedes `handover-2026-08-30-the-instrument-that-was-reading-prose.md`, written
mid-session and now stale in one line: it says step 5 is not started. Step 5 ran. All
five of the predecessor's next steps are done.

## Landing status

| Repo | HEAD | State |
|---|---|---|
| agentops | `6192bc6` | clean, verified at `origin` with `git ls-remote` |
| gitops-nixos | `b7cdf29` | clean, verified at Forgejo **and** the GitHub mirror; deployed to devbox twice |
| vuoro | `9886130` | clean, verified |
| cred-broker | `9b8ade8` | clean, verified |
| auditctl `af96357`, acceptance-lab `201a30a` | unchanged | clean |
| devbox `/projects/dev/agentops` | `6192bc6` | clean, current — **but see item 1** |

Nothing in a PR. No release cut. Every ref above read from the remote, not from push output.

---

## The part worth reading first

The plan's §10.6 has asked for one manual loop run across four handovers. It ran, on
`agentops#2101`, through every property it names: distinct principals and grants, durable
external state, independently checkable claims, interruption and resume, settlement.

**It did not settle. Two dispatched attempts were rejected at coordinator review, and the
rejections are the yield.**

- **Attempt 1** satisfied all five acceptance properties and produced **55 contradictions
  on the real corpus, every one false** — 21 commits that resolve in a sibling repository
  (the landing table's `Repo` column was never read), 33 "paths" that are git refs and
  model names, 1 status taken from adjacent prose. Precision on `contradicted`: **0**.
- **Attempt 2**, under an amended packet whose properties bound both directions, ran
  clean: 35 verified, 0 contradicted, 21 uncheckable, each uncheckable correctly
  reasoned. **It passes by not checking** — of the backticked hashes across the fifteen
  committed handovers that actually resolve in this repository, it extracts **4 of 33.
  Recall 12%.**

Two mechanics, which is exactly what §10.6 asked the loop to produce rather than to
design:

1. **An acceptance property over a classifier must bound both directions.** One that only
   forbids under-reporting is satisfied by noise.
2. **A two-sided property measured in aggregate is one-sided in practice.** My amended
   floor — zero contradictions *and* a non-zero verified count — was cleared by 35 claims
   concentrated in three old documents while ten were checked not at all. The floor has
   to be a **rate against a denominator the artifact under test does not compute**.

I wrote the property that let attempt 1 through, then wrote the property that let attempt
2 through, one iteration later. Neither was careless; both were the obvious next
tightening. That is the argument for running the loop.

Full record: `docs/dispatch/loop-run-2026-08-30-agentops-2101.md`, evidence
`ad:01M1A6YHTF99JRV316MPEW7Z51`, item notes `agentops#2101` #2631 and #2632.

---

## What got done before the loop

**The exit producer was reading prose** (`988780e`). `subagent-exit.sh` classified by
text-matching the last three assistant blocks. Over all 353 subagent transcripts on this
host it returned 76 non-`completed` verdicts where the records carry 19 — all 38
`timeout`, all 5 `cancelled`, 14 of 33 `usage-limit` spurious, every one from a subagent
that *completed* and whose report discussed the topic. Its stated premise was false at
the artifact: the terminating record carries `apiErrorStatus: 429`, `error: "rate_limit"`
and `quotaLimits.resetsAt`, an exact epoch second. Fixed to read the record; re-run gives
334/19 and nothing else, 12 with exact reset instants. The corpus holds exactly **two**
terminal outcomes; four of seven codes have no observed instance anywhere.

**`Stop` does fire headlessly — it was never awaited** (`c43573e`). Four controlled runs,
one variable: `"async": true`. An async hook is not awaited and a headless process exits
as the turn ends. Interactive sessions outlive their own hook and always win, which is
the whole explanation for 83 rows a day from attended sessions and none from either
headless host. Synchrony then exposed the other half — at `Stop` the turn is not on disk
yet (109 ms behind), so the first sync runs wrote `cost_usd: 0`. Bounded wait added.
Cost measured: 134 ms worst case, 8.8 MB transcript.

**`SessionBinding` v0** (`da77818`) — the session-scoped half of the resolved-context
invariant, resolved once at `SessionStart`, atomic, immutable, attributed. Records every
settings layer by path *and content digest*, which is the answer to "who set this and
what entitled them". Proven on both hosts. It is **not** `session-capsule/v1`; two
handovers said it was, and the capsule is end-of-session exhaust.

**Two owner decisions, put and answered.** `EvidenceSet` and `Decision` live in auditctl
(vuoro `9886130`, §14 narrowed with a falsifier bound to the claim; `verification/results/`
and acceptance-lab `campaigns/` are derived build outputs that cite a ledger id).
`cred-broker/.envrc` committed after reading it — no secret, identical in shape to five
siblings.

---

## Open items

1. **devbox's audit store is forked and cannot be reconciled. This is the top item.**
   Two clones of one repository share `origin_stream_id` `83d0b252-…` and each assigns
   sequences from its own index: the workstation shard ends 641, 642, **644**; devbox
   assigned **643–658**. Seq 644 names two different events on two hosts, and
   `auditctl rebuild` on devbox answers **`rebuild rejected [origin_discontinuity]`** —
   its own guard refusing, correctly. devbox's index holds 16 events its shard cannot
   carry; the four real ones survive only in `session-bindings/*.json` and
   `session-costs.jsonl`. Contract finding 5 called this a silent path collision; it is
   the **sequence space itself**, and it surfaces at rebuild, after the events exist.
   **Unverified and first to check: whether devbox can still *publish* after pulling the
   seq-644 event.** Reads work. If writes fail, that host's instrumentation is mute and
   everything built yesterday for it is inert.
2. **The test suite writes `EX-1` fixture events into the live audit store.** Twelve
   landed in devbox's clone at the four times the worker ran
   `python -m unittest discover -s templates/dispatch/tests`. **This closes the
   predecessor's item 9**, which measured `before=35 after=35` on the workstation and
   concluded the mechanism did not reproduce: it reproduces on any host without the
   direnv that roots `AUDITCTL_ARTIFACTS_ROOT` away from the live store. The tests do not
   isolate their own audit root and the workstation's `.envrc` was hiding it. None were
   committed. The fix is conftest-level and small.
3. **An interrupted worker still records nothing.** `Stop` does not fire on `SIGTERM`, so
   the loop's four killed minutes left a transcript and a `SessionBinding` and no ledger
   row. Reproduced on the first attempt, inside the loop, after a day spent fixing the
   adjacent case. This is the loss shape the whole design was commissioned for and it is
   still open.
4. **`agentops#2101` reads `blocked` and is not blocked.** There is no lifecycle
   transition for an attempted item returned unclaimed: `active → pending` is invalid and
   so is `blocked → pending`. The reachable states are `done` (a lie), `blocked` (this),
   or `active` with no holder. Note #2632 carries the truth. The state machine has no
   representation for the ordinary outcome of a dispatch cycle that does not settle.
5. **Nothing records a packet freeze.** Three of seven loop stages leave no durable
   record: the freeze (this is item **#2054**, pending), the coordinator review, and the
   interrupted worker (item 3). The frozen packet and its amendment lived in a scratch
   file.
6. **No dispatch command exists.** Packet, prompt and tracker state were `scp`'d and the
   worker launched by `nohup setsid` over ssh, twice. `limits.timeout_seconds: 1800` is
   declared and unenforced — attempt 2 ran 22 minutes inside a budget nothing measured.
7. **The authority split is prompt-level, not mechanism-level.** The worker ran six `git`
   commands (all read-only, all legitimate for the task) and published twelve events to
   auditctl, which the packet forbids outright. Nothing checked either. The packet's own
   wording is also wrong: "No git" forbids wholesale what it means to forbid selectively.
8. **Nothing consumes a `SessionBinding`.** The contract's first falsifier — *a tool can
   consume the resolved context and still need to walk the tree itself* — is untested
   because there is no consumer. No applier either (sequencing step 3's second half).
9. **`bindery-core`'s consumer proof** — 17% of measured spend, the only complete
   accept/reject/merge cycle on record, called "the highest-value item nobody has opened"
   two handovers ago. Still unopened.
10. **The capture rate has no honest number.** Both prior figures were computed against a
    cause that was not the cause. Headless capture was 0%, it was never a property of the
    harness, and both hosts capture from now on. The number worth having is forward and
    needs a day of headless runs.
11. **The worker's environment is weaker than the coordinator's and nothing declares it.**
    devbox has no `pytest` module; the workstation has 9.0.3. The worker excused four
    "pre-existing failures" that do not reproduce. `environment-record` carries a
    `capabilities` block that says nothing about this.
12. Unchanged and uninvestigated: `changes-carry-receipts` certifies the wrong phase;
    `no-local-only-authority` cannot fail; three `dispatch-cycle` checks charge the
    consumer for the harness's obligations; the scorer lock excludes classes; three
    verification result filenames resolve in no repo scope; `vuoro-dev` is stalled in flux;
    `gate-log.sh` is unregistered on devbox (and is `async`, so it would have had the same
    problem).

---

## Next steps, in order

1. **Answer item 1's open question first** — can devbox publish? One probe event tells
   you. Everything else about that host depends on the answer, and if it is no, the
   session-binding and cost instrumentation deployed there yesterday is decorative.
2. **Fix item 2** — isolate the test suite's audit root. It is small, it is the mechanism
   behind 35 fixture events already in the store, and every future clone repeats it.
3. **Attempt 3 on `agentops#2101`**, with the specification the loop produced: extraction
   must cover inline backticked hashes as well as landing tables, and the acceptance floor
   must be a rate against an independently computed denominator. The item's note #2631
   states it.
4. **Open `bindery-core`.** It has outranked everything for three handovers and been
   opened by none of them.

---

## Long goal

Unchanged: **keep long-running agent work resumable, and know which result actually
counts.**

The predecessor set the standard as four questions — declared, selected, invoked,
evidenced — and added a fifth: *is what the instrument reports the thing that happened,
or its own reading of something adjacent?* The loop added the sixth, and it is about the
questions themselves rather than the instruments:

> **A property that constrains one direction is satisfied by noise, and a property that
> constrains both in aggregate is satisfied by silence.**

Attempt 1 was noise; attempt 2 was silence; both passed every property written for them,
and I wrote both properties. Neither failure was visible from inside the candidate — its
tests passed in both cases — and neither was visible from the report. Both were visible
in one place only: the artifact measured against a denominator computed by something
other than the artifact.

That is the same rule as the fifth question, applied to specifications instead of
instruments. It is also the reason the day's earlier work stands up: the classifier fix
was measured against the transcripts' own records, the async fix against a control that
changed one flag, the binding against both hosts. Every claim that survived today
survived because something outside it did the counting.

Six months out, the thing worth having is that no gate in this workspace can be satisfied
by noise or by silence, and that the denominator is never computed by the thing being
measured.
