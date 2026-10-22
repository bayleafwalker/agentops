# MCP compatibility: retain and qualify the current implementation

Status: source disposition and regression checklist, 22 October 2026.

## What is already present

At inspected Vuoro commit `1eae8ace228af39bd224565bac5be0a1fb7c4f25`, the
[MCP edge](https://github.com/bayleafwalker/vuoro/blob/1eae8ace228af39bd224565bac5be0a1fb7c4f25/packages/vuoro-mcp-edge/README.md)
supports `server/discover` and no-handshake tool calls for revision `2026-07-28`.
It also accepts the documented older initialization revisions. It serves
stateless JSON POST responses without SSE or protocol-session identifiers.
The recommendation to build a new 2026-07-28 surface is therefore superseded
by this source observation. Installed source and actual client behaviour still
need their own evidence.

The existing
[client-compatibility lab](../../../../apps/client-compatibility/README.md)
already separates protocol conformance, configuration, connection health and
actual product-client observations. Reuse its matrix and validator. Vuoro's
strict-client job and pinned MCP schema remain the protocol gate; do not copy
the schema into Agentops or treat a protocol test as evidence that a particular
hosted UI exposes or successfully calls a tool.

## Durable operation identity is also already defined

The edge's
[idempotency contract](https://github.com/bayleafwalker/vuoro/blob/1eae8ace228af39bd224565bac5be0a1fb7c4f25/packages/vuoro-mcp-edge/src/vuoro_mcp_edge/idempotency.py)
requires a caller key for write-class tools. Scope includes workspace,
principal, tool and key; the remaining arguments are digest-bound. Reusing
the same key/body returns the stored result; changing the body conflicts.
The domain record owner holds the durable ledger. The in-memory ledger is a
test reference and must not be deployed.

A transport retry uses a new request ID while retaining the logical operation
key and arguments. This distinction follows the
[2026-07-28 transport change](https://modelcontextprotocol.io/specification/2026-07-28/changelog).
The key needs to survive the real retry path, including a new process when
supported. An origin-session/sequence pair is sufficient only when that path
preserves it for the same logical operation. Do not replace the existing key
contract with a transport-derived key.

## Evidence to refresh when the boundary changes

| Scenario | Evidence required | Reuse / owner |
| --- | --- | --- |
| New-revision client | Discovery and one actual bounded tool call at the named revision; no hidden initialize dependency. | Vuoro `test_edge_protocol.py`, strict-client job, then actual-client matrix. |
| Supported legacy client | Initialization and common tool operation still work within the declared compatibility window. | Vuoro protocol tests and named consumer trace. |
| Version/header/body mismatch | Deterministic refusal; no owner effect or accidental silent downgrade. | Vuoro protocol and assertion-boundary tests. |
| Same operation retried after lost response | Same logical key and body, new transport request, one owner effect and the first result. | Owner durable-ledger test, with receipt binding the exact implementation. |
| Concurrent duplicate or changed payload | No duplicate effect; conflicting payload cannot inherit another request's result. | `test_ledger_behaviour.py` plus the durable owner implementation. |
| Different principal/workspace | No cross-caller replay or key-existence leak; current authority still checked. | Edge auth and owner isolation cases. |
| Restart during an incomplete operation | Owner state distinguishes incomplete, committed and unknown external effect; reconciliation precedes a potentially duplicate external action. | Relevant record/effect owner; an in-memory test is insufficient. |
| Client reconnect/refresh | Actual selected client trace with exact mode/version, observation time and endpoint. | Existing compatibility matrix; connection health alone does not qualify it. |

Do not infer that every row is currently passed because corresponding source
tests exist. Refresh the affected checks on the exact source/release and retain
unknown client stages. Keep paid API execution and destructive expiry/revocation
experiments outside the existing non-paid disposable-client procedure unless
separately authorized.

The [21 October contract ADR](../../../architecture/2026-10-21-ec00-contract-stack-adr.md)
keeps MCP as an external protocol and projects tool schemas from the selected
estate contract source. Any new schema work follows that decision; there is no
second hand-authored MCP contract in this packet.
