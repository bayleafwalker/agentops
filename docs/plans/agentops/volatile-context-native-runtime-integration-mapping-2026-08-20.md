---
doc_id: volatile-context-native-runtime-integration-mapping-2026-08-20
status: current_mapping
created_at: 2026-08-20
owner: agentops
source_bundle: volatile-context-implementer-bundle@0.1.0
---

# Volatile-context native-runtime integration mapping

This completes the integration-mapping step for the imported volatile-context
bundle without modifying that checksum-pinned historical artifact. It maps the
bundle's useful projection/CAS requirements onto the 2026-08-20
native-runtime/federation boundary and identifies concepts that must be retired
rather than implemented.

Governing plan:
[`native-runtime-federation-realignment-2026-08-20.md`](native-runtime-federation-realignment-2026-08-20.md).
Source template:
[`volatile-context-implementer-bundle/docs/integration-mapping-template.md`](volatile-context-implementer-bundle/docs/integration-mapping-template.md).

## Existing-system mapping

| Reference concept | Existing owner/surface | Required integration | Evidence/gate |
|---|---|---|---|
| dispatch binding lookup | **Retired concept:** no dispatcher-owned queue row in the target | Resolve a native session/execution reference through ActionQ's federation API after its schema is owner-defined; manual sessions may remain explicitly unbound | Reference round-trip; missing/foreign refs fail closed; assurance level is mandatory |
| repo identity lookup | Agentops `project.toml`, root `*.dispatch.json`, and rendered project context | Use the stable project/member `repo_id`; never infer authority from a worktree path | Project renderer and dispatch-manifest validation |
| task revision/watermark | Sprintctl item read contract (`status_revision`) through its owning CLI/served adapter | Project the opaque Sprintctl revision and re-read it before mutation | Sprintctl stale-CAS tests on SQLite/PostgreSQL and served parity |
| atomic task mutation | Sprintctl owner operation with `--expected-revision` / equivalent served argument | Keep CAS at the authority boundary; hooks remain early feedback only | One winner under concurrent mutation; stale basis has no row/event effect |
| attributed claim append | **Retired concept:** Sprintctl v0.3.0 has no exclusive claim capability | If coordination visibility is needed, create/touch/reassign an advisory reservation. Do not describe it as proof or gate a projection/mutation on it | Overlapping reservations are both visible; status mutation still requires only the correct revision |
| idempotency identity | Sprintctl accepted/rejected command ledger for work mutations; ActionQ owner-defined idempotency for federation writes | Keep domain identities separate. A native execution reference must not become a Sprintctl mutation idempotency key | Lost-response retry returns the original domain decision/reference without duplicate effect |
| local consumer cursor | Disposable hook-adapter cache keyed by federation reference, harness, native session/subagent, and provider | Store only last-emitted provider revision/time; loss may duplicate projection but never authorize a write | Delete-cache test produces at-least-once reinjection only |
| served projection routing | Vuoro transport/composition over pinned Sprintctl and ActionQ domain adapters | Add projection reads only after the owner operations exist; Vuoro owns no projection authority or execution state | Catalog/schema compatibility, tenant/auth isolation, unavailable-owner degradation |
| actor credential resolution | Existing Vuoro/Appservice identity path and domain-scoped credentials | Resolve separately for Sprintctl reads/mutations and ActionQ federation writes; native runtime credentials never grant owner-domain mutation | Wrong-domain credentials rejected; logs contain no credential material |
| host capability generation | Agentops environment records and generated `.agents/environment.generated.md` pointers | Project bounded capability facts from the active environment record; do not dump environment variables | Deterministic render and secret-field rejection |
| workspace identity | Git repository identity plus Agentops project/member binding | Treat absolute worktree paths as host-local observations, never durable bindings or handoff references | Cross-host test succeeds from commit/PR/ref alone and rejects path-only handoff |
| metrics | OpenTelemetry instrumentation routed by Appservice | Emit provider ID, revision, bytes, latency, result class, runtime and assurance labels; no raw projected content | Schema check plus redaction test |
| structured logs | Existing deployment logging/Loki path | Log identifiers and result classes only; transcripts and raw projections are opt-in evidence with separate retention | Secret/raw-content negative tests |
| Claude hook/settings distribution | Root dispatch manifest hook selection plus Agentops lifecycle-adapter contract | Use native Claude hooks as projection/feedback adapters, not execution launchers or authorities | Native hook fixture and disabled-hook authoritative-CAS test |
| Codex hook/plugin distribution | Root dispatch manifest hook selection plus Agentops lifecycle-adapter contract | Use the smallest native Codex integration available; record only the binding assurance the runtime actually exposes | Native adapter fixture, disabled-hook CAS test, assurance downgrade test |
| large/raw harness evidence | Outctl is retired; standard telemetry plus selected Langfuse or Phoenix/object storage | Keep raw evidence non-authoritative, redacted, retention-scoped, and referenced by digest/URI | Retention/redaction decision plus digest retrieval test before enablement |

## Write-path inventory

| Mutation path | Revision support | Atomic/attributed/idempotent boundary | Migration action |
|---|---|---|---|
| Sprintctl CLI | Shipped on Sprintctl `origin/main` v0.3.0 for status mutations | Sprintctl owns CAS and audit history; reservation identity is advisory | Use current reservation/CAS verbs; remove claim-token assumptions from hook copy |
| Vuoro served work API | Must preserve the Sprintctl revision argument and decision result | Domain adapter calls Sprintctl; Vuoro does not reimplement CAS | Prove CLI/served accepted and rejected histories match |
| MCP tools | Tool-specific; never assumed from protocol transport | Must call the same owner operation with the same revision/idempotency fields | Do not enable mutation tool enforcement until bypass still fails at authority |
| Native runtime/coordinator federation writes | ActionQ federation schema not yet landed | ActionQ must own reference creation/reconciliation and its idempotency; the native runtime owns only its execution | Block implementation until the ActionQ owner contract exists; no queue-row fallback |
| Maintenance/reconciliation | Owner-specific | Reconciliation proposes or records references through owning APIs; no direct cross-domain SQL | Fault-test retries, duplicate delivery, and unavailable owners |
| Tests/fixtures | Disposable only | May use fakes to falsify contracts, never as evidence of deployed owner behavior | Run owner suites plus cross-boundary black-box acceptance |

## Bundle concepts explicitly not carried forward

- `VUORO_DISPATCH_ID` as a required queue-row binding;
- dispatcher environment injection as the primary binding event;
- an attributed **claim** append or claim proof;
- a dispatcher/worker internal write path;
- ActionQ daemon ownership of hook launch, worktrees, or session continuation;
- Outctl capture/projection as an active member.

The successor binding identifier must name a federated external execution, not
an ActionQ-owned execution attempt. Until that owner schema exists, volatile
context may project Sprintctl and environment data for a manually/native-bound
session, but it must report federation binding as unavailable rather than
manufacture one.

## Acceptance pins

Pin these exact values in any implementation packet; do not inherit the dates
in this plan as runtime truth:

```text
ActionQ federation schema/API revision: pending owner contract
Sprintctl owner baseline: origin/main 15afc87 (v0.3.0) or newer reviewed revision
Agentops boundary baseline: this document's Git commit
Claude Code version and hook contract: observed at acceptance time
Codex CLI/app version and integration contract: observed at acceptance time
Vuoro catalog/service revision: observed released artifact
Telemetry backend and retention policy: pending operator selection
```

Hook enablement remains reversible. Disabling hooks must restore ordinary
native runtime behavior while Sprintctl CAS and ActionQ federation validation
continue to enforce their own contracts.
