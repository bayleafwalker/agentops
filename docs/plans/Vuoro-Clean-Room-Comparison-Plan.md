# Vuoro Clean-Room Comparison Plan

Status: **READY — reduced-spec baseline frozen 2026-07-23**.

**2026-08-22:** `vuoro/docs/plans/2026-08-22-long-term-direction.md` §7.1 requires a one-time
five-way classification of the frozen R1–R8 spec — essential safety/recovery invariant,
essential workflow outcome, migration-only compatibility, incumbent convenience, or unresolved
assumption — before any lane runs. The classified spec becomes the Gate-5 baseline.
Classification is not a licence to amend requirements mid-comparison. That document's Beads/Gas
Town judgement (§7.3) is a desk prior only — the five lanes below have not run.

Successor to the sketch in
`Vuoro-Pre-Clean-Room-Assessment-Plan.md` ("Relationship to the clean-room
exercise"). Incorporates the 2026-07-23 external-candidate shortlist review
and the adopted items from `clean-room-adjustments-suggestions.md`
(scenario pack, Vuoro baseline lane, experimental controls, measurement
protocol, pre-registered decision thresholds, segmented cost model).

## Inputs

1. The reduced workflow specification (R1–R8) —
   `docs/assessments/vuoro-pre-clean-room/06-reduced-workflow-specification.md`.
   Frozen after Gate 4 reconciliation; five live timed observations are
   recorded in `08-resume-observations.md`.
2. Open hypotheses H1–H9 —
   `docs/assessments/vuoro-pre-clean-room/07-open-hypotheses.md`.
3. The 2026-07-23 candidate shortlist review (Beads, Gas Town, Restate,
   Windmill, Daytona, Temporal, `td`, and excluded candidates).

## Gate-5 integrity note

Gate 5 requires the reduced spec to be frozen before external tools are
studied in detail, precisely so requirements are not reshaped to favour or
disfavour a candidate. The shortlist review has now happened while the spec
is still one blocker short of freeze. To preserve the gate's intent:

* The spec text as committed 2026-07-23 is the recorded baseline.
* Between now and freeze, the spec may change **only** in response to
  evidence from the five timed resume observations (and H9), never in
  response to candidate capabilities or gaps. Any such change must cite the
  observation, not a tool.
* The shortlist's coverage scores are recorded below as **priors**, dated
  before any hands-on testing. The exercise is judged on whether hands-on
  evidence confirms or overturns them.
* Candidates are weighed against the **requirement-confidence column** of
  the spec's confidence table, not against the current-mechanism column.
  Model-sensitivity weights are frozen per H8.

---

## Framing: compare ownership boundaries, not products

The shortlist review's central finding: no single reviewed tool natively
covers all five Vuoro differentiators (proof-bearing claims; transfer and
recovery; semantic conflict-detecting resume; fenced execution;
cross-machine trust-separated authority). The market splits them across
agent-native work registries, durable workflow runtimes, and sandboxed
execution platforms. The credible alternative to Vuoro is therefore a
**composed stack**, which the reduced spec already anticipates (R6 expressly
does not require a single physical service).

The unit of comparison is the ownership boundary:

| Boundary | Requirements | Candidate owners |
|---|---|---|
| Work registry | R1, R4 | `td` / Beads / sprintctl |
| Claim authority | R2 | Vuoro / Restate Virtual Object adapter / planner-native claim (Beads/Gas Town) |
| Semantic resume | R3 | Vuoro handoff / Gas Town `prime` / derived adapter over registry + log |
| Execution queue | R5 (queue form — Provisional) | actionq / Windmill / Temporal |
| Sandbox boundary | R5 (safety envelope — High) | devbox worktree + ACL / Daytona / E2B |
| Knowledge distillation | R7 | kctl / downstream adapter over the event feed (H3) |
| Operator projection | R8 | cockpit / Gas Town dashboard / generated CLI view |
| Cross-machine authority | R6 | unified Vuoro service / composed domain authorities — every lane must state its answer explicitly |

This decomposition gives external tools a fair opportunity to replace what
they are actually good at, without requiring one vendor to have invented the
entire operating model. R6 is not a lane of its own: it is a cross-cutting
acceptance criterion (server-resolved identity, authority gating, credential
non-persistence, migration/runtime role split) that each lane must satisfy
or explicitly fail.

---

## Scenario pack

The batch scenario alone is Vuoro-shaped: it exercises exactly the
conditions under which Vuoro's economics look best. To avoid a comparison
biased toward burst coordination, every lane claiming workflow-level
coverage runs the full pack. The pack deliberately includes scenarios
where minimal process should win.

### S-BATCH — the standard multi-agent batch

The same Vuoro-shaped batch so results are comparable:

* ten agents;
* overlapping candidate work (tests R1 selection + R2 exclusion);
* one agent crash (R2 recovery, R5 crash path);
* one explicit ownership transfer (R2 handoff with proof rotation);
* one proof-loss/recovery event (R2 recovery path);
* one blocked dependency (R1 dependency gate, R3 conflict detection);
* one cold operator resume (R3 bundle, R8 supervision).

For each event, record which boundary handled it, whether the outcome was
**prevented** or merely **recorded**, and what manual intervention was
needed.

### S-SOLO — ordinary single-agent, same-day work

One agent, one repository, no interruption, no handoff. Tests whether
claims, serving, and resume machinery impose ceremony on the majority
workload. Minimal candidates should perform well here; any lane that
loses to Lane 0 on S-SOLO must justify the overhead from its S-BATCH
results, not from asserted future need. Feeds the segmented cost model
directly.

### S-RESUME — cold resume after idle period

Resume partially completed work after days or weeks with no prior
conversation context. Tests correct identification of active work,
blocked work, recent decisions, the in-flight branch or workspace, and
the correct next action — with remaining ambiguity recorded. The five
timed resume observations (the freeze blocker) double as the Vuoro
baseline measurement for this scenario; external lanes run the same
protocol so the numbers are directly comparable.

### S-DORMANT — dormancy and state rot

Leave candidate state untouched for an extended period, then resume with
a cold agent. Tests stale ownership, stale projections, manual
reconstruction burden, and whether the system required maintenance while
nothing was happening. Idle carrying cost is a real cost for a
single-operator homelab; this is where it surfaces.

### S-SIMPLIFY — workflow simplification challenge

Re-run S-BATCH's task set under deliberately reduced process: fewer
concurrent agents, no unattended execution, explicit operator
assignment, one end-of-session note. Purpose: determine per capability
whether it should be bought or built — or whether the workflow
generating the need should be shrunk instead. This is the direct
deletion-hearing complement to Lane 0.

### The R2 litmus test (applies to every lane)

The single most consequential distinction from the shortlist review:

> Does the candidate **prevent conflicting mutation**, or does it mainly
> **record who is supposed to be working**?

R2's evidence base includes two real token-exposure incidents and the
orchestrator-owned-token invariant in every dispatch skill. A candidate
passes R2 only if:

1. mutation of a claimed item requires possession of a proof, not merely a
   matching assignee/status field;
2. transfer rotates the proof;
3. the proof can be withheld from delegated subagents;
4. a lost proof has an authoritative recovery path.

An atomic status transition (e.g. if `bd update --claim` proves to be one)
may satisfy R1 and much of R3/R8 while failing the R2 security property.
Record the distinction explicitly rather than scoring "claims: partial".

### Hard gates

A candidate cannot win a boundary through convenience or lower carrying
cost if it fails a non-negotiable safety property there. Fixed before
testing:

* **Work correctness** — no two actors hold valid exclusive execution
  authority simultaneously; blocked work cannot be activated; recovery
  does not silently discard in-flight work.
* **Resume correctness** — a cold agent identifies the correct next
  action; stale information is marked stale rather than presented as
  current truth; ownership ambiguity is visible.
* **Execution safety** — duplicate delivery does not create duplicate
  authoritative effects; stale workers cannot renew or complete after
  ownership changes; verification failure cannot be represented as
  success.
* **Trust boundary** — R6's acceptance criteria (server-resolved
  identity, no self-asserted privilege, credential non-persistence,
  migration/runtime role split); proof secrets do not appear in prompts,
  logs, or delegated subagent context.

