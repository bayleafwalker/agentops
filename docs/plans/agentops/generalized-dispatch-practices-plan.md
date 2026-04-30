# generalized dispatch practices plan

Companion to `agent-ops-substrate-plan.md` and `meta-sprint-cross-repo-dispatch-plan.md`.
Those plans define the substrate: sprint state in `sprintctl`, action/session lifecycle in
`actionq`, audit artifacts in `auditctl`, operator surface in `agentops`, and deployment in
`appservice`. This plan defines the reusable dispatch policy that should sit above those
pieces so `homelab-analytics` stops being the only mature example.

## Goal

Give every `/projects/dev` repo a small, predictable dispatch contract:

- repo-local guidance states what the repo needs;
- shared dispatch policy states how work is routed, claimed, verified, audited, and reviewed;
- actionq carries machine-readable dispatch intent;
- skills and hooks stay reusable by default, with repo overlays only where the repo differs.

The target is not one universal agent prompt. The target is one universal decision model with
repo-specific adapters.

## Source references

- `agentops/docs/ecosystem.md` defines the current tool boundaries and quickstart tracks.
- `agentops/docs/plans/agentops/agent-ops-substrate-plan.md` assigns ownership across
  `sprintctl`, `kctl`, `auditctl`, `actionq`, `agentops`, and `appservice`.
- `agentops/docs/plans/agentops/meta-sprint-cross-repo-dispatch-plan.md` defines
  `_orchestration`, parent-child action fan-out, sequential/parallel dispatch, and structured
  predecessor handoff.
- `homelab-analytics/AGENTS.md` is the strongest repo-local model today: planning/build/review
  dispatch tiers, sprintctl claim rules, and targeted verification.
- `homelab-analytics/.agents/skills/dispatch-*` shows the current reusable skill shape, but is
  still too repo-owned to copy verbatim.
- `actionq-dispatcher/actionq_dispatcher/routing.py` already implements the correct routing
  precedence: action explicit, project default, action-kind default, single global fallback.

## Core decisions

- **Dispatch policy belongs to `actionq` / `actionq-dispatcher`; dispatch documentation and
  operator UX belong to `agentops`.** Individual repos should describe their domain constraints,
  verification commands, and escalation rules, not reimplement the scheduler.
- **Model assignment is data, not prose.** The model and harness should resolve from structured
  action payload/config fields. Top-level `AGENTS.md` files may describe the policy, but the
  dispatcher must not depend on reading prose to choose a model.
- **Repo-local skills are overlays.** The default planning/build/review skills should be shared
  templates. Repos may override inputs, verification, specialist roster, or safety rules, but the
  skill lifecycle should stay recognizable across repos.
- **Hooks are publishers, not policy engines.** Git hooks, session hooks, and stop hooks should
  emit audit/session/cost events with stable fields. They should not decide sprint scope, model
  routing, or done criteria.
- **Claims remain orchestrator-owned.** Subagents and dispatched workers can receive item context,
  but claim tokens stay with the orchestrator/daemon identity. This matches the
  `homelab-analytics` practice and avoids ownership proof leaking across workers.
- **Sequential cross-repo work uses structured predecessor result handoff.** The dispatcher passes
  branch/worktree/commit/result refs. It does not summarize the predecessor diff.
- **Every dispatch has a reviewable scope boundary.** A scope may contain one item or a tight set
  of related items. Stable code-bearing scopes get review before handoff or PR prep.

## Dispatch packet

Every queued action should carry enough information for a worker to execute without reading a
large repo-specific command catalog:

```json
{
  "project": "homelab-analytics",
  "action_type": "scope-iterate",
  "target": "wi:365",
  "dispatch_class": "build",
  "harness": "claude",
  "model": "anthropic/claude-haiku-4-5-20251001",
  "source_refs": ["sprint:365", "doc:docs/plans/example.md"],
  "scope": {
    "goal": "Implement the accepted item",
    "allowed_paths": ["packages/example/", "tests/test_example.py"],
    "out_of_scope": ["deployment manifests"]
  },
  "verification": {
    "commands": ["pytest tests/test_example.py -x --tb=short"],
    "full_suite_required": false
  },
  "review": {
    "required": true,
    "mode": "findings-first"
  }
}
```

`harness` and `model` may be omitted when project/action defaults cover them. The dispatcher
records the resolved values and routing source in actionq events so cockpit can explain why a
session used a given model.

## Model routing

Use this precedence everywhere:

1. **Action explicit**: `harness` and/or `model` on the action payload. Use for unusual cost,
   context, risk, or benchmark cases.
2. **Project default**: repo config such as `projects.<repo>.default_harness` and
   `default_model`. Use for the normal build worker in that repo.
3. **Action-kind default**: dispatch class such as `plan`, `build`, `review`, `release-ops`.
4. **Single global fallback**: only valid when exactly one harness is configured.

