# homelab-analytics + aligned-equity boundary migration

Date: 2026-07-21

This note records the third and final project-scoping migration
(ha-ae-boundary-migration, item #1183), the boundary case worked through in
`project-binding-spec.md` §6. It is implementation and acceptance evidence,
not a new project contract.

## Instantiated state

- Project UUID: `a40e9a1d-cf76-4bae-a330-f62ecc9e59f8`, matching the existing
  `agentops.toml` registry entry.
- Canonical binding and sources: homelab-analytics commit `dd1e4d5`
  (in-place — `project.toml` lives at the homelab-analytics repo root, no
  project folder, matching the appservice topology rather than vuoro's
  materialized one).
- Render output: aligned-equity commit `941e169` (`chore(render)`, segregated
  from the substantive homelab-analytics commit per §4).
- Members: `homelab-analytics` (home, `render: none`), `aligned-equity`
  (`backlog: true`, `render: baseline`).

## Separation properties (§6 acceptance criteria)

**AE backlog items appear in the union, attributed to AE.** `sprintctl item
list --project` from `/projects/dev/homelab-analytics` returns 573 items:
531 `origin_repo: homelab-analytics` + 42 `origin_repo: aligned-equity`,
matching AE's standalone total exactly. Confirmed generic — no AE-specific
code path.

**AE receives only the shared baseline render.** Diffed the full ordered
source bundle (`00-project-scope.md` + `10-ecosystem-boundaries.md`) against
AE's generated `.agents/project.generated.md`: the `full`-only
`10-ecosystem-boundaries.md` fragment ("Ecosystem ownership and safety
boundaries") is entirely absent from AE's output; only the `[baseline, full]`
fragment landed. `grep -c` for the full-only heading in AE's generated file
returns 0. This is the exclusion working structurally off the fragment
header, not by hand-curation.

**No HA-specific content lands in AE, and vice versa.** Direct consequence of
the above, and homelab-analytics itself (`render: none`) has no generated
file at all — render never pulls a member's local content into anything.

**The plugin contract remains the only code-level interface.** Neither
`.project/sources/` fragment names `aligned_equity.integrations` or
`homelab-analytics.registry.json` internals; only operational/workflow
guidance (sprintctl usage, project topology). Untouched by this migration.

## Deviation from acceptance-evidence expectations: no active sprint

The original acceptance path (used for vuoro's pilot) reads
`sprintctl usage --context --project --json` / `next-work --project --json`.
Both fail here — not with a project-union defect, but with the same
condition each repo already has standalone:

- `homelab-analytics`: 55 sprints, all `status: closed`, none `active` or
  `planned` — the CLI reports "Multiple backlog sprints... ambiguous" because
  nothing distinguishes a current one.
- `aligned-equity`: 6 sprints, all `status: closed` — "No backlog or active
  sprint found."

This is real, pre-existing repo state (both backlogs are fully wound down
right now), not something this migration should paper over by opening a new
sprint in either repo — that would be unrelated product-state mutation
outside this item's scope. It is itself evidence the hard invariant holds:
project scope did not invent activity that isn't there, and the identical
failure standalone vs. `--project` proves no special-casing. The item-level
union (`item list --project`, which is not sprint-scoped) was used instead
to demonstrate attribution, per above.

## Guidance observation

No missing domain constraint surfaced. One environment note carried forward
from the appservice migration: local git identity was unset in both HA and
AE checkouts on this host (commit failed with "Author identity unknown");
set per-repo (not global) to match the pattern already used for other
agent-authored commits in this environment (`Codex <codex@local>`, as
already configured in the agentops checkout). Both repos' `main` had also
moved upstream with unrelated commits since last sync; both rebases were
clean, no conflicts, content unchanged (verified via `git show --stat` before
and after).
