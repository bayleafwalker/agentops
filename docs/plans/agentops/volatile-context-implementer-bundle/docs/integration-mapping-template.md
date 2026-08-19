# Existing-System Integration Mapping

Complete this before editing production code. The point is to stop a sensible feature from quietly acquiring a second substrate because the first one was inconvenient to inspect.

| Reference concept | Existing module/API/table | Owner | Change required | Evidence |
|---|---|---|---|---|
| dispatch binding lookup |  | dispatcher/action queue |  |  |
| repo UUID lookup |  | agentops |  |  |
| task revision/watermark |  | sprintctl |  |  |
| atomic task mutation |  | sprintctl |  |  |
| attributed claim append |  | sprintctl/Vuoro |  |  |
| idempotency key |  |  |  |  |
| local consumer cursor |  |  |  |  |
| served HTTP routing |  | appservice |  |  |
| actor credential resolution |  | cred-broker/OpenBao |  |  |
| host capability generation |  |  |  |  |
| workspace identity |  | agentops/worktree binding |  |  |
| Prometheus metrics |  | homelab-analytics |  |  |
| structured logs |  | Loki |  |  |
| Claude plugin/settings distribution |  |  |  |  |
| Codex plugin/hooks distribution |  |  |  |  |

## Write-path inventory

| Mutation path | Current revision support | Atomic | Actor attributed | Idempotent | Migration action |
|---|---:|---:|---:|---:|---|
| sprintctl CLI |  |  |  |  |  |
| served HTTP API |  |  |  |  |  |
| MCP tools |  |  |  |  |  |
| dispatcher/worker internal writes |  |  |  |  |  |
| maintenance/reconciliation jobs |  |  |  |  |  |
| tests/fixtures that bypass service |  |  |  |  |  |

## Version pins

Record exact harness versions used for acceptance:

```text
Claude Code:
Codex CLI/app:
Hook adapter package revision:
Projection API schema version:
MCP protocol version, if used:
```
