# E1 first use: Routine verdict via the Vuoro connector

Tracks: agentops#2514, E1 (Define first use, not first deployment —
`docs/design/e1/e1-stronger-baseline-design-2026-09-22.md` §11.2 item 5).
Acceptance line under test: "a claude.ai Routine authenticates via OAuth,
calls `list_ready_work` and `describe_work`, and opens a PR in an operator
repo carrying its verdict."

## What this run did

This is a claude.ai Routine (scheduled cloud session), run 2026-09-25. Per
its instructions it was to call `list_ready_work` on the Vuoro MCP
connector, then `describe_work` for `work_id` 1, 2, and 3, call no other
Vuoro tool, and change nothing else in the repo.

## Calls attempted

All calls below were made in a single continuous session on 2026-09-25,
between the session's start (shortly after 13:20 UTC, based on the
scheduler's firing time) and 13:33:53Z, the last timestamp captured during
the run (via `date -u`, immediately after the final connector re-check
below). The harness does not expose a per-call timestamp, so calls are
listed in the order they were made rather than individually timestamped.

| Order | Call | Arguments | Result |
|---|---|---|---|
| 1 | `ListConnectors` (keywords: `["Vuoro"]`) | — | `{"name":"Vuoro","installState":"connected","connected":true,"enabledInChat":true}` |
| 2 | `ToolSearch` (query: `"Vuoro list_ready_work describe_work"`) | max_results 10 | `No matching deferred tools found` |
| 3 | `ToolSearch` (query: `"Vuoro"`) | max_results 20 | `No matching deferred tools found` |
| 4 | `ToolSearch` (query: `"list_ready_work"`) | max_results 10 | `No matching deferred tools found` |
| 5 | `ToolSearch` (query: `"describe_work"`) | max_results 10 | `No matching deferred tools found` |
| 6 | `ToolSearch` (query: `"mcp__vuoro"`) | max_results 20 | `No matching deferred tools found` |
| 7 | `ToolSearch` (query: `"work"`) | max_results 20 | Returned unrelated tools (EnterWorktree, ExitWorktree, SendMessage, Task*) — no Vuoro/work-item tool among them |
| 8 | `ListMcpResourcesTool` (server: `"Vuoro"`) | — | `No resources found. MCP servers may still provide tools even if they have no resources.` |
| 9 | `ToolSearch` (query: `"ready work item"`) | max_results 15 | Returned unrelated tools (EnterWorktree, ExitWorktree, SendMessage, Task*) — no Vuoro/work-item tool among them |
| 10 | `ToolSearch` (query: `"vuoro dispatch queue claim"`) | max_results 15 | Returned unrelated tools (ArtifactComments, TaskList, TaskUpdate) — no Vuoro tool among them |
| 11 | `ToolSearch` (query: `"sprintctl item status"`) | max_results 10 | Returned unrelated tools (ArtifactComments, TaskList, TaskUpdate) — no Vuoro tool among them |
| 12 | `ToolSearch` (query: `"Vuoro work read"`) | max_results 20 | Returned a large batch of unrelated deferred tools (ReadMcpResourceTool, github issue/PR read tools, visualize, DesignSync, Monitor, NotebookEdit, TaskCreate/Get/List, WebFetch) — no `list_ready_work`, `describe_work`, or any `mcp__vuoro__*` tool among them |
| 13 | `ListConnectors` (keywords: `["Vuoro"]`, re-check) | — | Same as call 1: `connected: true`, `enabledInChat: true` |

No call named `list_ready_work` or `describe_work` was ever made: neither
tool's schema was ever surfaced by `ToolSearch`, so there was nothing
callable to invoke. Per the task's own fallback instruction ("If the Vuoro
tools are unavailable or return an error, still write the file with the
exact error..."), this file records that unavailability instead of a
tool call result.

Exact error text returned in every failing lookup:

```
No matching deferred tools found
```

and, for the resource listing:

```
No resources found. MCP servers may still provide tools even if they have no resources.
```

No `work_id`/`title`/`status`/`as_of` items were returned for work items 1,
2, or 3, because no tool call that could return them ever succeeded.

## Verdict

**No.** The hosted runtime did not authenticate via OAuth and read the
workspace's work state in this run, because the Vuoro connector's tools
were never reachable from this session: `ListConnectors` reports the
connector as `connected: true` and `enabledInChat: true` at the org level,
but repeated `ToolSearch` lookups — by exact tool name (`list_ready_work`,
`describe_work`), by server name (`Vuoro`, `mcp__vuoro`), and by keyword
(`work`, `ready work item`, `vuoro dispatch queue claim`, `sprintctl item
status`, `Vuoro work read`) — never surfaced a callable schema for either
tool, and `ListMcpResourcesTool` found no resources either. Whether the gap
is on the connector's MCP tool-registration side, on OAuth token exchange
for this identity, or on this session's deferred-tool indexing cannot be
determined from this session alone; what is established is that the
acceptance line's read step (`list_ready_work` + `describe_work`
succeeding) did not happen. E1's first-use acceptance criterion is not yet
satisfied.
