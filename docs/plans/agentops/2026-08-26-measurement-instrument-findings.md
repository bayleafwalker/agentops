# The measurement instrument — five findings, one owner decision

Prepared 2026-08-26, after a session-1 pass that was asked to "root-cause the hook, register it on
devbox, and backfill the frontier half from transcripts."

Written to the standard set by `2026-08-26-open-owner-decisions.md`: every factual claim below was
re-verified against the hosts, the transcripts or the code before being written. Where the check
disagreed with the record — including with the brief that commissioned this pass — the record is
corrected here and marked. **Three claims changed shape during checking, and one reversed.**

Companion documents: `2026-08-25-l6-d9-restate-pilot-design.md` §2b (the number this corrects),
`docs/dispatch/handover-2026-08-23-metanarrative-v5.md` §5–§7 (the measurement contract),
`docs/dispatch/workflow-topology.md` ("Measure The Shape").

---

## Outcomes

| # | Finding | Status | Classification |
|---|---|---|---|
| A | `turns` does not count what §2b says it counts — D-9's baseline is inflated ≈3.2× | **Measured, unfixed** | derivable — needs a packet |
| B | The T-series ratio's numerator and denominator span different windows | **Measured, unfixed** | derivable — arithmetic |
| C | Cost coverage is host- and directory-coupled; execution placement is not | **Fixed (workstation + devbox)** | ratification |
| D | Sessions spanning a resume stop recording at the dormancy point | **Measured, unfixed** | derivable — needs a repro |
| E | Subagent spend is never counted, in a loop whose design is subagent-heavy | **Measured, unscoped** | **the one owner decision** |

**What was already done during the pass:** the sink was backfilled (169 corrected snapshots, sink
887 → 1056 lines, backup retained); devbox's Stop hook was registered and its stale 13 May hook
copy replaced with the canonical symlink; a global `hooks.Stop` was added to
`~/.claude/settings.json`. `cost-summary.sh` and `test-cost-hook-fields.sh` both pass against the
enlarged sink.

---

## Correction to the brief that commissioned this pass

The pass was commissioned on the claim that **"the measurement instrument went dark on
2026-08-24"** and that the scorecard's frontier block is **"half a session mislabelled as a whole
one."**

Both are wrong, and the second is wrong in a way that matters more than the first.

| Claim | Actually |
|---|---|
| The instrument went dark | **The hook has never failed.** Run by hand against a saved Stop payload for session `3ebf37bd`: exit 0, sub-second, correct row, empty stderr. It fired 30 times on 2026-08-26. `async: true` was concealing nothing. |
| devbox never had the hook registered | **True, and now fixed** — but irrelevant to the missing data. devbox has had **zero transcripts since 12 August**; no V6 work ran there. |
| The frontier block is a mid-session snapshot mislabelled as a whole session | **The block is correctly scoped.** Its 16 turns / 606 assistant messages / $268.55 exactly match the session's state at 2026-08-24T20:02:32Z, which is the window in which the T-series was worked. It never claimed to be the session total. |

The last row of the transcript-vs-sink diff is real — the session ran on to 2026-08-25T17:47 and
reached 31 hook-turns and $713.69 — but **that is a fact about the session, not an error in the
scorecard.** Reporting it as "the recorded figure is 38% of the truth," as this pass initially did,
repeats §3h's *units* error in a new costume: it compares a scoped measurement against an unscoped
one and calls the difference an understatement.

The scorecard's actual defects are A and B below, and neither was visible from the sink.

---

## Finding A — `turns` does not count human prompts

### Background

`2026-08-25-l6-d9-restate-pilot-design.md` §2b is explicit about what the number means:

> `log-session-cost.sh:115` computes `turns` as the number of `user` rows carrying no `tool_result`
> content — i.e. **human prompts into the session** … So the v5 T-series consumed **16
> owner/coordinator prompts to land 11 packets**, ≈1.45 prompts per packet.

The whole v7 falsifier rests on this: *"frontier turns per release drop ≥ 5× vs v5 scorecard"*, a
5× drop from 16 being ≤ 3.2 prompts.

### Measured — the 16 turns, enumerated

The predicate admits any `user` row without `tool_result` content. In the T-series window those 16
rows are:

| Kind | Count | Example |
|---|---|---|
| **Genuine human prompts** | **5** | *"No need to stop, you can continue. Also sessions are usage, not actual API cost."* |
| `<task-notification>` — background **subagent completions**, harness-injected | **9** | `<task-notification><task-id>a7a2092b…` |
| Slash-command plumbing (`/clear`, `/compact`, `<local-command-stdout>`) | **1** | `<command-name>/clear</command-name>` |
| `[Request interrupted by user]` marker | **1** | — |