A candidate failing a hard gate may still take a narrower boundary role
(as Daytona does under R5), but cannot displace the Vuoro capability
whose gate it failed.

---

## Lanes

Six lanes: four serious candidate systems, one minimization control, and
the Vuoro baseline.

### Lane B — Vuoro baseline (current, then reduced)

**Tests:** nothing external — it produces the numbers every other lane is
judged against. Run the scenario pack on Vuoro **as currently operated**,
including existing ceremony and maintenance, and record the same
measurements as every other lane. Where the frozen spec demotes or
removes mechanisms, re-run the affected scenarios with those mechanisms
disabled to approximate **reduced Vuoro**.

Without this lane, "matches or improves Vuoro outcome quality" is
unfalsifiable and the comparison degrades into external demos versus an
imaginary cost-free status quo. Equally, current Vuoro is **not**
automatically a finalist: its baseline run is evidence, not a bye.

**Status: mandatory; runs first** (its S-RESUME leg is the five timed
resume observations already required for spec freeze).

### Lane 0 — Minimized control: `td`

**Tests:** whether claim authority (R2), fenced execution (R5), and
trust-separated authority (R6) can simply be *removed* — how much observed
value survives with only a strong task graph and explicit structured
handoffs (done / remaining / decisions / uncertainty).

`td` is not a serious replacement for R2/R5/R6 and is not scored as one.
It is the deletion-and-tolerance hearing that Workstream 4 demanded.

