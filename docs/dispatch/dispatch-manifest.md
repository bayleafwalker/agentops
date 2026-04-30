# Dispatch Manifest

The dispatch manifest is the repo-local contract that lets `actionq` route work without reading
repo prose. It is intentionally smaller than `AGENTS.md`: it names the repo's adoption level,
selected shared skills, routing defaults, verification families, and hook publishers.

Schema:

```text
/projects/dev/agentops/templates/dispatch/manifest.schema.json
```

Examples:

```text
/projects/dev/agentops/templates/dispatch/examples/homelab-analytics.dispatch.json
/projects/dev/agentops/templates/dispatch/examples/appservice.dispatch.json
```

## Routing Precedence

Dispatchers must resolve `harness` and `model` in this order:

1. Action payload explicit fields.
2. Project defaults from the dispatch manifest or generated dispatcher config.
3. Action-class defaults.
4. Single global fallback, only when exactly one harness is configured.

The manifest may use logical `model_alias` values. Provider-specific model IDs belong in
dispatcher runtime config so repos can keep stable policy while providers change model names.

## Adoption Levels

- `guidance-only`: AGENTS/mode docs and local verification rules. No actionq dispatch.
- `observable`: audit hooks and artifact publication are enabled.
- `dispatchable`: actionq project config, shared dispatch skills, ACLs, gates, and optional
  sprintctl remote mode are enabled.

## Skills And Overlays

Shared skill templates live under:

```text
/projects/dev/agentops/templates/dispatch/skills/
```

Repos should select shared skills in the manifest and commit only overlay fragments for local
differences: domain boundaries, test commands, specialist roster, architecture rules, cluster
safety rules, or escalation rules. Full skill bodies should be copied into a repo only when the
repo has a real behavioral fork.

## Hook Contract

Hooks publish facts; they do not decide policy. Hook payloads should include `repo_id`, `actor`,
`runtime_session_id` when available, `action_id` when dispatched, refs (`wi:`, `sprint:`, `sha:`,
`pr:`), summary, and timestamp.

Dispatcher gates are the exception to best-effort publishing: if verification is part of the
action contract, missing or failed verification must fail closed.

## Runtime Format

The manifest is the portable source for repo defaults. `actionq-dispatcher` can keep TOML as its
runtime config while this format proves out, either by reading the manifest directly or generating
TOML from it.

## Cockpit Visibility

The cockpit reads manifests through:

```text
/cockpit/api/dispatch-manifests?repo_id=<repo>
```

The manifest directory defaults to:

```text
/projects/dev/agentops/templates/dispatch/examples
```

Override it with `COCKPIT_DISPATCH_MANIFEST_ROOT` when repos begin committing their own
`*.dispatch.json` files or when generated manifests are staged in `_artifacts`.
