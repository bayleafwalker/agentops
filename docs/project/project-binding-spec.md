# Project Binding Specification

Status: **draft** (kctl capture pending acceptance)

A **project** is a projection over repo bindings, never an authority. It declares which repos
belong together, how their sprintctl backlogs union, and what shared instruction content
distributes to each — nothing else. Repos stay ignorant of projects: nothing in a member repo's
code, config, or sprintctl state records that it belongs to one. Deleting or forgetting a
project.toml costs nothing but the union view and the render.

This spec gates every other project-scoping backlog item (sprintctl-project-union,
render-command, project-folder-materialization, and the three migrations). It defines the
project.toml schema, the home-repo convention, the single-repo (in-place) degenerate case, the
render contract, the precedence rule, and works the aligned-equity boundary case through
explicitly.

## Target end state

Three projects: **agentops** (rename pending — see Open Questions), **appservice**
(single-repo, in-place), **homelab-analytics** (+ aligned-equity, boundary flags). All other
repos in `/projects/dev/` stay standalone and untouched. Agents normally run from project scope;
direct repo sessions remain fully supported and behave exactly as they do today.

## Hard invariants

These hold across every item downstream of this spec, not just this one:

- **Standalone repos see zero behavior change.** No `project.toml` anywhere in a repo's
  ancestry (repo root or a project folder) means nothing about that repo's sprintctl, render,
  or dispatch behavior differs from today.
- **Local SQLite mode is unchanged.** `--project` union may decline to union across repos in
  local mode (see sprintctl-project-union); it must never alter single-repo local behavior.
- **Dispatcher isolation is untouched.** actionq-dispatcher worktrees anchor on primary repo
  clones (`/projects/dev/<repo>`), never on project-folder worktrees (project-folder-materialization,
  item 4). A dispatch worktree created from any member repo gets correct instructions with no
  project context in existence — the repo's own committed instruction files are always
  sufficient on their own.
- **No new state store.** A project is a projection: `project.toml` plus deterministic render
  output committed into member repos. There is no project database, no project_id column in
  sprintctl, no runtime service that "knows" about projects.

## Terminology collision

