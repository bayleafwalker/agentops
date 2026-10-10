# Real client compatibility evidence

Agentops owns this offline lab record and validator. Vuoro owns protocol
conformance; Cloud owns the existing endpoint and disposable hosted workspace.
This lab introduces no server, OAuth client, credential store or compatibility
authority. It never starts paid API inference. A dated observation does not
prove current availability, a vendor attestation, or an authorized effect.

Run from the agentops checkout:

```bash
python scripts/validate_client_compatibility.py matrix.json --evidence-root /path/to/private/redacted-receipts
python -m pytest scripts/tests/test_client_compatibility.py -q
```

The validator reads inputs and prints a derived report. Exit 2 means malformed,
unbound or changed evidence. A valid matrix can have every stage unknown. No
overall supported/unsupported verdict is inferred from partial observations.
Each pass/refusal is bound to exact surface, mode, observed date, endpoint,
version (including explicit unknown), stage and receipt bytes. Unknown auth,
workspace and repository identities remain named unknowns. Input receipts and
matrix are redacted before storage; headers, tokens, cookies, client secrets,
raw errors and arbitrary transcript fields are outside the allowlist. Hashes
bind redacted request/response artifacts; they do not attest who authored them.

## Product matrix contract

The `client-compatibility/v1` matrix has exactly `schema`, `as_of`, `endpoint`
and `clients`. `as_of` is an aware UTC timestamp; `endpoint` is the existing
`https://api.vuoro.cloud/mcp`. Each client has exactly `surface`, `mode`,
`version` (a redacted identifier or null), and `stages`. Include every row,
even when unavailable. Claude Code is an additional diagnostic row, separate
from Claude UI and API.

| Surface | Permitted mode | Separate evidence needed |
| --- | --- | --- |
| claude_ui | ui_oauth | Actual UI discovery, consent and rendered call |
| claude_api | api_bearer | Actual API connector trace; UI OAuth cannot substitute |
| claude_code | local_cli_oauth | Actual local tool exposure and call; connection health alone does not qualify |
| chatgpt_ui | ui_oauth | Actual ChatGPT UI tool visibility and call; Codex app exposure cannot substitute |
| codex_local | local_cli | Actual local CLI connection and tool trace |
| codex_local | local_app | Actual local app tool trace; this does not qualify the CLI |
| codex_cloud | hosted | Actual hosted session tool trace; undocumented/inaccessible behavior remains unknown |

Include both local Codex modes as separate rows, even when one is unobserved.
Every row has `discover`, `consent`, `call`, `refresh`, `reconnect`. Each stage
has exactly `status`, `reason`, `receipt`: status is `pass`, `refused`,
`unavailable` or `untested`; reason is a bounded redacted category. Unknown
stages have null receipt. Observed stages reference a relative receipt `path`
and lowercase `sha256`; absolute paths, traversal, escaped symlinks, changed
bytes, duplicate JSON fields and files over 1 MiB are refused.

Receipts have exactly these fields:

```json
{
  "schema": "client-observation/v1",
  "kind": "client_trace",
  "surface": "codex_local",
  "mode": "local_app",
  "version": "0.162.1",
  "stage": "call",
  "observed_at": "2026-10-10T06:22:00Z",
  "endpoint": "https://api.vuoro.cloud/mcp",
  "outcome": "refused",
  "tools": [],
  "tool": "describe_work",
  "request_sha256": "<64 lowercase hex characters>",
  "response_sha256": "<64 lowercase hex characters>",
  "error_code": "item-not-found",
  "auth_method": null,
  "workspace_id": null,
  "repo_id": null,
  "consent_scopes": []
}
```

This example describes a refusal shape, not successful item retrieval. A
successful discovery needs the actual visible tool inventory; a call needs
the actual tool name. A refusal needs its observed code. Consent and refresh
passes need observed OAuth authentication; consent also needs actual scopes.
`configuration`, `connection_health`, and `protocol_conformance` are allowed
receipt kinds for retaining diagnostics, but cannot qualify any client stage.
Do not populate auth or tenancy fields from registration configuration or a
different session. Where a tool wrapper hides transport/auth facts, leave
them null. No raw bearer/token response belongs in a receipt.

## Reuse strict conformance #2522

The existing Vuoro job `mcp-strict-client` runs
`scripts/mcp_strict_client.sh vuoro-service:ci`; its Python checker and pinned
`scripts/mcp_schema/2026-07-28.schema.json` validate the protocol envelopes,
completion/cache values, structured/text results, error/refusal shape,
assertion replay, edge proof and D-044 two-workspace isolation. Keep that
implementation and its deliberate regression tests in Vuoro. Do not copy its
schema or start a second public test service in agentops. Bind its CI receipt
to exact Vuoro source and service image digest in the private lab packet.
Protocol conformance is a prerequisite diagnostic, never vendor UI evidence.

## Probe and privacy procedure

Use a Cloud-owned disposable workspace through the existing endpoint and
already authorized named client. Record exact released endpoint/image/source,
client product/mode/version or unknown, observation time and authorized tenant
scope. Capture real tool visibility and one harmless bounded read with its
redacted request/response digests. Record one actual refusal; do not fabricate
a JSON variant as a native client response. For UI surfaces, preserve a
redacted client transcript/screenshot and correlate the exchange independently
where Cloud exposes a safe receipt. A transport-only HTTP probe cannot prove
the UI rendered a tool. A connection health command cannot prove a call.

Consent, refresh and reconnect require their own observed traces. Reuse the
existing grant and do not create vendor clients or broaden authorization for
this lab. Do not force production revocation/expiry to create a negative case.
Leave infeasible stages unknown. Paid API execution is excluded from this
implementation; Claude API therefore remains untested until a separately
authorized non-paid evidence route exists.

Store real traces, tenant identifiers and private source provenance in the
host-private implementation packet, outside public git. Publish only reviewed
redacted outcomes. The source template intentionally starts with all stages
untested; filling it is an evidence operation, not a change to product policy.
Registration/CIMD decisions consume actual demonstrated needs and must not
turn an unobserved ChatGPT tool-visibility gap into a configuration inference.

Current official OpenAI integration guidance:
[connect and test a plugin](https://developers.openai.com/plugins/quickstart)
and [Codex MCP configuration](https://developers.openai.com/learn/docs-mcp).
Those describe supported mechanisms; they do not establish account access or
prove this installation completed an actual client call.