**Coverage against:** R1 (partial), R3 (medium — handoff content without
conflict detection), R4 (partial).

### Lane 1 — Closest market substitute: Beads + Gas Town

**Tests:** whether the whole bespoke workflow can be replaced by an existing
agent-native ecosystem. Gas Town is the closest public analogue to the
actual Vuoro *operating workflow* (persistent agent identities, assignments,
worktree-backed hooks, session handoff/recovery, stuck-agent detection,
merge coordination), not merely its architecture. Beads supplies the
dependency-aware work graph, deterministic ready-work queries, atomic
claiming, and Dolt-based cross-machine sync.

**Protocol:** run the standard batch scenario using only Beads/Gas Town.
Aggressively test the R2 litmus (the shortlist's prior is that its claim
model is assignee/state-based, not proof-bearing). Test whether Gas Town
`prime` reproduces the R3 conflict bundle (unclaimed active work, dependency
blocks, staleness) or only prior-attempt context. Assess the Dolt/Git/tmux
trust model against R6's acceptance criteria.

**Priors (2026-07-23):** transfer/recovery strong; resume medium-strong;
claim proof partial; fenced execution medium; trust authority weak-medium.

**Status: mandatory.** The only reviewed system that challenges Vuoro at the
complete workflow level. If it passes R2, hypothesis H2 collapses toward
"planner-native" and the custom authority may be unnecessary.

### Lane 2 — Decomposed hybrid: Beads + minimal Restate adapter

**Tests:** H1 and H2 directly — the most plausible long-term architecture.
Beads owns R1/R4 as commodity registry; a narrow Restate service owns
R2 and the authoritative inputs to R3.

Restate Virtual Objects give keyed single-writer consistency (one write
handler at a time per object key, state survives crashes), which eliminates
concurrent claim mutation at the authority layer. Proof tokens and transfer
rotation remain custom domain logic, but Restate replaces the home-grown
durability, sequencing, retry, and recovery machinery. Note the fit with
H7: single-writer authority plus durable signals supports event-driven
invalidation without client heartbeat upkeep.

**Protocol:** build only a minimal adapter —

```text
WorkItemClaim[item-id]
  state: owner, proof_digest, claim_revision, recovery_policy, workspace_ref
  ops:   acquire, mutate (proof-gated), transfer (rotates proof),
         recover, release
  query: state needed by the R3 resume bundle
```

plus a guarded item transition against Beads. Do **not** rebuild catalog,
knowledge, or cockpit for the spike.

**Decisive question:** can Beads own R1/R4 while a very small Restate
service preserves the consequential R2/R3 semantics, *without splitting
authority in a way that recreates today's reconciliation cost* (H1's
sharpened form)?

**Status: strongest candidate for the likely end state.**

### Lane 3 — Execution substitution: existing work authority + Windmill + Daytona

**Tests:** whether the actionq/dispatcher/devbox machinery should be bought
rather than built. This lane is sharpened by the 2026-07-23 queue
inspection: R5's queue-specific design (fenced renew, sweep-requeue,
idempotency) has **never fired on live data** and was split to Provisional.
The demonstrated requirement is the safety envelope — isolation + ACL +
admission — and that is exactly what this stack is strongest at.

Windmill: shared job queue, atomic pickup, worker groups, tagged routing,
agent workers without direct database access, PID-namespace/NSJAIL
isolation. Daytona: disposable/persistent sandboxes with dedicated
filesystem and network, pause/resume, snapshots, and a secret mechanism
that keeps plaintext credentials outside the sandbox for allowlisted hosts
— directly relevant to R6's credential non-persistence and the
token-exposure incident class behind R2.

**Protocol:** keep Vuoro (or Beads) claims and resume; replace only the
execution path:

```text
claim → Windmill job → Daytona sandbox → agent execution
      → diff + verification artifact → completion callback → claim-gated close
```