actionq-dispatcher's own config (`config.py`) already uses `project` to mean *a single
configured repo* (e.g. `working_dir = "{worktree_root}/{project}/{action.id}"`, where `project`
is the dispatcher's per-repo config key). That is a different, older, and unrelated sense of the
word from the multi-repo `project.toml` this spec defines. Do not conflate them. Nothing in this
spec touches actionq-dispatcher's config vocabulary; the dispatcher invariant above exists
precisely to keep the two senses from ever needing to interact.

## 1. project.toml schema

Schema:

```text
/projects/dev/agentops/docs/project/schemas/project.schema.json
```

Examples:

```text
/projects/dev/agentops/docs/project/examples/agentops.project.toml
/projects/dev/agentops/docs/project/examples/appservice.project.toml
/projects/dev/agentops/docs/project/examples/homelab-analytics.project.toml
```

| Field | Type | Notes |
|---|---|---|
| `schema_version` | int, const `1` | Mirrors `manifest.schema.json`'s convention. |
| `project_id` | string (UUID v4) | Minted once at project creation. Immutable — no tool (render, sync, migration) ever regenerates it. |
| `display_name` | string | Human-facing name. |
| `home_repo` | string | A `repo_id` that must also appear in `members`. Hosts the backlog convention (§2) and render sources (§4). |
| `members` | array of tables, min 1 | See below. |

Per-member fields:

| Field | Type | Notes |
|---|---|---|
| `repo_id` | string | Matches the repo's sprintctl `repo_id` and `*.dispatch.json` `repo_id`. |
| `backlog` | bool | Include this repo in `--project` union views (sprintctl-project-union). |
| `render` | enum: `full` \| `baseline` \| `none` | Instruction distribution level (§4). |
| `path_notes` | array of strings, optional | Free-text agent guidance for this specific binding. Read directly from `project.toml`, never rendered into a file. |

`schema_version` and the `repo_id` pattern (`^[A-Za-z0-9._-]+$`) reuse
`templates/dispatch/manifest.schema.json`'s conventions directly, so a repo_id is guaranteed to
mean the same thing in a dispatch manifest and in a project binding.

### UUID discipline

The backlog prompt for this item cites "agentops.toml discipline" for `project_id` minting. No
file named `agentops.toml` exists anywhere in `/projects/dev/` at the time of writing (searched
whole tree). This spec applies UUID discipline directly rather than against an unverifiable
reference: `project_id` is a random UUIDv4, minted exactly once, stored as a plain string, never
regenerated. If a specific prior convention was intended, reconcile it against this spec before
ratifying — see Open Questions.

## 2. Home-repo convention

Cross-cutting work items — items that span more than one member repo, or are about the project
itself — live in the **home repo's** sprintctl backlog. No schema change: this is pure
convention, enforced by whoever files the item, not by tooling. (This document's own backlog
items are filed this way: agentops sprint #380, track `project-scoping`.)

Revisit only if it demonstrably chafes in practice — see the project-scoping-retrospective item.

## 3. Single-repo degenerate case (in-place mode)

In-place is a **topology**, not a code path. A project with exactly one member is not special-cased
in the schema or in any tool: `members` always has at least one entry, and every downstream tool
(union, render, folder materialization) operates generically over N members where N can be 1.

What makes a project "in-place" is where `project.toml` lives:

- **In-place**: `project.toml` sits at the home repo's root (sibling to its `*.dispatch.json`).
  No project folder exists. No worktrees exist. `--project` resolution from cwd finds the file
  directly by walking up from the working directory.
- **Materialized**: `project.toml`'s canonical copy still lives at the home repo's root (same
  rule), but a separate project folder (project-folder-materialization, item 4) holds worktrees
  of every member plus a mirrored copy of resolved context for agent-session convenience.

`project.toml`'s canonical location is *always* the home repo's root — in-place and multi-repo
projects differ only in whether a project folder additionally exists, never in where the source
of truth lives. This is why in-place needs nothing from project-folder-materialization (item 4):
there is no folder to build.

For a single-member project, `render` is typically `none` (see appservice example): there is no
second repo to source a baseline from, so there is nothing for render to produce. This is a
consequence of the render contract, not a special rule — see §4.

## 4. Render contract

### Source layout

Project-level render sources live at `<home_repo>/.project/sources/*.md`. Each fragment file
carries a small YAML-style header declaring which render levels include it, mirroring the
`name:`/`description:` frontmatter idiom already used by every `SKILL.md` in this repo:

```markdown
---
render_levels: [baseline, full]
---

<fragment content>
```

A fragment tagged `full` only is excluded from `render: baseline` members by construction — this
is how the AE boundary (§6) is enforced structurally rather than by discipline.

Per-member overrides live in the **member's own repo**, reusing the overlay convention already
established for dispatch manifests (`AGENTS.md`: "repository-specific overlays under
`.agents/overlays/`"): `<member_repo>/.agents/overlays/<repo_id>.project-overrides.md`. Overrides
are additive deltas, never full copies of the baseline.

### Output

Render produces one generated file per member with `render != none`:
`<member_repo>/.agents/project.generated.md`, containing:

1. A provenance header (below).
2. Every source fragment whose `render_levels` includes the member's render flag, concatenated
   in the order they appear in `.project/sources/` directory listing sorted lexically (stable,
   filesystem-independent ordering — same discipline `sync_skills.py` uses for its tree walk).
3. The member's own override fragment, if present, appended last.

Baseline-then-override, concatenated in that fixed order, in the same file, is the entire
precedence rule — see §5.

The member's own `AGENTS.md` gets exactly one additive, idempotent, sentinel-delimited block
inserted (created if `render != none` and the block doesn't exist yet; never touches anything
outside the sentinels):

```markdown
<!-- agentops-project-pointer:start -->
See `.agents/project.generated.md` for cross-repo project context (agentops-managed; do not hand-edit).
<!-- agentops-project-pointer:end -->
```

Rendered files (`.agents/project.generated.md` and the pointer block) are committed into member
repos as `chore(render)` commits, segregated from substantive changes (render-command, item 3).

### Provenance header

No timestamps — timestamps break the "two consecutive renders are byte-identical" acceptance
test for render-command. Content hashes only, sha256 over the ordered, concatenated source
fragment bytes at that render level (same algorithm as `sync_skills.py`'s `tree_digest`):

```markdown
<!-- agentops-render: DO NOT HAND-EDIT
     project_id: <uuid>
     project: <display_name>
     member: <repo_id>
     render: <full|baseline|none>
     source_bundle_sha256: <sha256 of ordered fragment bytes at this render level>
     tool: agentops-render/v1
-->
```

### Determinism

Fixed inputs (`project.toml` + `.project/sources/*.md` + the member's override file) plus fixed
ordering (lexical fragment order, then override last) plus no timestamps yields byte-identical
output on every run against unchanged inputs. This is the acceptance test for render-command.

### Drift

Two distinct kinds, both are "drift," both fail the Tier 0 hook:

- **Stale render** — sources changed since the last render. Detected by recomputing
  `source_bundle_sha256` from current sources at the member's render level and comparing to the
  header's declared value in the on-disk generated file. Mismatch = stale.
- **Hand-edited** — someone modified the generated file directly. Detected only when the bundle
  hash *matches* (sources haven't changed): recompute the full deterministic body from current
  sources and compare byte-for-byte against the on-disk body (excluding the header, which already
  carries its own hash check). Mismatch = hand-edited.

Wire the check into the same hook surface the golden-child skill's `sync_skills.py` currently
occupies (`templates/dispatch/scripts/sync_skills.py` — `check`/`--apply`, dirty-worktree
refusal, hash comparison). render-command (item 3) supersedes `sync_skills.py`'s mechanical
sync function for anything expressible as a project render; `sync_skills.py` itself is unrelated
tooling (shared *skill* trees, not project instruction content) and is untouched by this spec.

## 5. Precedence

Exactly one rule, stated once, here: **project baseline, then repo-specific override,
concatenated in that order into one file at render time.** There is no runtime resolution —
by the time an agent reads `.agents/project.generated.md`, precedence has already been baked
into the linear order of the text. Agents never choose between baseline and override; they read
one file, top to bottom, where later text (the override) is the more specific, more current
statement for that repo.

## 6. Worked case: aligned-equity

Project: `homelab-analytics`, home repo `homelab-analytics`, member `aligned-equity` bound
`backlog: true`, `render: baseline`.

Draft: `docs/project/examples/homelab-analytics.project.toml` (this doc's appendix).

Walking the separation properties this member binding must hold:

- **AE backlog items appear in the union, attributed to AE.** `backlog: true` is a plain per-member
  flag; sprintctl-project-union (item 2) unions over every member with `backlog: true` and tags
  each item with its origin `repo_id`. No AE-specific code path — this is the generic member loop.
- **AE receives only the shared baseline render.** Enforced structurally, not by convention:
  fragments in `homelab-analytics/.project/sources/` tagged `render_levels: [full]` only are
  excluded from AE's render by the source-selection rule in §4. AE's own `AGENTS.md` and
  `.agents/overlays/aligned-equity.project-overrides.md` are never touched by anything with
  `render: baseline` — override content is member-owned, read from the member's own repo, and
  takes effect via the same append step every other member gets (§5), not a special case.
- **No HA-specific content lands in AE, and vice versa.** A direct consequence of the previous
  point plus the additive-overlay rule: HA-specific guidance either lives in a `full`-only
  fragment (excluded from AE) or in HA's own overlay/AGENTS.md (never distributed at all,
  because render only ever pushes from home repo outward, never pulls a member's local content
  into anything). Acceptance evidence for the ha-ae-boundary-migration item is a diff of the two
  members' rendered outputs proving this.
- **The plugin contract remains the only code-level interface.** aligned-equity's existing
  integration boundary — `aligned_equity.integrations.homelab_analytics` plus the root
  `homelab-analytics.registry.json` — is untouched by any of this. Project source fragments are
  operational/workflow guidance (sprintctl, kctl, dispatch skills); nothing in `.project/sources/`
  may name either repo's internal modules. This is a content rule for fragment authors, not a
  schema constraint, because there is nothing in the schema that could reference code internals
  in the first place.

If any of these needed a special case in the schema or in render's source-selection logic to
hold, that would be a schema defect per this item's acceptance criteria — it doesn't: `backlog`
and `render` as plain per-member flags, plus lexical/tag-based fragment selection, express AE's
binding with the exact same code path every other member uses.

## Appendix: draft project.toml

The three files below are the acceptance-evidence appendix for this item. Each also lives at its
path under `docs/project/examples/` for direct reuse when the corresponding migration item runs.

### agentops

```toml
# Draft — see docs/project/project-binding-spec.md.
# Canonical location once instantiated (item pilot-agentops-project): agentops/project.toml
#
# Open question (see Open Questions below): the backlog prompt that named this project's
# members listed "sprintctl, kctl, actionq, cockpit". "cockpit" is not a separate repo — it is
# the agent-cockpit app inside agentops/apps/web. Modeled here as the home repo's own member
# entry. actionq-dispatcher was considered and excluded: it has no sprintctl repo_id and no
# *.dispatch.json, so it cannot be expressed as a member without first onboarding it as a
# tracked repo (out of scope for this spec).

schema_version = 1
project_id = "981b2073-d7af-4c28-bff3-3cf807495fba"
display_name = "agentops"
home_repo = "agentops"

[[members]]
repo_id = "agentops"
backlog = true
render = "none"
path_notes = [
  "Home repo: hosts the project's backlog (sprintctl sprint #380) and render sources (.project/sources/).",
  "Also hosts the agent-cockpit operator UI at apps/web — not a separate project member.",
]

[[members]]
repo_id = "sprintctl"
backlog = true
render = "full"

[[members]]
repo_id = "kctl"
backlog = true
render = "full"

[[members]]
repo_id = "actionq"
backlog = true
render = "full"
```

### appservice

```toml
# Draft — see docs/project/project-binding-spec.md, section 3 (single-repo degenerate case).
# Canonical location once instantiated (item appservice-in-place): appservice/project.toml
# (in-place: lives in the repo itself, no project folder, no worktrees).
#
# Sole member's render is "none" by design, not by special-casing: this project has no
# cross-repo baseline to distribute (appservice is the only member), so there is nothing for
# render to produce. If appservice ever gains sibling members, flip render on the affected
# entries — no schema change required.

schema_version = 1
project_id = "5bbc5637-182a-4d2b-bd73-f5343b248ff1"
display_name = "appservice"
home_repo = "appservice"

[[members]]
repo_id = "appservice"
backlog = true
render = "none"
```

### homelab-analytics

```toml
# Draft — see docs/project/project-binding-spec.md, section 6 (AE test case).
# Canonical location once instantiated (item ha-ae-boundary-migration): homelab-analytics/project.toml

schema_version = 1
project_id = "a40e9a1d-cf76-4bae-a330-f62ecc9e59f8"
display_name = "homelab-analytics"
home_repo = "homelab-analytics"

[[members]]
repo_id = "homelab-analytics"
backlog = true
render = "none"

[[members]]
repo_id = "aligned-equity"
backlog = true
render = "baseline"
path_notes = [
  "Semi-private by design: render:baseline means AE receives only source fragments tagged for the baseline level. AE's own AGENTS.md and .agents/overlays/aligned-equity.project-overrides.md remain locally authoritative and untouched.",
  "The plugin contract (aligned_equity.integrations.homelab_analytics + homelab-analytics.registry.json) is the only code-level interface. Project source fragments must not reference either repo's internals.",
]
```

## Open questions

Flagged rather than silently resolved — pick these up before marking this spec `ratified`, or
explicitly defer them with an owner:

1. **`agentops.toml` discipline reference.** No such file exists in the ecosystem today (see §1).
   If a specific prior convention was intended, it needs to be reconciled against this spec.
2. **"cockpit" as an agentops-project member.** The originating backlog text listed agentops
   project members as "sprintctl, kctl, actionq, cockpit." Cockpit is not a separate repo — it's
   `agentops/apps/web`. Modeled here as part of the home repo's own member entry (see the
   agentops draft's `path_notes`). Confirm this reading before pilot-agentops-project runs.
3. **actionq-dispatcher.** Considered as an agentops-project member and excluded: it has no
   sprintctl `repo_id` and no `*.dispatch.json`, so §1's schema has nothing to bind against. Out
   of scope for this spec; onboarding it (if wanted) is a separate, prior decision.
4. **ecosystem-rename-decision.** Referenced by the pilot-agentops-project item as a prior,
   not-yet-landed decision that soft-gates naming. Not tracked in sprintctl at the time of
   writing (searched agentops backlog). This spec's agentops draft uses the current name;
   pilot-agentops-project applies the rename first only if that decision has landed by then, per
   its own acceptance criteria — this spec does not need to resolve it.
