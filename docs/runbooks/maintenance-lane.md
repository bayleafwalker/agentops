# Maintenance lane

**Status:** proposed working practice (2026-09-14). Nothing here grants a model
tier authority it does not already have in `docs/dispatch/model-routing.md`, and
nothing here qualifies a worker route. Availability is not qualification.

The maintenance lane is a standing backlog of bounded engineering items that
cheaper Claude tiers and local inference work through, with a frontier
coordinator selecting, reviewing and integrating. It is the **intake and
measurement** layer. Contained OpenCode execution still follows
[`hybrid-dispatch.md`](hybrid-dispatch.md) unchanged; this runbook does not
fork that driver, its packet schema or its gates.

## Backlog home

One served sprintctl backlog in this repository:

| Field | Value |
|---|---|
| Sprint | `559` `maintenance-lane` (`kind: backlog`, `status: active`) |
| Backend | served, profile `environment-record/profiles/workstation-vuoro-shared.json` |

Items name their **target repository** in the description; the sprint lives
here because routing policy and the dispatch practice live here. Use the
repository's `.envrc`, or export the two non-secret variables explicitly:

```bash
export SPRINTCTL_BACKEND=served
export SPRINTCTL_VUORO_PROFILE=/projects/dev/agentops/environment-record/profiles/workstation-vuoro-shared.json
sprintctl item list --sprint-id 559 --json
```

## What belongs in the lane

An item is lane-eligible only if **all** hold:

- The change is bounded: a known fix, a mechanical refactor, tests for existing
  behaviour, a small tool with a written interface, a read-only analysis.
- Acceptance is checkable by a command or an explicit review question.
- It touches no enforcement boundary: gates, budgets, ACLs, hooks, credentials,
  deployments, cluster state, production data or queues. Those items may sit in
  the backlog for tracking, but their tier is `frontier-plan` or `operator` and
  cheap workers do not take them.

Route by boundedness and uncertainty, not diff size (`model-routing.md`).

### Item description template

```text
Repo: <owning repository>
Tier: clerical | fast-build | local | expert | frontier-plan | operator
Problem: <observed defect or gap, with evidence>
Scope: <what to change; what not to change>
Acceptance: <checkable outcomes>
Validation: <exact commands>
Writable: <paths the worker may modify>
Blocked-on: <decision or item, if any>
```

## Tiers

| Tier | Who works it | Use for |
|---|---|---|
| `clerical` | Claude Haiku (`clerical` alias) | Read-only triage, formatting, mechanical edits with a literal spec |
| `fast-build` | Claude Sonnet via `worker` agent, or Codex Spark | Bounded implementation with tests |
| `local` | `local3090/worker-fast` or `local3090/devstral` via OpenCode | **Sandbox/advisory only** — `supervised-experiment` and `corpus-run` task classes as defined in [`model-routing.md`](../dispatch/model-routing.md#unqualified-local-models-sandboxadvisory-allowlist); unqualified, results go to the local-inference scorecard; see [Local model qualification](#local-model-qualification) below |
| `expert` | Claude Sonnet via `expert` agent | Read-only analysis of current behaviour |
| `frontier-plan` / `operator` | Frontier coordinator / human | Design, enforcement boundaries, anything needing approval |

A worker that fails an item twice at one tier escalates one tier with a
`lane.review` note saying why; it does not retry indefinitely.

## Roles

- **Coordinator** (frontier session): selects items, writes the brief, reviews,
  integrates, and owns sprintctl item state. Workers never change sprintctl.
- **Worker** (`.claude/agents/worker.md`): one item, own worktree, proves the
  change with the repository's tests, commits on its branch, never pushes.
- **Expert** (`.claude/agents/expert.md`): analysis items; evidence tagged
  verified / inferred / unknown.
- **Sage** (`.claude/agents/sage.md`): answers mid-item design questions so the
  worker brief does not have to guess.
- **Oracle** (`.claude/agents/oracle.md`): keeps the lane pointed at recorded
  target state; proposes adding or retiring items.

## The loop

1. **Select.** Highest priority `pending` item whose `Tier` matches available
   capacity and whose `Blocked-on` is clear.
2. **Dispatch.** Mark it active and record the attempt:

   ```bash
   sprintctl item status --id <id> --status active --actor coordinator:<session>
   sprintctl item note --id <id> --type lane.dispatch \
     --summary "Dispatched to worker (<model>, <tier>)" \
     --tags "lane,tier:<tier>,model:<model>,harness:<claude-subagent|opencode|codex>" \
     --git-branch <branch> --git-worktree <path> --actor coordinator:<session>
   ```

   In served mode sprintctl ignores `--actor` and records the authenticated
   identity (e.g. `workstation-vuoro`), so attribution that matters for
   metrics (tier, model, harness, `agent:<id>`) must be in `--tags`.

   Worktrees go under `/projects/dev/_wt/<repo>-<slug>` from the repository's
   `origin/<default>`; the brief carries the item text verbatim plus the
   attribution lines. OpenCode packets use `hybrid_dispatch.py` as documented.
3. **Review.** The coordinator, not the worker, decides acceptance:
   - the diff touches only `Writable` paths;
   - the validation commands pass when re-run by the coordinator in the worktree;
   - the acceptance criteria are met; tests that encoded old behaviour were
     replaced only where the item made them wrong.
4. **Record the verdict** on the item:

   ```bash
   sprintctl item note --id <id> --type lane.review \
     --summary "<accepted|rework|rejected|escalated>: <one line>" \
     --tags "lane,verdict:<verdict>,<first-pass|attempt:N>,tier:<tier>,model:<model>" \
     --git-sha <commit> --actor coordinator:<session>
   ```

5. **Integrate** per the owning repository's convention (pull request from the
   worktree branch in PR repositories; human merge). Mark the item `done` when
   the change has landed, or back to `pending` with a `rework` note.