Measure: configuration/operational burden; sandbox startup and restore;
worktree/repository handling; secret exposure; retry and duplicate
execution against R5's idempotency bar; the R5 known gap (unfenced terminal
transitions — reproduce or consciously close); evidence returned to the
work authority; and whether actionq remains necessary at all.

**Status: best R5 replacement / addition, not a whole-Vuoro replacement.**
Claim proof stays out of this lane by design.

### Lane 4 — Durable-execution reference: Temporal

**Tests:** whether the custom coordination core is a small version of a
solved workflow-engine problem, and how much complexity the industrial
answer removes — or introduces. Model each claimed item as a workflow;
acquire/transfer/recover as signals/updates; attempts as activities;
recovery and timeout policy as workflow logic; devbox workers via task
queues.

**Status: reference ceiling, not presumed winner.** A small spike only; do
not migrate a project into it merely to admire the event history. Its
probable verdict — technically capable, operationally disproportionate for
a single-operator workflow — is itself the data point: it calibrates where
Restate (Lane 2) and Windmill (Lane 3) sit between bespoke and industrial.

---

## Experimental controls

To make lane results comparable:

* same repository snapshots, tasks, and acceptance tests;
* same agent models and reasoning settings (weights frozen per H8);
* same failure-injection schedule and maximum operator-intervention
  allowance;
* same evidence-capture format.

Lane-specific prompts may describe how to use the candidate, but may not
supply task knowledge unavailable to other lanes. Result artifacts are
assessed without candidate-identifying labels where practical.

## Measurements

Recorded per lane and scenario, in a common format:

* **Outcome quality** — task success, acceptance-test result, correct
  work-item state, duplicated or missed work, recovery correctness,
  unsafe operation attempts.
* **Operator economics** — time to first correct action, interventions,
  surfaces consulted, time repairing workflow state, supervision effort
  per concurrent agent.
* **Agent economics** — tool calls, retries, context consumed by
  workflow instructions, repeated project reconstruction, failed claims,
  time waiting on workflow infrastructure.
* **Operational burden** — installation/upgrade complexity, services and
  databases operated, backup/restore, migrations, idle carrying cost,
  failure modes requiring custom diagnosis.
* **Adaptation probe** — implement three deliberately small changes per
  serious candidate: (1) add an optional work-item field; (2) alter the
  resume-bundle output; (3) add one execution policy. Record files and
  repos touched, custom code required, upstream constraints, migrations,
  and rollback work. This reveals whether an external tool removes
  maintenance or merely relocates it into adapters and forks.
