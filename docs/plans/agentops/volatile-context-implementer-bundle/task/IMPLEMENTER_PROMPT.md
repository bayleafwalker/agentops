# Implementer Prompt

Implement the revision-gated volatile context feature described in this bundle inside the existing sprintctl/Vuoro served substrate.

Read, in order:

1. `IMPLEMENTER_HANDOFF.md`
2. `docs/architecture.md`
3. `docs/contracts.md`
4. `docs/hook-map.md`
5. `task/ACCEPTANCE_CRITERIA.md`
6. the three ADRs

Constraints:

- do not create a new user-facing `ctx` CLI, authority, database, or agent-maintained context file;
- use the dispatcher-owned dispatch ID and existing queue row for binding;
- use the existing cursor cache for disposable last-emitted revisions;
- enforce expected revision atomically in every authoritative mutation path before enabling hook enforcement;
- treat hooks as early validation and model feedback, not as the sole write control;
- implement full projection on session/subagent/compact continuation and revision-gated delta projection on user prompts;
- inject affected provider context after successful mutation;
- keep the complete projection at or below 7,500 UTF-8 bytes with semantic truncation;
- do not log raw projection content or inject credentials/environment dumps;
- do not add a Claude `WorktreeCreate` hook solely for invalidation;
- preserve rollback: disabling hooks must restore ordinary harness operation while authoritative CAS remains.

Use the reference package for contract behavior, not as a required production language or deployment unit. Replace fake providers and fake authority with the real interfaces.

Before implementation, produce a mapping from each reference concept to the exact existing module/table/API it will use. After implementation, run the full acceptance matrix, including hook bypass and two sessions sharing a worktree. Do not declare completion from unit tests alone.
