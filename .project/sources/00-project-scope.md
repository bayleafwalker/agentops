---
render_levels: [baseline, full]
---

# Vuoro project scope

This repository participates in the `vuoro` multi-repository project. The
project is a read and instruction projection; each member repository remains
the authority for its own runtime behavior and Git history.

- Canonical binding and shared sources live in the `agentops` home repository.
- Cross-cutting project work is tracked in the agentops sprintctl backlog.
- Use `sprintctl usage --context --project --json` and
  `sprintctl next-work --project --json --explain` from a materialized project
  folder. Every union row must retain its `origin_repo`.
- Direct repository sessions remain supported. Omitting `--project` must keep
  the repository-local sprintctl behavior unchanged.
- Project instructions are baseline guidance followed by member-owned
  overrides. The member's authored `AGENTS.md` remains authoritative for local
  workflow and safety constraints.

Before a cross-repository work window, synchronize the derived project folder.
Treat dirty, divergent, or unexpectedly branched member worktrees as a stop
condition; resolve them through the owning repository rather than resetting
them from project tooling.
