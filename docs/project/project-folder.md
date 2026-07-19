# Materialized project folders

`templates/dispatch/scripts/materialize_project.py` creates a rebuildable folder
for a multi-repository work window. The folder is derived state: deleting it
loses no project, sprint, queue, or repository truth.

## Layout

```text
<folder>/
  .agentops-project-folder.json  # immutable ownership marker
  AGENTS.md                      # resolved project-scope guidance
  project.context.json          # deterministic machine context
  members/
    <repo_id>/                   # linked Git worktree
```

The folder itself is never a Git repository. The canonical `project.toml` and
`.project/sources/` remain in the home repository; each member's commits and
generated instructions remain in that member repository. Dispatcher worktrees
continue to anchor on primary clones.

The tool refuses broad targets, symlinked folders, folders inside a member
repository, non-empty folders without its matching marker, and unexpected
top-level paths. It never deletes or resets a member worktree.

## Setup

```bash
python templates/dispatch/scripts/materialize_project.py setup \
  --project /projects/dev/<home-repo>/project.toml \
  --folder <derived-folder>
```

Setup fetches and prunes each primary clone, resolves `origin/HEAD` (falling
back to `origin/main` or `origin/master`), and adds one linked worktree per
member. Git cannot safely check out the same default branch in the primary clone
and a second worktree, so each project worktree uses the stable branch
`agentops-project/<project-uuid>/<repo_id>` tracking the remote default branch.

After all worktrees are current, setup invokes the deterministic project
renderer against `members/<home_repo>/project.toml`, with `members/` as its
workspace root. Missing or stale generated instructions are materialized in the
member worktrees for review and separate `chore(render)` commits.

## Sync

```bash
python templates/dispatch/scripts/materialize_project.py sync \
  --project /projects/dev/<home-repo>/project.toml \
  --folder <derived-folder>
```

Sync performs, in order:

1. `git fetch --prune origin` and `git worktree prune` in every primary clone;
2. recreation of a missing derived worktree when its safe tracking branch is
   available;
3. `git merge --ff-only <remote-default>` for clean worktrees whose current
   commit is an ancestor of the remote default;
4. project rendering after every member reaches a safe current state;
5. deterministic refresh of root `AGENTS.md` and `project.context.json`.

Dirty worktrees, local-ahead or diverged histories, detached heads, and
unexpected branches are reported and left unchanged. Any such finding skips
rendering so guidance is never projected from a mixed revision set. Exit `0`
means synchronization and rendering succeeded, exit `1` means an unresolved
member state, and exit `2` means invalid configuration or an unsafe operation.

## Delete and rebuild

Before removing a folder, verify its exact path and matching
`.agentops-project-folder.json`; remove only that explicit derived folder. A
later `setup` prunes the stale Git worktree registrations, reuses the stable
tracking branches, recreates the worktrees, and emits byte-identical resolved
context when repository revisions are unchanged.

Never resolve a non-fast-forward state by resetting from this tool. Commit,
merge, rebase, or abandon work through the owning repository's normal workflow,
then rerun sync.
