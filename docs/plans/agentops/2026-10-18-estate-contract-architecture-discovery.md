# Estate contract rewrite: architectural discovery and stack alternatives

Date: 18 October 2026. **Completed source/documentation discovery; provisional architecture recommendation.** No candidate implementation, benchmark, deployed migration or supplier qualification is claimed. EC-00 owns the executable comparison and final ADR. The [requirements map](2026-10-18-estate-contract-rewrite.md) governs all candidates.

## Decision and recommendation

The operator has selected an estate-wide rewrite destination, and subsequently requested an open comparison of protobuf with potentially better solutions. Preserve the rewrite scope; keep the canonical IDL, transport and implementation-language choices open until EC-00 passes. This is not a return to an optional isolated experiment. The first complete operator-action workflow qualifies a foundation intended for the whole estate.

**Provisional lead: protobuf-authored contracts with reproducible generation and compatibility checks, native gRPC where it fits, and a browser-capable edge selected on evidence. Strongest challenger: TypeSpec-authored OpenAPI/JSON Schema with generated Python/TypeScript interfaces and explicitly specified resumable events.** A binary encoding alone is not the architectural benefit. Shared ownership, evolution, semantic validation and generated surfaces are the benefit.

Retain Python for domain services unless a measured workload warrants another language. Retain TypeScript for browser clients and existing Go/Rust consumers. Do not rewrite all application logic in Go to obtain a convenient RPC server. Treat a thin Go/TypeScript Connect edge, qualified Python Connect implementation, and Python gRPC plus browser projection as different deployment options with different operational costs.

Choose the TypeSpec/HTTP alternative if it satisfies the same evolution, event, tool and authority tests with materially less adapter/deployment burden. Prefer the protobuf path if mixed-language clients and contract tooling produce a measured maintainability advantage and browser/Python integration is qualified. No current evidence establishes a universal winner or a latency saving.

## Observed estate fit

Source manifest inspection found Python projects in Vuoro, Cloud, Sprintctl, broker, Auditctl, acceptance-lab and several domain applications. Vuoro and Cloud declare FastAPI/httpx/Pydantic dependencies; Cloud also declares psycopg. Vuoro has service/client/schema-runtime/adapter-kit/MCP-edge/evidence/workspace packages. There are existing JSON schemas and immutable adapter pins, so the rewrite must reconcile multiple current contract surfaces rather than start from an empty system.

Bindery has a Go module; browser-workbench has Python, JavaScript and Rust manifests; homelab-analytics has a web frontend package. Nix flake packaging and existing GitOps deployment are present. These are source observations only: manifests do not establish every active language, installed version, traffic shape, dependency health or live deployment. EC-01 must inventory actual producers/consumers and observed use. Source observation revisions and manifest digests are recorded in the machine-readable requirements map.

## Separate the choices

| Layer | Decision to make | Recommendation / constraint |
|---|---|---|
| Domain semantics | Work, requests, evidence, authority, context, learning | Explicit owner contracts and state transitions before transport choice |
| Authoring | Protobuf IDL vs TypeSpec/OpenAPI vs alternatives | One canonical source convention, generated projections; no handwritten competing schemas |
| Encoding | Binary vs readable JSON | Choose per supported boundary; test presence, numeric and unknown-field semantics |
| RPC transport | gRPC, Connect, HTTP/JSON | Qualify actual Python/browser/proxy paths; retain the same semantic operations |
| Events | Durable cursor/replay and delivery | Persist within existing owner transactions; add a transactional outbox if required; transport stream alone is not durability |
| Service language | Python, Go, TypeScript, Rust | Preserve existing domain languages by default; require evidence for migration |
| TUI / web | Python TUI candidate and TS web | Shared generated client; UI does not own authoritative work/approval state |
| Persistence | Existing PostgreSQL/SQLite/Git/object stores | Preserve ownership; transport rewrite does not imply replacing stores or historical bytes |
| Infrastructure | Nix, current GitOps, identity, telemetry | Extend existing composition; no mandatory new event broker, service mesh or hosted schema registry without demonstrated need |

