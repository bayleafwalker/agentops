# Handover — the producer that never ran, and the class it belongs to

## Landing status

| Repo | HEAD | State |
|---|---|---|
| agentops | `05ea0f8` | clean, pushed, verified at `origin` |
| auditctl | `af96357` | clean, pushed, verified at `origin` |
| acceptance-lab | `201a30a` | clean, pushed, verified at `origin` |
| gitops-nixos | `5ff73da` | clean, pushed — Forgejo **and** the GitHub mirror |
| cred-broker | `bf81ee1` | pushed; one deliberate untracked `.envrc` (item 11) |
| vuoro / vuoro-cloud / sprintctl / actionq / bindery-core / scribectl / homelab-analytics | unchanged | clean |

Nothing in a PR. Every ref above was checked with `git ls-remote`, not read off push output.

## Releases

| Artifact | Version | State |
|---|---|---|
| auditctl | **0.1.7** | released `d0f00b3`, wheel `bd0883326af5…`, **installed and probed on workstation and devbox** |

Production went 0.1.6 → 0.1.7 on both hosts. Verified at the installed tree, not the
install command: `__version__`, `validate_dispatch_exit_metadata` present,
`require_artifacts_root` absent, and three live contract probes on each host.

`agentops#2329` commissioned it and is `done`, note `#2629`. auditctl has no local
sprintctl; its items live in agentops scope, per the `#2063` precedent.

---

## The part worth reading first

`subagent-exit.sh` was built on 2026-08-29 to make dispatched death observable. This
morning it had written two rows ever, both probes.

I found the settings-scope defect — project settings load only from a session's primary
working directory, and a dispatch-ready project folder has no `.claude/` — registered the
hook at user scope, and reported it fixed pending a reload. **That was the second gap, not
the first.**

The script was mode **644**. Invoked by bare path, which is how a settings file names a
hook, the harness's shell answers `Permission denied` and exits **126** before the script
reads a byte of stdin. I had verified that script by running `bash <path>`, watched it
exit 0, and wrote "the hook works when invoked."

It does. That is not the claim that mattered, and running a script through an interpreter
is precisely what hides a missing exec bit. **I verified the thing next to the thing.**

Two mechanisms kept it invisible, and both are worth carrying forward. `core.fileMode` is
`false` in agentops, so git never recorded that someone had chmod'd the working copies —
the workstation's hooks were 755 on disk and 644 in the index, and that difference never
appears in `git status`. And devbox's `/projects/dev` is an independent clone, so it
received the *tracked* mode. That is the entire explanation for devbox recording nothing:
not only was nothing registered there, nothing registered there could have run.

Seven hooks were affected. The seventh was found by the completeness test rather than by
inspection: `forge-credential.sh` is executed with arguments by `forge-context.sh`, which
swallows the failure as `PROBE FAILED` — so on every fresh clone the credential probe has
been reporting a failure that was really a permission error.

The predecessor's rule was that a dismissal needs the same treatment as a finding. This
one adds: **a verification needs its own subject checked.** "The hook works" and "the
registration works" are different claims, and the cheap test answers the first one.

---

## What got done

**One defect class, found six times, then mechanized.** A contract declared, tested, and
never produced — each instance individually invisible because *the test passes either
way*.

| Instance | Disposition |
|---|---|
| `ACTIONQ_TERMINAL_REASON_CODES` — validator live, its only writer retired 2026-08-22 | contract rebound to the event type (`c094ad4`) |
| `SubagentStop` hook — registered out of scope, then mode 644 | both fixed; **proven firing on both hosts** |
| `require_artifacts_root` — a stated requirement, passing test, no caller | retired (`fb8ee82`) |
| `skill-lock.v1.schema.json` — **unparseable**, two unclosed braces, never loaded | repaired; producer still validates by hand |
| `session-capsule.schema.json` — 81 test functions, zero instances | open (item 6) |
| `.auditctl-id` — implemented, zero instances | **not a defect**; worktrees already resolve correctly |

Vuoro's direction doc §13 already states this as falsifier 11 — *"an object that emits no
lifecycle events is not an object, it is a name"* — and names `vuoro-dispatch-ready`, this
session's own working directory, as the counterexample on record. Nothing mechanized it,
which is why it caught none of the six. `check_producers.py` (`b10cd91`, `973d1a2`) now
does: 31 contracts, and the largest class is **14 whose only instances are their own
committed fixtures** — `test-context` with 69 of them, `verification-result` with 48.

Its mirror is the more actionable half: **auditctl declares no event-type vocabulary at
all**, so 46 observed types are producers with no contract, `workflow.session` at 1747
rows among them. The workspace has contracts without producers *and* producers without
contracts, and neither side had a way to notice.