Across the full session: 31 hook-turns, **15** human. The contamination is not incidental and not
specific to this session — `c128df61` records 31 hook-turns of which **11** are human and **20**
are task notifications.

### What it does to D-9

**[CORRECTED 2026-08-26, second pass]** — the first version of this table read:

| | turns | / 11 packets | 5× drop target |
|---|---|---|---|
| As recorded | 16 | 1.45 | ≤ 3.2 prompts |
| Human prompts only | 5 | ~~0.45~~ | ~~≤ 1 prompt~~ |

**That 0.45 was wrong, and wrong in exactly the way Finding B names.** The `5` is scoped to the
T-series window; the `11` includes T-11, which landed on 2026-08-25, outside it. Dividing a
window-scoped numerator by an unscoped denominator is Finding B's defect, committed inside Finding
A's headline. The two internally consistent readings are:

| Window | turns | human | packets | human/packet | 5× target |
|---|---|---|---|---|---|
| Truncated at 2026-08-24T20:02:32Z | 16 | 5 | **10** | 0.50 | ≤ 0.10 |
| Whole release, to T-11's close | **31** | **15** | 11 | **1.36** | **≤ 0.27** |

They differ by 2.7×, and the published 0.45 was neither. Use **1.36** — pinning the window to the
release's actual span keeps the denominator honest, because T-11 is part of the T-series by §3i.

The finding itself survives, and its direction is unchanged: the recorded 1.45 counts the loop
notifying itself, so the baseline is inflated and the falsifier correspondingly easy to pass. But
the *size* of the inflation is ≈1.07× against the correctly-scoped human figure, not 3.2×. Had the
0.45 shipped, a v7 challenger would have been graded against ≤0.09 prompts per packet — about one
human prompt per eleven packets — making the falsifier unfalsifiable in the opposite direction.

**The sharpest form of it:** the metric counts a subagent *finishing* as a human prompt (Finding A)
while counting none of that subagent's *tokens* as spend (Finding E). It is wrong in both
directions at once, and the two errors push the "frontier cost per packet" ratio the same way —
down.

### Recommendation

A packet against `log-session-cost.sh` adding `human_turns` alongside `turns` — additive, one
writable file, an attainable red oracle, and squarely within Rule 9's "cheap-tier packets are
additive." Keep `turns` as-is so old rows still parse (T-1 precedent). Then restate §2b and D-9
against `human_turns`, and mark the v5 baseline **superseded, not wrong** — it measured something
real, just not what it was labelled.

---

## Finding B — the ratio spans two windows

### Measured

**[CORRECTED 2026-08-26, second pass — the mechanism below was wrong as first written.]** This
finding originally said the numerator "ends at 2026-08-24T20:02:32Z". It does not. The scorecard's
own scope block reads:

```json
{"project": "agentops", "since": "2026-08-24T18:00:00Z", "until": null}
```

**`until` is `null` — the window has no right edge at all.** The numerator is not scoped to
20:02:32Z; it is scoped to whenever the sink last happened to be written before the generator ran,
so the scorecard is **not reproducible from its own scope block** and drifts every day. Re-reducing
the sink today over that same scope gives **5 sessions and 56 turns**, against the committed 1 and 16.

The denominator problem is real as stated: 11 packets includes **T-11, which landed on
2026-08-25** — handover §3i, *"T-11 (2026-08-25) — the detector that fired on good news."*

So the defect is worse than a window mismatch: it is an unbounded numerator divided by a fixed
denominator. This is the fifth instance of the §3h pattern, and it sits on the scorecard built by
T-9 specifically so *"a reader never has to tell 'absent' from 'unbounded'."* T-9 made all three
scope keys always present; it did not make anyone fill the third one in. A field that is always
present and always `null` is the same defect as a `format: "uuid"` that never bites.

This is the *scope* error §3h already names — *"an unscoped window overcounting the frontier half
by 56%"* — recurring on the same scorecard that documents it. Arithmetically correct, means the
wrong thing, not catchable by a gate.

### Recommendation

Pin the window; do not shrink the denominator. Re-generate `v5-t-series.generated.json` with an
explicit `--until` at T-11's close (`2026-08-25T18:00:00Z` covers the final snapshot at 17:47:06Z),
keeping `--project agentops --since 2026-08-24T18:00:00Z`. The denominator stays **11**, which is
honest: T-11 is part of the T-series by §3i. Then restate §2b and D-9 against **1.36** human
prompts per packet, with a 5× target of **≤ 0.27**.

