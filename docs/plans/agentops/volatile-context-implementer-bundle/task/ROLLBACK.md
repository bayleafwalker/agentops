# Rollback Plan

## Fast rollback

1. Disable repo/plugin hook configuration for projection events.
2. Leave authoritative `if_revision` enforcement enabled.
3. Stop or route around the projection endpoints.
4. Remove the local hook adapter package after sessions are drained.
5. Delete disposable cursor rows/files after their TTL.

No projection content is authoritative, so no data migration or reconstruction is required.

## Partial rollback options

- Disable `UserPromptSubmit` delta injection but retain session/subagent projection.
- Disable fail-closed local mutation precheck but retain authoritative CAS.
- Disable host/workspace providers while retaining binding/task.
- Disable MCP resource exposure without affecting hooks.

## Do not roll back casually

Authoritative CAS is a correctness improvement independent of context injection. Rolling it back recreates lost-update behavior and should require a separate decision and evidence.

## Recovery validation

After rollback:

```text
- root harness starts normally;
- tools execute normally subject to existing permissions;
- current task remains readable through existing sprintctl paths;
- stale mutation still receives a typed conflict;
- no hook adapter processes remain;
- cursor cache expiry/cleanup succeeds.
```