**Two evaluators stopped scoring vacuous passes.** `_ratio(0, 0)` returned 1.000, so three
acceptance-lab scorers awarded a perfect score to a candidate that demonstrated nothing —
including one nobody had reported, where a candidate that changed nothing passed the gate
proving changes were independently verified (`add5ca1`). And `resume-and-settle` scored
PASS 1.000 on eight hard gates while several passed for reasons weaker than their names;
it is 1.0.2 now and the previously-clean candidate scores **0.000** on provenance
(`7e164e3`). A scenario that cannot fail proves nothing.

One finding from that generalises and is worth stating alone: **a forbidden-shaped gate
cannot catch a candidate that says nothing.** Adding a forbidden-fact check left the old
artifact at 1.000. Requiring provenance *positively* is what bit.

**The scorer lock now covers what a scorer computes** (`201a30a`). Ten of thirteen reach
their verdict through `_ratio`, so editing that one helper would have changed what all ten
measure while every digest stayed green. Found because the empty-subject fixes had to be
written inline *specifically to avoid* touching it — working around a hole is the point at
which to close it. 12 of 13 digests moved, **zero revisions moved**, and `digest_algorithm`
is new in the lock so those two cases are distinguishable in a diff.

**The refusal that was paid for has a producer** (`e3d1c42`). `bindery-core` holds the only
two complete accept/reject/merge cycles on record, and the driver could publish the cheap
refusal — before any worker starts — and never the expensive one, which is the whole
argument for the guard. ERM-005 passes the new gate; **ERM-WIDE drops from PASS to FAIL**,
correctly, because its only refusal was a preflight one.

**devbox is current and instrumented.** auditctl 0.1.7, `SubagentStop` registered in the
NixOS-declared settings and proven firing, and `deploy-host.sh` no longer needs a
hand-supplied `NIX_SSHOPTS` (`5ff73da`) — `nixos-rebuild` resolves the destination with
`ssh -G` and copies to the resolved `user@address`, and ssh_config `Host` blocks match the
destination *as spelled*, so the alias's identity was being dropped on the second
connection.

---

## Open items

1. **Six of seven terminal reasons have never been written.** `completed` and
   `crash-inferred` exist; `usage-limit` — the code the 2026-08-28 incident that
   commissioned this whole design actually needed — does not. The producer fires, and it
   has never been tested against the case it exists for. **This is the top item.**
2. **Headless work records no cost anywhere.** Measured on both hosts with the workstation
   as its own control: `SubagentStop` fires for `claude -p`, **`Stop` does not** — 83
   `session-costs.jsonl` entries today from interactive sessions, zero from either headless
   run, and the devbox run made tool calls so it is not a threshold. This inverts today's
   own devbox fix: `log-session-cost.sh` was registered there because devbox is where the
   spend happens, and that identity exists *precisely* to run headless. Harmless, and it
   does not reach the gap. Every `workflow.session` on record comes from a session a human
   was sitting in front of.
3. **Where `EvidenceSet` and `Decision` canonically live** — vuoro direction doc §14, open
   architecture decisions. **This is the owner call, and it is upstream of two things this
   session tripped over.** `verification/results/` and acceptance-lab's `campaigns/` both
   stand in for a durable evidence record with no declared home, so each improvises whether
   it is a *record* or a *build output*, and the gate guarding each improvises to match.
   Same defect as the census, one level up: declared-versus-produced is contracts with no
   writer; stored-versus-derived is artifacts with no declared kind.
4. **`changes-carry-receipts` certifies the wrong phase.** Every effect in
   `resume-and-settle`'s trajectory comes from the arrange phase; the recover phase writes
   nothing, so the gate proves the *pre-interruption* session's writes. Fixing it needs one
   live, idempotent, receipt-carrying write to `vuoro-shared`, which cannot be rehearsed
   without performing it. Recorded in the scenario's `metadata.known_gaps` with the
   operation named.
5. **The scorer lock excludes classes**, deliberately and with the reason in code: a
   dataclass field rename in `models` can still change what a scorer reads. Including them
   would bump all thirteen digests on any model edit, and a lock that cries wolf gets
   regenerated without being read.
6. **The session-scoped half of the resolved-context invariant has no producer.**
   `AuditContext` instantiates the *write-scoped* half — atomicity, fail-closed,
   attribution. `SessionBinding` is named and unbuilt, and `session-capsule.schema.json` is
   its schema with 81 test functions and zero instances. This is the concrete shape of the
   entitlement question both prior handovers rank first: the record answers *where a write
   came from*, not *who set the context and what entitled them to*.
7. **`no-local-only-authority` has no honest subject** in `dispatch-cycle`. Nothing today
   can cite `local:working-tree` and the probe is built so it never will. It cannot fail. By
   §2's own rule that is an instrument, not a bar, and it should not be a model for new
   checks.
