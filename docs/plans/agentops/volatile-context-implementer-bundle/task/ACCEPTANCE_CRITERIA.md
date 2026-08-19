# Acceptance Criteria

## Core projection

- [ ] A new root session receives one full bounded projection.
- [ ] A resumed and cleared session receives a full projection.
- [ ] After compaction, `SessionStart(source=compact)` reinjects current context before continuation.
- [ ] A subagent receives binding/task context before its first prompt.
- [ ] An unchanged user turn emits no stdout and adds zero model-visible context.
- [ ] A changed task revision emits exactly one task delta.
- [ ] Later provider blocks explicitly supersede earlier revisions by provider ID.
- [ ] Complete projection output is at most 7,500 UTF-8 bytes.
- [ ] Truncation is semantic and explicit; no harness spill/head-tail preview occurs.

## Binding and isolation

- [ ] Two root sessions sharing one worktree have separate cursor keys.
- [ ] Two subagents have separate cursor keys from each other and the root session.
- [ ] Dispatcher environment binding wins over fallback file.
- [ ] Fallback binding contains identifiers and expiry only.
- [ ] A mismatched repo UUID/cwd hint is rejected or surfaced; it never silently rebinds.

## Mutation correctness

- [ ] Missing expected revision is rejected by the authoritative API.
- [ ] Stale expected revision is rejected atomically by the authoritative API.
- [ ] The same stale mutation is rejected when local hooks are disabled.
- [ ] A recognized stale mutation is denied in `PreToolUse` with current revision feedback.
- [ ] A successful mutation returns the new revision.
- [ ] `PostToolUse` injects the affected provider at the new revision.
- [ ] An agent can append an attributed claim but cannot write projection state.

## Failure and recovery

- [ ] Projection endpoint outage does not prevent read-only agent work.
- [ ] Recognized mutation precheck fails closed by default during endpoint outage.
- [ ] Authoritative CAS remains effective during hook/adapter outage.
- [ ] Cursor database loss causes duplicate reinjection, not lost authority or accepted stale writes.
- [ ] Disabling hook configuration rolls back context injection without schema/database repair.
- [ ] CAS enforcement remains enabled after projection rollback.

## Security and observability

- [ ] Provider data is field-allowlisted and JSON-escaped.
- [ ] No credential/environment dump can enter the projection.
- [ ] Raw projection bodies are absent from normal logs.
- [ ] Metrics report validation/render counts, bytes, latency, truncation, and CAS rejection classes.
- [ ] Audit metadata can correlate projection ID, revisions, dispatch, and mutation event without storing raw content.
