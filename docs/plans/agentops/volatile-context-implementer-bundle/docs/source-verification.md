# Source Verification — 17 August 2026

This file records the external behavior checked while preparing the bundle. Recheck before implementation if harness versions move materially.

## Claude Code

Official hooks reference:

- https://code.claude.com/docs/en/hooks

Verified points:

- lifecycle includes `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `SubagentStart`, `PostCompact`, `CwdChanged`, `FileChanged`, and `WorktreeCreate`;
- `SessionStart` source includes `startup`, `resume`, `clear`, `compact`, and `fork`;
- `SessionStart`, `SubagentStart`, `UserPromptSubmit`, `PreToolUse`, and `PostToolUse` can inject `additionalContext` in their documented event-specific forms;
- exit code 2 blocks `PreToolUse` when used as an exit-code decision;
- output strings are capped at 10,000 characters before spill/preview behavior;
- `PostCompact` has no decision control and is documented for follow-up tasks;
- `CwdChanged` and `FileChanged` can update environment/watch state but do not directly inject context;
- configuring `WorktreeCreate` replaces default worktree creation;
- command, HTTP, MCP-tool, prompt, and experimental agent handlers are supported;
- `Setup` fires only for explicit init/maintenance flows, not ordinary interactive startup;
- `CLAUDE_ENV_FILE` is available on selected events including `SessionStart`.

## Codex

Official hooks reference:

- https://developers.openai.com/codex/hooks
- currently redirects to https://learn.chatgpt.com/docs/hooks

Verified points:

- lifecycle includes `SessionStart`, `SubagentStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PreCompact`, and `PostCompact`;
- `SessionStart` source includes `startup`, `resume`, `clear`, and `compact`;
- `SessionStart(source=compact)` runs before the next model request and can inject context;
- `SubagentStart`, `UserPromptSubmit`, `PreToolUse`, and `PostToolUse` document `additionalContext` support;
- `PreToolUse` can deny with hook JSON or exit code 2;
- default model-visible hook output spills at roughly 2,500 tokens, with a head-and-tail preview and file path;
- `PostCompact` ignores plain stdout and does not document an event-specific `additionalContext` shape;
- only `type: command` handlers execute currently; prompt/agent handlers are parsed but skipped;
- current documented event set does not include Claude-style `CwdChanged`, `FileChanged`, or `WorktreeCreate`.

## Microsoft Agent Framework

Official context provider concept:

- https://learn.microsoft.com/en-us/agent-framework/concepts/agents/conversations/context-providers

Verified point: context providers run around invocations to add context before execution and optionally process data after execution. This supports the provider/tool distinction, but does not supply the revision-gated projection policy described here.

## MCP

Official resource specification:

- https://modelcontextprotocol.io/specification/2026-07-28/server/resources
- https://modelcontextprotocol.io/specification/2026-07-28/changelog

Verified points:

- resource templates provide parameterized addressing;
- the 2026-07-28 protocol uses `subscriptions/listen` for opted-in resource update notifications;
- notifications provide invalidation/update signals, not automatic model-context injection;
- cacheable list/read results include freshness-oriented fields in the 2026-07-28 revision.