Then close the hole rather than the instance: make a scorecard whose `scope.until` is `null` fail
to generate, or force an explicit `"unbounded (deliberate)"` sentinel. A release scorecard
describes a closed release; an open right edge is never what was meant. That is one file, one
outcome, additive, with an attainable red oracle — a `mechanical_bulk` packet, not coordinator work.

---

## Finding C — coverage is coupled to host and directory; execution is not

### Background — and a correction to how this pass first framed it

This pass initially wrote up "devbox is the documented coordinator host but has been idle since
12 August" as a **topology divergence**. The owner's correction, recorded here because it changes
the finding:

> devbox can technically *also* coordinate, implement, etc. Workstation, devbox, separate
> sandboxes, cloud can all be running execution surfaces, depending on contextual desires and
> general requirements.

That is not a divergence, then — it is the intended design, and handover §1's "coordinator on
devbox" is a snapshot of one run's placement, not a constraint. **The defect is in the instrument,
not the placement.**

### Measured

| | |
|---|---|
| Hook registration model | per-project-directory, in each repo's `.claude/settings.local.json` |
| `~/.claude/settings.json` | had **no `hooks` key at all** — no global registration |
| Project dirs under `/projects/dev` registering the Stop hook | **6 of 16** |
| Sessions with transcripts | 179 |
| **Never recorded at all** | **148** |
| Recorded but truncated | 20 |
| Recorded imputed total vs transcript truth | **$5,545 vs $14,433** |

Unregistered dirs include `bindery-core`, `frontier-weave`, `gitops-nixos`, `vuoro`, `vuoro-cloud`
and `_projects/vuoro-dispatch-ready`.

So: measurement was opt-in, per directory, on one machine, while execution placement is
deliberately fluid across four surface types. **Every new surface starts unmeasured by default.**
That is a model mismatch, not a forgotten hook, and it is the whole of the 2.6× gap.

### Done

- `~/.claude/settings.json` — global `hooks.Stop` added (`timeout: 30`, `async: true`). Validated:
  JSON parses, all 29 `additionalDirectories` intact.
- devbox — Stop hook registered via `sync-devbox.sh --apply`; its 13 May hook file (pre-T-1,
  md5 `1a3244af…`) replaced by the canonical symlink (`a0e74e66…`, matching the workstation).
- Sink backfilled from transcripts: 169 corrected final snapshots, appended rather than rewritten,
  exploiting the existing newest-row-per-session reducer. §5's *"max per session, never the sum"*
  is preserved; `cost-summary.sh` renders and `test-cost-hook-fields.sh` passes.

### Still open

Sandboxes and cloud surfaces have no registration path at all. `sync-devbox.sh` handles exactly one
named host. Whatever replaces it should make registration a property of the *surface being
provisioned*, not of each repo checked out onto it.

---

## Finding D — resume truncation

### Measured

| session | true hook-turns | recorded to | true $ | recorded $ |
|---|---|---|---|---|
| `3ebf37bd` | 31 | turn 16 | 713.69 | 268.55 |
| `559557f4` | 91 | turn 14 | 601.29 | 95.50 |
| `c128df61` (single sitting) | 31 | turn 31 | 247.93 | 247.93 |

Both sessions that went dormant on 24 August and resumed at 13:30 on 25 August stopped recording at
the dormancy point despite running 800+ further assistant messages each. The one session that ran
start-to-finish in a single sitting recorded every turn.

**A competing hypothesis was tested and rejected.** Handover §6 warns that the hook symlinks point
into `/projects/dev/agentops` and that checking out a branch there without `templates/dispatch/hooks/`
would break them. The agentops reflog shows no such checkout in the window, and the symlink resolves
correctly today. It does not explain the gap.

### Recommendation

Not yet root-caused — this is the one finding still at hypothesis stage, and it should be labelled
that way rather than carried as fact. The global registration from C now gives a cheap repro: start
a session in a previously-unregistered directory, resume it, and check whether rows continue past
the resume. Until that runs, treat resumed sessions' cost rows as lower bounds.

---

## Finding E — subagent spend is uncounted — **the owner decision**

### Background

`log-session-cost.sh` reads only the main transcript. Subagent transcripts live in
`<session>/subagents/*.jsonl` and are never opened. Their tokens are real metered usage on the same
account.

This is not a rounding error in this programme. The T-series window alone contains **9 subagent
completions in 16 recorded turns** — and Rule 5 makes that structural, not incidental: *"No actor
is the sole attester of its own change. Oracles for code you wrote are written by a fresh author (a
subagent with no access to your implementation)."* **Every packet's oracle is authored by a subagent
by design.** So the loop's own independence guarantee is the thing the cost metric cannot see.

