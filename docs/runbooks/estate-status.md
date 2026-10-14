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
- Redaction happens before anything is printed, returned or recorded. It covers:
  - bearer tokens, `vuo_*` tokens and DSNs;
  - credential `key=value` pairs in URL queries, upper-case env assignments and libpq conninfo;
  - JSON string values under credential-like keys (`password`, `*_secret`, `*token*`, `api_key`, `private_key`, `authorization`, …), except keys that only reference a secret (`*_ref`, `*Name`, `*_path`, `*_file`, `*_id`);
  - GitHub and age keys.
- An independent emit guard runs over every report before it leaves the process, on CLI JSON and Markdown, `--from` and MCP alike. It checks for JWTs, `user:pass@host`, PEM private keys, prefixed vendor tokens and high-entropy strings, and shares no logic with redaction. Any string it flags is replaced whole with `[REDACTED: possible secret]` (fail closed), and its JSON path is listed in `guard_redactions`.
- The vuoro-cloud operator token is read from `~/.config/vuoro/credentials/vuoro-cloud.token` and sent as a header, but it is never echoed or recorded.
- `--from FILE --json` adds `saved_report_age` (`rendered_at`, `age_seconds`, `warning`), and `--from` Markdown prints the same warning.

The report never decrypts secrets. `desired.compatibility_mirror_agrees` reports the non-secret half of `verify-runtime-pin.py`. The deployed tenant-runtime pin is `running.tenant_runtime_pin`, read only from a digest-only field of the operator rollout status (see the request below).

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

## Declared host holds

Agent hosts declare their holds in their environment record as `holds`: an array of `{id, reason, since?, ref?}`. The workstation and devbox records carry `"holds": []`, which states that nothing is held, so `held.declared_host_holds` is known. These holds are *declared (from the agentops record)*, not observed on the host: the fact name and its evidence say so. To take a host out of service, add an entry and bump the record's `revision`, for example:

```json
"holds": [{"id": "out-of-dispatch", "reason": "kernel upgrade", "since": "2026-10-14T18:00:00Z"}]
```

The host gate then stops at `holds`. A record without the field reports `held.declared_host_holds` as `unknown`, because holds are not modelled for it. The report reads the record from agentops `origin/main`, so a hold takes effect in the report once it is merged.

## What remains unknown, and why

| Fact | Why it is unknown | What would make it known |
|---|---|---|
| vuoro-shared `usable.work_schema_version` | The handshake reports work compatibility state, not the schema number. Reading the number needs a database role (`sprintctl remote-schema check`), which this report does not hold. | Ask vuoro to add the numeric schema version to `handshake.compatibility.domains.work`. The pin and the Complete migration Job are already known. |
| vuoro-cloud `running.*`, `held.suspended_*`, `held.scaled_below_declared` | The operator tunnel is down. | Run `nmcli connection up vuoro-cloud-operator`. The report never raises the tunnel itself. |
| vuoro-cloud `held.tenants_in_maintenance` | No read-only, non-member endpoint lists workspaces in maintenance. | The rollout-status field requested below. |
| vuoro-cloud `running.tenant_runtime_pin` | The deployed pin lives only inside a SOPS-encrypted Secret. | The rollout-status field requested below. |
| vuoro-cloud `usable.handshake` | It needs a workspace bearer token. | A designated read-only workspace credential, if one is ever wanted. |
| vuoro-cloud `gate.*` | These follow from the rows above. | The rows above. |

## Request to the vuoro-cloud lane

Both fields are additive to the existing operator `GET /api/control/v1/operator/rollout/status`, which already uses the operator token and returns `vuoro-rollout-status/v1`. Neither field requires decryption on the reader's side, and neither exposes a credential. `agentops estate status` already reads both when present; no change on the agentops side is needed.

1. **`maintenance_workspaces`** (array; empty means none) lists every workspace whose `maintenance_mode` is true or whose `state` is `MAINTENANCE` or `MIGRATING`. Each entry is `{"id", "state", "maintenance_mode", "active_migration_id", "since"}`, built from the same `workspaces` columns that `cli_routes.py`'s rollout route already selects. The estate report treats a non-empty list as a hold and the empty list as "no tenant held".
2. **`runtime_image`** is `{"digest": "sha256:<64 hex>", "source": "VUORO_CLOUD_RUNTIME_IMAGE"}`. The control plane fills it from its own environment, where the controller-runtime Secret has already been decrypted by Kubernetes, emitting the digest only and never the rest of the Secret. The estate report compares it with `config/compatibility.json` `packages.vuoro-service` at the predicted release tag. This replaces the decrypting half of `verify-runtime-pin.py` for read-only callers. An equivalent alternative is to move `VUORO_CLOUD_RUNTIME_IMAGE` out of the SOPS Secret into the plain `vuoro-compatibility` ConfigMap, since an image digest is not secret. That would make the pin readable from Git and from `kubectl get configmap`.

Until both fields ship, vuoro-cloud's gate and recovery class stay `unknown`. That is correct, not a defect.

## MCP server

`agentops estate mcp` is a stdio MCP server that exposes one tool, `estate_status`:

| Argument | Type | Default | Meaning |
|---|---|---|---|
| `env` | environment name, or a list of names | all | `vuoro-shared`, `vuoro-cloud`, `workstation`, `devbox` |
| `fetch` | boolean | `false` | same as `--fetch` |

The tool returns the `estate-status/v1` report:
- as `structuredContent`;
- as JSON text in `content[0].text`.

It runs the same `build_report`/`Probe` code and the same emit guard as the CLI, so the read-only guarantees and redaction are identical. It never records fixtures.

Error handling:
- Invalid arguments come back as a tool error (`isError: true`), not as a protocol error.
- Request ids must be strings or numbers. Object, array, boolean and null ids are rejected with `-32600`.

The tool sets `readOnlyHint: false` and `destructiveHint: false`. With `fetch: true` it runs `git fetch`, which updates remote-tracking refs and FETCH_HEAD in the local clones; it never touches a working tree, a cluster or a service. The tool and parameter descriptions say so.

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
