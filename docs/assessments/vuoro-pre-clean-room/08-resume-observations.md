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

---

## Observation 3 — 2026-07-23 (provisional — see validity flags)

A fresh Claude session, no prior transcript, dispatched by the operator
with "Initiate resume (another session is active currently)". Recorded
live per protocol. **Two validity concerns are flagged inline rather than
resolved; whoever reconciles Gate 4 decides whether this counts toward
the five.**

| Field | Value |
|---|---|
| Repo | agentops (docs/tracker only); sprintctl, homelab-analytics, actionq-dispatcher cross-checked via `git log`, not modified |
| Idle duration | **3m37s only** — prior session's pre-pause note at 2026-07-23T17:04:44Z (commit `65cd123`) → this session's first action at 17:08:21Z. This is a near-immediate continuation, not a meaningful idle gap. The gate's idle-gap requirement is already satisfied by Observations 1–2, so this does not damage the sample on that axis, but under the "five uninterrupted same-day solo continuations do not qualify" rule this observation's marginal value is shape/context, not gap. |
| Session shape | **Solo, beginning while other sessions were active.** This session dispatched no sub-agents. The operator attested another session was active at resume time; `pgrep` corroborated multiple concurrent standalone `claude` and `codex` processes beyond IDE servers. **However, the tracker shows zero evidence of a multi-agent batch**: no active claims on any item (checked #1216, #1217), no active items in sprints #428/#421, no dispatch events since 17:04:30Z. Per Observation 1's definition (concurrent *dispatched agents* on real work) and the pre-pause guidance above ("an actually-running multi-agent batch"), concurrent *interactive operator sessions* are a different phenomenon. **This observation does NOT claim to satisfy the multi-agent-batch requirement.** |
| Resume surface used | In order: (1) `date`; (2) the operator's dispatch message (restated gate status: 2 of 5, three remaining, multi-agent condition rules); (3) read of `docs/plans/evidence-needed.md` (the standing untracked note — see H9) and `git show --stat` on commits `4b76e7e`/`d7a17c9`; (4) full read of this document (08), which functioned as the primary handoff artifact; (5) `git status`/`git log` in agentops — HEAD `65cd123` matched the pre-pause note; (6) `sprintctl sprint list` → `item show --id 1216 --json` (status `blocked`, zero claims, events #1387/#1388/#1398); (7) claim-evidence sweep for the concurrent session: `pgrep`, `claim list` on #1216/#1217, `item list` on both sprints, cross-repo `git log` — all negative on tracker-visible concurrent work; (8) `sprintctl claim start --item-id 1216` (claim #159 reissued, `blocked` → `active`). |
| Time / effort to first confident, evidence-backed next action | **2m09s wall-clock** (17:08:21Z → claim acquired 17:10:30Z), ~7 tool-call rounds (~13 invocations). Comparable to Observation 2's 2m05s despite the extra verification branch (hunting for the attested concurrent session in observable state) — because this document itself now functions as a mature, self-describing resume surface: the pre-pause section stated exactly what a future Observation 3 should check. |
| Conflicts / blockers surfaced | None on the claim (reissued cleanly as #159). One near-miss worth recording: `claim start` failed once on a missing required `--actor` flag — CLI-contract friction, not contention. The concurrent-session attestation itself surfaced the observation's central finding: **operator-attested concurrency was invisible to every tracker-native surface.** If the other session is doing real work, a resuming agent has no way to discover or avoid colliding with it through Vuoro/sprintctl — the same docs-corpus-unprotected asymmetry Observation 1 flagged, now generalized to whole sessions. |
| Other sources consulted (non-Vuoro) | OS process list (`pgrep`) — the only surface that corroborated the operator's concurrency claim at all; Claude auto-memory (supplied repo roles and the append-only sprintctl convention, minor). |
| Ambiguity remaining after resume | (1) Whether this counts toward the five at all, given the 3m37s gap — deliberately left to the gate reconciler. (2) What the concurrent session is actually doing — unresolved and unresolvable from tracker state; its only durable trace remains the untracked `docs/plans/evidence-needed.md`, now three sessions old. |
| H9 — did an authored note change/accelerate the next action? | **Mixed, with a new wrinkle: the observation log itself was the accelerant.** The standalone note (`evidence-needed.md`) was again redundant — its content restated the protocol fields already in the operator's message and this document (third consecutive redundancy finding). But this document (08) *did* materially accelerate the resume: the pre-pause section's "what a future Observation 3 should prioritize" paragraph pre-answered the classification question this session faced. That is evidence for authored *in-repo assessment logs* as a resume surface — still not evidence for the session-note/v1 mechanism H9 specifically tests. |

### Gate 4 status after this observation

**2 of 5 firm, plus this provisional row.** If the reconciler accepts
Observation 3, the count is 3 of 5. Either way the multi-agent-batch
requirement remains **open** — concurrent interactive sessions without
any tracker-visible dispatched batch do not meet Observation 1's
definition, and counting this row as the multi-agent sample would be
exactly the flattering shortcut this document exists to prevent. Still
needed: one true multi-agent-batch resume, and enough more rows
(any shape, meaningful gaps preferred) to reach five.

---

## Observation 4 — 2026-07-23 (attempted multi-agent capture; determination: batch not tracker-qualifying)

A fresh Claude session dispatched explicitly to attempt the multi-agent
observation, under a tightened operator protocol: the batch qualifies
only if **at least two genuinely independent work items are visibly
active with tracker-native claims and dispatch/session events** —
operator assertions and `pgrep` explicitly do not count. The operator's
dispatch message included a pasted excerpt of the concurrent session's
own output (it reported reconciling items #1187–#1189 and proceeding
with #1189/#1190/#1191); per protocol this was treated as untrusted
until verified against the tracker.

| Field | Value |
|---|---|
| Repo | agentops (docs/tracker only); tracker items span agentops sprint #380 (the concurrent session's reconciliation work) and sprint #428 (this item) |
| Idle duration | **3m47s** — prior commit `bab5852` at 17:11:32Z → this session's first action at 17:15:19Z. Same near-immediate-continuation caveat as Observation 3; the marginal value of this row is the batch-qualification determination, not the gap. |
| Session shape | **Solo resume beginning while one concurrent session was verifiably active.** Unlike Observation 3, the concurrency was **tracker-visible this time**: events #1400/#1401/#1402 (actor `claude:reconcile-1187/1188/1189`) landed at 17:12:00–17:12:20Z, roughly three minutes before this session started. **But the batch does not qualify as multi-agent** under the stated bar: zero active claims across sprints #380 and #428 (`claim list-sprint --all` returned empty for both), zero items in `active` status in sprint #380 (#1189/#1190/#1191 all `pending`, unclaimed), zero dispatch events for worker agents, and the three fresh events show one actor working sequentially (17:12:00 → :11 → :20), not two independent dispatched items. |
| Active item and claim IDs | Concurrent work: items #1187 (done), #1188 (done), #1189/#1190/#1191 (pending, zero claims). This session: item #1216, claim #161 (claim ID only; token not recorded anywhere, including this file, per protocol). |
| Dispatch/session event IDs | Concurrent session's evidence events #1400/#1401/#1402 on #1187/#1188/#1189; no dispatch events. This session's prior-thread trail: #1387/#1388/#1398/#1399 on #1216. |
| Resume surface used | In order: (1) `date`; (2) operator dispatch message incl. pasted concurrent-session output — used only for targeting, then verified; (3) `git status`/`git log` in agentops (HEAD `bab5852`, clean but for the standing untracked note); (4) `sprintctl sprint list` + `item show --id 1189 --json` (located sprint #380); (5) `item list --sprint-id 380 --status active --json` (empty) + `claim list-sprint --sprint-id 380 --all --json` (empty); (6) `event list --sprint-id 380 --limit 100 --json` — **the decisive surface**: surfaced events #1400–#1402 proving real concurrent work minutes old; (7) `item show` on #1187/#1188/#1190/#1191; (8) `claim list-sprint`/`event list` on sprint #428 (no new activity); (9) `claim start --item-id 1216`. |
| Time / effort to first confident, evidence-backed next action | **2m38s wall-clock** (17:15:19Z → claim #161 at 17:17:57Z), ~8 tool-call rounds. The batch-qualification determination itself was reached at ~17:16:40Z (~1m20s in), after the sprint-380 claim/event sweep; the remainder was the sprint-428 completeness check and claiming. |
| Conflicts / blockers surfaced | None for this session's claim. **One live collision hazard recorded:** the concurrent session is actively working #1189 (its event #1402 is minutes old and its pasted output says it is proceeding on it) while #1189 sits `pending` with zero claims — any other agent could legitimately claim #1189 right now. The claim mechanism exists in this repo (this session used it on #1216 twice), so this is a discipline gap, not a tooling gap. |
| Other sources consulted (non-Vuoro) | The operator's pasted transcript excerpt (verified, not trusted); no `pgrep` this time — deliberately, since the protocol demoted it; no source-code reading needed. |
| Ambiguity remaining after resume | (1) Whether the concurrent session will claim #1189/#1190/#1191 as it proceeds, or continue unclaimed. (2) Whether this row counts toward the five — left to the gate reconciler, same as Observation 3. (3) Whether the planned "real workers" phase (two dispatched items, different repos) will materialize later in this burst — this resume fired while the batch was still one sequential session. |
| H9 — did an authored note change/accelerate the next action? | The operator's pasted excerpt accelerated *targeting* (named the items and sprint region to inspect) but not the *determination* — that came entirely from tracker queries, and the excerpt alone would have been misleading if trusted (it reads like an active multi-item batch; the tracker shows an unclaimed single-actor session). This document (08) again pre-answered the classification method. Standalone note `evidence-needed.md`: untouched, unconsulted — fourth consecutive session where it contributed nothing. |

### Determination and refined finding

**Not a qualifying multi-agent batch.** Two independent dispatched items
with visible claims did not exist at resume time; what existed was one
concurrent session doing real, sequential, unclaimed work.

The refinement over Observation 3's finding: concurrent work *was*
discoverable this time — but only via the **event log, after the fact**
(events land when work units complete), not via claims, which are the
only surface that gives *forward-looking* collision protection. Events
tell a resuming agent what already happened; claims tell it what is
happening. A batch that emits events but holds no claims is visible yet
unprotected — #1189 being actively worked while claimable by anyone is
the concrete instance.

### Gate 4 status after this observation

**2 of 5 firm; Observations 3 and 4 both provisional.** The
multi-agent-batch requirement remains **open** — this was a deliberate
capture attempt that correctly refused to qualify itself. The next
attempt should fire only once the dispatching session can point to two
items with **active claims** and dispatch events, per the operator
protocol now on record above.

---

## Observation 5 — 2026-07-23 (first tracker-qualifying multi-agent batch)

Dispatched under the exact protocol Observation 4 established: the
orchestrating session first dispatched two independent forked workers on
genuinely different, real backlog items (agentops #1189, appservice
scope; agentops #1190, vuoro+agentops scope), confirmed via `sprintctl`
that both held real active claims with dispatch and evidence events,
recorded non-secret pre-pause metadata (note #1408 on #1216), and only
then launched a **genuinely fresh, non-forked** Claude session with no
prior transcript to independently verify and resume cold. This is the
first observation in the set where the fresh session verified the batch
itself, rather than being told it existed.

| Field | Value |
|---|---|
| Repo | agentops (docs/tracker); items span sprint #380 (#1189, #1190); cross-verified against vuoro, appservice, sprintctl via `git log` |
| Idle duration | **Not meaningful, and the resuming session said so plainly rather than dressing it up.** Most recent tracker event (#1407, 17:24:49Z) and most recent commit (agentops `011a687`, 17:24:30Z) both landed ~75–95s before resume start (17:26:04Z) — resuming into the tail of a still-warm burst, not after a dormant period. Idle-gap coverage remains satisfied by Observations 1–2 (3h30m, 4h22m). |
| Session shape | **Multi-agent — the first observation to clear the tracker-native bar Observation 4 set.** Two independent items simultaneously `active` in sprint #380 with distinct, unexpired, exclusive claims passing the tool's *default* (non-`--all`) active-claim filter: #1189 claim **#159** (`claude:reconcile-1189-worker`, created 17:17:10Z, expires 19:17:10Z) and #1190 claim **#160** (`claude:env-injection-worker`, created 17:17:24Z, expires 19:17:24Z). Each has its own dispatch event (#1403, #1404) and its own evidence event (#1405, #1407). The resuming session independently cross-verified both workers' cited commits (vuoro `ccc0c4d`, agentops `011a687`) actually exist in `git log` with matching timestamps — corroboration beyond tracker text alone. One honest caveat the resuming session itself flagged: `ps -p` on the recorded PIDs (528248, 528557) found neither running at check time — the claims are lease-valid and tracker-visible-active, but the underlying worker processes had already exited (short-lived dispatched workers whose claims outlive the process). Not treated as disqualifying — the protocol's bar is tracker state, not process liveness — but recorded plainly rather than glossed over. |
| Active item and claim IDs | #1189/claim #159, #1190/claim #160 (the qualifying batch). #1216/claim #161 also found via `--all`, correctly TTL-expired (17:22:57Z) and absent from the default view — no real collision. |
| Dispatch/session event IDs | #1400–#1402 (reconciliation-evidence on #1187/#1188/#1189, 17:12:00–17:12:20Z, a separate prior thread); #1403/#1404 (dispatch, this batch); #1405/#1407 (evidence, this batch). One gap noted: event **#1406 does not appear** in sprint #380's event list up to limit 100 — not chased further, low value relative to effort. |
| Resume surface used | In order: `date`/`date -u` → `git status`/`git log` (agentops) → directory/file discovery (`pwd`, `ls`, `find` for the assessments dir) → `ls -la` on the assessments directory (mtimes only) → full read of this document (08), read-only → `sprintctl sprint list --json` with archive/backlog flags (surfaced sprint #380) → `item list --sprint-id 380` → `claim list-sprint --sprint-id 380 --all` → `item show --id 1189/1190 --json` → `event list --sprint-id 380` → sprint #428 sweep (`item list`/`claim list-sprint`/`claim list --item-id 1216` with and without `--all`, confirming expiry filtering) → `claim list --item-id 1189/1190` (confirmed genuinely active) → cross-repo `git log`/`status` in vuoro, appservice, sprintctl → non-decisive `ps -p` check → `date`/`date -u` again → `docs/plans/evidence-needed.md`, read last, for H9 only. |
| Time / effort to first confident, evidence-backed next action | **~4 minutes of a 5m38s total investigation** (17:26:04Z → 17:31:42Z), roughly 15 of ~22 tool-call rounds. The determination point was confirming claims #159/#160 pass the *default* active-claim filter, not merely `--all`. |
| Conflicts / blockers surfaced | #1189 left `active`/claimed with a genuine unresolved cross-repo policy conflict (same-digest promotion violated between vuoro-dev and vuoro-shared — see item #1189's evidence note #1405), explicitly deferred to the orchestrating session, not unilaterally fixed. #1190 left `active`/claimed as honestly partial (automatic pipeline wiring and per-identity record auto-selection explicitly deferred — evidence note #1407). Claim #161 on #1216 is stale/TTL-expired/unreleased — a minor recurring tracker-hygiene gap already flagged in Observations 3–4. Claims #159/#160 are lease-valid for ~1h50m more but their recorded PIDs are not running — an orphaned-lease risk if nobody explicitly releases them before natural TTL expiry. |
| Other sources consulted (non-Vuoro) | `git log`/`git status` across four repos (agentops, vuoro, appservice, sprintctl); `ps` (non-decisive OS-level check, explicitly not treated as tracker evidence per protocol). |
| Ambiguity remaining after resume | Whether the dispatching/orchestrating session is still active anywhere to act on #1189's deferred policy decision or release the claims before TTL expiry; the missing event #1406; whether the near-zero idle gap limits this row's marginal value the same way it did for Observations 3–4 (the marginal value here is the multi-agent qualification itself, not the gap, same reasoning as those rows applied to their own axes). |
| H9 — did an authored note change/accelerate the next action? | **No — a fifth consecutive negative/redundant finding for the standalone note.** `docs/plans/evidence-needed.md` was read last, for completeness, after the determination was already made; it restated fields already in the operator's dispatch instructions and in this document. What did help, again, was this in-repo assessment log (08) itself, which supplied the exact qualifying bar Observation 4 established, which the resuming session then applied. Same pattern as all four prior observations: tracker-native state and in-repo assessment logs carry the accelerant value; the standalone note file consistently does not. |

### Determination

**This is a real, tracker-qualifying multi-agent batch** — the first in
the set to clear the bar Observation 4 correctly refused to grant itself.
Two genuinely independent real work items (different repos: appservice
for #1189's scope, vuoro+agentops for #1190's scope), each with its own
active exclusive claim, dispatch event, and evidence event, cross-verified
against real git commits by an independent fresh session that had no
foreknowledge the batch existed and confirmed it entirely from tracker
and git state.

### Gate 4 status after this observation

The multi-agent-batch requirement is satisfied by Observations 5 and 6,
and meaningful idle gaps are satisfied by Observations 1 and 2. The gate
reconciler accepts Observation 3 as the fifth valid timed row despite its
near-immediate gap; its shape is explicitly solo and it is not used as the
multi-agent evidence. Observation 4 remains supplemental evidence of a
correctly rejected batch qualification attempt.

**Gate 4 passed 2026-07-23.** Accepted rows: 1, 2, 3, 5, and 6. No further
observations should be dispatched.

---

## Observation 6 — 2026-07-23 (second qualifying multi-agent batch; caught an orchestrator overclaim)

Dispatched under the same protocol as Observation 5, this time against a
three-worker real burst (agentops #1189 continuation, #1190 continuation,
#1191 design pass — three genuinely different backlog items, two
different repos as the primary pair). The orchestrating session recorded
pre-pause metadata (note #1415 on #1216) asserting **three** active
claims, then launched a fresh, non-forked, zero-context Claude session
immediately after. By the time that session actually inspected tracker
state, #1191's worker had already finished and released its claim —
the fresh session caught this discrepancy itself, independently, and
corrected the record rather than accepting the pre-pause note at face
value. This is the sharpest test yet of "do not rely on prior transcript
or operator assertions," because the operator-adjacent assertion here was
wrong, not just redundant.

| Field | Value |
|---|---|
| Repo | agentops (docs/tracker); qualifying items span sprint #380 (#1189, #1190); #1191 also in #380 but non-qualifying (see below); cross-verified against vuoro, appservice, sprintctl via `git log` |
| Idle duration | **Not meaningful / effectively none.** Claim heartbeats on the batch sit at 17:41:59Z/17:42:01Z; one of the batch's own evidence events (#1418) landed at 17:44:55Z — *after* this session's own resume start (17:43:44Z). A resume into a still-live batch, not after a gap. Idle-gap coverage remains satisfied by Observations 1–2. |
| Session shape | **Multi-agent — confirmed, but exactly TWO qualifying items, not the three the pre-pause note claimed.** #1189 (claim **#159**, `claude:1189-backfill-worker`, rotated via handoff event #1410, dispatch #1412, evidence #1418) and #1190 (claim **#160**, `claude:1190-completion-worker`, rotated via handoff event #1411, dispatch #1404, evidence #1407) both passed `claim list --item-id` with a live result. **#1191 did not qualify**: `claim list --item-id 1191` returned `[]` — zero claims — despite having dispatch event #1414 and decision event #1416. The resuming session correctly applied the two-part bar (active claim *and* dispatch/evidence events) rather than counting event-presence alone, and explicitly flagged that the pre-pause note's claim of "claim #162" was not corroborated by live query. |
| Active item and claim IDs | #1189/claim #159, #1190/claim #160 (the qualifying pair). #1216/claim #161 found expired (17:22:57Z, ~21 min stale at inspection) — correctly excluded, flagged as tracker-hygiene debris consistent with Observations 3–5. |
| Dispatch/session event IDs | #1189: 1402, 1403, 1405, 1410, 1412, 1418. #1190: 1404, 1407, 1411. #1191 (non-qualifying, event-only): 1414, 1416, 1417. #1216 meta-chain: 1387, 1388, 1398, 1399, 1406, 1408, 1409, 1415. |
| Resume surface used | In order: `date` → agentops `git status`/`git log` + `sprintctl --version` → directory listing of the assessments folder (not opened) + read of `docs/plans/evidence-needed.md` → `sprintctl sprint list --json` → `item list --sprint-id 428` → `claim list-sprint --sprint-id 428 --all` + `claim list --item-id 1216/1217` → `item show --id 1216/1217` + `event list --sprint-id 428` → `claim list --item-id 1189/1190/1191` + `item show --id 1189/1190/1191` → `claim list-sprint --sprint-id 380 --all` → detailed event-payload extraction for #1189/#1191 → cross-repo `git log`/`git show` (agentops, appservice, vuoro) → `sprintctl sprint show --id 380` → sprintctl repo `git status`/`git log` (negative check, ruled out as unrelated). |
| Time / effort to first confident, evidence-backed next action | **~3 minutes of a 4m18s total** (17:43:44Z → 17:48:02Z), roughly 12–13 of ~23 tool-call rounds. |
| Conflicts / blockers surfaced | #1189 left `active`/claimed with an unpushed appservice digest-backfill commit (`770763fa`) awaiting an operator push decision, plus an honestly-flagged verification gap (only a local `kind-bindery` cluster was reachable, not the real appservice cluster). #1190 left `active`/claimed with two sub-scopes still deliberately deferred. #1216's claim #161 remains stale/expired/unreleased. Both #1189 and #1190 show claim-handoff "lost-proof-adopted" rotations — the original short-lived workers lost their tokens and had to be recovered via `--allow-legacy-adopt`, a minor recurring irregularity, not a collision. **The concrete finding this observation adds to the set: tracker-authored text (this thread's own pre-pause note, #1415) was itself wrong** — it asserted three active claims when only two were live by inspection time — and the resuming session caught this by direct query rather than trusting it. |
| Other sources consulted (non-Vuoro) | `git log`/`git status`/`git show` across four repos (agentops, appservice, vuoro, sprintctl); deliberately did *not* open this document (08) itself this time, only listed the directory, to avoid being anchored by it — a stricter self-imposed bar than Observations 1–5 applied. |
| Ambiguity remaining after resume | Whether #1216's stale claim #161 will be treated as noise or a real collision risk by whoever writes next; whether #1191's event-only activity should count under a looser future batch definition (this session correctly did not extend it that benefit); whether appservice's unpushed backfill commit gets pushed; process-liveness beyond heartbeats/fresh-commit-timestamps was not independently checked this time (no `ps` call), consistent with the instruction to treat tracker state, not process inspection, as decisive. |
| H9 — did an authored note change/accelerate the next action? | **No — sixth consecutive negative/redundant finding for the standalone note**, and this time a piece of *tracker-native* text (#1415) actively required correction rather than helping. `docs/plans/evidence-needed.md` again added nothing beyond what item #1216's own description and the operator protocol already state. What drove the determination was direct `claim list --item-id` queries plus independent cross-repo git corroboration — not any authored note, and specifically not the pre-pause note this same investigation had to overrule. |

### Determination

**A second real, tracker-qualifying multi-agent batch — and the first
observation to independently catch and correct an inaccurate tracker
note rather than merely finding standalone notes redundant.** The
pre-pause note's overclaim (three items asserted, two verified) is not a
process failure to paper over: it is exactly the kind of discrepancy this
five-observation gate exists to surface, and it was caught by the
resuming session doing what the protocol asked — verifying tracker state
directly rather than trusting prior text, including text written by this
same assessment's own orchestrator.

### Gate 4 reconciliation

Observations 5 and 6 independently satisfy the tracker-visible
multi-agent-batch requirement. Observations 1 and 2 satisfy the meaningful
idle-gap requirement. Observation 3 is accepted as the fifth live timed
resume row; Observation 4 remains supplemental and non-qualifying for
batch shape.

**Gate 4 passed 2026-07-23.** The remaining action is reduced-spec freeze
and clean-room setup, not more observation.
