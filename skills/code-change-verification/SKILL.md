---
name: code-change-verification
description: Use after repo-tracked code or docs changes to select, run, and report verification before review, handoff, or PR prep.
---

## Goal

Map changed surfaces to the smallest useful verification commands first, then run broader gates only when the manifest, dispatch packet, or PR path requires them.

## Inputs

- Changed files or diff.
- The dispatch packet, manifest verification block, and repo overlay.
- Relevant local test, lint, typecheck, docs, contract, Docker, or Helm targets.
- Whether the work is headed to review, PR, deployment, or another dispatched action.

## Steps

1. Classify changed surfaces using the manifest's command families and overlay rules.
2. Prefer targeted checks from the action packet. Fall back to project commands, then action-class commands.
	For Python tests, use the focused project target with fail-fast, concise output where supported, for example: `pytest <targeted-tests> -x --tb=short`.
   Establish a cheap reproducible setup and representative dev smoke path first.
   Check the actual installer/entrypoint, required tool versions, backend and
   fixture availability before expensive work; a missing prerequisite must fail
   promptly with an actionable diagnosis, never a false pass or silent skip.
   Reuse the project's documented environment with isolated fixtures, ports and
   cleanup ownership. Improve the shared entrypoint when the same setup failure
   recurs instead of making each agent rediscover it.
3. Run commands foreground and blocking; wait for their exit status before proceeding.
4. Record exact commands, results, and any skipped checks.
5. Emit or hand off verification data for dispatcher hooks when the action contract requires it.
6. Select broader checks for the risk and changed boundaries, then run required
   integration/CI checks. Repeat them when new changes, failures or unresolved
   concerns justify it; retain their value rather than optimizing for cheapness
   alone. Record measured setup/check latency when available, not invented targets.

## Output Contract

- Verification summary with exact commands.
- Pass/fail status for each command.
- Remaining verification debt or blockers.

## Do Not

- Do not imply a command passed if it was not run.
- Do not replace repo-specific checks with generic reassurance.
- Do not background or detach verification commands when their result gates the next step.
- Do not run destructive or cluster-mutating verification unless the repo overlay explicitly allows it.
