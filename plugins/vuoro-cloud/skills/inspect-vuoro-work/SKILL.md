---
name: inspect-vuoro-work
description: Inspect ready or specifically identified work in Vuoro Cloud, and summarize the state a new agent can safely continue from. Use when a user asks what Vuoro work is ready, asks about a known Vuoro work ID, or asks to continue work already identified in Vuoro.
---

# Inspect Vuoro work

Use Vuoro's MCP tools as the source of current work state. `list_ready_work`
lists ready items; `describe_work` accepts a numeric work ID and returns one
item in any status. A title alone is not a search key in the current surface.

1. If the user supplied a work ID, call `describe_work` for it. Otherwise call
   `list_ready_work`, and use the returned IDs to inspect plausible items. If
   several match, show the candidates and ask which one the user means.
2. Report the work ID, title, status, blocking state, priority, and resolution
   when present. Distinguish fields returned by Vuoro from inferences. Say
   explicitly when the requested item is absent or cannot be identified from
   the available tools.
3. For a continuation request, summarize only the known state and the next
   action that follows from it. The current read surface does not provide run
   history, artifacts, evidence, or acceptance decisions. Do not claim that a
   run succeeded or work was accepted from a `done` status alone.

Vuoro owns work and decision state. The agent host owns execution. Do not
invent work, run, claim, or effect calls that the connected MCP server does not
advertise. When the server has additional tools in a future release, follow
their current schemas and authority requirements before using them.
