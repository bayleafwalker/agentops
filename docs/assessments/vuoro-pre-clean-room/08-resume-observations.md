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
