# Estate status: CLI and MCP

`agentops estate status` is a read-only report. It covers vuoro-shared, vuoro-cloud and the agent hosts (workstation, devbox), and answers what is **desired**, **running**, **usable** and **held** in each. It then gives the **next blocking gate** and the **recovery class** (`cancel`, `image-revert` or `forward-fix-or-restore`). Each fact carries `{status, value, source, observed_at, evidence}`. `unknown` is a valid answer and always has a `reason`. The report shape is `environment-record/estate-status-v1.schema.json`.

## vuoro.cloud operator self-use

The vuoro.cloud environment also prints `operator_self_use`, a named lower
qualification for the operator-owned `kotona` workspace on the operator-owned
host. It is independent of the estate gate: it never changes
`gate.next_blocking_gate` or `desired.release_ready`. Its status is `met`,
`not_met` or `void`; it is never a boolean and never grants use to another
user, tenant or host. The reviewed record is
`environment-record/vuoro-cloud.operator-self-use.json`, validated by
`environment-record/vuoro-cloud-operator-self-use.schema.json`.

Each referenced cutover plan and evidence file is bound to the SHA-256 digest
of its current bytes. The B2 open-rows result comes from exactly one actual
plan comment block containing `operator-self-use-open-rows:v1`; every
occurrence outside fenced code and quoted lines is counted, regardless of its
body. Zero or multiple occurrences, a malformed body, or a marker found only
inside a fence or quote are malformed, and the record's copy is not
authoritative. A changed file, including a hand-edited empty open-rows marker,
fails until reviewed. Updating a digest is the reviewer's act: whenever any
digest changes, refresh both `reviewer` and `reviewed_on`. `reviewed_on` must
be on or after every referenced evidence date. Evidence paths must be
repository-relative, contain no `..` path component, and resolve within the
repository after symlinks are followed.

The report prints the following exact status-dependent label (the same string
appears in JSON and as the sole operator-self-use Markdown line):

> met: `operator-self-use: met. NOT release_ready. Valid only for operator-owned workspace(s) kotona; grants nothing to other users, tenants or hosts. release_ready=false. Expires <YYYY-MM-DD> (<PAT expiry|review age|restored observation age>).`

> not_met: `operator-self-use: not_met (<first failing check, including its B-number when present>). NOT release_ready. release_ready=<true|false|unknown>.`

> void: `operator-self-use: void (release_ready=<true|false|null>; <void reason>). NOT release_ready.`

The qualification is void on and after the Expires date and when review age
reaches 90 days. This intentionally makes the PAT expiry day itself void
(previously it could still report met on that day).

**Change note (2026-11-09):** PAT expiry now takes effect on its stated date;
the reported `Expires` date is void on and after that date.
`void` indicates invalidating record conditions such as expiry, revocation,
stale recovery evidence, a newer rehearsal, changed pins, changed fallback,
scope expansion or stale review. B7 is waived only while
`desired.release_ready` is false. The qualification is time-bounded to the PAT
and review and is not a release qualification.

### Known limits

- Digest binding proves that referenced bytes match the reviewed record; it does
  not establish that the evidence is truthful or adequate. A reviewer must
  assess evidence and refresh `reviewer` and `reviewed_on` whenever a digest
  changes.
- `review age` is part of the expiry calculation but cannot govern a `met`
  result: the B5 check requires PAT expiry within 30 days of review, earlier
  than the 90-day review limit. Met labels therefore name PAT expiry or restored
  observation age.

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
- vuoro-cloud `usable.handshake` and `usable.catalog` use the `file:` credential designated by `environment-record/profiles/workstation-vuoro-cloud.json` (`work:read`). The path is expanded from the profile's `credential_ref`; the credential is read only for live probes, sent only in the Authorization header, and never included in output or recorded fixtures. A single trailing newline (or CRLF) is accepted; other whitespace, non-ASCII, control characters, unsafe permissions, symlinks, missing or unreadable credentials leave the facts `unknown`. Replay never reads the credential file.
- `--from FILE --json` adds `saved_report_age` (`rendered_at`, `age_seconds`, `warning`), and `--from` Markdown prints the same warning.

