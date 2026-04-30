# meta-sprint and cross-repo dispatch plan

A follow-on to `/projects/dev/agentops/docs/plans/agentops/agent-ops-substrate-plan.md`. The substrate plan seeds the answer: "meta-sprints are not architecturally special; they just have a designated `repo_id` (e.g. `_orchestration`)." This plan defines what that means in practice — the sprint model, the dispatch model, the operator UX, and the sequencing — without requiring schema changes to sprintctl or actionq.

## Goal

Give the operator a single ergonomic path for cross-repo work: one sprint item describes a multi-repo goal, one dispatch command fans it out, one cockpit row shows aggregate progress. The substrate tools (sprintctl, auditctl, actionq) gain no new concepts; the coordination layer sits entirely in `_orchestration` sprint state and the actionq parent-child action model that already exists.

## Core decisions (do not relitigate)

- **`_orchestration` is a `repo_id`, not a new sprint kind.** The sprintctl pg schema treats it identically to any other repo. No new columns, no new event types, no new CLI verbs in sprintctl. The operator creates and manages `_orchestration` sprints and items exactly as they do for any other repo.
- **Work spec lives in the actionq action payload, not in sprintctl.** The meta-sprint item in sprintctl is the human-readable description of intent. The actionq action's `payload` field carries the machine-readable fan-out spec (repos, action types, dependency order). These are separate concerns; keeping them separate avoids encoding execution details into the sprint data model.
- **Dependency ordering is explicit in the work spec, not inferred.** The dispatcher does not read diffs or reason about what changed. If repo B depends on repo A, the operator declares that dependency in the work spec. The dispatcher enforces it; no implicit topological analysis.
- **Child actions use the existing actionq parent-child model.** `parent_id` and `chain_depth` are already in the schema. No new tables or fields are needed to represent the fan-out. The parent action is the coordination unit; children are ordinary `scope-iterate` (or other) actions with a `parent_id` set.
- **Sequential and parallel dispatch are both first-class.** Sequential is the default because it allows each child agent to read the predecessor's output. Parallel is opt-in and appropriate when children are genuinely independent. The dispatch mode is declared per-spec, not per-action-type.
- **Handoff context flows as structured payload, not prompt prose.** When a sequential child depends on a predecessor, the dispatcher appends the predecessor's `result_ref` (branch, worktree path, head commit) to the child's dispatch payload. The child's prompt template references `{predecessor_result}` explicitly. The dispatcher does not summarise or interpret the predecessor's diff; the child agent reads it directly.
- **The cockpit shows cross-repo work via parent-action rollup, not via a new "meta" view.** The claims table already shows actionq sessions. A parent action row expands to show child rows. No new cockpit pane; source labels for children are per-repo as usual.
- **The `_orchestration` repo is always remote-mode.** It has no per-repo SQLite. There is no workstation-only meta-sprint. If the pg backend is unreachable, the operator cannot manage cross-repo sprints; that is an acceptable constraint.

## The `_orchestration` sprint

Create one sprint in sprintctl with `repo_id = "_orchestration"`:

```bash
SPRINTCTL_BACKEND=remote sprintctl sprint create \
  --name "substrate-wiring" \
  --status active
```

Items in this sprint describe cross-repo goals at the same granularity as items in any other sprint. Each item maps to one dispatched parent action.

```bash
sprintctl item add \
  --sprint-id <id> \
  --track infra \
  --title "Wire auditctl publisher into sprintctl remote-mode"

sprintctl item add \
  --sprint-id <id> \
  --track infra \
  --title "Extend actionq-daemon to emit sprintctl takeup on session boundaries"
```

Items carry notes and decisions just like any other sprintctl item. The `_orchestration` sprint's `sprintctl render` output is the human-readable record of cross-repo work history.

## Work spec schema

The actionq action for a meta-dispatch carries a `payload` field with this shape:

```json
{
  "goal": "Human-readable one-line description matching the sprintctl item title",
  "dispatch_mode": "sequential",
  "repos": [
    {
      "index": 0,
      "project": "auditctl",
      "action_type": "scope-iterate",
      "target": "publish client library interface",
      "source_refs": ["wi:42"],
      "depends_on": []
    },
    {
      "index": 1,
      "project": "sprintctl",
      "action_type": "scope-iterate",
      "target": "integrate auditctl publisher on remote-mode events",
      "source_refs": ["wi:43"],
      "depends_on": [0]
    }
  ]
}
```

`dispatch_mode` is `"sequential"` or `"parallel"`. `depends_on` lists indices from the same spec; it must be empty when `dispatch_mode` is `"parallel"`. `source_refs` references the per-repo sprintctl item so the agent can read sprint context before starting work.

The spec is not committed as a file. It lives in the actionq event log as the payload of the parent action, making it recoverable from the queue without a separate artifact store.

## Dispatcher-meta mode

`actionq-dispatcher` gains a `dispatcher-meta` entry point (or a `--meta` flag on `dispatcher-once`). Its job is to read a parent action's payload as a work spec and orchestrate child dispatch.

### Sequential mode

