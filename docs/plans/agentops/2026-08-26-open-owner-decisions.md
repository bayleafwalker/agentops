# Four open owner decisions — background, options, implications

**Status: RULED AND EXECUTED 2026-08-26. Retained as the record of what was decided and why.**

> ## How this document should have been written
>
> The owner's assessment of it: *"zero to one of the four required fresh human judgment... the human
> was mostly being used as a very expensive Enter key."* That is correct, and the failure is worth
> keeping in front of the next person who writes one of these.
>
> Three distinct things were collapsed into one bucket labelled "owner decision":
>
> | | |
> |---|---|
> | **Can the answer be derived?** | All four: **yes.** Three had *already been derived* before this document was written — devbox was measured, all 18 manifests' UUIDs were checked, all six `#2046` criteria were verified at file and line. They were then presented as open questions anyway. |
> | **May the agent perform the action?** | An authorization gate, not a deliberation. `#2046` genuinely required the designated human acceptance event; dropping someone's stashes wanted delegated operational authority. Both are *ratification* — bring a resolved action, not a question. |
> | **Is a new value choice necessary?** | At most `#2100`, and probably not even that. See below. |
>
> **`#2100` was policy application, not policy making.** The governing text was already in the
> manifest: the 2026-08-23 ruling reads *"a green evidence gate **on this class** disposes
> candidate"* — class, not route — while `self_candidate_class` looked the entry up by
> `packet["route"]`. Doctrine was class-scoped and mechanism was route-scoped, and they agreed only
> because the strings matched. This document argued C-versus-D on a *prediction* ("is a second route
> coming") when the ruling's own words already settled where authority attaches. Escalation would
> have been justified only if separating them were **new policy** rather than enforcing existing
> policy.
>
> **The right output** of that pass was an execution packet of three resolved actions plus, at most,
> one narrowly framed policy question — not a memo presenting four owner decisions. Correct
> classification: `#2046` *ready for ratification*; `#2100` *policy application, escalate only on
> conflicting doctrine*; devbox *bounded maintenance*; uuid *review-derived fix*.

## Outcomes

| # | Decision | Ruling | Landed as |
|---|---|---|---|
| 1 | Accept `#2046` | **B** — accept, attach criterion 6's negative finding | Notes #2538 (on `#2046`) and #2539 (the control-arm gap, on `#2017`); item `done` |
| 2 | `#2100` route vs authority | **C on principle** — authority is durable and stated, execution is transient | `action_class` landed; `#2100` closed as written (note #2544); successor `#2306` opened |
| 3 | devbox checkout | **B** — fast-forward, inspect, dispose | Fast-forwarded; one unique line landed; **two files in the stash would have been a regression** — see below |
| 4 | `format: "uuid"` | **A** — assert it | `validate_manifest_identity`, 13 regression tests, field stays optional |

**The one place the recommendation was too casual:** decision 3 called the stashes twenty minutes of
tidying. Inspecting them found that `stash@{1}` would have reverted `overlay_hash` to sorted keys and
deleted the test pinning the property — against an explicit comment in `main` explaining that sorting
makes behaviourally different worker sandboxes share a digest. "Old branch, main moved on" is not a
safe default: an old branch can carry a reversal of a decision made after it.

---

**Original document follows, unchanged apart from this header.**

Prepared 2026-08-26. Every factual claim was re-verified against the code, the tracker or the hosts
before being written; where the check disagreed with the record, the record is corrected in place and
marked. Two of these four decisions changed shape during that checking, which is the point of doing it.

Companion documents: `2026-08-25-mechanical-bulk-boundary-decision.md` (decision 2's full analysis),
`2026-08-26-build-from-spec-probe.md` (decision 2's measurement).

---

## Decision 1 — Accept `agentops#2046`?

### Background

Six acceptance criteria, all met and wired, verified at file and line:

| Criterion | Where |
|---|---|
| `context_churn` enforced | `hybrid_dispatch.py:1757` |
| Receipts expose churn metrics | `:1827` + `churn_metrics.py` |
| Registered-command execution proven in-worker | `:2418`, `:2426`, `:2469` |
| Gate stratification | `:2095` + `gate_tiers.py` |
| Defect-seeded acceptance cases | `:1492`, `:1509` |
| Corpus comparison attached to `#2017` | refs #707/#708 |

The manifest sets `acceptance_authority: human`, so no machine can close it. There is **no open design
question** — this is a signature, not a deliberation.

Two facts make it less trivial than that sounds:

1. **`#2046` blocks `#2017`.** Accepting it unblocks the qualification item.
2. **Criterion 6 was met, and its finding is negative.** The corpus comparison exists and says *do not
   admit the pair yet*. Accepting `#2046` therefore means accepting a criterion whose answer was
   "not yet" — which is the correct outcome, and should be knowing rather than incidental.

### The thing worth seeing before signing

`#2017`'s own text demands more than receipt coverage: *"measure preparation time, runtime and cost,
deterministic pass rate, correction and review effort, acceptance rate, and human minutes per accepted
patch **against the coordinator-only baseline**"*.

The corpus has **no control arm** — its §5 says so explicitly. So unblocking `#2017` reveals a gap that
no amount of further worker rows will close: nothing currently produces a frontier-only comparison.
That is not a reason to withhold acceptance of `#2046`; it is a reason not to expect `#2017` to fall
out shortly after.

### Options

| | Implication |
|---|---|
| **A. Accept plainly** | `#2017` unblocks. Risk: a later reader sees "criteria met, item accepted" and reads it as the pair having been qualified. Nothing in the item record contradicts that. |
| **B. Accept, attaching criterion 6's negative finding as an event** | Same unblocking, but the record carries "accepted; the corpus comparison says do not admit". Costs one `sprintctl event` call. |
| **C. Hold until the corpus re-measures** | Keeps `#2017` blocked. **Buys nothing**: the engineering is finished, so the item accrues no further evidence by staying open — waiting produces no new information about `#2046` itself. |

### Recommendation — **B**

The work is done and holding it teaches nothing, so the only real question is whether acceptance can
later be misread as admission. One attached finding removes that permanently for the cost of a
sentence. **C is the weakest option**: it conflates "this item is finished" with "the conclusion this
item reached is favourable", which is exactly the conflation the corpus document exists to prevent.

---

## Decision 2 — `#2100`: are route and authority one axis, or two?

### Background

`mechanical_bulk` is simultaneously a **route** (who executes: which model, which agent, under which
mode, permitted in which repositories) and an **action class** (whether a green gate may mint a
`candidate` with no human review record). They are the same string in one dict lookup:
`self_candidate_class()` is `classes.get(packet["route"])` (`hybrid_dispatch.py:2119`).

The collision is **enforced, not incidental**. `validate_hybrid_dispatch.py:182` raises if a
`self_candidate` class is not also a worker route — so renaming the class alone is impossible. That
kills the obvious repair before it starts.

Four of the five owner calls in the decision document collapse once the first is answered. **The real
question is call 1**, and nothing technical decides it.

### What changed since the decision document

It recommended **Option C** and named its own falsifiers. The cheap test it prescribed has now been run
(`2026-08-26-build-from-spec-probe.md`):

- **Falsifier 2 is answered NO.** A `build_from_spec` task needs no different model, agent or attempt
  budget — because **four have already run** on the existing binding. V6-E, V6-F, V6-G and V6-H each
  had a sole writable path that did not exist at its `starting_commit`, against an oracle red precisely
  because it was absent. For the whole V6 tract, building from spec is the *only* thing the route did.
- **`#2100`'s premise is stale, and not marginally.** It asks for an explicit expected-failure receipt.
  `oracle.starts_red` is not a flag but a list of command ids that `check_oracle_attainable`
  (`:1165`) **executes** at the starting commit, rejecting exit 127 because a missing oracle is not a
  failing one. That is an *executed proof*, stronger than what the item requests. 38 of 38 packets pass it.
- **A second route costs more than first stated.** Correcting the probe after review: a route needs a
  `model-routing.json` entry with `mode: supervised_hybrid` **and** a per-repo `hybrid.worker_routes`
  allowlist edit in each repository meant to use it — seven opt into `mechanical_bulk` today.
- **`risk` and `task_class` are not free either.** `validate_packet` *requires* `mechanical_implementation`
  and `low` (`:224-227`). So "new behaviour is riskier" is **not expressible at any price today**,
  whichever option is chosen.

### Options

| | Implication |
|---|---|
| **A. Rename the action class only** | **Blocked** by `validate_hybrid_dispatch.py:182`. Recorded so it is not re-proposed. |
| **B. Rename the route, class in lockstep** | Touches both schema enums, the policy, the agent name, 38 packets, 7 manifests, 15 test files. Editing `route` in a frozen packet **moves `packet_hash`**, so every receipt's `execution_id` de-links — the exact breakage just repaired across the corpus. **Pays no debt**: the welding survives the rename. Strictly worse than doing nothing. |
| **C. Optional `action_class` on the packet, falling back to `route`** | One agentops-only hand-pass. The fallback is what makes it free for history: no packet edited, no `packet_hash` moved, no receipt de-linked, and the six external repos stay bit-identical. |
| **D. Keep the collision, document it, close `#2100` as substantially delivered** | Zero migration. Cost: the next route added silently inherits whatever `action_classes[<that name>]` says — nothing (fail-safe), or a copy-pasted `self_candidate: true` (not). |

### What the measurement changed

C's case rested on route and class being **about to fork**, with the concrete danger that adding
`build_from_spec` as a route would tempt copy-pasting an `action_classes` block carrying
`self_candidate: true`. The probe says **no second route is coming**, and the corrected cost says
minting one is expensive. So C's own third falsifier — *"six months on, every packet's `action_class`
still equals its `route`; the decoupling bought nothing"* — would apply **on day one**, for all 38
packets.

**That points at D where the document pointed at C.** The measurement did not decide the question; it
removed the urgency argument. Neither option is racing a forthcoming route any more.

### Recommendation — **the owner's call, on one principle**

This is genuinely a values question, not a calculation:

- If **route and authority are one axis by design** — an execution binding legitimately carries its own
  review posture — then **D**, and this analysis is the evidence for closing `#2100`.
- If **authority to skip human review should never be inherited from an execution binding**, whatever
  the roadmap says, then **C**, and it is cheap: one hand-pass, nothing historical disturbed. Under C
  the grant requires writing a fresh `self_candidate_ruling` — an act, not an inheritance.

My reading: the evidence now favours **D**, and the honest reason to prefer C anyway is a principle
about inherited authority, not a prediction about routes. Either is defensible; only B is not.

**Also decide (call 4):** `#2100` is rescoped or closed. Its premise is contradicted by four dispatched
rows. Rescoping a p2 item is a scope change, not a formality.

---

## Decision 3 — devbox's `/projects/dev/agentops` checkout

### Background — the recorded debt is materially wrong, re-measured today

Debt entry 9 says: *179 commits behind, 23 files genuinely diverged from both its HEAD and origin/main
including `hybrid_dispatch.py` and six `SKILL.md` files, plus two stashes. That is uncommitted work, not
stale copies.* On that description this is a salvage operation.

**Measured on devbox 2026-08-26:**

| Claim in the debt entry | Actually |
|---|---|
| 179 commits behind | **29 behind** |
| 23 files genuinely diverged | **0 dirty files** — the working tree is clean |
| uncommitted work, not stale copies | **HEAD is a pure ancestor of `origin/main`** — no unique local commits |
| "the hook symlinks point into it" | **No symlink anywhere under `~/.claude` resolves into that path, and no `settings.json` hook references it** |
| two stashes | **confirmed — the only thing actually at stake** |

So this is not a salvage operation. It is a stale-but-clean checkout that nothing points at, plus two
stashes. `/tmp/v5-coordinator` — the workspace the dispatch path actually uses — is at `7571077` and
unaffected either way.

The two stashes:

- `stash@{0}` — `codex-project-sync-20260811`, one file, `.agents/environment.generated.md`, 5 lines
  changed. A **generated** file.
- `stash@{1}` — `pre-merged-agentops-sync-20260802`, 21 files. Its substantive content is test files;
  `origin/main` has since moved **132 insertions ahead** of it in `test_materialize_project.py` alone.
  The name says "pre-merged".

### Options

| | Implication |
|---|---|
| **A. Fast-forward, keep both stashes** | Two minutes. Checkout current. Stashes persist indefinitely and will be re-litigated by the next person who runs `git stash list`. |
| **B. Fast-forward; inspect each stash, then drop or land it** | Perhaps twenty minutes. Ends the entry for good. `stash@{0}` is a generated file — regenerating it is the correct disposal, not applying it. `stash@{1}` needs one look at whether anything in it is *not* already in main. |
| **C. Leave it alone** | Free. But the debt entry stays open on a description that is now wrong, and the next reader re-does today's measurement to discover there was never much there. |

### Recommendation — **B**

The reason this sat open was the belief that it held 23 files of unique uncommitted work. It does not,
and it no longer blocks on an ownership question — nobody's work is at risk in a clean tree with no
unique commits. What remains is two stashes and twenty minutes.

**Correct the debt entry regardless of the option chosen.** An entry that overstates its own risk is
worse than a closed one: it is what kept this deferred for a month.

---

## Decision 4 — should `format: "uuid"` start biting?

### Background

V6-I made `format` assertable: `schema_check` gained `FORMAT_CHECKERS` and `validate` gained an opt-in
`assert_formats` set. The default is unchanged, deliberately — `validate` is on the live dispatch path
and every manifest is checked with it, so assertion had to be something a caller *asks for*, never
something arriving with an upgrade.

The residual: `manifest.schema.json`'s `"format": "uuid"` on `authority_repo_uuid` is now **checkable
but unasserted**. The checker will certify a non-UUID.

### What it would cost — measured across all 18 manifests today

| | |
|---|---|
| Manifests carrying `authority_repo_uuid` | **8 of 18** |
| Of those, valid UUIDs | **8 of 8** |
| Is the field required by the schema? | **No** — not in `required` |

**Turning assertion on for `validate_hybrid_dispatch` breaks nothing today.** Zero manifests fail. The
decision is therefore not about migration cost; it is about what future manifests must satisfy.

### Options

| | Implication |
|---|---|
| **A. Assert `uuid` in `validate_hybrid_dispatch`** | Zero manifests break. A future manifest with a malformed `authority_repo_uuid` fails at validate rather than being certified. Does not force the field's presence. |
| **B. Assert *and* make the field required** | The 10 manifests without it must acquire one. A genuine migration, and a bigger claim: that every hybrid-eligible repo must carry an authority identity. |
| **C. Leave it annotation-only** | Free. The constraint stays decorative, and `schema_check` continues to certify a value the schema visibly constrains — which is the "certifying what was never checked" defect V6-I was written to end, left standing in the one place it was found. |

### Recommendation — **A**

It costs nothing measurable, and it closes the exact hole that motivated V6-I in the first place. **C is
the option to argue against**: keeping a `format` in the schema that nothing enforces is a claim the
repository makes and does not keep. If the constraint was never meant to bite, the honest move is to
delete it from the schema — not to leave it as decoration.

B is a separate and larger question about authority identity across repositories, and should not ride
along on a format decision.

---

## Summary

| # | Decision | Recommended | Really gated on |
|---|---|---|---|
| 1 | Accept `#2046` | **B** — accept, attach criterion 6's negative finding | A signature, plus one guard against future misreading |
| 2 | `#2100` route vs authority | **D** on the evidence; **C** if inherited authority is unacceptable in principle | One values question |
| 3 | devbox checkout | **B** — fast-forward, resolve two stashes, correct the entry | Nothing, once the entry is corrected |
| 4 | `format: "uuid"` | **A** — assert it | What future manifests must satisfy |

Only decision 2 is genuinely a judgement call. Decisions 1, 3 and 4 read as gated because the records
describing them were stale or incomplete; re-measuring each one shrank it.
