# Handover — the instrument that was reading prose, and the flag that dropped the record

Continues `handover-2026-08-30-the-producer-that-never-ran.md` (`24d997a`). Its next
steps 1–4 are done. Step 5 — run the loop once, manually — was not started when this
was written, and ran later the same session. **Superseded by
`handover-2026-08-31-the-loop-that-rejected-itself-twice.md`**, which is the pickup point.

## Landing status

| Repo | HEAD | State |
|---|---|---|
| agentops | `da77818` | clean, verified at `origin` with `git ls-remote` |
| gitops-nixos | `b7cdf29` | clean, verified at Forgejo **and** the GitHub mirror; **deployed to devbox twice** |
| vuoro | `9886130` | clean, verified at `origin` |
| cred-broker | `9b8ade8` | clean, verified at `origin` — the untracked `.envrc` is resolved |
| auditctl `af96357`, acceptance-lab `201a30a` | unchanged | clean |

Nothing in a PR. No release cut: nothing shipped needed a version.

---

## The part worth reading first

The predecessor's top item was that six of seven terminal reasons had never been
written, and it asked for the producer to be tested against the case it exists for.
Testing it found something worse than a missing code.

**`subagent-exit.sh` was classifying by reading prose.** It matched `session limit` /
`rate limit` / `timed out` / `cancelled` against the last three assistant text blocks.
Run unchanged over all **353 subagent transcripts on this host**, it returns 76
non-`completed` verdicts where the records carry 19:

| Verdict | Text match | Records | Spurious |
|---|---|---|---|
| `usage-limit` | 33 | 19 | 14 |
| `timeout` | 38 | 0 | **38** |
| `cancelled` | 5 | 0 | **5** |

Every spurious verdict came from a subagent that **completed** and whose final report
discussed rate limiting, timeouts or cancellation — a research subagent reporting on a
queue design says "retries, concurrency/rate limits". Prose about a failure is
indistinguishable from the failure. It is structural, not a threshold to tune.

It would have got the commissioning incident right, by coincidence: those transcripts
end with text that happens to contain "session limit".

**The premise was false at the artifact.** The hook's own comment said a usage limit
arrives only as a localized wall-clock string and that a reset instant "cannot be
derived at all". The terminating record carries `isApiErrorMessage: true`,
`apiErrorStatus: 429`, `error: "rate_limit"` and, since ~2026-08, `quotaLimits.resetsAt`
— an **exact epoch second**. `1787952600` on `agent-a5d642b86112f09ec.jsonl` is
`2026-08-29T00:30:00` Europe/Helsinki, precisely what the string rendered.

Re-run end to end through the fixed hook over the same 353 transcripts: **334
`completed`, 19 `usage-limit`, nothing else** — equal to the records, 12 carrying an
exact reset instant and 7 older ones honestly declaring none.

**So the vocabulary statement was wrong in both directions.** It is not "14%
exercised". The corpus contains exactly *two* terminal outcomes. Four of seven codes
have no observed instance anywhere, and the instrument that appeared to be producing
three of them was producing artifacts of its own reading. **A producer that infers can
manufacture coverage of a vocabulary nothing has ever exercised.**

---

## What else got done

**`Stop` does fire headlessly. It was never awaited** (`c43573e`). The predecessor
measured that `Stop` does not fire for `claude -p` and concluded every unattended
session was missing by construction, with no publisher fix able to recover it. Four
controlled runs — same prompt, same directory, one variable:

| Registration | row |
|---|---|
| `Stop → log-session-cost.sh`, synchronous | **written** |
| the same, `"async": true` | none |
| no `--settings`, user settings with `"async": true` | none |
| no `--settings`, after removing `async` | **written** |

An async hook is not awaited; a headless process exits as the turn ends and the write
loses the race. An interactive session outlives its own hook and always wins it — the
entire explanation for 83 rows a day from sessions a person was sitting in front of and
none from either headless host. `SubagentStop` survives the same flag only because a
subagent ends *mid*-session; the last subagent of a headless run does not.

Making it synchronous exposed the other half: **at `Stop` the assistant turn is not on
disk yet**, measured 109 ms behind. The first four synchronous runs wrote
`assistant_msgs: 0, cost_usd: 0` — a row that exists and says nothing, which is worse
than a missing one because it aggregates as a free session. The hook now waits, bounded,
for the last conversational record to be a *closed* assistant turn.

Cost of synchrony, measured rather than assumed: **134 ms** for `log-session-cost.sh`
against the largest transcript here (8.8 MB), **38 ms** for `subagent-exit.sh`.

Proven on devbox, the host it was about: a headless run as the `agent` identity wrote
`{"model":"claude-sonnet-5","turns":1,"assistant_msgs":1,"cost_usd":0.045387}`.

**`SessionBinding` v0 exists** (`da77818`) — the session-scoped half of the
resolved-context invariant, the last item in the predecessor's defect table still fully
open. Resolved once at `SessionStart`, written atomically, immutable, attributed. It
records harness, actor, host, the resolved environment record with revision and digest,
the workspace and its `project_id`, and **every settings layer in effect by path and
content digest**, present or absent.

That last field is the whole point. The contract's open question was never "do these
values agree", which a coherent redirect already satisfies — it was **"who set this,
and what entitled them to"**. A shared-scope edit changes one of those files, and the
digest is what makes it legible afterwards from the record alone.

