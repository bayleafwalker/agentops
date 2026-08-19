# Harness Hook Map

## Portable core

| Lifecycle | Claude Code | Codex | Action |
|---|---|---|---|
| New/resumed/cleared session | `SessionStart` | `SessionStart` | full session projection |
| Compaction continuation | `SessionStart` with `source=compact` | `SessionStart` with `source=compact` | full projection before next model request |
| Subagent spawn | `SubagentStart` | `SubagentStart` | full session projection keyed by `agent_id` |
| New user prompt | `UserPromptSubmit` | `UserPromptSubmit` | validate providers, emit changed deltas only |
| Before recognized mutation | `PreToolUse` | `PreToolUse` | validate required revision; deny stale/missing precondition |
| After successful mutation | `PostToolUse` | `PostToolUse` | inject affected provider at new revision |
| Mutation failure/conflict | `PostToolUseFailure` or tool result path | `PostToolUse` may observe non-zero Bash output | inject current revision where detectable |

Current Codex and Claude Code both accept `hookSpecificOutput.additionalContext` on `PreToolUse` and `PostToolUse`. Keep the response builder capability-driven in case parity changes again.

## Compaction

Do **not** depend on `PostCompact` for reinjection:

- Claude Code describes `PostCompact` as a follow-up/side-effect event with no decision control.
- Codex ignores plain stdout on `PostCompact` and does not document event-specific `additionalContext` there.
- Both document `SessionStart(source=compact)` as the context reinjection path.

You may still use `PostCompact` asynchronously for metrics or auditing the generated compact summary, without storing the summary as task authority.

## Claude-only lifecycle helpers

| Event | Use |
|---|---|
| `CwdChanged` | invalidate workspace cursor; optionally update watched paths/environment |
| `FileChanged` | invalidate a hand-start fallback binding or environment-derived provider |
| `DirectoryAdded` | invalidate/re-resolve workspace set if multi-root sessions are supported |

These events do not inject model context directly. They prepare the next projection/tool boundary.

### `WorktreeCreate` warning

Configuring Claude Code's `WorktreeCreate` hook replaces its default worktree creation. Do not add a context-only handler. If the deployment already owns worktree creation, add binding/workspace setup inside that existing implementation and still use `SessionStart`/`SubagentStart` for projection.

Codex currently does not expose `CwdChanged`, `FileChanged`, or `WorktreeCreate` lifecycle hooks in its documented hook event set. Validate workspace identity on session start and relevant tool boundaries instead.

## Binding environment

The dispatcher should launch the harness with:

```bash
export VUORO_DISPATCH_ID="..."
export VUORO_REPO_ID="..."   # optional validation hint
```

Claude's `CLAUDE_ENV_FILE` can persist environment variables for later Bash commands from selected hooks, but it is not needed when the dispatcher already supplies the binding environment. Claude `Setup` does not run on ordinary interactive startup, so do not use it as the primary binding event.

## Handler transport

- Claude Code supports command, HTTP, MCP-tool, prompt, and agent hook handlers.
- Codex currently runs command handlers only.

Use one local command adapter for parity. It should contain no business state: read stdin JSON, add dispatcher environment, call the served endpoint, validate/serialize the response, and exit.

## Recommended output limit

Set a service hard cap of **7,500 UTF-8 bytes** for the complete projection envelope and tighter per-provider caps. This stays below Claude's 10,000-character cap and normally below Codex's default roughly 2,500-token spill threshold. Also set Codex `additionalContextLimit` explicitly as a second guard, not as the primary truncator.