* **Authority and reconciliation count** (H1's sharpened form) — number
  of authoritative stores, projections, duplicated state, synchronization
  paths, states where two systems can disagree, and the recovery
  procedure when they do. Decisive for Lane 2: Beads owning R1/R4 while
  Restate owns R2 is not a win if it creates two competing notions of
  whether work may proceed.

## Cost model

Costs are computed over three horizons — adoption (integration,
migration, retraining, parallel run, rollback implementation), monthly
carrying (upgrades, service operations, incident repair, adapter
maintenance, subscriptions), and per-workflow.

Per-workflow cost is computed **separately per scenario class** (S-SOLO,
S-RESUME, S-BATCH, interrupted execution, unattended run) and never
averaged into a single "typical session". The observed pattern — Vuoro
positive during multi-agent bursts, roughly neutral during ordinary solo
work — makes the segmentation load-bearing: a legitimate end state is
*minimal workflow by default, Vuoro (or successor) activated only for
burst coordination or unattended execution*, which an averaged cost model
cannot represent.

## Pre-registered decision thresholds

Fixed now, before hands-on testing; any later change must be logged with
the evidence that forced it, mirroring the Gate-5 note. Per boundary:

* **Remove** — Lane 0 / S-SIMPLIFY passes the relevant hard gates,
  succeeds in ≥90% of the relevant scenarios, adds ≤20% operator time
  versus baseline, and causes no recovery or trust-boundary regression.
* **Buy (external replacement)** — the candidate passes the relevant
  hard gates, matches or improves the Lane B outcome quality, reduces
  expected carrying cost by ≥30%, does not require adapters or forks
  recreating more than roughly one-third of the displaced custom logic,
  and has a credible rollback path.
* **Wrap (external + thin adapter)** — commodity functionality is
  genuinely externalized, the adapter owns a narrow stable interface and
  is substantially smaller than the displaced component, authority
  remains unambiguous, and reconciliation paths decrease rather than
  increase.
* **Keep bespoke (reduced)** — reduced Vuoro materially outperforms
  current Vuoro at the boundary, external candidates fail hard gates or
  require broad adaptation, and the retained custom code maps directly
  to consequential scenarios.
* **Keep bespoke (current)** — only when compression yields little,
  current Vuoro materially outperforms all alternatives, and migration
  cost is unjustified by multi-year savings. This should be a difficult
  outcome to earn: inertia is not evidence.

## Recorded priors (2026-07-23, pre-testing)

Comparative judgments from the shortlist review, not product claims and not
results. Kept to detect confirmation bias at readout.

| Candidate | Claim proof | Transfer/recovery | Conflict resume | Fenced execution | Trust authority | Likely role |
|---|---:|---:|---:|---:|---:|---|
| Beads + Gas Town | 1.5/3 | 3/3 | 2.5/3 | 2/3 | 1.5/3 | Closest full replacement |
| Beads + Restate | 2.5/3 | 3/3 | 2/3 | 2.5/3 | 2.5/3 | Best architectural hybrid |
| Beads + Windmill + Daytona | 1/3 | 2/3 | 1/3 | 3/3 | 2.5/3 | Best execution replacement |
| Temporal | 2/3 | 3/3 | 2/3 | 3/3 | 2.5/3 | Durable-runtime reference |
| `td` alone | 0/3 | 1.5/3 | 2/3 | 0/3 | 0/3 | Minimization control |

**Declared expected result (prior, to be confirmed or overturned):** Beads
replaces much of sprintctl's registry surface; a small custom or
Restate-backed service retains claim proof and semantic resume; an external
execution/sandbox platform replaces more of actionq and dispatcher. Gas
Town may prove even the claim/resume layer can be bought, pending the R2
litmus. Temporal proves capable but disproportionate.

## Excluded from the primary comparison

* **LangGraph** — checkpointed graph state and thread persistence solve
  *resuming one agent workflow*, not project work claims, cross-repo
  conflict detection, or sandbox authority. Revisit only if the exercise
  expands to replacing the internal agent loop.
* **OpenAI Agents SDK** — handoffs are delegation between agents within a
  run, not authoritative work-item ownership transfer. Agent-runtime
  component, not a work authority.
* **E2B or Daytona alone** — execution sandboxes, not coordination systems;
  valuable under R5 but silent on R2/R3. Daytona participates via Lane 3.

---

## Outputs

1. **Per-lane result sheet:** scenario-pack event log (prevented vs
   recorded, per boundary), hard-gate results, R-by-R coverage verdict
   against the priors, R2 litmus verdict, R6 acceptance-criteria verdict,
   measurements per the protocol above, raw evidence links.
2. **Boundary disposition table:** for each ownership boundary — buy /
   wrap with thin adapter / keep bespoke / remove — with the evidence
   line, the threshold rule it satisfied, a confidence rating, and **what
   evidence could reverse the decision**.
3. **Segmented cost comparison:** the three-horizon model per finalist,
   with per-scenario-class figures preserved (no averaging).
4. **Hypothesis readout:** H1, H2, H3, H5, H7 updated with lane evidence;
   H8 weights untouched.
5. **Recommended end-state composition** and a migration-shaped sketch
   (which boundary moves first, what interops during transition, rollback
   path per moved boundary).

## Execution order

1. **Completed 2026-07-23:** freeze the reduced spec after five accepted
   live timed resume observations. The observations double as Lane B's
   S-RESUME leg.
2. Confirm scenarios, hard gates, measurements, and decision thresholds
   as written here — frozen before any hands-on lane work.
3. Lane B (Vuoro baseline) — the yardstick; complete before external
   lanes are scored.
4. Lane 0 (`td` control) — cheapest, sets the floor; includes S-SIMPLIFY.
5. Lane 1 (Beads + Gas Town) — mandatory; run the R2 litmus early, since
   its outcome reshapes how much Lane 2 must carry.
6. Lane 2 (Beads + Restate adapter spike).
7. Lane 3 (Windmill + Daytona execution path) — may run in parallel with
   Lane 2; it shares no boundary with it.
8. Lane 4 (Temporal spike) — last; it is calibration, not a candidate.
9. Score against the pre-registered thresholds without altering them;
   then boundary disposition and end-state recommendation.

## Success criterion

The exercise succeeds when every ownership boundary has an explicit
disposition backed by hands-on evidence against the frozen R1–R8 spec —
including the honest outcomes "the bespoke mechanism is the requirement"
and "this boundary should not exist." A composed-stack recommendation must
account for the reconciliation cost of the new seams it introduces (H1's
sharpened form), not only for the code it deletes.