Recommended default classes:

| Class | Typical use | Default model tier |
|---|---|---|
| `plan` | Architecture choices, ambiguous scope, multi-repo sequencing | frontier / Opus-equivalent |
| `build` | Approved, bounded implementation | fast low-cost model |
| `review` | Findings-first review of stable diff | mixed: cheap pattern checks plus stronger synthesis |
| `release-ops` | CI, PR, merge, deployment, rollback | strong general model |
| `meta-dispatch` | Cross-repo fan-out coordinator | deterministic coordinator, no creative model by default |

Repo-local `opencode.json`, Claude settings, or Codex defaults may remain for manual sessions,
but automated dispatch should use actionq routing config as the source of truth.

## Shared skills

Promote the current `homelab-analytics` skill pattern into shared templates with repo overlays:

- `dispatch-plan`: read-only planning; produces a decision-complete implementation brief.
- `dispatch-build`: implements approved scope; owns targeted checks and item-level verification.
- `dispatch-review`: read-only findings-first review; consolidates specialist outputs.
- `code-change-verification`: chooses scoped commands from changed files and repo policy.
- `pr-handoff-summary`: renders reviewer-ready handoff.
- `sprint-resume`, `sprint-packet`, `item-done`, `sprint-snapshot`, `kctl-extract`: keep as
  sprint/knowledge workflow skills with shared defaults.

Shared skill files should live in a template location owned by `agentops` or a future
`agentops/templates/skills/` directory. Repos should commit only:

- a manifest that selects shared skills;
- optional overlay fragments for repo-specific paths, test commands, architecture rules, and
  review specialists;
- tests that assert the repo guidance still references the selected skills.

Do not copy full skill bodies into every repo unless the repo has a real behavioral fork.

## Hooks

Standard hook classes:

| Hook | Owner | Purpose |
|---|---|---|
| Git `post-commit` / `post-merge` | `auditctl` | Publish commit/merge audit events |
| Session start/exit | `actionq-daemon` | Publish session lifecycle and sprint takeup/release |
| Stop/cost hook | workspace `.claude` / harness adapter | Append usage/cost accounting |
| Verification hook | dispatcher post-gates | Record test command and result for the action |
| PR hook | future actionq/github integration | Publish PR open/merge events |

Hook payloads should include `repo_id`, `actor`, `runtime_session_id` when available,
`action_id` when dispatched, refs (`wi:`, `sprint:`, `sha:`, `pr:`), summary, and timestamp.
Hooks should self-silence when their tool is missing, except dispatcher gates, which must fail
closed when they are part of the action contract.

## Repo adoption levels

Use three adoption levels instead of expecting every repo to become `homelab-analytics` at once:

1. **Guidance only**: `AGENTS.md`, mode docs, and local verification rules. No actionq dispatch.
2. **Observable repo**: adds `auditctl` hooks and `_artifacts/<repo>/audit` publication.
3. **Dispatchable repo**: adds actionq project config, shared dispatch skills, ACLs, gates, and
   optional sprintctl remote mode.

Remote sprintctl mode is required for cockpit-wide sprint coordination. It is not required for
basic audit publishing or manual local work.

## Implementation order

1. Define a shared dispatch manifest schema in `agentops` docs. Include selected skills, repo
   defaults, allowed action classes, verification command families, and hook level. Initial
   schema, examples, and shared skill templates now live under
   `agentops/templates/dispatch/`, with the operator-facing contract documented in
   `agentops/docs/dispatch/dispatch-manifest.md`.
2. Add actionq-dispatcher support for reading project defaults from that manifest or generating
   dispatcher TOML from it. Keep current TOML as the runtime format until the manifest proves out.
3. Extract shared skill templates from `homelab-analytics` into an `agentops` template directory.
4. Convert `homelab-analytics` to consume the shared templates with overlays, preserving current
   behavior.
5. Apply the same template to `appservice`, where the existing dispatch skills already show a
   repo-specific GitOps overlay.
6. Add cockpit visibility for resolved routing source, model, harness, hook level, and dispatch
   class.
7. Roll out to other repos by adoption level, not by wholesale copy.

## Open questions

- Whether shared skills should be symlinked, vendored by a small sync command, or resolved at
  runtime from `agentops`. Runtime resolution is cleaner but requires every harness to know the
  same lookup path.
- Whether review specialists should be workspace-global or repo-selected. The safer default is
  repo-selected specialists backed by shared templates.
- Whether actionq should store the full dispatch packet unchanged, or normalize selected fields
  into columns for cockpit filtering. Keep JSON first; promote fields only after repeated query
  needs appear.
- Whether model tiers should use provider-specific names or logical aliases. Prefer logical aliases
  in repo manifests and resolve to provider IDs in dispatcher config.