The report never decrypts secrets. `desired.compatibility_mirror_agrees` reports the non-secret half of `verify-runtime-pin.py`. The deployed tenant-runtime pin is `running.tenant_runtime_pin`, read only from a digest-only field of the operator rollout status (see the request below).

How it derives its answers:
- **Gate.** The next blocking gate is `none` only when every check passes and every hold is known and absent. Holds are suspended Kustomizations, CronJobs suspended without a Git declaration, Deployments scaled below their declared replicas, tenants in maintenance (except reviewed [workspaces held by design](#vuoro-cloud-workspaces-held-by-design)), and host holds. A local ref behind its remote, or a moved tag, makes desired state `unknown`, not a pass.
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

The devbox additionally reports `held.inbox_launches_disabled`, observed from the
user inbox adapter policy at `~/.config/agentops/host-adapter/policy.json`. The SSH
probe emits only its `launches_enabled` boolean, never the policy body. `false`
means this launch capability is held; `true` means this specific hold is absent.
A missing, unreadable or nonboolean field makes the fact and otherwise passing
host gate `unknown`. Historical replays without the observation remain unknown.
This observed hold is separate from `held.declared_host_holds`; an empty declared
list does not clear it. The workstation does not require an inbox adapter.

`usable.served_doctor` describes served-client usability. Neither a passing doctor
nor enabled launches proves inbox launch qualification, available authority,
harness readiness or successful execution. The host gate checks the reported
client state and holds; launch qualification remains outside this report.

## vuoro-cloud workspaces held by design

Some vuoro-cloud test workspaces stay in maintenance on purpose until they can be retired. They are listed in `environment-record/vuoro-cloud.held-workspaces.json` (schema `environment-record/vuoro-cloud-held-workspaces.schema.json`). Each entry has `workspace_id`, `slug`, `reason`, `reviewer`, `reviewed_on`, `expected_state`, `expected_maintenance_mode` (always `true`), `expected_read_only` and `retire_blocked_by`. The operator reviewed the current four entries on 2026-11-07 (`blocker12-canary`, `isolation-proof`, `g2-gen71-canary`, `g3-gen72-canary`; [readiness page §5](../dispatch/verification/2026-11-07-vuoro-cloud-workspace-readiness.md#5-estate-gate-semantics-for-held-test-workspaces-implemented-2026-11-07)).

The report reads the list from agentops `origin/main`, never from the working tree. An entry therefore takes effect only once it is merged. The local `origin/main` must equal the remote `main` (checked with `git ls-remote`). If the clone is behind, the list is `unknown` and exempts nothing; rerun with `--fetch`. This way, an entry removed upstream cannot keep hiding a hold. The list is `document.held_workspace_allowlist`.

A `maintenance_workspaces` entry from `rollout/status` stops blocking the `holds` gate only when all of these are true:

- its id is on the list (`expected_state` is always `READY`);
- the served `state` equals `expected_state`, and `maintenance_mode` is `true`;
- if the route serves `read_only`, it equals `expected_read_only` (the route does not serve it yet, so it is not checked today);
- `active_migration_id` is null or absent.

Anything else still yields `holds`. That includes an id on the list whose served fields differ; the gate detail names it as `allowlist deviates, blocking`. It also includes a list that is missing or malformed: then nothing is exempted, and the detail says `held-workspace allowlist unusable`. Malformed route data makes the tenant facts and the gate `unknown`, never a pass.

Nothing is dropped from the report:

- `held.tenants_in_maintenance` still lists every served workspace.
- `held.tenant_hold_review` splits them into `blocking`, `held_by_design`, `deviating` and `allowlist_stale`.
- When the gate stops at `holds` or reports `none`, its detail and its `notes` list carry one `held-by-design: <id> (<slug>, <reason>)` line per exempted workspace. When the `holds` check cannot be evaluated, the same lines are appended to the gate's `unknown` reason. A gate that stops at an earlier or later check leaves them out; `held.tenant_hold_review` always has them.
- `allowlist_stale` names listed ids that are no longer served in `maintenance_workspaces`, which is the signal to prune the list after a retirement.

**Scope and risk.** This changes only the agentops estate report's `holds` gate. It does not change or exempt anything in vuoro-cloud's own rollout or fleet-convergence gates. The held workspaces must still be counted there, or be retired first. For example, `isolation-proof` is on tenant schema 2, so a rollout that requires every tenant on schema 3 must not proceed past it on the strength of this list. The list duplicates the server's `is_test` fact, so it is a stopgap. Follow-up items:

- agentops#2877: deploy the retire worker.
- agentops#2878: B4 base-backup and recovery qualification.
- agentops#2879: serve `is_test`, `read_only` and a hold reason in `rollout/status`, so the list can be dropped.
- agentops#2880: retire the four workspaces and delete their entries.

## What remains unknown, and why

| Fact | Why it is unknown | What would make it known |
|---|---|---|
| vuoro-shared `usable.work_schema_version` | The handshake reports work compatibility state, not the schema number. Reading the number needs a database role (`sprintctl remote-schema check`), which this report does not hold. | Ask vuoro to add the numeric schema version to `handshake.compatibility.domains.work`. The pin and the Complete migration Job are already known. |
| vuoro-cloud `running.*`, `held.suspended_*`, `held.scaled_below_declared` | The operator tunnel is down. | Run `nmcli connection up vuoro-cloud-operator`. The report never raises the tunnel itself. |
| vuoro-cloud `held.tenants_in_maintenance` | No read-only, non-member endpoint lists workspaces in maintenance. | The rollout-status field requested below. |
| vuoro-cloud `running.tenant_runtime_pin` | The deployed pin lives only inside a SOPS-encrypted Secret. | The rollout-status field requested below. |
| vuoro-cloud `usable.handshake` | The designated workspace credential is absent/unreadable, or the gateway probe failed. | Restore the profile-designated `work:read` credential or resolve the reported gateway failure. |
| vuoro-cloud `gate.*` | These follow from the rows above. | The rows above. |

## Request to the vuoro-cloud lane

Both fields are additive to the existing operator `GET /api/control/v1/operator/rollout/status`, which already uses the operator token and returns `vuoro-rollout-status/v1`. Neither field requires decryption on the reader's side, and neither exposes a credential. `agentops estate status` already reads both when present; no change on the agentops side is needed.

1. **`maintenance_workspaces`** (array; empty means none) lists every workspace whose `maintenance_mode` is true or whose `state` is `MAINTENANCE` or `MIGRATING`. Each entry is `{"id", "state", "maintenance_mode", "active_migration_id", "since"}`, built from the same `workspaces` columns that `cli_routes.py`'s rollout route already selects. The estate report treats a non-empty list as a hold, except entries on the reviewed held-by-design list whose served fields match (above), and the empty list as "no tenant held". Adding `slug`, `is_test`, `read_only` and a hold reason per entry (agentops#2879) would let the report drop that list.
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

## Checkout freshness at session start

Before planning reads, run:

```sh
python3 scripts/checkout_freshness.py --fetch   # or: agentops checkout-freshness --fetch
```

For agentops, sprintctl, vuoro, vuoro-cloud, sovite, cred-broker, appservice and gitops-nixos under `/projects/dev`, it reports:
- the current branch;
- local `main` ahead/behind `main@{upstream}` (falling back to `origin/main`);
- the last fetch time (the newer of the remote-tracking ref's newest reflog entry and `FETCH_HEAD`);
- dirty tracked paths, and untracked entries in git's `normal` mode (a wholly untracked directory counts once);
- the worktree count.

`--fetch` runs a non-interactive `git fetch --no-auto-gc --recurse-submodules=no` of the upstream remote, which updates only remote-tracking refs and `FETCH_HEAD`; nothing touches a working tree, index or local branch. Pass repo names, absolute paths or `NAME=PATH` to override the list. `--json` emits `checkout-freshness/v1`. `--strict` exits 1 when any main is behind or any checkout is dirty; without it the exit is always 0. A git query that times out shows as `timeout`; any other missing value as `unknown`. The schema catalog records each sibling's upstream sha, so `schema_catalog.py --check` reports stale after any sibling push and fetch, even with no schema change: regenerate with `python3 scripts/schema_catalog.py` and commit.

The report is advisory, not a hook. A behind main means file reads describe an older state than the remote: pull, or read from `origin/main`, before planning from them.
