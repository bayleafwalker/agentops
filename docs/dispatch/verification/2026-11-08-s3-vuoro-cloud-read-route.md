---
status: resolved-cause-confirmed
last_verified: 2026-11-08
---

# S3 Vuoro Cloud workspace read route

## Finding

**The `work:read` workspace PAT route is live; the failed call exposed a
request-correlation mismatch between vuoro-client and the gateway.** Operator
live evidence on 2026-11-08 used the `kotona` workspace PAT and repo ID `vuoro`:

- `GET /api/catalog/v1` and `GET /api/meta/v1/handshake` succeeded.
- `POST /api/invoke/v1` for `work.read.sprints`, using the catalog revision
  returned by the GET, failed with 401 `identity-required` / `gateway identity
  request correlation failed` when `X-Request-ID` was absent.
- The same invocation succeeded with `X-Request-ID` equal to the body
  `request_id`; it returned `repo_id` and two sprints:
  `m1-4-scenario-20260929T082145Z` and `restore-drill-2026-09-25`.

The code explains the result. `vuoro-client` puts a generated request ID in the
invocation body, but its POST does not send that ID as `X-Request-ID`
(`vuoro/packages/vuoro-client/src/vuoro_client/client.py:224-250`). The
gateway middleware therefore mints its own ID
(`vuoro-cloud/src/vuoro_cloud/gateway.py:722`). The PAT proxy signs and
forwards the middleware ID (`vuoro-cloud/src/vuoro_cloud/gateway.py:2185-2198`),
while the service requires the signed ID to match the invocation envelope
(`vuoro/packages/vuoro-service/src/vuoro_service/gateway_identity.py:365-370`).
This confirms a client/gateway handoff bug, not a missing profile option or
missing PAT authority. The credential table identifies workspace API tokens as
the Vuoro/Sprintctl API credential
(`vuoro-cloud/03-TENANCY-IDENTITY-AND-AUTHORIZATION.md:33-34`).

The durable fix belongs at either end of this handoff: vuoro-client can send
`X-Request-ID` equal to the body ID on `/api/invoke/v1`, or the gateway PAT
proxy can sign with the body `request_id` (connector `dispatch_operation`
avoids the mismatch by building its own envelope with the middleware ID).
Line numbers refer to vuoro-cloud `bcc55a9`; they have since moved. The probe uses the verified matching-header
workaround until that fix is deployed. `/mcp` refusing workspace tokens is by
design; it is the OAuth/MCP route, not the PAT work API. Cloudflare returns
error 1010 for Python's default User-Agent, so the probe uses the plain client
name `agentops-operator`.

## Profile environment ID

`target.environment_id` must match the tenant runtime handshake name,
`vuoro-cloud-ws-01m3abjs1qw0`, for Sprintctl's environment check to pass. The
workstation profile now uses this per-workspace ID. The validator and schema
accept only the generic `vuoro-cloud` ID or the exact lowercase
`vuoro-cloud-ws-<26-character-id>` form; both remain production targets with
exactly `work:read` and `production_endpoint_denied: false`. Sprintctl compares
the configured value with the handshake environment
(`sprintctl/sprintctl/backend.py:232-238`,
`vuoro/packages/vuoro-client/src/vuoro_client/client.py:124-131`).

## Local probe

`scripts/vuoro_cloud_read_probe.py <credential-file> --repo-id vuoro` reads the
provided credential at runtime, gets handshake and catalog metadata, then
invokes only `work.read.sprints` with the catalog revision and matching
`X-Request-ID`/body `request_id`. It refuses redirects and uses
`User-Agent: agentops-operator`. Output is limited to sprint names and their
count. Unit tests stub every HTTP request; no live network call was made by
this change.
