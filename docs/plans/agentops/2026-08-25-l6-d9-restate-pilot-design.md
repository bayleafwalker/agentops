# L-6 — D-9 durable-workflow challenger pilot design (Restate)

**Status: design only. Not authorized to deploy.** This document satisfies the L-6 row of
`docs/plans/agentops/2026-08-23-handoff-loop-and-telemetry.md` ("D-9 pilot design — *design
only*, separately authorized before any manifest lands"), whose gate is "design doc reviewed".
The owner has authorized the *design*. Nothing here authorizes a manifest, a PVC, a cluster
change, a schema, or a line of service code. See §10.

- **Decision:** D-9, vuoro `docs/plans/2026-08-23-requirements-pathway-v5-v7.md:170` — "First
  durable-workflow challenger and pilot envelope … Restate on appservice, pilot = one actionq
  review round reshaped to 4–8 parallel packets. Analysis needed: orchestration-planning
  session; **not before v6**."
- **Blocks:** G3.4 (`:112-113`) — "Provider-neutral pilot through incumbent + minimization
  control + one durable-workflow challenger (Priority 7; Restate candidate)".
- **Sequencing:** v6+ per the register. This document is written during v5 so the
  orchestration-planning session starts from measured numbers rather than from the 2026-08-21
  memory, which predates the driver.
- **Placement:** appservice cluster. Settled by the `orchestration-restate-pilot` memory and
  **not re-litigated here.** §6 costs it; it does not reopen it.

**The one-line recommendation, up front:** run the pilot only as a *fan-out* experiment with a
pre-registered falsifier, and run the cheap control (a fan-out mode in `dispatch_release.py`)
**first**, in the same release, against the same packets. On the evidence in §2 the most likely
outcome is that Restate adds a cluster service, a PVC, a schema and a Python service for a
frontier-turn reduction that is not measurable, because `dispatch_release.py` has already taken
most of the available gain. §8 says exactly what would have to be observed for that reading to
be wrong.

---

## 1. What the challenger was originally supposed to beat, and why that premise is stale

`/projects/dev/orchestration-meta-planning.md` (an external model's analysis, saved 2026-08-21)
argued that a frontier session burns **30–60 turns** per multi-worker workflow acting as a
dispatch/poll event loop, and that replacing only the supervision loop with Restate would drop
that to **2–4**. The `orchestration-restate-pilot` memory records that premise and the two
decisions taken from it (pilot workload = an actionq review round reshaped into 4–8 parallel
contracted tasks; placement = appservice).

That memory is dated **2026-08-21**. Between then and now the agentops supervised-hybrid loop
was built and measured. `templates/dispatch/scripts/dispatch_release.py` (969 lines) already
chains `prepare → run → gate → receipt` and then commits, pushes and runs `gh pr create`, with:

- a fixed, non-configurable step order (`:43`, `STEPS`);
- an encoded one-retry policy (`:47`, `MAX_GATE_ATTEMPTS = 2`; `RETRY_STEPS` re-runs
  `run/gate/receipt` only, because `prepare` is what makes a dispatch expensive) — L-4;
- the four L-2 stop conditions as a closed vocabulary (`:61`, `STOP_CONDITIONS` =
  `release-boundary`, `command-not-allowed`, `path-outside-writable`, `gate-red-twice`), each
  firing exactly once and writing a `workflow.escalation` event to auditctl (`:348`);
- a five-part PR step whose failure names its own part (`:75`, `PR_STEP_NAMES`).

**The polling loop the orchestration doc set out to remove does not exist any more for the
single-packet case.** It was removed by a Python driver, not by a durable execution runtime.
Any honest challenger analysis has to be a delta against that driver — §3 — and not against the
30–60-turn world the memory describes.

---

## 2. What has already been measured (the v5 T-series baseline)

Two artifacts, and they are not interchangeable:

- `docs/evidence/scorecards/v5-t-series.generated.json` — **produced by the instrument**
  (`templates/dispatch/scripts/release_scorecard.py`), schema `workflow-scorecard/v1`. This is
  the comparison baseline.
- `docs/evidence/scorecards/v5-t-series.json` — the hand-written narrative scorecard
  (`workflow-scorecard/v0`) with per-packet rows, findings and debt. Read for context; do not
  compare against it field-by-field, because it is a different schema.

From the generated scorecard, scoped `project: agentops`, `since: 2026-08-24T18:00:00Z`:

| Field | Value |
|---|---|
| `frontier.sessions` | 1 |
| `frontier.turns` | **16** |
| `frontier.assistant_msgs` | 606 |
| `frontier.tool_calls` | 353 |
| `frontier.duration_s` | 7620 |
| `frontier.rework_rounds` | 0 |
| `worker.tasks` / `worker.attempts` | **11 / 11** |
| `worker.first_pass_rate` | **1.0** |
| `worker.tokens` | **2,874,316** |
| `worker.billed_usd` | **$0.158969** |
| `escalations.count` | **0** |
| `cost_usd.frontier_usage_equivalent_usd` | 268.546437 |
| `cost_usd.total_billed_usd` | 0.158969 |
| `cost_usd.commensurable` | **false** |

The hand scorecard's `totals` add: `wall_seconds` 759, `rework_rounds` 0,
`hand_steps_inside_the_loop` **0**, `coordinator_packet_defects_caught_before_spend` **2**.

### 2a. The two figures are not the same kind of number

`$268.55` is **not spend.** It is `tokens × a hardcoded 2025 list-price table` computed by
`templates/dispatch/hooks/log-session-cost.sh`; nothing meters it and on a subscription plan it
is never billed. `$0.158969` is OpenCode's own `step-finish` accounting of real metered API
spend, read from the receipts. There is deliberately **no key holding their sum**, and
`test_release_scorecard_kinds.py` exists solely to fail if anyone reintroduces one (handover
§3h, "Correction, same day"; fixed in #91).

This project has been burned by exactly this three times in one week — §3h (units: $241.43
quoted as spend, of which eleven cents was money), §3h (scope: an unscoped window overcounting
the frontier half by 56%), §3h (names: `frontier_totals` and `worker_totals` both reporting a
key called `cost_usd`). Every one was arithmetically correct and meant the wrong thing, and not
one was catchable by a gate. **Any pilot report that adds a Restate figure to a worker figure,
or quotes a usage-equivalent as cost, is wrong before it is read.** This is a design constraint
on §7, not a footnote.

### 2b. What `frontier.turns = 16` actually counts

`log-session-cost.sh:115` computes `turns` as the number of `user` rows carrying no
`tool_result` content — i.e. **human prompts into the session**, not assistant messages (606)
and not tool calls (353). So the v5 T-series consumed **16 owner/coordinator prompts to land 11
packets**, ≈1.45 prompts per packet.

That is the number the v7 falsifier is about ("frontier turns per release drop ≥ 5× vs v5
scorecard", pathway `:183`), and it is the number a challenger has to move. A 5× drop from 16 is
**≤ 3.2 prompts for a release of comparable scope**.

Two honesties about it:

1. The hand scorecard's own `frontier_turns` block says the figure is **"not packet-isolated"** —
   one session produced eleven packets, eleven oracles by subagent, eleven reference patches, a
   CI gate fix (#83) and the scorecard itself. 1.45 is a ratio over the whole session, not a
   measured marginal cost per packet. The marginal cost of the twelfth packet is plausibly lower
   than 1.45 and is not measured.
2. Most of those 16 turns were **judgment work** — writing the packet's purpose text and its
   reference patch — not supervision. The handover's §3h reference-patch section measures the
   reference at "roughly one coordinator turn each", eleven for eleven passing their
   independently-authored oracle first try. Restate cannot make a packet's purpose text write
   itself.

---

## 3. What the challenger must beat: the delta over the driver, not over the memory

The correct question is not "what does Restate do that a frontier session does badly", it is
**"what does `dispatch_release.py` not do that a durable execution runtime would"**. Candidate
by candidate, honestly:

| Capability | Does the driver have it today? | Verdict |
|---|---|---|
| Fan-out across 4–8 concurrent packets | **No.** `drive()` takes exactly one packet path and runs one `while True` attempt loop over `STEPS` (`:645-808`). There is no scheduler, no concurrency, no join. | **Real gap.** The only unambiguous one. |
| Join barrier / aggregate verdict over N packets | **No.** Nothing in the repo aggregates N receipts into one release verdict except `release_scorecard.py`, which is a post-hoc reporter over a time window and receipt directory, not a barrier. | **Real gap**, downstream of the first. |
| Durable state across a coordinator session boundary | **Partly present.** T-11 was frozen at the previous session's checkpoint and dispatched the next day; only `claim_id` moved, `starting_commit 1a780314` was untouched (hand scorecard, `V5-T11-worse-signal.note`). The freeze — a git commit plus a JSON packet on disk — *is* the durable state, and it survived a session boundary intact once, observed. What is **not** durable is an *in-flight* run: kill the driver mid-`run` and the worktree, the attempts file and the auditctl trail are what is left; there is no resumable execution log. | **Narrow gap.** State survives; *execution position* does not. Do not claim the blanket version. |
| Retry with backoff across **infrastructure** failure | **No.** `MAX_GATE_ATTEMPTS = 2` retries a **red gate** only, with no backoff, and the comment at `:797-800` is explicit that a stage exiting non-zero "never produced a verdict to feed back". A network blip in `gh pr create` escalates and stops (`pr_failed`, `:816`). | **Real gap**, and a small one: measured infra failures in the T-series = 0. |
| Timers / scheduled resumption | **No.** No timer exists anywhere in the loop. | Gap with **no demonstrated demand**. |
| Surviving the coordinator machine going away mid-run | **No.** Everything is local to devbox: worktrees under `/tmp/actionq-hybrid/worktrees` (`actionq.dispatch.json` `hybrid.worktree_root`), the attempts file beside them, the driver process itself. | **Real gap**, but see §6 — Restate on appservice moves the *orchestration* off devbox, not the *workers*, who must still run where the repo and the uv cache are. |
| Queue with backpressure when releases contend | **No**, and `prepare_workspace` (`:998`) *hard-refuses* two workers in one workspace, so contention today is an error rather than a queue. | Gap with **no demonstrated demand**: one coordinator, one release at a time. |

**Summary of the delta.** Of seven candidate capabilities, exactly one is both absent and
currently wanted: **fan-out with a join barrier.** Two more (infra retry, crash-resumption) are
absent and would be nice; four have no observed demand in this project. That is a thin brief for
a cluster service.

---

## 4. The pilot envelope: one actionq review round as 4–8 parallel packets

### 4a. What a real actionq review round looks like

Read from the repo, not invented. `/projects/dev/actionq/docs/evidence/w3-review-rounds.jsonl`
records four W3 rounds:

| round | reviewed_head → fix_head | channels | findings_total | claim / line | mech-failure rounds |
|---|---|---|---|---|---|
| 1 | 96e184b → 2ba3475 | pr_gate 7 | 7 | 2 / 5 | 1 |
| 2 | 2ba3475 → 4014081 | pr_gate 10, opus_design 6 | 16 | 3 / 13 | 1 |
| 3 | 4014081 → fc76635 | pr_gate 8, opus_design 7 | 15 | 4 / 11 | 1 |
| 4 | fc76635 → 4da9256 | pr_gate 4, opus_design 8 | 12 | 3 / 9 | 1 |

`/projects/dev/actionq/docs/evidence/w3-finding-records.jsonl` carries 32 per-finding records
against schema `actionq/review-finding-record/v1`
(`docs/evidence/finding-record-schema.json`), whose `baseline_definition` already draws exactly
the line the pilot needs:

> `eligible_for_cheap_tier`: `classification == 'line'`. A claim-level finding changes what the
> plan asserts, so it routes to the plan tier by definition and is never handed to the implement
> tier.

Distribution over the 32 records: 18 `line` / 14 `claim`; per round `routed_to == implement` is
**5, 2, 3, 8**. Note the records are **partial** for rounds 2–4 (7 vs 16, 7 vs 15, 11 vs 12
against `findings_total`) — the schema's own `known_limits` says per-finding `first_attempt_pass`
for W3 is "genuinely unrecoverable, not merely unrecorded", and 13 of 32 carry a measured value,
all `implemented_by: opus`.

**The mechanical part of a round is already automated and already understood.** All four rounds
recorded the same mechanical failure — suite run before regenerating derived artifacts — and
`verification/run_round_checks.py` exists precisely to fix the *ordering*: reachability manifest
→ seven verification packets → suite twice → wheel. Its docstring calls that "orchestration work
rather than engineering work, and the first thing an orchestrator should own", and it has owned
it since. **The polling half of an actionq round has already been eaten by a 260-line script**,
the same way the dispatch half was eaten by `dispatch_release.py`. That is the second time the
cheap tool got there first, and it should be read as a pattern.

### 4b. Reshaping a round into 4–8 packets

Take a single round's findings, of which the `line`-classified subset is the fan-out candidate
(5–8 per round on the W3 evidence — inside the D-9 envelope without padding). One packet per
line-level finding:

- `task_id` per finding, carrying the finding `id` (`w3-r4-g02`) so a receipt joins back to
  `w3-finding-records.jsonl` without a lookup table;
- `purpose` = the finding `summary` plus the seam, which is what the T-series proved sufficient
  (eleven references, eleven first-try greens against independently authored oracles);
- `oracle.starts_red` = the falsifier that the finding turns red, plus `oracle.reference_patch`
  under `docs/evidence/packets/`;
- `starting_commit` = the round's `reviewed_head`, identical across all packets in the fan-out.

**What makes two fix-tasks independent enough to run in parallel** is not "they are different
findings" — it is a *declared, disjoint* `writable_patch_paths` per packet plus a
non-overlapping oracle. The existing gate already enforces the first half: `post_gates`
(`hybrid_dispatch.py:1760`) computes `out_of_scope = [p for p in touched if not
_matches_any(p, packet["writable_patch_paths"])]` and reds `diff-scope-respected`. So a fan-out
scheduler does not need a new independence check; it needs a **freeze-time** check that the
union of the N packets' `writable_patch_paths` is pairwise disjoint. That check does not exist
today and is roughly twenty lines. It is not a durable-execution feature.

The residue that parallelism does *not* solve is **collateral breakage**, which the finding
schema keeps as a field distinct from `first_attempt_pass` precisely because "a fix can pass its
own falsifier and break another" — and W3 round 3 introduced a regression that "produced no red
test at all and was caught only by review". Disjoint write paths do not make a suite disjoint.
This is the join barrier's real job (§4d).

### 4c. Four hard obstacles the envelope hits in actionq, none of them Restate's fault

These are the findings that most change the shape of the pilot, and all four are read directly
from `/projects/dev/actionq/actionq.dispatch.json`.

1. **Almost no line-level fix is worker-eligible in actionq.** `hybrid.protected_paths` includes
   `actionq/**` in its entirety, plus `pyproject.toml`, `.github/**`, `AGENTS.md`,
   `tests/conftest.py` and three named authority tests. The manifest's own notes say it plainly:
   *"Worker-eligible surface in this repository is therefore `tests/` (excluding the authority
   tests listed above), `docs/`, `verification/contexts/`, and `README.md`. A packet that needs
   to change `actionq/` is a coordinator packet by definition."* A W3 line-level finding such as
   "`is_backfilled_change`'s positional fallback assumed a column index wrong for the module's
   own query" (`w3-r4-g02`) is a change to `actionq/`. **It cannot be a worker packet at all
   under the current manifest.** Either the pilot fans out packets that mostly cannot be
   dispatched, or the manifest is widened — which is an authority decision for the owner, not a
   pilot parameter (§9, owner).
2. **Every actionq packet needs a coordinator-written review record.** `self_candidate_class`
   (`hybrid_dispatch.py:1806`) mints a candidate without a review record only when
   `routing.action_classes[<route>].self_candidate` is `true`. In `actionq.dispatch.json` no
   class carries that key at all, and D-8's promotion rule requires N≥5 first-pass greens with
   zero escalations *measured by R4.3* before a class qualifies. actionq has zero such greens on
   record. So **8 parallel packets = 8 coordinator-authored review JSONs = frontier turns that
   scale linearly with fan-out width**, which is the exact opposite of what the pilot is trying
   to demonstrate. Fan-out reduces *wall time*; without a self-candidate flip it does not reduce
   *turns*.
3. **The round's own gate cannot be a packet gate.** `run_round_checks.py` requires
   `initdb`/`pg_ctl` (`_require_postgres`), regenerates seven verification packets, and runs the
   suite twice plus a wheel build. `actionq.dispatch.json`'s notes state that only the
   non-PostgreSQL subsets are registered as commands, because "a gate that cannot pass cold is
   not a gate", and that "PostgreSQL verification stays with the coordinator". The join barrier
   therefore runs **outside** any packet, on a host with Postgres — i.e. on devbox, i.e. not on
   the cluster where Restate would sit.
4. **Commit 1 of every freeze mutates one protected file.** The T-series found that
   `.github/workflows/protected-paths.yml` was structurally red on every hybrid packet PR
   because commit 1 of each freeze branch registers the packet oracle's command id under
   `hybrid.commands` in the repo's `*.dispatch.json`, a protected path (handover §3h, "Rule 14
   was crying wolf"). Fixed in #83 for **`agentops.dispatch.json` only**. Eight parallel freezes
   in actionq each append a key to `actionq.dispatch.json` at the same `starting_commit` — eight
   branches, eight conflicting edits to one JSON file, converging at merge. actionq has no
   equivalent exemption (its `.github/workflows/` holds only `ci.yml` and
   `release-actionq-wheel.yaml`). **This is a genuine fan-out blocker in the freeze shape, and
   Restate does not touch it**: it is a git-level conflict, not an orchestration one.

Obstacle 4 is the one I would put in front of the owner first, because it says something
uncomfortable: **the freeze shape is currently serial by construction**, and making it parallel
is packet-contract work in `hybrid_dispatch.py`, not runtime work.

### 4d. The join barrier

After N packets reach `candidate`, the barrier must:

1. verify the N diffs still apply disjointly (they were gated individually against
   `starting_commit`, never against each other);
2. merge them into one integration branch;
3. run `verification/run_round_checks.py` — the full sequence, Postgres and all — **once**, not N
   times, which is where the parallel shape actually pays;
4. attribute any red to a specific packet, which the per-packet `writable_patch_paths` makes
   mechanical but the collateral-breakage case makes fallible;
5. record the round: append to `w3-review-rounds.jsonl` (which
   `run_round_checks.py --record-round N` already does, `_append_round_record:158`, and which
   deliberately leaves counts and classification hand-written because "an orchestrator that
   filled them in would be deciding rather than recording"), and set
   `first_attempt_pass` / `collateral_breakage` per finding in `w3-finding-records.jsonl` — the
   two fields the schema's `known_limits` says W3 could never measure because fixes were
   batched.

**That last point is the strongest independent reason to run a fan-out pilot at all, and it has
nothing to do with Restate.** One packet per finding is exactly the shape that makes per-finding
`first_attempt_pass` measurable for the first time, which is what pathway obstacle O9 ("cheap-vs-
expensive tier is unmeasured; first-attempt-pass baseline 'unrecoverable'") needs and what the
v7 falsifier's second clause ("cheap-tier first-pass ≥ agreed threshold") is read from.

### 4e. What carries over from the existing contract, and what does not

**Carries over unchanged:** the `agentops-task/v2` packet contract and its twenty required
fields (`hybrid_dispatch.py:59`); `prepare`'s cold gate; L-2a oracle attainability (each
`starts_red` command run at `starting_commit` in a throwaway checkout, red for a reason other
than absence); L-2b both halves (reference-patch overlay must turn the oracle green within
`writable_patch_paths`; strace read-trace); `post_gates`' five gates; the receipt; the secret
scan; `_preflight_stop` and the four stop conditions.

**Does not carry over, and needs new design:**

- **Pairwise-disjointness across a packet set.** Every existing check is single-packet. There is
  no group-level validation anywhere.
- **The sprintctl reservation.** `verify_live_coordinator_claim` (`:417`) reads one active
  reservation per `sprint_item.ref` and rejects if it is idle beyond four hours. N packets on
  one round share one item, so they share one reservation id — which is fine, but a long fan-out
  can idle the reservation past the horizon while it is legitimately in flight. `sprintctl
  reservation touch` is the intended remedy and nothing currently calls it automatically. **A
  durable orchestrator holding a timer is one honest use for Restate here** — and it is also
  four lines of `subprocess` in a scheduler.
- **The worktree guard.** `prepare_workspace:998` refuses to dispatch into an existing workspace
  unless the packet is a declared retry. Worktree paths are
  `<worktree_root>/<repo_id>/<task_id>`, so distinct task ids do not collide — parallel is safe
  here — but N concurrent `git clone --no-hardlinks` of actionq into `/tmp` is N full object
  stores, and nobody has measured the disk or IO cost of eight at once.
- **The packet schema file.** `templates/dispatch/hybrid/task-packet.schema.json` was realigned
  on 2026-08-25 in #97 (hand-pass), and the live validator still checks required fields by hand
  because there is no `jsonschema` on the host. Any fan-out group descriptor would have to
  decide whether it is a new schema or a list of existing packets. **Prefer a list of existing
  packets plus a thin group file**; a new packet schema version to express fan-out would put the
  contract's blast radius inside the pilot.

---

## 5. Architecture sketch, and what each Restate feature would replace or duplicate

```
              owner
                │  (turns: this is the number under test)
                ▼
   coordinator frontier session ──── writes N packets + N reference patches
                │                     (judgment; NOT replaceable by any runtime)
                │ freeze: commit 1 (oracle) + commit 2 (packet), per packet
                ▼
        ┌───────────────────────────────────┐
        │  FAN-OUT SCHEDULER  (the seam)    │  ← the only thing in dispute
        │  cheap control: dispatch_release  │
        │      --fan-out N  (new mode)      │
        │  challenger: Restate workflow on  │
        │      appservice, calling out      │
        └───────────────────────────────────┘
                │        │        │
                ▼        ▼        ▼          (N = 4–8, concurrent)
        dispatch_release.py per packet  ──►  hybrid_dispatch stages
          prepare → run → gate → receipt      │
                                              ├─ worker: OpenCode, devbox, agentworker uid
                                              ├─ sprintctl: reservation read (coordinator-side)
                                              └─ auditctl: workflow.escalation / workflow.session
                │        │        │
                └────────┴────────┘
                         ▼
                 JOIN BARRIER (devbox — needs Postgres)
                 disjointness recheck → integration branch
                 → run_round_checks.py once → attribute reds
                 → append round record + per-finding measurements
                         ▼
                 release_scorecard.py --release <id> --project <p>
```

Explicitly, feature by feature, what Restate would **replace** versus **duplicate**:

| Restate feature | In this architecture it would… |
|---|---|
| Durable workflow / journaled steps | **Duplicate** the freeze. The packet JSON + `starting_commit` + the attempts file are already the durable record of intent, and a git commit is a stronger checkpoint than a journal entry. It would *add* durability only for *execution position* inside a run. |
| Retries | **Duplicate** `MAX_GATE_ATTEMPTS`/`RETRY_STEPS`, and the driver's version is *semantically richer* — it appends the red gate's stdout/stderr into the retry packet's `purpose` (`build_retry_packet:617`, with a comment explaining that a retry which only sets a sibling key re-runs the same dispatch). A generic runtime retry cannot do that. Restate would have to call *into* the driver's retry, not replace it. |
| Timers | **Add**: sprintctl reservation touch; a per-packet wall-clock ceiling above `max_timeout_seconds`. Small, real, and also achievable with `threading.Timer`. |
| Virtual queues / keyed concurrency | **Add**, with no demonstrated demand (§3). Would become real only if several releases contend, which has never happened. |
| Fan-out / join primitives | **Add.** The genuine gap. |
| Observability / invocation history | **Duplicate** auditctl (`workflow.session`, `workflow.escalation`) and the driver report JSON. A second observability sink with different semantics is a §2a-shaped risk, not a benefit. |
| Service discovery / RPC | **Add**, and add a *requirement*: the workers run on devbox as the `agentworker` uid against a warm uv cache with `network_policy: disabled`. A cluster-side Restate cannot run them; it can only *call* something on devbox that does. That inverts the network direction — cluster → devbox — and needs a listener on devbox that does not exist. **This is the single largest unpriced item in the whole design.** |

---

## 6. Placement and operational surface (cost side; the placement decision itself is settled)

Restate goes on the appservice cluster. That is decided. What it costs, read from
`/projects/dev/appservice/docs/service-deployment-guide.md` and the existing app tree:

- **A GitOps service directory.** `clusters/main/kubernetes/apps/restate/{ks.yaml,app/…}` with
  `kustomization.yaml`, `helm-release.yaml` or a plain Deployment, `namespace.yaml`, and an entry
  in `apps/kustomization.yaml`. Flux prunes anything hand-applied (pathway obstacle O4), so there
  is no "try it by hand" path — the first experiment is a committed cluster change. That is
  precisely why L-6 is design-only.
- **A PVC, and therefore a backup story.** Existing stateful neighbours carry real ones:
  `apps/actionq-db/app/` holds `scheduled-backup.yaml`, `backup-credentials.yaml` and
  `cnpg-restore-drill.yaml`. A Restate PVC with no scheduled backup and no restore drill is a
  new unbacked stateful service in a cluster whose convention is that stateful services are
  backed up and rehearsed. Either the pilot writes that (volsync per
  `docs/backups-volsync.md`, or an equivalent) or it knowingly ships an exception.
- **An upgrade story.** Restate is a single binary with an on-disk state format. Nobody in this
  project has upgraded one. **Open question (§9, repo-answerable only by reading upstream, which
  I could not do — no network): whether Restate's on-disk state is forward-compatible across
  minor versions, and what its documented upgrade procedure is.** I did not verify this and do
  not assert it.
- **A network path that currently does not exist.** Cluster-internal, no ingress, per the memory.
  But §5's last row: the workers are on devbox. Either devbox exposes a listener to the cluster,
  or the driver stays devbox-side and *polls* Restate — which reintroduces a poll loop, in a
  different place, to remove a poll loop that no longer exists.
- **What breaks when it is down, and who notices.** If the fan-out orchestrator is the only path
  to dispatch, a Restate outage stops all dispatch — and a release loop that cannot run because
  a cluster pod is unhealthy is strictly worse than one that runs from a laptop. If it is *not*
  the only path (the driver still works standalone), then Restate is optional infrastructure and
  the case for it weakens further. Nothing in the cluster's Gatus monitoring
  (`docs/gatus-monitoring-maintenance.md`) knows about it; adding a check is more surface.
- **A schema and a Python service.** The task-contract schema and the plan-compiler the memory
  names still do not exist. That is real code with real gates in a repo that already has 870
  tests and a protected-path regime.

Rough count of new operational objects on the smallest honest version: 1 namespace, 1 Deployment,
1 Service, 1 PVC, 1 backup schedule, 1 restore drill, 1 monitoring check, 1 schema, 1 service
codebase, 1 network path. **Against one measured gap (fan-out) with a control that costs one
new `--fan-out` flag.**

---

## 7. Evidence plan

**Instrument:** `templates/dispatch/scripts/release_scorecard.py`, unchanged. Do not write a new
measurement tool for the pilot; a challenger measured by its own instrument is not measured.

**Sinks, unchanged:** `/projects/dev/.claude/session-costs.jsonl` (frontier half, via the Stop
hook), `docs/evidence/receipts/` (worker half, via `worker_spend_from_receipt`), auditctl
`workflow.escalation` / `workflow.session`.

**Three scorecards, all produced by the same command shape:**

```
python templates/dispatch/scripts/release_scorecard.py \
  --release <id> --project actionq \
  --sink /projects/dev/.claude/session-costs.jsonl \
  --receipts docs/evidence/receipts \
  --since <ISO> --until <ISO> --out docs/evidence/scorecards/<id>.json
```

- **A — serial control.** One actionq review round run the way v5 ran: packets dispatched one at
  a time through `dispatch_release.py`. Release id `v6-actionq-round-serial`.
- **B — cheap fan-out control.** The same round, same packets, same `starting_commit`, dispatched
  through a `--fan-out` mode added to `dispatch_release.py`. Release id
  `v6-actionq-round-fanout-driver`.
- **C — challenger.** The same round, same packets, orchestrated by Restate. Release id
  `v6-actionq-round-fanout-restate`.

**`--project actionq` is mandatory on all three.** The sink is global; the T-series measured an
unscoped window overcounting the frontier half by 56% (handover §3h, "Second correction"). A
pilot report without a `scope` block naming project, since and until is not admissible.

**Fields compared, and nothing else:**

| Field | Why |
|---|---|
| `frontier.turns` | The falsifier's own number. §2b: human prompts. |
| `frontier.sessions` | Guards against moving turns into a second session and calling it a reduction. |
| `frontier.rework_rounds` | From the T-4 auditctl drain (red gate then a later retry of the same command). |
| `worker.first_pass_rate`, `worker.tasks`, `worker.attempts` | The v7 clause "cheap-tier first-pass ≥ agreed threshold". |
| `worker.billed_usd`, `worker.tokens` | The only money in the comparison. |
| `escalations.count`, `escalations.stop_conditions` | A challenger that halves turns and triples escalations has lost. |
| `cost_usd.frontier_usage_equivalent_usd` | **Comparison unit only.** Never summed with `billed_usd`; `commensurable: false` is in the schema for this reason. |
| wall-clock (`frontier.duration_s`, and per-packet `wall_seconds` from receipts) | Fan-out's real, expected win. Report it — and do not let it stand in for the turn reduction. |

**Additionally, outside the scorecard:** per-finding `first_attempt_pass` and
`collateral_breakage` appended to `w3-finding-records.jsonl` under the existing schema, one
record per packet (§4d). This is the pilot's most durable output regardless of which
orchestrator wins.

**Three-scorecard minimum for `detect_worse`.** `release_scorecard.detect_worse:217` reports
`insufficient_series` below three scorecards, and its signals (`rework`, `escalations`,
`cost_up_without_more_turns`) each need two consecutive worsening transitions. A/B/C give
exactly three, which is the floor and not a comfortable series. Do not claim a trend from it.

---

## 8. Falsifier and kill criteria

Written in the pathway's own style — a number, a comparison, and the artifact it is read from.

> **Falsifier L6-F1 (adoption).** Restate is adopted only if, for the same actionq review round
> reshaped into the same N packets at the same `starting_commit`:
>
> `C.frontier.turns ≤ 0.6 × B.frontier.turns`
>
> read from `docs/evidence/scorecards/v6-actionq-round-fanout-restate.json` and
> `…-fanout-driver.json`, both produced by `release_scorecard.py` with `--project actionq`,
> **while** `C.escalations.count ≤ B.escalations.count` and
> `C.worker.first_pass_rate ≥ B.worker.first_pass_rate`.
>
> The comparison is **C against B**, the driver's own fan-out mode — not against A, and never
> against the 30–60-turn figure in the orchestration doc, which describes a world this repo left
> on 2026-08-23.

> **Falsifier L6-F2 (the pilot's own worth, independent of the winner).** The fan-out shape is
> worth keeping only if `B.frontier.turns < A.frontier.turns` **and**
> `w3-finding-records.jsonl` gains at least N records with non-null `first_attempt_pass` for
> the round — i.e. the per-finding measurement that the W3 schema's `known_limits` calls
> unrecoverable becomes recoverable going forward.

**Kill criteria — stop and report rather than continue:**

1. **B beats or ties C on `frontier.turns`.** The gap was in the driver, not in the runtime.
   Ship `--fan-out`, do not deploy Restate.
2. **N cannot reach 4 worker-eligible packets** without widening `actionq.dispatch.json`'s
   `protected_paths` (§4c.1). The envelope is unrealizable in actionq as it stands; return to
   the owner with the manifest question rather than widening it inside a pilot.
3. **The parallel freeze cannot produce N non-conflicting branches** because of the
   `hybrid.commands` registration in the protected `actionq.dispatch.json` (§4c.4). This is a
   packet-contract defect; fix it before any runtime work, because it blocks B as well as C.
4. **Any escalation whose `stop_condition` is caused by the orchestrator rather than the work** —
   the T-11 shape, where `dispatch_release.py` took its packet positionally and a `--packet` flag
   landed in passthrough, writing an auditctl record meaning "the driver was called wrong". Two
   of these in the pilot means the orchestrator is the new failure mode.
5. **Restate's presence changes any figure a human reads without saying so** — a new sink, a new
   total, a duration that is wall-clock in one place and CPU in another. §2a. Three occurrences
   of this class in one week is the project's worst-attested failure mode and it is not tied to
   any particular tool.

### The honest null hypothesis, stated plainly

> **H0: the driver already captured most of the available gain, and the pilot will show Restate
> adding operational surface — a cluster service, a PVC, a backup and restore drill, a
> monitoring check, a contract schema, a Python service, a cluster→devbox network path and a new
> outage mode — without a measurable reduction in `frontier.turns`.**

I think H0 is **more likely than not**, for four reasons that are all in the evidence rather
than in taste:

1. 16 turns for 11 packets (§2b) leaves very little to remove. A 5× drop means ≤3.2 prompts for a
   comparable release, and most of the 16 were packet-writing and reference-patch turns that no
   runtime touches.
2. Without a `self_candidate` flip on an actionq class, coordinator review records scale *with*
   fan-out width (§4c.2), so the turn count may **rise** with N under both B and C.
3. The two obstacles that actually block fan-out today — protected-path eligibility and the
   `hybrid.commands` freeze conflict — are git and manifest problems that Restate cannot touch
   (§4c.1, §4c.4).
4. The pattern has now repeated twice: the dispatch/poll loop was eaten by `dispatch_release.py`,
   and the round-check ordering loop was eaten by `run_round_checks.py`. Both times the cheap
   deterministic script arrived before the runtime and took the gain.

**If H0 holds, the project should:** ship `dispatch_release.py --fan-out` (a scheduler over N
packets, a group descriptor with pairwise-disjoint `writable_patch_paths`, a join barrier that
runs `run_round_checks.py` once); add a reservation-touch timer; record D-9 as *challenger
evaluated, not adopted*, with scorecards B and C as the evidence; and leave G3.4's
"provider-neutral pilot" clause to be satisfied by a challenger with a demonstrated gap, chosen
later. **That is a successful outcome, not a failed one** — the register asks for a decision
about a challenger, not for a deployment.

---

## 9. Open questions

### Answerable by a further session from the repos

1. What is the **marginal** frontier-turn cost of packet number N+1? The T-series ratio is not
   packet-isolated (hand scorecard, `frontier_turns.figure`). A session could reconstruct it from
   the transcript rather than the aggregate, and the whole falsifier rests on it.
2. Exactly which W3 line-level findings would have been worker-eligible under
   `actionq.dispatch.json` as it stands? I read the policy and the finding summaries and expect
   the answer to be "almost none", but I did not classify all 18 `line` records path-by-path.
3. What is the disk and IO cost of 8 concurrent `git clone --no-hardlinks` of actionq into
   `/tmp/actionq-hybrid/worktrees`, and does devbox have the headroom?
4. Can 8 freeze branches be produced without conflicting on `hybrid.commands` — e.g. by
   registering all N command ids in a single pre-fan-out commit that every packet branches from?
   This is the cheapest candidate fix for §4c.4 and it is untested.
5. Does `verify_live_coordinator_claim`'s 4-hour staleness horizon bind on a realistic fan-out,
   and what is the wall-clock of a full W3-scale round?
6. What does `run_round_checks.py` cost in wall time on devbox (suite twice + seven packets +
   wheel)? That number decides whether "run the barrier once instead of N times" is a large win
   or a rounding error.

### Only the owner can decide

1. **Does actionq's worker-eligible surface widen?** `actionq/**` protected in full is why the
   envelope barely fits. Widening it is an authority decision with the manifest's own reasoning
   against it (owner authority over claim atomicity, the append-only event ledger, the operator
   write contract). **Recommendation: do not widen it for a pilot.**
2. **Does an actionq action class get `self_candidate: true`?** D-8's rule (N≥5 first-pass green,
   zero escalations, measured by R4.3) is not met in actionq. Without this, fan-out cannot reduce
   turns. **Recommendation: earn it in agentops first, where `mechanical_bulk` already has eleven
   greens, and revisit actionq afterwards.**
3. **Is a new unbacked stateful cluster service acceptable for an experiment**, or must the pilot
   ship the backup schedule and restore drill its neighbours carry?
4. **Is cluster→devbox network reachability acceptable at all?** If not, §5's last row makes the
   cluster placement architecturally awkward regardless of its operational merits — and that is a
   consequence of the settled placement, not a challenge to it.
5. **Is a challenger that wins only on wall-clock worth adopting?** The pathway's falsifier is
   about turns. If C halves wall-clock and moves turns by zero, that is a real result and the
   register does not say what to do with it.

### Facts about Restate I could not verify (no network access; not asserted anywhere above)

- Whether the single-binary deployment's on-disk state is forward-compatible across minor
  versions, and the documented upgrade procedure.
- Its backup/restore story for the state directory, and whether a filesystem-level PVC snapshot
  is a supported restore path.
- Whether it can invoke a service that is *not* reachable from the cluster, or whether every
  handler must be network-reachable from the Restate server (this determines whether §5's
  devbox listener is required or avoidable).
- Its resource footprint at rest, which decides whether "always-on" is cheap here.
- Whether its retry semantics can be made to *defer* to the driver's packet-mutating retry
  rather than duplicating it.

Every one of these must be answered from upstream documentation by the orchestration-planning
session **before** any manifest is written. Where this document needed one of these facts, it
said so instead of assuming.

---

## 10. What this document does **not** authorize

Mirroring D-10's style in the pathway register (`:171`) — "still **not authorized** by this doc".

This document authorizes **nothing beyond its own review**. Specifically it does not authorize:

1. Any manifest, `ks.yaml`, `HelmRelease`, Deployment, Service, PVC, NetworkPolicy or namespace
   in `/projects/dev/appservice`, nor any edit to `apps/kustomization.yaml`.
2. Any Restate binary, container image or chart being pulled, run or pinned anywhere.
3. Any change to `actionq.dispatch.json` — `protected_paths`, `hybrid.commands`,
   `routing.action_classes` or a `self_candidate` flip.
4. Any change to `agentops.dispatch.json`, the packet schema, `hybrid_dispatch.py` or
   `dispatch_release.py`, including the `--fan-out` mode this document recommends. That is a
   separate packet with its own oracle.
5. Any task-contract schema or plan-compiler service.
6. Dispatching a real actionq review round in any shape.
7. Recording D-9 as decided. **D-9 remains open.** This document is the analysis the register
   asks for ("orchestration-planning session; not before v6"), not the decision.

The next authorized step is **owner review of this document**, which closes L-6's gate ("design
doc reviewed") and nothing else.

---

## Provenance

Read while writing, with the lines relied on:

- `/projects/dev/vuoro/docs/plans/2026-08-23-requirements-pathway-v5-v7.md` — `:112-113` (G3.4),
  `:170` (D-9), `:171` (D-10 style), `:183` (v7 proving point), §5 gate set.
- `docs/plans/agentops/2026-08-23-handoff-loop-and-telemetry.md` — Track T/L tables; L-6 row.
- `docs/dispatch/handover-2026-08-23-metanarrative-v5.md` — §3e–§3i in full; §3h for the
  imputed-vs-billed correction, the Rule 14 `hybrid.commands` finding, and the reference-patch
  cost; §3i for T-11's session-boundary freeze.
- `docs/evidence/scorecards/v5-t-series.generated.json` (schema v1 — the baseline) and
  `v5-t-series.json` (schema v0 — narrative).
- `templates/dispatch/scripts/dispatch_release.py` — `:43` STEPS, `:47` MAX_GATE_ATTEMPTS,
  `:61` STOP_CONDITIONS, `:348` write_escalation, `:617` build_retry_packet, `:645` drive.
- `templates/dispatch/scripts/hybrid_dispatch.py` — `:59` REQUIRED_PACKET_FIELDS, `:417`
  verify_live_coordinator_claim, `:742` worktree_path, `:984` prepare_workspace, `:1760`
  post_gates, `:1806` self_candidate_class.
- `templates/dispatch/scripts/release_scorecard.py` — `:208` detect_worse.
- `templates/dispatch/hooks/log-session-cost.sh` — `:115` the definition of `turns`.
- `/projects/dev/actionq/verification/run_round_checks.py` — module docstring, `:74`
  `_require_postgres`, `:158` `_append_round_record`.
- `/projects/dev/actionq/docs/evidence/w3-review-rounds.jsonl` (4 rows),
  `w3-finding-records.jsonl` (32 rows), `finding-record-schema.json`.
- `/projects/dev/actionq/actionq.dispatch.json` — `hybrid.protected_paths`, `hybrid.commands`,
  `hybrid.notes`, `routing.action_classes`.
- `/projects/dev/appservice/docs/service-deployment-guide.md`;
  `clusters/main/kubernetes/apps/` tree, `apps/actionq-db/app/` for the stateful convention.
- Memory `orchestration-restate-pilot` (2026-08-21) — origin, pilot workload, placement.

Not read, because there is no network access from this session: anything on restate.dev. Every
Restate-specific claim above is marked as an open question rather than asserted.
