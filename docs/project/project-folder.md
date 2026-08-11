# Project materializations

Status: **v2 foundation implemented; operating-model hardening remains**. This
document distinguishes the behavior implemented by the materializer from the
lease and policy integrations still required before treating it as a shared
workspace service.

A logical **project** is the source-controlled binding described by
`project.toml`: its members, home repository, shared guidance, and backlog
projection. A **materialization instance** is one local, generated realization
of that binding for a working session. A project may have zero, one, or many
instances. An instance is not a project authority and has no independent
backlog, queue, deployment, or runtime state.

The recommended local convention is:

```text
/projects/dev/_projects/
  vuoro/                         # conventional instance
  vuoro--sprintctl-1160/         # separate working instance
  vuoro--actionq-1116/
```

`_projects` is under `/projects/dev` for predictable environment and guidance
resolution. Workspace policy must exclude it from backup, cross-host
synchronization, broad repository discovery, dispatcher clone discovery, and
broad IDE indexing. That exclusion is an operational prerequisite and is not
installed by this repository's materializer. Each host materializes its own
instances. The source-controlled binding and guidance remain backed up through
their owning repositories.

## Terms and lifecycle

An instance is **derived** because its folder structure and resolved context can
be regenerated from the binding and member repositories. It is **ephemeral**
because it is intended to be short lived. It is **destroyable only when clean**:
uncommitted edits are real state, and deleting a writable worktree can lose
them. Do not call a writable instance “disposable.”

Each repository still has a local anchor checkout (normally
`/projects/dev/<repo>`), which supplies Git objects and worktree registration
on this host. It is not a portable Git authority or a privileged execution
contract: durable Git identity is commits and refs. Dispatch must consume
repository identity, immutable commit SHA, and its execution envelope; it must
not consume arbitrary state from an anchor checkout or a project instance.

The folder itself is never a Git repository. `project.toml` and
`.project/sources/` remain in the project's home repository; commits and
repository-local instructions remain owned by their member repositories.
Dispatcher worktrees continue to use local anchor checkouts, never project
member worktrees.

## Implemented v2 foundation

`templates/dispatch/scripts/materialize_project.py` creates an identified local
instance for a multi-repository work window:

```text
<folder>/
  .agentops-project-folder.json  # v2 identity and binding provenance
  AGENTS.md                      # resolved project-scope guidance
  project.context.json           # machine context
  members/
    <repo_id>/                   # linked Git worktree
```

```bash
python templates/dispatch/scripts/materialize_project.py setup \
  --project /projects/dev/<home-repo>/project.toml \
  --folder <derived-folder> \
  --instance <instance-id> \
  --mode exclusive-write
```

`setup` records the project and instance identities, mode, source binding
commit, and source binding digest. Exclusive-write instances use distinct
`agentops-project/<project-uuid>/<instance-id>/<repo-id>` branches. Shared-read
instances use detached worktrees and intentionally do not render into members,
because doing so would immediately dirty an inspection instance.

The home member is seeded from the exact clean canonical binding commit, not
from a potentially newer remote default. Its logical binding shape must match
before context or rendering proceeds, and legacy `sync` never advances the home
member implicitly. A newer home remote is reported as `behind`; changing the
active project definition requires an explicit owner-reviewed Git update and a
new or deliberately refreshed instance.

```bash
python templates/dispatch/scripts/materialize_project.py sync \
  --project /projects/dev/<home-repo>/project.toml \
  --folder <derived-folder>
```

Legacy-compatible `sync` fetches, may recreate a missing worktree, and
fast-forwards a clean tracking worktree before rendering. It reports and leaves
unchanged dirty, ahead, diverged, detached, and unexpected-branch states. It is
not a synonym for context refresh. `status` inspects without fetching or
writing generated context, while `refresh-context` regenerates context without
fetching or advancing member revisions.

`context --explain` reports broad-to-narrow source provenance. `destroy --check`
validates teardown, and `destroy` refuses dirty, untracked, ahead/diverged,
unexpected, leased, or non-empty `.session` state before removing worktrees
through Git. The marker and `project.context.json` carry a deterministic digest
over the recorded environment, binding, project fragments, repository guidance,
generated guidance, and member overlays present in the instance.

Local lease commands are implemented as `lease acquire`, `lease heartbeat`,
`lease status`, and `lease release`. Lease records are mode `0600`, never expire
or transfer automatically, and require exact holder identity for mutation.
They are protected by a host-local advisory lock, not a distributed authority.
An active lease blocks destroy, context regeneration, and Git-moving
materializer operations until explicitly released. `shared-read` setup can add
Unix-local filesystem enforcement with `--enforce-readonly`; the marker records
that choice. Reference members are always detached and filesystem-read-only,
even inside an exclusive-write instance, and are excluded from render writes.

Project-scoped Sprintctl reads run from a member worktree, not the folder root:

```bash
cd <folder>/members/<home-repo>
sprintctl usage --context --project --json
sprintctl next-work --project --json --explain
```

The root intentionally has no Git `repo_id`; the project context supplies the
ordered backlog-member union while the command's member checkout makes the
backend repository identity explicit.

