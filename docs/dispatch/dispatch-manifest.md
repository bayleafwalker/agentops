# Dispatch Manifest

The dispatch manifest is the repo-local contract that lets `actionq` route work without reading
repo prose. It is intentionally smaller than `AGENTS.md`: it names the repo's adoption level,
selected shared skills, routing defaults, verification families, and hook publishers.
It may also provide a default `dispatch_group_id` for cockpit grouping, although
the per-dispatch payload value is the authoritative grouping key for lifecycle rows.

Schema:

```text
/projects/dev/agentops/schemas/dispatch-manifest.schema.json
```

Checker: `scripts/validate_dispatch_manifest.py <manifest.dispatch.json> [...]`.
It was deleted 2026-09-17 (S2 item 6) with `templates/dispatch/scripts` and
restored the same day per TS-11 (goal-state target claim: manifests and their
schema stay, and a kept schema must have its checker, until S3 contracts and
S6 digests replace their remaining inputs). It is exercised by
`scripts/tests/test_validate_dispatch_manifest.py` and
`test_manifest_schema_enums.py` in CI (`.github/workflows/scripts-tests.yml`).

The worked `templates/dispatch/examples/*.dispatch.json` fixtures were retired
2026-09-17 (S2 item 6) with the rest of `templates/dispatch`. For a real
manifest, read a member repo's own `agentops.dispatch.json` directly, e.g.
`/projects/dev/agentops/agentops.dispatch.json`.

## v2 instruction provenance

`schema_version: 2` is backward-compatible with v1 and may add an
`instruction_set` source catalog. The catalog records native root-to-CWD
instruction sources (`AGENTS.md` and `CLAUDE.md`) with exact digests, source
revisions, refs, mechanical rule ids, hooks, and optional line budgets. It is
an inspection record; it does not redefine provider precedence.

A dependency-free measurement doctor (`instruction_doctor.py`) used to run
this check from a repository root; it was retired 2026-09-17 (S2 item 6) with
`templates/dispatch`. Its observation half -- the native root-to-CWD walk,
recorded as path plus content digest -- is restored as the `instructions`
field of `scripts/session_binding.py`'s output (TS-3,
`docs/plans/2026-09-17-target-state.md`). It does not compare the walk
against this manifest's `instruction_set` catalog, gates.json or a skill
lock: TS-3 keeps role and skills observed, not compiled, so that comparison
has no successor here.

Reports distinguish `validated`, `degraded`, and `unbound`. A report is
managed-eligible only when its status is `validated` and handling is `none`.
Handling values are `none`, `degraded`, `repair-only`, and `fatal`. The doctor
performs mechanical checks only; prose conflicts are advisory unless a source
declares the same scoped `rule_id`.

## Routing Precedence

Dispatchers must resolve `harness` and `model` in this order:

1. Action payload explicit fields.
2. Project defaults from the dispatch manifest or generated dispatcher config.
3. Action-class defaults.
4. Single global fallback, only when exactly one harness is configured.

The manifest may use logical `model_alias` values. Provider-specific model IDs belong in
dispatcher runtime config so repos can keep stable policy while providers change model names.
The canonical alias-to-provider mapping is
`model-routing.json`; see [Model Routing](model-routing.md)
for availability, fallbacks, and reasoning-control rules.

## Adoption Levels

- `guidance-only`: AGENTS/mode docs and local verification rules. No actionq dispatch.
- `observable`: audit hooks and artifact publication are enabled.
- `dispatchable`: actionq project config, shared dispatch skills, ACLs, gates, and optional
  sprintctl remote mode are enabled.

## Skills And Overlays

Shared skill templates live under:

```text
/projects/dev/agentops/skills/
```

Repos should select shared skills in the manifest and commit only overlay fragments for local
differences: domain boundaries, test commands, specialist roster, architecture rules, cluster
safety rules, or escalation rules. Full skill bodies should be copied into a repo only when the
repo has a real behavioral fork.

`sync_skills.py` materializes a consumer's selected canonical skill bodies under
`.agents/skills/` and exposes them to Claude through `.claude/skills/` symlinks. When the template
root is inside the repository being synchronized (the canonical `agentops` repository), it links
`.claude/skills/` directly to `skills/` instead of creating a redundant self-copy.
Saved cross-repository workflows must still carry a complete action contract in their prompts:
project-scoped skill discovery is fixed when an agent starts and is not a reliable runtime
dependency after merely changing shell cwd.

## Stateful Protocol Risk Surfaces

The optional `risk_surfaces` array maps closed stateful subjects to changed paths, shared
verification skills, a default verification depth, and an optional `required_on_change` gate.
Use `context_ids` to bind a surface to the repository-owned v1 context packets
that describe its evidence contract.
Use the `verify` and `reconcile` action classes for these workflows. See
[Stateful protocol verification](state-protocol-verification.md) for modes, overlays, and
data-only context/result packets.

## Hook Contract

Hooks publish facts; they do not decide policy. Hook payloads should include `repo_id`, `actor`,
`runtime_session_id` when available, `action_id` when dispatched, refs (`wi:`, `sprint:`, `sha:`,
`pr:`), summary, and timestamp.

The Tier-0 session-mechanization wrapper is the mechanical superset of this contract for a whole
session rather than one hook payload — see
[Session mechanization contracts](session-mechanization-contracts.md) for the `session-capsule/v1`
and `reconciliation-proposal/v1` schemas it and the periodic scribe produce.

Verification gates are coordinator-owned acceptance inputs: if verification is
required by the work contract, missing or failed evidence must fail closed.
Hooks may publish the resulting facts, but no publisher is itself acceptance
authority.

The schema continues to parse historical `actionq-daemon` and
`dispatcher-gate` publisher names so existing manifests can be migrated
without losing their meaning. New and refreshed manifests must not select
them; use only the actual non-retired evidence destination (`git`, `github`, or
`workspace-cost`) and keep coordinator acceptance separate.

## Runtime Format

The manifest is the portable source for repository defaults consumed by a
frontier coordinator and the selected native harness/runtime. It is not a
worker configuration and does not authorize a queue, daemon, or process
launcher. The retired `actionq-dispatcher` must never read or generate runtime
configuration from it.

## Cockpit Visibility

The cockpit reads manifests through:

```text
/cockpit/api/dispatch-manifests?repo_id=<repo>
```

The manifest directory used to default to `templates/dispatch/examples`, which
was retired 2026-09-17 (S2 item 6); that default no longer resolves to
anything. Set `COCKPIT_DISPATCH_MANIFEST_ROOT` explicitly to a directory of
real `*.dispatch.json` files (each member repo's own, or generated manifests
staged in `_artifacts`).