```
dispatcher-meta claims parent action
  for each repo in dependency order:
    enqueue child action (parent_id = parent.id, payload includes predecessor_result)
    wait for child to reach terminal state (completed / failed / rejected)
    if child failed or rejected: fail parent, stop
    extract child result_ref → predecessor_result for next child
  all children completed → complete parent
```

The wait loop polls `actionctl show <child_id>` at a configurable interval. It does not need a push mechanism; the parent action's claim deadline is set to the sum of child timeout budgets plus slack.

### Parallel mode

```
dispatcher-meta claims parent action
  enqueue all children simultaneously (parent_id = parent.id, no predecessor_result)
  poll until all reach terminal state
  if any failed or rejected: fail parent (other children may still run to completion)
  all completed → complete parent
```

Partial failure in parallel mode does not cancel siblings. The operator inspects the parent action to see which children failed and re-dispatches those individually.

### Predecessor result handoff

In sequential mode the dispatcher appends to each child's dispatch payload:

```json
{
  "predecessor_result": {
    "project": "auditctl",
    "branch": "agent/scope-iterate/17",
    "worktree": "/home/dev/.local/state/actionq-dispatcher/worktrees/auditctl/17",
    "commit": "abc123def456",
    "result_ref": "branch=agent/scope-iterate/17 commit=abc123def456"
  }
}
```

The child's prompt template receives `{predecessor_result}` as a structured variable. The concrete instruction to the agent is to read `git diff <commit> HEAD` in the named branch before starting work. The dispatcher does not summarise the diff; the agent does.

This requires that child A's branch is pushed (or at least the worktree is accessible on the shared mount) before child B starts. The existing post-gate `branch-exists` already enforces that child A produced a branch; the dispatcher additionally verifies the branch is reachable from child B's worktree root before enqueuing child B.

### Coordinator events

`dispatcher-meta` emits coordinator events into the parent action's event log:

```bash
actionctl emit --type coordinator_cycle --actor dispatcher-meta \
  --payload '{"phase": "fan-out", "children_enqueued": 2, "mode": "sequential"}'

actionctl emit --type coordinator_cycle --actor dispatcher-meta \
  --payload '{"phase": "child-complete", "child_id": 17, "index": 0, "status": "completed"}'

actionctl emit --type coordinator_cycle --actor dispatcher-meta \
  --payload '{"phase": "complete", "children_completed": 2}'
```

These appear in `actionctl show <parent_id>` alongside the child action ids, giving a full trace of the fan-out.

## Operator ergonomics

### CLI path (no cockpit required)

```bash
# 1. Create a meta-sprint item
SPRINTCTL_BACKEND=remote sprintctl item add \
  --sprint-id <orchestration-sprint-id> \
  --track infra \
  --title "Wire auditctl publisher into sprintctl remote-mode"

# 2. Enqueue the parent meta-dispatch action
actionctl add \
  --type meta-dispatch \
  --project _orchestration \
  --target "wi:<item-id>" \
  --created-by "human:cli" \
  --priority 50 \
  --payload '{
    "goal": "Wire auditctl publisher into sprintctl remote-mode",
    "dispatch_mode": "sequential",
    "repos": [
      {"index": 0, "project": "auditctl",  "action_type": "scope-iterate",
       "target": "publish client lib",       "depends_on": []},
      {"index": 1, "project": "sprintctl", "action_type": "scope-iterate",
       "target": "integrate auditctl publisher", "depends_on": [0]}
    ]
  }'

# 3. Run dispatcher-meta (or let cron pick it up)
dispatcher-meta --config /path/to/config.toml

# 4. Observe progress
actionctl show <parent-id>
actionctl sessions --active
```

The operator never manually enqueues the child actions. All fan-out is the dispatcher's job.

### Cockpit path

The cockpit claims table shows the parent action as a single row with a child-count badge (e.g. `2/2 children`). Expanding the row reveals one sub-row per child, each with its own repo label, heartbeat, and TTL from actionq. The dispatch composer gains a **Cross-repo** tab that renders the work spec form: goal field, dispatch mode selector, and an ordered list of repo entries with dependency arrows. Submitting posts to `actionq-server` the same way single-repo dispatch does.

The `_orchestration` repo appears in the cockpit's REMOTE group alongside the substrate repos. Its sprint hero shows the cross-repo sprint progress in the same burn-bar format. The takeup panel shows `_orchestration` as a separate row when a meta-dispatch session has taken it up.

### Ergonomic invariants

These must hold for the operator experience to work:

1. **One command to see all in-flight cross-repo work.** `actionctl sessions --project _orchestration` plus `actionctl ls --status pending --project _orchestration` covers the full picture without switching between repos.

2. **One command to pause all dispatch.** The existing pause-file mechanism applies to `dispatcher-meta` the same way it does to `dispatcher-once`. Creating the pause file stops both.

3. **Failure is always attributable.** A failed parent action shows which child failed and why. `actionctl show <parent-id>` names the failed child; `actionctl show <child-id>` shows the failure reason and any partial worktree left for inspection.