[Textual](https://textual.textualize.io/) is a Python TUI candidate to evaluate for the operator inbox. Its use is a provisional sourcing choice, not a new approved dependency. TUI qualification must include keyboard use, terminal behavior, reconnect, packaging and measured responsiveness.

## Candidate comparison

Judgments below are architectural inferences from source fit and official capabilities, not measured scores.

| Candidate | Potential advantage | Estate-specific cost or uncertainty | Disposition |
|---|---|---|---|
| Protobuf + native gRPC | Shared typed RPC contracts and generated multi-language clients; explicit service operations | Browser adaptation, proxy behavior, deadlines, Python async/runtime packaging, JSON/tool projections | Lead qualification candidate for native service boundaries |
| Protobuf + Connect | Same protobuf authoring with browser-oriented HTTP/JSON or binary access | Python maturity and per-implementation protocol support; adding an edge must not duplicate authority logic | Lead browser-edge option; qualify independently of gRPC |
| TypeSpec -> OpenAPI/JSON Schema + HTTP | Fit with Python HTTP and readable tools; generation can reduce repeated schema authoring | Event/replay semantics still need specification; emitter fidelity, client quality, compatibility policy and types must be tested | Strong challenger; can win without weakening estate-wide rewrite |
| Canonical OpenAPI/JSON Schema directly | Fewer authoring tools than TypeSpec; close to current ecosystem | Must still remove duplicated sources and qualify generated clients; events and shared domain package governance need deliberate design | Baseline / simpler challenger if TypeSpec adds little value |
| Cap'n Proto | Typed evolving schema; distinct RPC/representation model worth considering for tightly coupled native systems | Language/browser/tool integration and capability-model mapping need evidence; runtime object capabilities are not estate delegation policy | Scoped candidate only if native RPC workloads justify it |
| FlatBuffers | Direct buffer access can suit large structured native data | That benefit does not establish a better control-plane contract; Python/browser ergonomics and lifecycle operations remain work | Potential bulk-data exception, not current estate control-plane lead |

Connect's official introduction describes stable Go and ECMAScript implementations and labels Python beta. Its web guide limits practical browser streaming to server streaming. These are reasons to test the actual path, not assume all language implementations and transports share identical behavior. [Connect introduction](https://connectrpc.com/docs/introduction/), [browser guide](https://connectrpc.com/docs/web/getting-started/), [Python guide](https://connectrpc.com/docs/python/getting-started/).

TypeSpec documents OpenAPI mappings and multi-protocol emission including JSON Schema and protobuf. Emitter availability does not prove round-trip semantic equivalence. If TypeSpec wins, emitted protobuf/OpenAPI must be generated outputs, never independently edited peer authorities. [OpenAPI mapping](https://typespec.io/docs/getting-started/typespec-for-openapi-dev/), [multi-protocol authoring](https://typespec.io/multi-protocol/).

Cap'n Proto documents schema evolution using member identities/ordinals. FlatBuffers describes buffer access without a separate parsing/unpacking step. Neither property alone resolves our request lifecycle, domain authorization or migration requirements. [Cap'n Proto schema](https://capnproto.org/language.html), [FlatBuffers white paper](https://flatbuffers.dev/white_paper/).

MCP, provider APIs, OIDC, OpenTelemetry and native inference protocols are external integration boundaries, not competing estate-wide IDLs. A schema registry or event broker is an operational component, not a replacement for the domain contract. No new broker is selected by this discovery. Existing data/export formats may remain where justified and referenced through typed contracts.

## Stack options to qualify

**A — Python domains, protobuf/gRPC, generated browser projection.** Keep domain implementations and persistence; generate native clients and readable tool schemas. Browser access uses a qualified generated projection or small Connect edge. Cost to measure: extra process/hop, duplicate mapping risk, auth propagation and independent deployment compatibility.

**B — Python domains, protobuf/Connect where qualified.** Avoid an extra gateway if the Python implementation satisfies required behavior. Python beta status makes supported runtime versions, error/stream behavior, deployment integration and maintenance a hard qualification gate. Do not present a vendor maturity claim as a measured estate result.

**C — Python domains, TypeSpec/OpenAPI/JSON Schema, HTTP plus durable event reads.** Generate readable tools and Python/TS clients from the same source. Express server events with a cursor-bearing watch/SSE/poll contract qualified for the existing network path. Cost to measure: generated-client quality, event tooling, numeric/presence fidelity and schema governance across Go/Rust consumers.

Go or Rust domain rewrites are not prerequisites for A/B/C. Evaluate new implementation languages only for an identified workload, using total maintenance/build/packaging costs as well as performance. Keep external runtimes responsible for execution and model routing.

## Hard correctness concerns

Protobuf serialization is not canonical, including when deterministic serialization is enabled. ER-022 therefore requires domain-specific versioned signed/hashed representations and golden vectors, with original bytes retained. Do not silently change existing acceptance digests when changing transport. [Official serialization guidance](https://protobuf.dev/programming-guides/serialization-not-canonical/).

Field presence and JSON projections can change the meaning of absent versus default values; these require explicit tests. Protobuf best practices cover field identity reservation and evolution, while Buf distinguishes source, binary-wire and JSON compatibility. Configure appropriate source and JSON checks, then add business conformance tests; lint alone is insufficient. [Field presence](https://protobuf.dev/programming-guides/field_presence/), [best practices](https://protobuf.dev/best-practices/dos-donts/), [Buf compatibility categories](https://buf.build/docs/breaking/rules/).

gRPC does not establish an application deadline by default. Every operation needs an explicit deadline/retry/cancellation policy, and timeout after commit remains an uncertain effect to reconcile. [gRPC deadlines](https://grpc.io/docs/guides/deadlines/).

## Executable decision gate: EC-00

Build disposable, credential-free prototypes of A or B and C using the same operator request operations: publish, revise with expected revision, withdraw one dependant, report performed, verify outcome, watch after cursor and acknowledge continuation. Include an exact-artifact decision and a paginated scoped query. The prototypes are future qualification work, not completed by this document.

Mandatory cases: Python and TS clients; inventory-confirmed Go/Rust consumers; old/new schema clients; absent/zero/null and unknown enums/fields; large numeric identifiers; duplicate command; concurrent update; timeout after committed write; disconnect/replay/expired cursor; slow subscriber; revoked/cross-tenant access; changed signed meaning; browser proxy buffering; unsupported native wake; offline package restore; deterministic generation. Use owner stubs with real transaction behavior, not mocks that declare success unconditionally.

Predeclare representative payload sizes, concurrency and network conditions from EC-01. Report p50/p95 latency, CPU/RSS, payload bytes, reconnect recovery, build/generation time, generated/manual code volume, added deployable components, debugging effort and operator steps. No invented target numbers or inferred binary speedups. Safety and semantic correctness are pass/fail gates, not weighted tradeoffs.

After gates pass, compare maintainability, developer ergonomics, interoperability, operational footprint, supply-chain support, cost and measured performance. The ADR must identify selected source convention, package ownership, exact toolchain/runtime versions, transport by boundary, retained exceptions, dependency/license support, removal plan and reasons rejected candidates lost. If evidence is inconclusive, retain the shortlist and narrow the experiment; do not label an unqualified stack selected.

EC-02 implementation and broad migration depend on this ADR. Requirements analysis and owner inventory can proceed in parallel. Later evidence may revise the stack through a versioned decision without abandoning estate-wide contract consistency.
