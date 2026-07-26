# Vuoro Ecosystem Remediation Pre-Flight Checklist
**Date:** 2026-07-25  
**Mode:** execution planning helper (documentation only)

Use this before starting each remediation wave to reduce regression risk.

## Global pre-flight (before any wave)

- [ ] Confirm target repo checkouts are on the expected branches and clean where required.
- [ ] Confirm `git status` for working repos is either clean or intentionally isolated.
- [ ] Confirm `.envrc` is sourced where required (`direnv allow`, `direnv exec` for script-driven checks).
- [ ] Confirm required tooling versions are available (Node, Python, pytest, etc.) for targeted tests.
- [ ] Confirm no active manual dispatch/closeout is underway against the same repos.
- [ ] Create a checkpoint note with date/time and operator initials.

## Wave A pre-flight

### A1 — Vuoro served cutover
- [ ] Run baseline cutover check and archive output.
- [ ] Identify all repos in scope for the boundary (active runtime repos only).
- [ ] Identify any local-only rollback snippets that can stay out of committed shared config.
- [ ] Confirm required profile names (workstation/devbox/prod) before editing.

Validation checkpoints (before edits)
- [ ] `python templates/dispatch/scripts/validate_vuoro_workstation_cutover.py --root /projects/dev --profile workstation-vuoro-shared`
- [ ] Spot-check target `.envrc`/config files for direct backend markers.

### A2 — Long-running claim lease renewal
- [ ] Confirm action execution timeout and TTL knobs in current actionq/sprintctl usage.
- [ ] Identify both worker paths: `run_forever` and one-shot handlers.
- [ ] Confirm test harness can simulate long-running action and failure/kill scenarios.

Validation checkpoints (before edits)
- [ ] Baseline reproduction test for stale claim behavior (if currently available).
- [ ] Confirm log collection paths for session/action events.

## Wave B pre-flight

### B1 — Repo identity canonicalization
- [ ] Identify all repo modes tested: local sqlite vs served/backend mode.
- [ ] Collect one reference path per mode for the same logical repo.
- [ ] Confirm `sprintctl.dispatch.json` and marker IDs for each repo.

### B2 — Lease-lineage parity
- [ ] Identify whether both sqlite and pg behaviors are used in practice in deployment.
- [ ] Confirm test data setup for each backend in CI/local harness.
- [ ] Confirm any docs or policy currently claims lease semantics.

### B3 — Dispatch contract parity (agentops)
- [ ] List current accepted enums/fields per layer (schema, runtime, MCP, UI).
- [ ] Confirm if codegen/central contract path already exists.
- [ ] Identify all schema/normalizer/UI tests to update together.

## Wave C pre-flight

### C1 — Mode portability of claim handoff
- [ ] Capture command examples for local mode vs served mode and the intended parser behavior.
- [ ] Confirm script expectations on claim effect shape.
- [ ] Ensure test fixtures for both mode responses exist or can be added.

### C2 — Terminal ownership fencing
- [ ] Confirm action terminalization flow and error paths.
- [ ] Confirm existing event fields can hold claimant proof/ownership token.
- [ ] Identify rollback behavior on rejected terminal transitions.

### C3 — Vuoro operational CLI clarity
- [ ] Identify all workflows currently invoking deferred CLI commands.
- [ ] Confirm mode/adaptation prerequisites for each command.
- [ ] Confirm docs references for operational commands in repo and runbooks.

## Acceptance checklist before moving between waves

- [ ] Required wave-specific validation commands pass.
- [ ] Issue-level exit criteria in implementation plan are met.
- [ ] No new critical/high findings introduced in wave scope.
- [ ] Notes updated with before/after evidence artifacts (command + summary).

## Post-wave close actions

- [ ] Capture diff summary (files touched + changed behavior).
- [ ] Record validation command outputs in a dated appendix.
- [ ] Verify no unintended config mode backslide.
- [ ] Prepare next-wave blocker/clearance decision:
  - **Continue** only if all exit criteria passed.
  - **Pause** and escalate if ownership, data safety, or identity safety changed unexpectedly.