## Preflight evidence

Run the read-only preflight before materializing from canonical sources and
again against a completed instance:

```bash
python templates/dispatch/scripts/validate_project_workspace.py \
  --project /projects/dev/<home-repo>/project.toml \
  --folder /projects/dev/_projects/<instance> \
  --projects-root /projects/dev/_projects \
  --exclusion-policy <explicit-policy-file> \
  --json
```

It checks canonical-source cleanliness, binding and context digests, source
records, Git worktree registration/common directories, member role/access and
effective mode, root direnv absence, and the literal supplied exclusion policy.
Exit `0` is a passing report, `1` is failed evidence, and `2` is an inspection
or configuration error. It does not claim to run external agent harnesses or
prove that a backup, synchronization, or indexing system applies the inspected
policy.

Path exclusions apply only to tools that support them. A parent Btrfs snapshot
or block-level zvol snapshot can still retain `_projects`; true exclusion at
those layers requires a separate subvolume, dataset, or backing volume outside
the snapshotted parent.

## Instance contract and remaining hardening

The materializer records an explicit v2 instance marker containing the immutable
`project_id`, `instance_id`, mode, binding source, binding commit and binding
digest and complete context-bundle digest. Folder names are only a convenience;
identity is marker data. Lease-holder identity is stored separately in the
local lease record rather than becoming project truth.

Initially, modes are intentionally narrow:

- `shared-read`: detached worktrees at recorded commits for orientation and
  inspection. `setup --enforce-readonly` removes write bits within member
  worktrees without touching their anchor repository or common Git directory.
- `exclusive-write`: a unique branch per instance and member. Dirty state is
  expected during work; context refresh cannot move member code revisions
  implicitly. The local lease lifecycle prevents concurrent lifecycle mutation
  by cooperating processes on the same filesystem.

The implemented script commands are `setup`, `rebuild`, legacy-compatible `sync`, `status`,
`refresh-context`, `context --explain`, `lease`, and `destroy`. A future ergonomic
`projectctl` may add `list`, `members`, `path`, and `materialize` aliases. There
is no planned project-owned work selection, broad command
execution wrapper, or ambiguous `sync`: Sprintctl selects work, Actionq owns
queue execution, and normal Git commands update branches. A shell helper may
use `projectctl path` to change the caller's directory; a child command cannot
change its parent shell's working directory.

`refresh-context` regenerates guidance and provenance from the instance's
recorded inputs. It must not fetch, merge, rebase, reset, or otherwise advance
member worktrees. Any future Git-state inspection or advancement command must
be named separately and be explicit about its effects.

`rebuild --descriptor` is the release-pinned path. It uses the descriptor's
committed home binding and exact Git refs (or a verified package), never a
local project file supplied as authority, and does not render member documents.
Release-pinned instances refuse legacy `sync` and `refresh-context`; changed
release state requires a new descriptor. Cloud authority, uploads, registries,
signatures, ref pushes, and distributed locks remain out of scope.

## Guidance and provenance

Context resolution must be inspectable rather than assumed to be identical
across harnesses. The implemented `context --explain` reads the persisted
ordered source records and reports their scope, kind, path, digest, applicable
member, and source commit where available. The complete record list has its own
deterministic bundle digest. A materializer trace is evidence; it does not prove
that every agent harness discovered parent instructions identically, so the
pilot must test actual harness behavior.

The semantic policy is:

| Guidance class | Rule |
| --- | --- |
| Safety and authority restrictions | Most restrictive applicable rule wins. |
| Ownership declarations | The repository owner remains authoritative. |
| Shared terminology | Additive. |
| Commands and local paths | Nearest applicable scope wins. |
| Project membership metadata | The active project binding wins. |
| Secrets and credentials | Never aggregated from members. |

The existing renderer's baseline-then-member-override order remains a textual
render rule, not proof that free-form Markdown can automatically detect every
semantic conflict. Structured declarations are required before automated
authority merging can be claimed.

One instance activates one project binding. A repository may belong to several
logical projects, but their guidance is not merged into one worktree; separate
instances provide separate active contexts. Collections are catalog metadata
only and never inject guidance or grant authority.

## Scratch and safe destruction

Instances reserve `<instance>/.session/` for local investigation notes,
output, and handoff material. It is non-authoritative, excluded from backup,
and included in destroyability checks. Material intended to survive an instance
must be committed to its owner repository or recorded in its owning audit,
sprint, queue, or other durable system. `.session/` must not hold credentials.

Implemented `destroy` is a checked operation, not recursive deletion. It refuses
an instance with dirty, staged, or untracked work; unexpected heads; commits not
at the protected remote default; a lease marker; non-empty scratch; or
unexpected top-level paths. It removes member worktrees via
`git worktree remove`, prunes registrations only after successful removal, and
removes the instance directory last. Git itself refuses locked or otherwise
unsafe worktree removal. Rich lease lifecycle and explicit in-progress-operation
diagnostics remain hardening work. The exact instance marker must match the
requested target. No tool can recover uncommitted files after unsafe manual
deletion.
