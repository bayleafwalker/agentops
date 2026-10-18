# Estate interface source census (EC-01 seed)

This is a source-only discovery seed for [EC-01](../plans/agentops/2026-10-18-estate-contract-rewrite.md#interface-inventory-and-disposition-contract), not a complete interface inventory, owner attestation, configured-deployment register, or evidence of current runtime use. The machine-readable companion includes **32 repositories confirmed public by canonical GitHub visibility**, 62 root-level interface candidates, and 7 member-level source boundaries across Agentops, Vuoro, and Sprintctl. The member-level records cover Agentops’ estate-status MCP tool and native host adapter, Vuoro’s service HTTP API, MCP edge and Python client, and Sprintctl’s work/inbox operation family.

Each record has a stable ID, exact local Git HEAD, hashes for inspected source files, and explicit unknown fields. Dirty checkouts are marked; HEAD alone does not identify dirty bytes. The 62 root-level candidates comprise declared CLI entry points, dispatch-manifest candidates, and package API candidates. These are seeds for deeper discovery, not claims that every command, method, protocol or consumer has been found.

## Boundaries this pass could identify

| Source evidence | Candidate boundary | What remains unknown |
|---|---|---|
| Python/JavaScript/Go/Rust package manifests | Package API candidate, with declared package name/version where available | Exported member list, producer/consumer edges, wire/schema contracts, authority, persistence, retry semantics and live use |
| Python `project.scripts` | One record per declared CLI command and entry point | Subcommands, machine-readable schemas, auth/target, side effects, version compatibility and configured use |
| `<repo>.dispatch.json` | Agent-tooling manifest candidate | Effective loader, installed revision, runtime adoption, consumers and whether the declaration is active |
| Directly inspected service and adapter source | HTTP/MCP/owner-operation boundary with source-declared method and operation facts | Exact deployed versions, full input/output compatibility, all callers and live use |
| Build/deployment manifests and READMEs | Repository discovery evidence only | Rendered or deployed configuration and actual service/tool clients |

The confirmed-public source subset exposes declared commands including `sprintctl`, `actionctl`, `credctl`, `auditctl`, `kctl`, `scribectl`, `acceptlab`, `box-validate`, and `cfo`. Exact entry-point module names and file hashes are in the JSON. Direct source inspection also found Agentops’ `estate_status` MCP tool and host-adapter owner calls, and the Vuoro `/api/meta/v1/handshake`, `/api/catalog/v1`, `/api/invoke/v1`, and `/mcp` paths. These are source declarations, not evidence of deployment or use.

## Coverage and next discovery

The local source survey included primary owner repos and smaller projects. Only repos whose canonical GitHub `visibility` field returned `public` are represented in the JSON. Repositories whose canonical visibility was private or could not be verified are excluded from this public artifact and require separate entitled owner review. Visibility checks retained only the canonical `public`/`private`/`unverified` enum; no credentials, API response bodies or remote URLs were saved. Repositories with `owner-unconfirmed` still need owner assignment before their boundaries can be disposed.

The owner-level inventory still needs per-method/API and schema extraction, configured-deployment reconciliation, generated-client and artifact/event inspection, and owner-identified consumer lists. This pass did not query deployment configuration or live traffic. Authentication/target, authority/persistence, data/retention, retry/delivery, use evidence, disposition, compatibility, cutover/rollback and shim expiry remain unknown or unassigned where not stated in source. Some owner source is not publicly visible; its source-level details are omitted here and require entitled owner review. Target contract packages remain pending EC-00; no protobuf or transport choice is assumed.

Next, owners should expand package/CLI/dispatch candidates into concrete operations, artifact/event boundaries and schema revisions, then reconcile source dependency edges with configured consumers. Add live observations only as separately sourced evidence. Source text, manifests, tests and dependency declarations cannot stand in for runtime observation. Retired components remain candidates until their current callers, deployed residue and owner disposition are verified.

## Capture limits

The public JSON was generated from local checkouts, not freshly fetched remote trees. Evidence hashes bind only the selected files at capture time; local branches may lag canonical main. Included records identify dirty local checkouts. Repositories not confirmed public are excluded from the public artifact and require entitled owner review. No credentials, cluster state, production service, or live consumer traffic were accessed. Any separately retained host-local source inventory must not be published without an owner/privacy review.
