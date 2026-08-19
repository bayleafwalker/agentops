# Test Matrix

| Layer | Scenario | Expected result |
|---|---|---|
| Unit | validator revision unchanged | renderer not called |
| Unit | validator revision changed | renderer called once; cursor advances |
| Unit | render races revision | retry once or explicit unstable status |
| Unit | provider exceeds budget | semantic truncation marker; envelope within cap |
| Unit | cursor missing | full/delta output may duplicate; no authority effect |
| Unit | MCP mutation missing revision | recognized and denied |
| Unit | simple sprintctl CLI mutation stale | denied with current revision |
| Unit | unrecognized complex shell | hook does not pretend certainty; authority still enforces |
| Contract | projection request/response | validate against JSON Schema |
| Contract | mutation validation | typed allow/deny/current revision |
| Integration | two sessions same worktree | cursor isolation |
| Integration | root plus two subagents | binding inherited; cursor isolation |
| Integration | external task update | next delta emits new revision |
| Integration | successful mutation | post-tool context contains returned revision |
| Integration | hook bypass | stale write rejected by authority |
| Integration | compact mid-turn | compact SessionStart projection reaches immediate continuation |
| Chaos | projection service unavailable | read context fail-open; mutation precheck fail-closed |
| Chaos | cursor cache deleted | duplicate only |
| Chaos | provider unstable twice | provider omitted with status; no mislabeled snapshot |
| Acceptance | Claude Code current pinned version | all applicable criteria pass |
| Acceptance | Codex current pinned version | all applicable criteria pass |
| Rollback | hooks disabled | normal harness operation; CAS remains |