Proven on both hosts. Workstation: `hostname-match` → `workstation-linux` revision 3.
Devbox: → `devbox` revision 2, actor `agent` uid 1100. The schema had 81 test functions
and zero instances for a week.

**It is not `session-capsule/v1`, and two handovers said it was.** The capsule is
*end*-of-session exhaust answering "what did this session do". A binding is written at
the start and answers "what is this session". Building capsules would have closed the
plan item and left the entitlement question exactly as open.

**Two owner decisions, put and answered.**

- **`EvidenceSet` and `Decision` live in auditctl** (vuoro `9886130`). Direction doc §14
  narrowed, not closed — `WorkRelease`, `EffectGrant` and the agent-profile artifacts
  stay open. The consequence is why it was asked: `verification/results/` and
  acceptance-lab `campaigns/` are **derived build outputs that cite a ledger id**, and
  the gate guarding each stops improvising which it is. Falsifier bound to the claim: an
  evidence artifact no ledger id resolves to, or a decision reachable only by reading a
  file in a working tree. Scoped against §11 — these are ledger objects auditctl
  records, not a licence to grow it into an analytics platform.
- **`cred-broker/.envrc` is committed** (`9b8ade8`). Read before deciding: it carries no
  secret, and is the file five siblings each commit, differing only in the repo name in
  its comment.

**One incidental fix.** `schema_check.py` accepted `{"type": "null"}` in `audit_schema`
and then raised `KeyError` the first time an instance reached it — a checker that
accepts a schema it cannot check.

---

## Open items

1. **Run the loop once, manually.** Unchanged from §10.6 and now carried by four
   handovers. It is the only remaining step from the predecessor's list, and the
   instruments to tell whether each step left a record now exist and are proven on both
   hosts. **This is the top item.**
2. **`bindery-core`'s consumer proof** — 17% of measured spend, the only complete
   accept/reject/merge cycle on record, absent from every plan, and the amendment calls
   it "the highest-value item nobody has opened". Still unopened.
3. **Nothing consumes a `SessionBinding`.** The contract's first falsifier — *a tool can
   consume the resolved context and still need to walk the tree itself* — is not yet
   under test, because there is no consumer. The obvious first one is the publisher.
4. **No applier.** Sequencing step 3's second half is untouched. `materialize_project.py`
   and NixOS activation remain two appliers a third must absorb rather than duplicate.
5. **Cross-host binding collision.** Both hosts now produce bindings with the same shape
   and no host field in the path. The binding carries `host.hostname`, which is one input
   the shard path never had, but the merge story is still unstated (contract finding 5).
6. **The capture rate has no honest number yet.** It cannot be re-derived from the old
   figure *or* from the predecessor's, because both were computed against a cause that
   was not the cause. What is known: headless capture was 0%, it was never a property of
   the harness, and both hosts capture from the next session onward. The number worth
   having is forward-looking and needs a day of headless runs.
7. **`session.binding` events are unaggregated.** The producer publishes them; nothing
   reads them. Same shape as the defect class, one day old.
8. **`changes-carry-receipts` still certifies the wrong phase** — needs one live,
   idempotent, receipt-carrying write to `vuoro-shared`. Unchanged.
9. **`no-local-only-authority` cannot fail**; **three `dispatch-cycle` checks charge the
   consumer for the harness's obligations**; **the scorer lock excludes classes**;
   **35 `EX-1` fixture events sit in agentops' store**; **three verification result
   filenames resolve in no repo scope**; **`vuoro-dev` is stalled in flux**. All
   unchanged from the predecessor, none investigated today.
10. **`gate-log.sh` is still unregistered on devbox** — the blocker is gone, the question
    of whether a `PostToolUse` hook belongs on a headless `bypassPermissions` identity is
    not answered. Note it is `async` there and would have had the same problem.

---

## Next steps, in order

1. **Run the loop once, manually.** Everything built in the last three sessions exists to
   make this legible, and it has never been done.
2. **Give the binding a consumer.** The publisher is the natural one, and it is what puts
   the contract's first falsifier under test instead of on a list.
3. **Open `bindery-core`.** It has outranked everything else for two handovers and been
   opened by none of them.
4. **Re-derive the capture rate forward**, after a day of headless runs, from the fixed
   instruments rather than from either retired figure.

---

## Long goal

Unchanged, and it should stay unchanged: **keep long-running agent work resumable, and
know which result actually counts.**

The predecessor set the standard as four questions in order — declared, selected,
invoked, evidenced. Today adds a fifth that sits between the last two, and it is the one
that bit three times:

> **Is what the instrument reports the thing that happened, or the instrument's own
> reading of something adjacent to it?**

Three instances in one day, all of them passing every check they had. A hook was
verified by running it through `bash`, which hid mode 644. A capture rate was measured by
observing that no row was written, which hid a hook that fired and was abandoned. A
terminal-reason producer was tested by confirming it emitted `usage-limit` on a real
limit death, which hid that it emits `usage-limit` on any report that mentions one.

Each was a correct measurement. Each closed an investigation on the wrong subject, which
costs more than no measurement, because a closed investigation is not revisited.

What distinguished today's answers was not more evidence. It was the **control**: same
hook, same prompt, one flag changed. Same classifier, same corpus, verdict compared
against the record rather than against expectation. A measurement with no control tells
you what happened in one condition and lets you believe it was caused by the thing you
were thinking about.

Six months out, the thing worth having is still not more contracts. It is that every
contract can answer the five questions, and that something other than a person's
attention checks the answers — including the fifth, which is the only one a passing test
cannot establish.
