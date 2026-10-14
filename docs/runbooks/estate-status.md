# Estate status: CLI and MCP

`agentops estate status` is a read-only report. It covers vuoro-shared, vuoro-cloud and the agent hosts (workstation, devbox), and answers what is **desired**, **running**, **usable** and **held** in each. It then gives the **next blocking gate** and the **recovery class** (`cancel`, `image-revert` or `forward-fix-or-restore`). Each fact carries `{status, value, source, observed_at, evidence}`. `unknown` is a valid answer and always has a `reason`. The report shape is `environment-record/estate-status-v1.schema.json`.

## CLI

```sh
agentops estate status                      # Markdown, all environments
agentops estate status --env vuoro-shared   # one environment (repeatable)
agentops estate status --json               # estate-status/v1 JSON
agentops estate status --fetch              # git fetch deploying repos' remote-tracking refs first
agentops estate status --from report.json   # render a saved JSON report as Markdown
agentops estate status --record DIR         # also write redacted probe results (fixtures)
agentops estate status --replay DIR         # answer every probe from fixtures (no network)
```

Read-only guarantees:
- kubectl is refused for any verb other than `get` or `version`.
- HTTP requests are GET only.
- `--fetch` updates only remote-tracking refs.
- Bearer tokens, `vuo_*` tokens, DSNs, `password=` values, and GitHub and age keys are redacted before anything is printed, returned or recorded.
- The vuoro-cloud operator token is read from `~/.config/vuoro/credentials/vuoro-cloud.token` and sent as a header, but it is never echoed or recorded.

The report never decrypts secrets. vuoro-cloud's tenant-runtime pin exists only in a SOPS-encrypted Secret, so `desired.tenant_runtime_pin` stays `unknown` and the vuoro-cloud gate cannot reach `none`. `desired.compatibility_mirror_agrees` reports the non-secret half of `verify-runtime-pin.py`.

How it derives its answers:
- **Gate.** The next blocking gate is `none` only when every check passes and every hold is known and absent. Holds are suspended Kustomizations, CronJobs suspended without a Git declaration, Deployments scaled below their declared replicas, tenants in maintenance, and host holds. A local ref behind its remote, or a moved tag, makes desired state `unknown`, not a pass.
- **Recovery class.** It is derived only when every input it depends on is known. For vuoro-shared, the migration Job's state is decisive:
  - not started: `cancel`;
  - running or Failed: `unknown`;
  - TTL-deleted: counts as committed only if the handshake proves it;
  - committed with a forward-only schema: `forward-fix-or-restore`, unless a newer compatible image is serving.
- **Forward-only marker.** Forward-only comes from a structured marker in the cutover runbook: front matter `rollback: forward-only|reversible`, or a `Rollback (forward only)` heading.
- **vuoro-cloud.**
  - The Flux semver constraint is read from the remote Flux actually watches (`github`), not the canonical remote.
  - The selected tag is labelled `predicted`. Flux's applied revision is the Kustomizations' `lastAppliedRevision`.
  - The report card builder runs from the tag's own tree.
- **Freshness.** Each git-derived fact is timestamped with when its ref was last confirmed against the remote, not when the command ran.
- **`--from`.** Rendering a saved report with `--from` prints its age.

Cluster access:
- vuoro-shared uses `KUBECONFIG=/projects/dev/appservice/clusters/.kube/config`.
- vuoro-cloud uses `~/.config/vuoro/kube/poc.yaml` and the operator tunnel. The report does not bring the tunnel up. If the tunnel is down, the cluster facts are `unknown` with that reason. To include them, run `nmcli connection up vuoro-cloud-operator` and rerun the report.

## MCP server

`agentops estate mcp` is a stdio MCP server that exposes one tool, `estate_status`:

| Argument | Type | Default | Meaning |
|---|---|---|---|
| `env` | environment name, or a list of names | all | `vuoro-shared`, `vuoro-cloud`, `workstation`, `devbox` |
| `fetch` | boolean | `false` | same as `--fetch` |

The tool returns the `estate-status/v1` report:
- as `structuredContent`;
- as JSON text in `content[0].text`.

It runs the same `build_report`/`Probe` code as the CLI, so the read-only guarantees and redaction are identical. It never records fixtures. Invalid arguments come back as a tool error (`isError: true`), not as a protocol error. The tool carries `readOnlyHint: true`.

It is a stdlib implementation of MCP stdio (newline-delimited JSON-RPC 2.0) with no dependencies, because the official `mcp` SDK is not available through any agentops tooling. It supports these methods: `initialize`, `ping`, `tools/list`, `tools/call` and notifications. It negotiates protocol versions `2025-06-18`, `2025-03-26` and `2024-11-05`. The tool is named `estate_status` rather than `estate.status` because Claude tool names cannot contain a dot.

### Register with Claude Code

Do one of the following:
- Project scope: merge `mcp/agentops-estate.mcp.json` into `/projects/dev/.mcp.json`.
- User scope: run
  ```sh
  claude mcp add --scope user agentops-estate -- /projects/dev/agentops/bin/agentops estate mcp
  ```

Sessions then see the tool as `mcp__agentops-estate__estate_status`.

### Register with Codex

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.agentops-estate]
command = "/projects/dev/agentops/bin/agentops"
args = ["estate", "mcp"]
tool_timeout_sec = 120
```

A full run takes about 10 seconds. With `fetch: true` it takes longer.

### Smoke test

```sh
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}' \
  '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"estate_status","arguments":{"env":"vuoro-shared"}}}' \
  | agentops estate mcp
```