4. **Re-dispatch is per-child, not per-parent.** If child B fails after child A succeeded, the operator re-enqueues child B only (with the predecessor result from child A's completed action, which is in the event log). They do not restart the whole fan-out.

## auditctl integration

`dispatcher-meta` emits audit events at the same boundaries as `dispatcher-once`:

```bash
auditctl add --type dispatch   --source actionq-daemon --actor dispatcher-meta \
  --summary "Meta-dispatch started for _orchestration wi:<id>" \
  --refs "wi:<id>,sprint:<id>"

auditctl add --type session.start --source actionq-daemon --actor dispatcher-meta \
  --summary "Child dispatch: auditctl scope-iterate action <child-id>" \
  --refs "wi:<id>,sprint:<id>"
```

These land in the `_artifacts/_orchestration/audit/` shard, giving the operator a per-day record of all cross-repo dispatch activity separate from the per-repo audit shards.

## Implementation order

Each step is independently shippable. Stop after any of them and the system is coherent.

1. **`_orchestration` sprint.** Create the sprint in sprintctl remote-mode. No code changes. Validates that the existing pg schema handles `_orchestration` as a `repo_id` without special-casing. The cockpit should already show it in the REMOTE group.

2. **Work spec schema and validation.** Define the JSON schema for the work spec payload. Add a `dispatcher-meta validate --payload '...'` subcommand that parses and validates a spec without dispatching anything. Operator uses this to check specs before committing them to the queue.

3. **`dispatcher-meta` parallel mode.** Enqueues all children simultaneously, polls until terminal, marks parent complete or failed. No predecessor result passing yet. Covers the independent-repos case (e.g., adding documentation to three repos that don't depend on each other).

4. **`dispatcher-meta` sequential mode with predecessor result.** Adds the wait-for-predecessor loop, result extraction, and payload injection into child dispatch. Covers the common case where repo B's work depends on repo A's output.

5. **Cockpit parent-child rollup.** Claims table expands parent rows to show child rows. Child-count badge on parent. No new cockpit pane needed; this is a display change to the existing claims table component.

6. **Cockpit dispatch composer cross-repo tab.** Work spec form in the composer. Submits via the existing `/api/dispatch` gateway endpoint, which forwards to actionq-server.

7. **`_artifacts/_orchestration/audit/` rollout.** Wire `dispatcher-meta` audit emission. Verify the cockpit's right-pane audit feed shows `_orchestration` activity when that repo tab is selected.

Steps 1–2 are validation with no automation. Steps 3–4 are the dispatch core. Steps 5–7 are operator surface polish.

## Rejected paths

- **New "meta" sprint kind in sprintctl.** Adds schema complexity for no runtime benefit. `_orchestration` as a `repo_id` is already the right shape; the kind column stays as-is.
- **Work spec as a committed file in agentops.** Adds a config surface that diverges from the queue event log, which is the authoritative record of what was dispatched and when. The payload in the actionq action is the spec; the commit history is not.
- **Dispatcher reading predecessor diffs and summarising for child agents.** Too much responsibility in the dispatcher. The agent reads the branch; the dispatcher only passes the ref. Keeping the dispatcher dumb makes it predictable.
- **Cancelling siblings on partial failure in parallel mode.** Adds cancellation complexity and may waste completed work. Operator inspects and re-dispatches failed children. In practice, independent children should succeed or fail on their own terms.
- **Implicit dependency inference from imports or file overlap.** Requires the dispatcher to understand each language's module system. Explicit `depends_on` in the spec is boring and correct.
- **A shared "meta-dispatcher" sprint visible to all repo tabs in the cockpit.** `_orchestration` is its own REMOTE repo tab. Cross-repo aggregation already handled by the ALL view. No special cockpit treatment needed beyond parent-child row expansion in the claims table.

## Open items

- **`_orchestration` repo-id convention.** The leading underscore distinguishes it from real repos by name convention. Verify sprintctl's `repo_id` validation accepts leading underscores (it uses directory-name derivation; `_orchestration` would need to be manually set since no directory of that name exists on the shared mount).
- **Pause-file scope.** Should the pause file pause all dispatch (meta and single-repo) or support per-mode pause files? Probably a single pause file is correct for the single-operator homelab case; revisit if two operators ever run concurrent dispatchers.
- **Child claim_deadline calculation.** The parent action's claim deadline must exceed the sum of all child timeouts. The dispatcher should set `claim_deadline = now + sum(child.timeout_minutes) + slack` on the parent before beginning fan-out. Confirm `actionctl claim` supports a custom deadline at claim time or that the dispatcher updates it after claiming.
- **Re-dispatch ergonomics for failed children.** The operator needs to know the predecessor result for re-dispatching a failed child. This is in the parent action's event log, but reading it is not ergonomic today. A `dispatcher-meta retry --parent-id N --child-index M` convenience command would help; defer until the pattern is observed in practice.
- **`_artifacts/_orchestration/` directory on the NFS mount.** `AUDITCTL_ARTIFACTS_ROOT` resolves to `/projects/dev`, so `_artifacts/_orchestration/audit/` would be created automatically on first `auditctl add`. Verify the cockpit pod's read-only NFS mount exposes this path alongside the repo-specific artifact dirs.