### Why this one is genuinely yours

Findings A–D are defects: the record says X, the machine does Y, and closing the gap needs no new
policy. E is different, because §2a already fixed a *definition* that E would reopen:

> There is deliberately **no key holding their sum** … `test_release_scorecard_kinds.py` exists
> solely to fail if anyone reintroduces one.

`frontier_totals` is a **usage-equivalent** — tokens × a 2025 list-price table, never billed on a
subscription. `worker_totals` is **real metered spend**. Subagent tokens are frontier-side usage,
so folding them into `frontier_totals` is consistent — but it changes what every historical
frontier figure means, and the v5 baseline becomes non-comparable with everything measured after
it. That is a new value choice about what the programme's central metric denotes, and §2a's
guard-test is the record of how expensive getting it wrong has been.

### Options

| | Implication |
|---|---|
| **A. Fold subagent usage into `frontier_totals`** | The number finally matches the loop's actual shape. Every pre-2026-08-26 frontier figure becomes non-comparable; the v5 baseline must be recomputed or retired. Cheapest to implement, most expensive to interpret. |
| **B. Add a sibling `subagent_totals`, leave `frontier_totals` untouched** | Comparability preserved; §2a's no-sum rule extends naturally to a third kind. Anyone quoting "frontier cost" still under-reports unless they read two keys — the exact failure §3h names under *names*. |
| **C. Leave it uncounted, and say so in the scorecard** | Free. The scorecard then carries an explicit "excludes subagent usage" caveat, which is honest but makes D-9 and the v5/v7 comparison rest on a number known to omit the loop's dominant cost. |

### Recommendation — **B**

It is the only option that does not silently restate history, and the two-kinds discipline §2a
already enforces generalises to three without weakening. Pair it with a scorecard field naming the
exclusion, so C's honesty is kept without C's blind spot.

But this is a recommendation, not a ruling: A is defensible if the v5 baseline is being retired
anyway on the back of Finding A, and that is a judgement about the programme's direction rather
than about the code.

---

## What this unblocks

| Item | Was blocked on | Status now |
|---|---|---|
| **Reference-patch mandate** (carried into this pass as "an open owner decision") | *"the economics claim being structural — measurement settles it"* | **Not open, and was not open before this pass.** §7 asked for the cost; the handover's *"The reference-patch cost, which §7 asked for"* answers it — five references, five first-try oracle passes, ≈one coordinator turn each. Rule 10 makes it a state machine (mandatory while the class is off, SHOULD once on) and states the value is *diagnostic, not labour saving*. Carrying it back to the owner was the §-header error repeating: re-deriving from chat what the brief already records. |
| **Debt entry 10** — *"scorecard generated in-session, session hasn't ended yet"* | nothing; the explanation was self-sealing | **Falsified and superseded.** The session did end, and no row was written — but Finding C explains why (coverage), and Finding A shows the scorecard block itself was correctly scoped. Rewrite the entry against C, not as data loss. |
| **`#2017` control arm** | no baseline existed | **Baseline exists** — 179 sessions reduced newest-per-session. Still needs A and B applied before it is quotable. |
| **`agentops#2254`** — two-way control, direct half done, loop half never dispatched | the instrument | **Dispatchable**, once A lands. Take a fresh reservation (§6: no reservation is currently held; actor must match the authenticated profile). |
| **D-9 restatement** | a metric that measured supervision | **Blocked on A**, not on the owner. |

---

## How this pass should have been written

Recording it in the same spirit as the companion document, because the failure repeated one that
was already documented — from earlier the same day.

`2026-08-26-open-owner-decisions.md` opens with the owner's assessment that *"zero to one of the
four required fresh human judgment"* and names the fix: classify each item as **derivable**,
**ratification**, or **new value choice** before writing it up.

This pass produced three items labelled "what's actually yours to decide." On re-measurement:
**global hook registration** was derivable and had already been decided by the goal (a permission
gate was misread as a policy question); **subagent scoping** was reported as unscoped when the
correct action was to go and scope it; **the resume bug** was unfinished diagnosis filed as a
handoff. Of the three, the true count of owner decisions was **zero** — and the one genuine
decision in this document, Finding E, was not among them and surfaced only after reading the
process docs that should have been read first.

Handover §1 says it plainly: *"This document is the whole brief. Read the files it names; do not
re-derive them from chat."* Rule 4 enumerates the owner touchpoints — release boundary, freeze
amendments, admission-policy coordinator-only items, the v5.9 refactor pass — and none of the three
qualified. Both were on disk before the pass started.
