# ADR EC-00: estate contract stack

Date: 21 October 2026. Status: **Accepted: architecture selected by the operator.** Tracker: EC-00, vuoro#2734. Governing map: [estate contract rewrite](../plans/agentops/2026-10-18-estate-contract-rewrite.md).

The operator, who owns this repository set, selected option (b): TypeSpec to OpenAPI as the estate default. This ADR records that selection and its implementation rules. It does not reopen the selection.

**Selecting (b) does not close EC-00.** The selected architecture is kept separate from the evidence still owed. The [outstanding acceptance conditions](#outstanding-acceptance-conditions) list the ER-002, ER-010, ER-043, ER-047 and ER-048 evidence that EC-00 still needs. Until those conditions are met, vuoro#2734 stays open. EC-02 (vuoro#2735) builds on the selected architecture, but it does not take over EC-00's evidence obligations.

## Decision

> Adopt TypeSpec as the authoritative authoring format for estate-owned service contracts. Generate version-pinned OpenAPI for HTTP interfaces and JSON Schema 2020-12 for operation discovery and validation. Preserve domain ownership and generic runtime discovery; generated SDKs are projections of the contracts. Use HTTP/JSON for shared service commands and queries, with an explicit durable cursor contract for observation. Retain external and existing native protocols through documented boundary dispositions. New protobuf/gRPC boundaries require an evidenced requirement and an explicit exception decision.

Operation-catalog schemas are generated as JSON Schema 2020-12. Existing native protocols are recorded as explicit exceptions (see [named exceptions](#named-exceptions-and-boundary-dispositions)).

## Basis of the decision

**This is an architectural judgment. The EC-00 experiments did not find a winner on performance or maintenance.** The qualification record has correctness and security results for both arms. It has no representative operational comparison. The only latency figures are single-run ingress fixture numbers (n=20 per case), and the record itself says they are not a performance comparison. It has no CPU/RSS, load, generation-time or maintenance-effort comparison. No result in this ADR should be read as a measured speedup, a measured maintenance saving, or a measured advantage for either stack.

The judgment rests on fit with the estate's existing shape:

- The first consumer path is HTTP and JSON Schema all the way through: Agentops `VuoroOwner` → Python `vuoro-client` → Vuoro HTTP v1 → the Sprintctl operation catalog ([EC-01](2026-10-18-estate-first-consumer-contracts.md)).
- Vuoro [Protocol v1](https://github.com/bayleafwalker/vuoro/blob/1eae8ace228af39bd224565bac5be0a1fb7c4f25/docs/architecture/protocol-v1.md) already requires JSON Schema 2020-12 input and result schemas for every catalog operation.
- One authoring source can project HTTP interfaces, catalog schemas and model-facing tool schemas without adding a second contract family.

### Options

The operator's labels are used here. The [discovery document](../plans/agentops/2026-10-18-estate-contract-architecture-discovery.md) used different letters: its stacks A and B are both forms of (a), and its stack C is (b).

| Option | Disposition | Reason recorded |
|---|---|---|
| (a) Protobuf/gRPC with Connect | **Not selected. Kept as the alternative if requirements change.** | Viable. Both qualification arms passed comparable correctness cases (see the comparison below). It was not selected as the estate default. |
| (b) TypeSpec → OpenAPI / JSON Schema 2020-12, HTTP/JSON, durable cursor observation | **Selected (estate default)** | Operator's architectural judgment, as recorded in this ADR. |
| (c) Protobuf internally, OpenAPI at the edges | **Rejected as a blanket rule** | It makes network location decide the contract stack. It also creates two compatibility surfaces and translation obligations between them. |
| Direct OpenAPI/JSON Schema without TypeSpec | Not selected | The discovery shortlist listed it as a simpler baseline. The qualification procedure ran it only as a conditional third arm, and it was not run separately. Under (b), OpenAPI and JSON Schema are generated outputs, never sources authored in parallel. |
| Cap'n Proto; FlatBuffers | Not selected for the control plane | The discovery dispositions stand: at most a scoped native-RPC candidate or a bulk-data exception candidate. Either one needs its own evidenced requirement and an explicit exception decision. |

## Implementation rules

1. **TypeSpec is authoritative in the build.** Generate the boundary types and schemas that can be represented, and verify implemented request and response behaviour against them. Never maintain hand-edited Pydantic models, catalog schemas or MCP schemas in parallel with them. Domain state transitions, authorization and persistence stay with their owners. The compiler is not an authority.
2. **Preserve dynamic discovery alongside the generated SDKs.** This is [Protocol v1](https://github.com/bayleafwalker/vuoro/blob/1eae8ace228af39bd224565bac5be0a1fb7c4f25/docs/architecture/protocol-v1.md) discovery. Generate an input schema and a result schema for each operation. An OpenAPI document whose `/invoke` takes `arguments: object` is not enough. The catalog gets its own JSON Schema output path. It is not taken from the OpenAPI output.
3. **IDs and exact revision counters have explicit wire representations.** Mutation revisions are canonical decimal strings with declared bounds. The EC-00 qualification found generated TypeScript clients rounding revisions. The decimal-string repair passed in Python, TypeScript, Go and Rust. Each field specifies how it behaves when absent, null, zero, empty or unknown.
4. **Recovery is defined independently of delivery.** This covers:
   - expected-revision checks and durable idempotency;
   - reconciliation after a timeout or a lost response;
   - cursor retention, replay and expiry;
   - cancellation, and effects that were already committed.

   Bounded cursor reads are the baseline. SSE is optional and reads the same durable history.
5. **Pin the whole generation chain.** That means the compiler, the emitters, the OpenAPI target version, the client generators and the runtimes. The TypeSpec OpenAPI emitter defaults to 3.0.0, so choose the target version deliberately against the qualified client matrix. Test compatibility in both directions: an old client against a new server, and a new client against an older server. "Additive" alone is not a compatibility policy.
6. **Migration is reversible at the interface boundary.** Use versioned contracts and adapters, with one domain owner and one state path. Previous endpoints and clients stay available through a declared window. They retire only after consumer reconciliation. Original signed artifacts and evidence bytes are preserved.

## Named exceptions and boundary dispositions

Every interface gets one of four dispositions: **migrate**, **adapt**, **retain** or **retire**. EC-01 owns the full census, and an interface left without a disposition is a coverage defect. The dispositions this decision sets are:

| Boundary | Disposition | Condition |
|---|---|---|
| Bindery Go `EngineModule`: protobuf `game.engine.v1`, four unary gRPC methods | **Retain** (named exception) | Retained unless its owner has a concrete reason to migrate. |
| Browser Workbench Python ↔ Rust worker: ordered NDJSON protocol v1 | **Retain** (named exception) | Existing native boundary. Its `seq`/`ordinal` continuity and unknown-effect-on-crash semantics stay owned by Browser Workbench. |
| HostProto TypeScript Playwright MCP adapter (MCP `2026-07-28`) | **Retain** (named exception) | External MCP adapter boundary. |
| Agentops `VuoroOwner` → `vuoro-client` → Vuoro HTTP v1 → Sprintctl operation catalog (EC-01 first consumer path) | **Migrate** | The first TypeSpec-authored domain package. Catalog input and result schemas are generated as JSON Schema 2020-12. This migration follows rules 1, 2, 3 and 6. |
| Vuoro MCP edge tools (`list_ready_work`, `describe_work` and conditional toolsets) | **Adapt** | MCP stays the external protocol. Tool schemas become projections of the same contract (rule 1). |
| Every other EC-01 inventoried interface | Assigned by EC-01 / EC-19 | EC-01 assigns one of the four dispositions. A retained boundary names its owner and rationale. |

Retained native protocols are not a precedent. A new protobuf/gRPC boundary needs an evidenced requirement and an explicit exception decision.

## Mandatory-case comparison

The comparison below draws on the [EC-00 qualification record](https://github.com/bayleafwalker/vuoro/blob/1eae8ace228af39bd224565bac5be0a1fb7c4f25/docs/experiments/ec00-qualification/README.md). Both arms ran against the same SQLite owner oracle on loopback, in disposable experiment code, with fixture identities. "Open" means the record does not establish the case for that arm.

| Mandatory case | (a) protobuf / gRPC / Connect | (b) TypeSpec / OpenAPI / HTTP |
|---|---|---|
| Python and TypeScript clients | Pass: generated Python gRPC and Connect, TypeScript protobuf and Connect | Pass: generated Python and TypeScript (Hey API) |
| Go and Rust consumers | Pass: lifecycle and presence checks | Pass: lifecycle checks; the v2 decimal counters pass in Go and Rust |
| Old/new schema clients | Partial. Frozen clients interoperate on common Publish/Revise, and on legacy reads in both directions. New RPCs against the old server return `UNIMPLEMENTED`. A typed-read change caused a **silent mis-decode** in an old `JsonResult` decoder (negative finding). | Partial. v1 and v2 routes coexist. Frozen v1 Python and TypeScript clients interoperate with the versioned server. A v2 client against a v1-only server gets 404, with no downgrade. |
| Absent, zero, null, unknown | Pass for absent and zero. Protobuf has no scalar `null`; a `NullValue` oneof is used, and an unrecognized `NullValue` enum is rejected. Unknown fields: open. | Pass for absent, null and zero. A limit-zero mismatch was found, then repaired through explicit v2 presence identities. Unknown enums and fields: open. |
| Large numeric identifiers and counters | Pass: `int64`, and `bigint` in TypeScript | **v1 failure:** the TypeScript client rounded 9007199254740995, and a committed result was misreported. **v2 decimal-string pass** in Python, TypeScript, Go and Rust, up to signed `int64` maximum. |
| Duplicate command | Pass: same-key replay; a changed body is refused | Pass: same-key replay; a changed body is refused |
| Concurrent update | Pass: CAS stale refusal, plus 16 concurrent signed publications per arm. Broader concurrency: open. | Same as (a) |
| Timeout after a committed write | Pass for Python and the five browser arms. Cancellation does not imply rollback. Go, Rust and TypeScript native cancellation: open. | Same as (a) |
| Disconnect, replay and expired cursor | Pass: Python bounded unary watch pages. Other languages: open. | Pass: Python bounded cursor reads. Other languages: open. |
| Slow subscriber | Open. Only delayed polling was tested; streaming and backpressure were not qualified. | Open (same scope) |
| Revoked and cross-tenant access | Pass: fixture identities, signed assertion across all transports | Pass (same) |
| Changed signed meaning | Pass: an altered signature is refused with no effects | Pass (same) |
| Browser and proxy buffering | Pass on unary Chromium 155 through a loopback proxy. On the internal Gateway, Connect and HTTP reached the backend as HTTP/1.1, and grpc-web was translated. Streaming through a proxy: open. | Pass on unary Chromium through the loopback proxy. HTTP v2 also passed over the internal Gateway, with a non-browser client. |
| Unsupported native wake | Open: not exercised | Open: not exercised |
| Offline package restore | Pass on prepared Nix runtimes. Cold OS/Nix bootstrap was not qualified. | Same as (a) |
| Deterministic generation | Pass: generator falsifiers reject drift; Connect output is normalized deterministically | Pass: v1 OpenAPI must stay byte-identical; falsifiers reject altered v2 output |

Both arms reached comparable correctness on the cases that were exercised. The cases marked open are still owed; see condition 1 below. They are not claims of parity.

## Toolchain matrix

The versions below come from the qualification record and the candidate locks (`package.json`, `pyproject.toml`, `uv.lock`, `toolchain/flake.lock`). Where the record does not establish a pin for estate use, the row says **to pin**. No version here is inferred.

### Selected chain (b)

| Component | Version | Status |
|---|---|---|
| `@typespec/compiler` | 1.17.0 | Qualified pin |
| `@typespec/http`, `@typespec/openapi`, `@typespec/openapi3` (OpenAPI emitter) | 1.17.0 | Qualified pin |
| `@typespec/versioning`, `@typespec/rest` | 0.87.0 | Qualified pin. Versioning was used by the `/v2` projection. |
| `@typespec/events`, `@typespec/sse`, `@typespec/streams` | 0.87.0 | Locked in the experiment. SSE was not qualified, so these stay **to pin** for SSE use. |
| `@typespec/json-schema` (JSON Schema 2020-12 emitter for the catalog) | — | **To pin.** Not part of the qualification record. |
| OpenAPI target version | Qualified output 3.0.0 (emitter default) | **To pin** deliberately against the qualified client matrix (rule 5) |
| Node / npm | 24.21.0 (binary SHA-256 `f89c69d1…a9e433`) / 11.19.0 | Qualified pin |
| TypeScript client generator: `@hey-api/openapi-ts` | 0.99.0, with TypeScript 5.9.3 | Qualified pin |
| Python / uv | 3.13.16 / 0.13.0 | Qualified pin (candidate `requires-python >=3.11,<3.15`) |
| Python client generator: `openapi-python-client`, with `httpx` | 0.29.1, with 0.28.1 | Qualified pin |
| Python boundary-model (Pydantic) generator | — | **To pin.** Not qualified. Vuoro's lock carries Pydantic 2.13.4. |
| MCP tool-schema projection generator | — | **To pin.** Not qualified. |
| Go / Rust client generator: OpenAPI Generator, on JDK 21.0.12.1 | 7.26.0 | Qualified pin |
| Go / Rust and Cargo | 1.26.8 / 1.98.1 and 1.98.0 | Qualified pin |
| Nixpkgs toolchain input | `f20cd90e28fe0403873f473b29e42662cd86e8c4` | Qualified pin |
| HTTP server runtime (fixture: FastAPI 0.139.2, Uvicorn 0.54.0) | — | **To pin** against the production Vuoro lock |
| Catalog JSON Schema validator runtime | — | **To pin** (the existing Vuoro registry; not in the qualification record) |
| Browser harness: Chromium / Playwright | 155.0.8059.79 / 1.64.0 | Qualification harness pin |

### Alternative (a), retained for reference (not selected)

`protoc` 36.2 (binary SHA-256 `2c089b2c…8ee953`), Python `protobuf` 7.36.2, `grpcio`/`grpcio-tools` 1.84.0 (bundled `libprotoc` 35.1), `connectrpc`/`protoc-gen-connectrpc` 0.12.1, Connect ECMAScript 2.2.0, `@bufbuild/protobuf`/`protoc-gen-es` 2.16.0, `protoc-gen-go` 1.36.12, `protoc-gen-go-grpc` 1.6.2, `tonic-prost-build` 0.14.6 and esbuild 0.28.2. Bindery's own toolchain pins belong to Bindery and are not established here.

## Outstanding acceptance conditions

EC-00 (vuoro#2734) closes only when all of the following hold:

1. **ER-002: mandatory cases.** Qualify the cases still open for the selected chain:
   - unknown enums and fields;
   - slow-subscriber and backpressure behaviour on the durable cursor contract, plus SSE if it is adopted;
   - unsupported native wake;
   - TypeScript, Go and Rust behaviour for cancellation, deadlines and cursor replay.
2. **ER-002: selected versions.** Replace every **to pin** row in the selected-chain matrix with an exact version and provenance. That includes choosing the OpenAPI target version against the client matrix.
3. **ER-002: no independently edited generated schemas.** Show the build-time check that catalog schemas, boundary models and MCP schemas are generated from TypeSpec, and that drift fails. So far this has only been demonstrated by the experiment's generator falsifiers.
4. **ER-010: ingress.** Representative HTTP/JSON commands, queries and cursor reads (plus SSE, if adopted) must traverse every actual supported ingress pattern. The 20 October internal-Gateway run covered LAN clients only. Two gaps remain from that run:
   - clients outside the internal range, and remote revocation after commit, were not exercised;
   - the underscore header-name defence still needs a disposition.

   gRPC and Connect ingress need qualification only where a retained or excepted boundary uses them.
5. **ER-043: operational comparison.** Report results from the predeclared EC-01 workloads, with sample size, warm-up and variance:
   - p50/p95 latency;
   - CPU/RSS;
   - payload bytes;
   - reconnect and load behaviour;
   - generation and build time;
   - maintenance effort and manual adapter code.

   Report no speedup without measurement. The existing ingress latency figures are single-run fixture numbers and do not satisfy this condition.
6. **ER-047: supply.** Record licence, support and provenance for every pinned component. Rehearse an upgrade and a rollback of the generation chain, and confirm that no paid registry or hosted code generator is required. The qualification already used no hosted generator.
7. **ER-048: economics.** Take a before-and-after measurement of:
   - workflow success;
   - repeated prompts;
   - stale requests;
   - cost per accepted cohort;
   - interface maintenance.

   If the evidence is inconclusive, it is recorded as inconclusive.

## Consequences and revision

- EC-02 defines the TypeSpec package and ownership foundation under these rules. Broad migration still depends on the outstanding conditions above.
- Option (a) remains the alternative if requirements change. Adopting it, or any other non-default contract stack at a new boundary, needs an evidenced requirement and a versioned exception decision. It does not reopen the estate-wide rewrite.
- The [architectural discovery](../plans/agentops/2026-10-18-estate-contract-architecture-discovery.md) had a provisional protobuf lead. That lead is superseded by this selection.