## Telemetry

The lane adds no new store. It joins records that already exist:

| Source | What it gives |
|---|---|
| sprintctl item notes `lane.dispatch` / `lane.review` | tier, model, verdict, attempt number, commit |
| auditctl `dispatch.exit` (written by `hooks/subagent-exit.sh`) | agent id, terminal reason, transcript path, reset time |
| Subagent transcript (`transcript_path`) | model and per-message usage; de-duplicate by `message.id` (one message can span several records) |
| `local-inference/benchmarks/scorecard.csv` | local-model attempts: tests passed, accepted, wall time, tokens |

`/projects/dev/.claude/session-costs.jsonl` covers top-level sessions only; it
cannot measure worker tiers. Costs derived from transcripts are **list price**,
not subscription spend. A `completed` terminal reason means the process ended
normally, not that the work was right; only `lane.review` says that.

### Metrics, per tier and per model

- first-pass acceptance rate (`verdict:accepted` with `first-pass`);
- rework, rejection and escalation rates;
- input and output tokens per accepted item, and peak context;
- worker wall time per accepted item;
- abnormal exit rate (`dispatch.exit` terminal reasons other than `completed`).

### Check-up

Weekly, or after every ten lane attempts, the coordinator:

1. lists items `active` for more than a day without a `lane.review` note;
2. computes the metrics above for the window;
3. records a `lane.checkup` note on the sprint's oldest open item, or opens an
   item when a tier's first-pass acceptance falls below the level the operator
   has accepted for it.

Thresholds for "a tier is good enough for an item class" are **not set yet**
for `clerical`, `fast-build`, and `expert`. Propose them from at least ten
reviewed attempts per tier; the operator accepts them. The `local` tier does
not use this flat count — see below.

## Local model qualification

This section is the qualification standard referenced from
[`model-routing.md`'s sandbox/advisory allowlist](../dispatch/model-routing.md#unqualified-local-models-sandboxadvisory-allowlist).
It replaces a flat "≥10 attempts" threshold for the `local` tier with a
per-task-class sampling floor, class-specific pass criteria, and a
zero-critical-failure rule. It governs only `local_workstation` routes
(`local3090/worker-fast`, `local3090/devstral`); it does not change the
generic tier threshold above for `clerical`, `fast-build`, or `expert`.

**Task classes.** An unqualified local route is dispatched only as one of:

- `supervised-experiment` — one bounded implementation attempt in a disposable
  worktree, reviewed by the coordinator or `expert` before any part of it is
  reused.
- `corpus-run` — a batch generation or transformation over an existing corpus,
  scored in `local-inference/benchmarks/scorecard.csv`.

**Sampling floor — proposed, operator to confirm.** At least **20 reviewed
attempts per task class per model** (e.g. 20 `supervised-experiment` attempts
and, separately, 20 `corpus-run` attempts for `local3090/worker-fast`, and the
same again for `devstral` before it qualifies independently), each recorded
in the scorecard with tier, model, task class, and verdict. This floor is
double the prior generic ten-attempt count and is per class rather than
pooled, because a route qualifying on `corpus-run` volume says nothing about
its `supervised-experiment` judgment, and vice versa. It does not take effect
until the operator confirms it.

**Class-specific pass criteria**, evaluated once the sampling floor for that
class is met:

- `supervised-experiment`: first-pass acceptance rate over the sampled window
  meets or exceeds the level the operator has accepted for the class, the
  diff in every sampled attempt touched only the item's declared `Writable`
  paths, and no sampled attempt required more than one rework cycle before
  acceptance.
- `corpus-run`: a coordinator-reviewed sample of run output (size
  proportional to run volume, never smaller than the sampling floor) meets or
  exceeds the operator-accepted accuracy level for the class, with no
  fabricated or hallucinated corpus entries in the reviewed sample.

**Zero-critical-failure rule.** A **critical failure** is any of:

- a write to a protected path;
- a merge, or a push to a shared or tracked branch;
- use of a production credential;
- a cluster mutation;
- exposure of sensitive or production data.

One critical failure anywhere in the sampled window fails qualification for
that task class outright, regardless of the rest of the sample's pass rate.
It requires a `lane.review` note describing the failure and blocks further
`local`-tier dispatch in that task class until the coordinator records a
remediation and the sampling floor is met again from a clean window.
