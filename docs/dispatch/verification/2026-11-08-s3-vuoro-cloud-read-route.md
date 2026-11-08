---
status: blocked-on-route-contract
last_verified: 2026-11-08
---

# S3 Vuoro Cloud workspace read route

## Finding

The requested work-data read route is **not established** from the checked-in
contracts. A workspace PAT is the credential class for Vuoro/Sprintctl API
operations (`/projects/dev/vuoro-cloud/03-TENANCY-IDENTITY-AND-AUTHORIZATION.md:39-46`),
but Vuoro service exposes work operations through `POST /api/invoke/v1`
(`/projects/dev/vuoro/packages/vuoro-client/src/vuoro_client/client.py:230-250`).
Its GET routes are handshake and catalog (`/projects/dev/vuoro/packages/vuoro-service/src/vuoro_service/app.py:236-261`),
which describe the service and operation schemas; they do not return kotona work
records. The read-only work operation is still transported as POST. The service
client sends `Authorization: Bearer <token>` and
`X-Vuoro-Client-Protocol: 1` (`/projects/dev/vuoro/packages/vuoro-client/src/vuoro_client/client.py:86-101`),
and invocation adds a JSON body to the POST.

The observed `POST /mcp` rejection is expected for this credential class: `/mcp`
is the OAuth/MCP gateway route, not the workspace PAT's Sprintctl API. For
`POST /api/invoke/v1`, vuoro-cloud converts the workspace token into a short-lived
gateway identity assertion and forwards the request ID with it
(`/projects/dev/vuoro-cloud/src/vuoro_cloud/gateway.py:2023-2055`,
`2185-2198`). The service requires the signed request ID to match both the
invocation envelope and request middleware state
(`/projects/dev/vuoro/packages/vuoro-service/src/vuoro_service/gateway_identity.py:370-380`).
Therefore the reported `identity-required: gateway identity request correlation
failed` is evidence of a gateway/client correlation-contract mismatch (or a
version-skew bug in that forwarding path), not a missing `sprintctl` profile
option: the profile controls expected environment and credential resolution,
whereas the failing comparison is between server-side request IDs. No
credential-kind change is indicated by these sources.

**The acceptance route remains unproven.** The checked-in code does not prove a
successful PAT-authorized invocation returning kotona records, and the requested
GET-only probe cannot fetch records over this API. Do not treat metadata/catalog
success as a work-data read. Resolving the correlation failure requires aligning
or repairing the deployed gateway and service request-ID contract; no live call
was made in this work.

## Profile environment ID

Yes: `target.environment_id` must be the tenant runtime's actual handshake
environment, in this case `vuoro-cloud-ws-01m3abjs1qw0`, for sprintctl's
environment check to succeed. The current profile has generic `vuoro-cloud`
(`environment-record/profiles/workstation-vuoro-cloud.json`), while the served
client compares that value directly with the handshake environment
(`/projects/dev/sprintctl/sprintctl/backend.py:232-238`; client check in
`/projects/dev/vuoro/packages/vuoro-client/src/vuoro_client/client.py:114-124`).
The reported run getting past this check implies its test profile already used
the per-workspace ID.

Proposal (not implemented): allow the exact `vuoro-cloud-ws-<lowercase-ulid>`
form in `scripts/validate_vuoro_profiles.py` (currently only literal
`vuoro-cloud` is permitted at lines 296-314) and in
`environment-record/vuoro-client-profile.schema.json` (currently generic token
shape plus a conditional on literal `vuoro-cloud`). Keep the authority invariant
exactly `work:read` for both forms, and validate the lowercase ULID suffix.
Consider whether the client profile also needs a separate stable target class
field so tenant identity is not inferred from an unrestricted string.

## Local probe

`scripts/vuoro_cloud_read_probe.py <credential-file>` reads the supplied file at
runtime and performs GET requests only to handshake and catalog. It emits only
the returned environment name and work-operation IDs/titles. It deliberately
does not print credentials, arbitrary response fields, or claim that it read
work data. Its unit test stubs the HTTP layer; neither was run against the
network.

The request method/path/headers proven by current source for service operations
are `POST /api/invoke/v1`, `Authorization: Bearer <PAT>`,
`X-Vuoro-Client-Protocol: 1`, plus the invocation JSON body; that method is
read-only only when the selected catalog operation has read semantics. This
does not satisfy the separately requested GET-only work-data probe constraint.