8. **Three `dispatch-cycle` checks charge the consumer for the harness's obligations** —
   `containment-held`, `the-merge-carries-a-receipt` and `spend-was-reported`. A consumer
   cannot make the driver write a receipt. ERM-005 is `CONDITIONAL` solely because its
   receipt predates a field, which is charging it for a substrate field's birthday.
9. **35 fixture events sit in agentops' store**, `task_id` `EX-1`, indistinguishable from
   production. The ingestion is *not* live — I measured `before=35 after=35` running the
   suite — so the mechanism named in the assessment does not reproduce; those came from
   something else on 2026-08-29. `check_producers.py` now reports spread so a reader can
   see the shape, but it aggregates across the corpus and does not isolate this case.
10. **`gate-log.sh` is not registered on devbox**, deliberately. It fires on every tool
    call and its write target was unconfirmed at the time. It is now known that
    `/projects/dev/.claude/` is `agent`-writable there, so the blocker is gone; the
    remaining question is whether a `PostToolUse` hook belongs on a headless
    `bypassPermissions` identity at all.
11. **`cred-broker/.envrc` is untracked and unignored**, deliberately. Five repos here
    commit theirs; whether this one belongs in the tree is a question about its contents,
    not a defect to paper over from outside. **Owner's call.**
12. **Three verification result filenames name items that resolve in no repo scope** —
    1201, 1202, 1207. Only 2063 does. Left as found.
13. **`vuoro-dev` is stalled in flux** at an older revision with
    `Deployment/vuoro-dev/vuoro-dev status: 'Failed'`. Carried from the previous handover,
    still not investigated.

## Next steps, in order

1. **Test the producer against the case it exists for** (item 1). Drive a dispatched unit
   into a real `usage-limit` and confirm the row carries it, or establish that the
   transcript tail cannot be matched and say so. Everything about loss observability rests
   on a vocabulary that is 14% exercised.
2. **Re-derive the capture rate from item 2's fact**, not by adjusting the old figure. If
   `Stop` never fires headlessly, every unattended session is missing by construction and
   no publisher fix recovers it. The question is whether `SessionEnd`, or the `SubagentStop`
   path that demonstrably does fire, is the right carrier.
3. **Put item 3 to the owner.** It is one question, it is already written down, and two
   separate release-shaped decisions this session were downstream of it.
4. **Build the session-scoped half** (item 6). It has a schema, tests, and no instance; it
   is the entitlement question in buildable form; and it is the last item in the defect
   table still fully open.
5. **Then run the loop once, manually** — unchanged from the plan's §10.6, and now with an
   instrument that can tell whether each step left a record.

---

## Long goal

The product sentence has not moved and should not: **keep long-running agent work
resumable, and know which result actually counts.** Everything below serves recovery or
settlement, or it is honestly adjacent.

What this session changes is the standard of evidence for claiming either.

Six months out, the thing worth having is not more contracts. It is that **every contract
in this workspace can answer four questions in order — declared, selected, invoked,
evidenced — and that something other than a person's attention checks the answer.** Today
exactly one item completed that arc, and it took a day, because each stage looked correct
from the one before it. A validator looked live because its test passed. A hook looked
registered because the settings file said so. A registration looked working because the
script ran. A PASS looked earned because every gate was green.

The concrete shape of that, in dependency order:

- **A ledger that can disagree with reality.** auditctl records what was observed and never
  what should be. That rule is right and is now enforced in one more place; it needs
  enforcing wherever an artifact is currently doing double duty as record and build output
  (item 3). Until then, a routine version bump keeps looking like a decision.
- **Gates that can fail.** Two evaluators stopped awarding perfect scores to candidates that
  demonstrated nothing, and one scenario regained the ability to fail. The generalisation
  is worth more than either fix: a check whose subject can be empty, or that is shaped as a
  prohibition, is satisfied by silence — and silence is what a broken producer emits.
- **An admission subject on every gate.** Three checks currently charge a consumer for the
  platform's obligations. A gate with no named subject becomes something everyone must
  clear, which is how `dispatchable` died.
- **Resumability proven as an outcome, not as a green run.** `resume-and-settle` establishes
  something real and narrower than its name: that a process with a credential and a repo id
  can *read back* what a prior process wrote. Recovery of capability — a recovered session
  that writes, and carries a receipt for it — is item 4 and is the honest next bar.
- **Then, and only then, the consumer question.** `bindery-core` proves the substrate works
  for one consumer whose gates, oracle and language are its own. `homelab-analytics` is the
  real test, because it is not agent infrastructure at all. A substrate that serves only its
  own tooling has proved nothing.

The method is the product, and it has one rule this session earned the hard way. Measure
the claim you are actually making. A correct measurement of the wrong question closes the
investigation, and that costs more than no measurement at all.
