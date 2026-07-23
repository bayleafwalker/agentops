# Output 8 — Timed Resume Observations (Gate 4)

Protocol per `Vuoro-Pre-Clean-Room-Assessment-Plan.md:114` and
`README.md:114`. Five observations required to complete Gate 4 and unblock
spec freeze; at least one must be a multi-agent resume and one must follow
a meaningful idle gap. These double as Lane B's (Vuoro baseline) S-RESUME
leg in the Clean-Room Comparison Plan.

Recorded live, in the session performing the resume, immediately after
reaching the first confident next action (a safe pause: a dispatched build
agent was running async, nothing else in flight). Not reconstructed after
the fact.

---

## Observation 1 — 2026-07-23

| Field | Value |
|---|---|
| Repo | sprintctl (item #1195); vuoro and agentops cross-checked, not the resumed work itself |
| Idle duration | **3h30m**, tracker-timestamped: prior session's handover event (#1384) at 07:05:58Z → this session's claim re-acquisition (claim #156) at 10:35:34Z. Session-start wall clock is not independently instrumented, so this is a tracker-to-tracker gap, not a true first-token timestamp. |
| Session shape | **Delegated** — solo verification/orchestration, then one sequential build-worker dispatch (Build A3). Not multi-agent: no concurrent agents were active at once. **This observation does not satisfy the gate's multi-agent requirement**; a separate observation into an active multi-agent batch is still needed. |
| Resume surface used | (1) An inline handoff message pasted at session start, structured like a session-note but not a file — see finding below. (2) `sprintctl item show --id 1195 --json`, specifically events #1359 (design brief), #1382/#1383 (Build A2 dispatch+verify), #1384 (session-end handover). (3) Claim re-acquisition (`sprintctl claim start --item-id 1195`). (4) `git log`/`git status` across all three repos, run *before* trusting the handoff text, as independent corroboration. (5) Claude's own auto-memory file (`project_vuoro_served_backend_1195.md`) — not a Vuoro/sprintctl surface at all, a parallel out-of-band system that supplied repo roles and a key finding independently of the tracker. (6) Direct source reading (`cli.py`, `served.py`, `authority.py`, `db.py`, `vuoro_adapter.py`) — required because the tracker text described the next unit of work narratively ("two transient bindings") but did not encode the exact schema/field contract; that had to be derived from `authority.py::_handle_claim_mutation` directly. |
| Time / effort to first confident, evidence-backed next action | No reliable wall-clock (see idle-duration caveat). Proxy: **~17-18 tool-call rounds** (~35-40 individual tool invocations) from session start to dispatching Build A3, split roughly: verification of the handoff against tracker + all three repos' git logs (~9 rounds), reading the design brief and prior events in full (~3 rounds), reading source code to derive the exact technical contract for the next unit (~5 rounds), claiming + extending TTL + dispatch (~2 rounds). The tracker/handoff text alone was NOT sufficient to reach a confident implementation-level plan — roughly half the effort was source-code archaeology the tracker did not obviate. |
| Conflicts / blockers surfaced | None. Claim #156 was cleanly released by the prior session (confirmed in event #1384's own text) and re-acquired without contention. No stale or competing claims found. |
| Other sources consulted (non-Vuoro) | Claude's own persistent auto-memory (a system entirely outside Vuoro/sprintctl); direct source-code reading in the sprintctl repo; `git log` in all three repos as a trust-but-verify step against the pasted handoff text. |
| Ambiguity remaining after resume | Two scope decisions were explicitly *not* resolved by the tracker and had to be made fresh this session (documented in the dispatch brief and logged as event #1386): (1) whether `--allow-legacy-adopt` is supported in served mode, (2) the served bundle's `item`/`sprint` field shape given no single-sprint served read op exists. Neither the handoff text nor the design brief (#1359) resolved these; they were genuine open judgment calls, correctly left open rather than silently guessed by the prior sessions. |
| H9 — did an authored note change/accelerate the next action? | **Partially, but with an important scope caveat.** The accelerant here was an ordinary tracker **event payload** (event #1384, a `session-end handover` event type), not the session-note/v1 mechanism H9 is specifically scoped to test. Classification against H9's five options: closest to **(2) the note materially improved the next-action decision** — it named the exact next unit ("Build A3 — served claim handoff, two transient bindings") which made the source-reading phase targeted (confirm *why* two bindings are needed) rather than open-ended (rediscover the whole 7-route backlog from #1359 alone). But this is evidence about handover-event-payload value, not session-note/v1 value — **do not credit this observation to H9's specific gate** without noting that distinction. |

### Finding: the referenced handoff bundle file does not exist on disk

The inline handoff text referenced a written artifact ("a fresh handoff
bundle (handoff-407.json) is written"). A filesystem-wide search
(`find / -iname "handoff-407.json"`) found nothing. Everything actually
useful for the resume was recoverable from the tracker's **event log**
(event #1384 in particular), which was richer and independently
verifiable (timestamps, actor, cross-checked against real git commits) in
a way the pasted narrative text was not. This is a direct data point for
the assessment: the consequential resume surface in this observation was
the event log, not a separate handoff-bundle file — the bundle claim
should be treated with the same "verify, don't trust" posture applied to
any other resume input, and its absence did not block the resume at all.

### Gate 4 status after this observation

**1 of 5 recorded.** Still needed: at least one true multi-agent-batch
resume, at least one solo resume, and enough additional observations to
reach five, per the gate's "five same-day solo resumptions do not
satisfy it" rule (this one is not same-day solo either way, but the
multi-agent requirement remains open).

---

### Cross-reference: a concurrent session audited the same event retrospectively, and disagreed with itself on timing

While writing this, `git log` on this repo surfaced two commits
(`77f1253`, `8628803`, both 2026-07-23 13:39–13:41, same git author as this
session) made by a **different, concurrently running session** editing
`06-reduced-workflow-specification.md` and `07-open-hypotheses.md` — neither
of which I had open or was told about. Neither session held any claim or
lock on these docs files while editing; the two working trees happened not
to touch overlapping lines, but nothing prevented that. Worth recording
plainly: **the docs corpus this very assessment lives in has zero R2-style
conflict protection**, unlike the sprintctl code this session was
simultaneously careful to serialize around (see this session's Build A3
work: builds were deliberately sequenced, never run concurrently, on
shared non-worktree files). That asymmetry — code protected, docs not — is
itself a small data point for the R2 litmus test applied reflexively to
this project's own working process.

More importantly, that session's retrospective table (`06`, "Five cold-resume
observations") lists as its **row 4**: *"sprintctl #1195 end-of-day handoff
into next-session continuation... Deterministic next action produced...
`<5 min` assisted; `15–60 min` counterfactual reconstruction"* — sourced
from `02-workflow-economics.md`'s analytical counterfactual writeup.

**That is the same event as this document's Observation 1.** The
2026-07-22 EOD handoff for #1195 that row 4 describes retrospectively and
analytically is the exact handoff this session resumed from live, this
morning, in real time.

The two accounts disagree substantially:

| | Row 4 (retrospective/analytical) | Observation 1 (live, this doc) |
|---|---|---|
| Assisted resume time | `<5 min` | No wall-clock (uninstrumented), but ~17-18 tool-call rounds, roughly half spent on source-code archaeology the handoff text did not obviate |
| Characterization | "Deterministic next action produced" | Handoff text alone was **not** sufficient for a confident implementation-level plan; required reading 5 source files (`cli.py`, `served.py`, `authority.py`, `db.py`, `vuoro_adapter.py`) beyond anything the bundle or tracker text encoded |
| Bundle claim | Not scrutinized | The specific bundle file the handoff text referenced (`handoff-407.json`) does not exist on disk — see finding above |

This is a direct, first-hand illustration of exactly the risk Gate 4's own
protocol distinguishes: analytical/retrospective counterfactual estimates
("12 documented resumption incidents + analytical counterfactuals," the
category Gate 4 was already marked insufficient on) can read as faster and
cleaner than a genuinely live, protocol-complete measurement of the *same*
event. Do not average or reconcile the two numbers into one — record both,
flag the disagreement, and let it stand as exactly the kind of discrepancy
the five-observation gate exists to catch. Neither this session nor the
concurrent one should silently pick whichever number is more flattering to
Vuoro.

**Recommendation for whoever reconciles Gate 4 next:** row 4 in `06` should
be re-labeled to make clear its timing is analytical/retrospective, not a
protocol-complete live observation, and should cross-link to this document
rather than stand as an independent data point — counting it separately
from Observation 1 would double-count one real event as two samples.

---

## Observation 2 — 2026-07-23

### Pre-pause half, recorded 2026-07-23T12:38:26Z

This is the *before-pausing* half of the protocol, recorded by the prior
session before it paused.

**Repository, branch/worktree, task/item:**
- sprintctl, `main`, no worktree (all work landed directly on the shared
  checkout, deliberately sequenced rather than parallelized across
  worktrees — see the concurrent-edit correction below). Item #1195
  (status `done`, closed 2026-07-23T11:32:22Z) plus its two spun-out
  siblings, #1211 and #1212 (both `done`).
- appservice, `main`, no worktree. One unrelated fix (a malformed RBAC
  manifest), unclaimed — appservice isn't sprintctl-claim-tracked at all,
  so there was no claim to release there.
- agentops, `main`, no worktree. This assessment's own docs, plus a memory
  update (see below). Not sprintctl-claim-tracked either.
- vuoro: touched only earlier in the day (invocation/v2 transport, already
  captured in the prior handover); untouched this segment.

**Timestamp and session shape:** 2026-07-23T12:38:26Z. This session's shape
was **not static** — it started **delegated** (one build agent, A3), then
became genuinely **multi-agent** at two points: #1211's build ran
concurrently with Group C's decision-scoping brief, and later Group C's
build ran concurrently with a CI-fix agent (up to 3 background agents
alive at once at the peak). Recording the shape as a single label for the
whole session would understate this — if a future protocol run wants a
"multi-agent session" sample, this session qualifies for the *later*
portion of itself, not uniformly throughout.

**What state is intentionally left in Git/Vuoro:** everything committed
and pushed, working trees clean in sprintctl/appservice/vuoro. No active
sprintctl claims held by this session on #1195/#1211/#1212 (all released
via `item done-from-claim`). agentops has one untracked file
(`docs/plans/evidence-needed.md`) belonging to the *other* concurrent
session (see the earlier collision finding above) — deliberately left
untouched, not this session's to commit or discard. Real CI verified green
on sprintctl (run 30003277273) before considering any of this settled —
not just locally-green tests.

**Whether a handoff bundle or authored note exists:** no file-based
handoff bundle was written for this pause, consistent with this session's
earlier finding that the *previous* handoff's own referenced bundle
(`handoff-407.json`) didn't exist on disk either — this looks like a
pattern, not a one-off. What *does* exist: a complete tracker event trail
on #1195 (events #1382 through #1397 — dispatch, verification, and
correction events for every build in this segment, including two
independent-review-caught bugs and the CI-breakage discovery), and two
persistent-memory updates in this session's own memory store
(`project_vuoro_served_backend_1195.md`, now marked complete;
`feedback_verify_real_ci_not_just_local_pytest.md`, new). Whether a *future*
resuming session finds the tracker event trail sufficient without a
separate authored note — or gets tripped up by the same absence this
session flagged for the prior handoff — is exactly the H9-relevant data
point the eventual resume-side observation should capture.

### Resume half, recorded live 2026-07-23

A fresh Claude session, no prior transcript, invoked by the operator with
an explicit instruction to record the resume-protocol fields. This is the
resume-side counterpart to the pre-pause state above, and also the direct
continuation of item #1216 (this assessment's own gate-completion item).

| Field | Value |
|---|---|
| Repo | agentops (docs/tracker only); sprintctl, appservice, vuoro cross-checked via `git log`, not modified |
| Idle duration | **4h22m05s**, wall-clock and tracker-timestamped this time: prior session's pre-pause note at 2026-07-23T12:38:26Z (commit `739116a` landed 2026-07-23T12:39:21Z) → this session's first action at 2026-07-23T17:00:31Z. Unlike Observation 1, both endpoints are real timestamps, not a tracker-event proxy. |
| Session shape | **Solo** — no sub-agent dispatched, no delegation, single continuous investigation. This satisfies the gate's outstanding "at least one solo resume" requirement (README.md:105 flagged this as still needed after Observation 1, which was delegated). |
| Resume surface used | In actual order: (1) `date` for a start timestamp; (2) `git status` + `git log --oneline -10` in agentops — surfaced the untracked `docs/plans/evidence-needed.md` and confirmed HEAD matched the pre-pause note's commit; (3) `sprintctl sprint list` — found active sprint #428 ("Vuoro Clean-Room Comparison — Foundation"); (4) `sprintctl item list --sprint-id 428` — found item #1216, status `blocked`, p1, unclaimed, title matching this exact task; (5) `sprintctl item show --id 1216 --json` — full description, prior codex-spark dispatch events #1387/#1388, zero active claims; (6) `git log -1` on commit `739116a` to get an exact timestamp for idle-gap arithmetic; (7) cross-repo `git log` in sprintctl and appservice for corroboration (found unrelated served-authority and infra-chore commits — no direct bearing on #1216); (8) read of `06-reduced-workflow-specification.md`'s status block — confirmed freeze-blocker text unchanged; (9) `sprintctl claim start --item-id 1216` — claimed the item, which auto-transitioned it `blocked` → `active`. |
| Time / effort to first confident, evidence-backed next action | **~2m05s wall-clock** (17:00:31Z start → 17:02:36Z claim acquired), across ~9 tool-call rounds (~15 individual invocations). Substantially faster than Observation 1's ~17-18 rounds — no source-code archaeology was needed here, because the task itself *is* the tracker/observation-recording work, not an implementation whose contract lived only in source. This is the first observation in the sample with a genuinely instrumented (not proxied) wall-clock reading. |
| Conflicts / blockers surfaced | None — item #1216 had zero active claims; claim #159 was acquired cleanly. Note a terminology wrinkle worth flagging: the item's `blocked` status here means "evidence-gate blocked" (waiting on more observations), not "claim-contended" — a reader skimming `sprintctl item list` status alone could conflate the two; only `item show` disambiguates. |
| Other sources consulted (non-Vuoro) | The untracked `docs/plans/evidence-needed.md` note (see H9 below); no source-code reading was required this time. |
| Ambiguity remaining after resume | Whether recording this as a same-calendar-day second observation is legitimate under the gate's "five same-day solo resumptions do not satisfy it" rule — resolved here as legitimate: this observation is not same-day *solo-only* in aggregate (Observation 1 was delegated), and it crosses a genuine multi-hour idle gap rather than being an uninterrupted continuation. Flagging explicitly for whoever reconciles the gate next, per the same discipline Observation 1 applied to its own cross-reference finding. |
| H9 — did an authored note change/accelerate the next action? | **No, and this is a cleaner negative data point than Observation 1's.** The untracked note (`docs/plans/evidence-needed.md`) restates the same protocol fields, but it added no information beyond what was already available from three independent sources: the operator's own dispatch instruction (which pasted the identical field list), item #1216's tracker description (a detailed, item-specific scope statement), and `README.md`/`Plan.md` at the cited line numbers. My actual navigation to the next action did not route through the note at all — it came from `sprintctl sprint list` → `item list` → `item show`, i.e., straight from the tracker. Classify as: the note was redundant with tracker-native state, not accelerating. Contrast with Observation 1, where the tracker's own handoff-event payload (not a standalone note file) *did* materially narrow the task. Two observations in, the pattern favors tracker-native event/item data over standalone authored note files as the higher-value resume surface. |

### Gate 4 status after this observation

**2 of 5 recorded** — one delegated (Observation 1), one solo (this one).
Still needed: at least one true multi-agent-batch resume, and enough
additional observations (any shape) to reach five. The solo requirement
flagged as outstanding in Observation 1's write-up is now satisfied.

---

## Pre-pause state, 2026-07-23T17:04:44Z (prep for a future Observation 3)

This is the *before-pausing* half only. Item #1216 was claimed (claim
#159), an evidence note (#1398) was recorded, the claim was released, and
status was explicitly set back to `blocked` — no claim is currently held.
Do not count this section as a third observation on its own.

**Repository, branch/worktree, task/item:** agentops, `main`, no worktree.
Item #1216 (status `blocked`, unclaimed, 2 of 5 sub-observations done).
No other repo's runtime/deployment state was touched this session.

**Timestamp and session shape:** 2026-07-23T17:04:44Z. This session was
uniformly **solo** — no sub-agent dispatched at any point.

**What state is intentionally left in Git/Vuoro:** commit `d7a17c9`
pushed-eligible (not yet pushed — same as prior sessions in this thread,
confirm push policy before assuming remote is current). Working tree
clean except `docs/plans/evidence-needed.md`, still untracked and still
not this session's to commit or discard (it predates this session and
its ownership remains unresolved — flagging again since it has now
survived two consecutive sessions untouched). Item #1216 explicitly
`blocked`, no active claims.

**Whether a handoff bundle or authored note exists:** no new authored
note was written beyond this document itself and note #1398 on the item.
The standing untracked note (`docs/plans/evidence-needed.md`) still
exists and, per this observation's H9 finding, was redundant with
tracker-native state — a future resuming session re-encountering it is
itself a small additional H9 data point worth recording if it recurs.

**What a future Observation 3 should prioritize:** the multi-agent-batch
resume is now the sole remaining shape gap. That cannot be manufactured
by claiming #1216 alone — it requires resuming into an actually-running
multi-agent batch (as Observation 1's pre-pause note for #1195 briefly
was, mid-session). The next genuine opportunity is whatever real
multi-agent dispatch next occurs in this or another repo; do not dispatch
throwaway concurrent agents solely to check this box, per the plan's
"do not artificially exercise unused features merely to generate data"
principle (Vuoro-Pre-Clean-Room-Assessment-Plan.md:147).
