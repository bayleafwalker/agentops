# Operator requests from native runtimes

AgentOps provides one CLI and one stdio MCP adapter over Sprintctl's
`operator-request/v1` owner operations. The CLI command is
`agentops operator-requests`; the MCP server is
`agentops operator-requests mcp`. Both use the same bounded Vuoro client
adapter. Sprintctl binds the authenticated principal and workspace, checks
revisions, and enforces operation scopes. Request packets remain untrusted
instructions and never grant effect authority.

## Configure a local runtime

Set `AGENTOPS_VUORO_PROFILE` in the native runtime's process environment to a
protected `vuoro-client-profile/v1` file for the intended development or
workstation environment. The profile selects the environment; its `file:`
credential reference is resolved by the released Vuoro client helper. Do not
put credential values in the profile, MCP configuration, a request packet, or
command arguments. A production target denied by the profile is refused.

Copy `mcp/agentops-operator-requests.mcp.json` into a harness MCP configuration
and replace `/path/to/agentops` with the checked-out AgentOps path. The process
inherits `AGENTOPS_VUORO_PROFILE`. The server exposes finite tools named
`operator_request_publish`, `operator_request_get`, `operator_request_list`,
`operator_request_events`, `operator_request_revise`,
`operator_request_dependent_add`, `operator_request_dependent_withdraw`,
`operator_request_progress`, `operator_request_report_performed`,
`operator_request_attest`, `operator_request_decline`, and
`operator_request_supersede`. Each takes `repo_id` and an `arguments` object;
the owner catalog and operation schema remain the source of argument rules.

The request owner must advertise the requested operation. Older or otherwise
unsupported owners return `owner-capability-unavailable`; AgentOps does not
emulate request state locally. Calls also fail closed when the profile,
credential helper, service handshake, or transport cannot be used.

## CLI

Pass one JSON argument object from a file or stdin. For example:

```sh
agentops operator-requests invoke publish \
  --repo sprintctl \
  --arguments /secure/path/publish-operator-request.json
```

The object follows the operation's owner schema. A publish includes a stable
`req_` ID, a complete `operator-request/v1` packet, every dependent work/session
pair, and an idempotency key. Revision, progress, report, decision, and
attestation operations include the current expected revision. The service
validates these fields again; AgentOps does not treat a successful transport
call as evidence that the operator's requested work was performed.

Raw transcripts, credentials, authority claims, and identity claims are
refused in request arguments. Text that resembles common credential formats is
also refused. This is a screening check, not a general secret detector: keep
secret values and conversation transcripts out of all request text.

## Runtime qualification limits

This adapter is a local stdio interface only. Claude Code and Codex local
installations must each be configured and exercised separately. Codex Cloud,
Claude hosted sessions, wake/resume behavior, and any mode without a local stdio
MCP client are not qualified by this source change. Session closure never
resolves a request. A performed report remains pending verification. The
current owner candidate exposes human attestation as its completion-basis
path; `work:approve` is required for attestation or decline, and that scope
does not authorize a protected effect.

## Continuation-ready fallback

When a native runtime cannot wake a successor, request a read-only fallback
packet after resolution:

```sh
agentops operator-requests continuation-ready --repo sprintctl \
  --request-id req_01JZZZZZZZZZZZZZZZZZZZZZZZ --profile /secure/path/vuoro-profile.json
```

The command reads the current request snapshot and its event at the current
revision. It emits a fallback only for a resolved request whose event identifies
the owner's `resolved-human-attestation` basis. A `report-performed` result by
itself is refused. Active dependants are marked `continuation-ready` only when
owner freshness is current and their source work revision still matches;
others are marked `needs-refresh`. The packet contains request/work identity
and owner event coordinates, not attestation text or actor identity. It does not
wake a runtime, acknowledge delivery, change owner state, or replace reading the
full current request packet from the owner.

## Offline publication outbox

For offline callers, the CLI provides a local outbox for `publish` only. It
stages content without contacting the owner; staged entries are explicitly
unsynced and confer no grant, owner acceptance, or completion. Stage only
complete request packets with the original stable `req_` request ID and
`idempotency_key`:

```sh
agentops operator-requests outbox stage-publish --repo sprintctl \
  --arguments /secure/path/publish-operator-request.json
agentops operator-requests outbox list
agentops operator-requests outbox deliver --profile /secure/path/vuoro-profile.json
agentops operator-requests outbox reconcile --profile /secure/path/vuoro-profile.json
agentops operator-requests outbox prune-acknowledged
```

Delivery is manual and sends the exact staged request ID, arguments, and
idempotency key back to the owner. The owner decides whether it is new,
already applied, stale, or conflicting. Only the owner response containing
exactly the matching `request_id`, a positive integer `revision`, and boolean
`replayed` marks the entry acknowledged. Once a publish call has started, a
transport failure or malformed acknowledgement moves the entry to `uncertain`
and further delivery skips it. Reconcile performs a repo-scoped owner `get`:
a matching current snapshot acknowledges it, and an explicit owner `not-found`
returns it to `pending`; changed or malformed snapshots and read/auth failures
leave it `uncertain`. `prune-acknowledged` removes acknowledged rows to free
bounded local storage.
The outbox never retries an effect, attestation, decline, or other operation.
It does not resolve ambiguous owner outcomes locally. Re-delivery after a
confirmed absence is explicit and relies on owner idempotency for the preserved
key.

The default path is `$XDG_STATE_HOME/agentops/operator-requests` or
`~/.local/state/agentops/operator-requests`; set
`AGENTOPS_OPERATOR_REQUESTS_OUTBOX` to choose another location. Storage is
limited to 200 rows and 1 MB, requires an owner-only directory and regular
singly-linked files, uses no-follow opens and atomic replacement, and refuses
obvious credential/transcript/authority/identity fields before writing. This
screen is not a general secret detector. The outbox is local plaintext; protect
the host account and do not stage confidential values. There is no automatic
background delivery, cross-machine sync, or native wake/resume integration.
