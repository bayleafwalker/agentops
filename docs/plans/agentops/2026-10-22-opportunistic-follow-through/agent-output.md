# Agent-facing output: review profile

Status: proposed owner-local adoption criteria, 22 October 2026. This profile
defines the questions a consumer must be able to answer. It does not define a
new service ABI. Field names belong to existing owner contracts; future
service-boundary additions follow the estate's TypeSpec authoring decision.

## Baseline before changes

For each candidate command record its owner, exact source/release, explicit
format options, exit codes, stdout/stderr behaviour, truncation behaviour and
one actual consumer failure or unnecessary retry. Include the consumer and
its version. A formatting preference alone does not establish an operational
gain or justify changing existing machine output.

The inspected
[`vuoro-knowledge` retrieval code](https://github.com/bayleafwalker/vuoro/blob/1eae8ace228af39bd224565bac5be0a1fb7c4f25/packages/vuoro-knowledge/src/vuoro_knowledge/retrieval.py)
already returns total search matches and bounded result lists; `get` returns
line ranges, `truncated`, notices and a source SHA-256. The
[CLI](https://github.com/bayleafwalker/vuoro/blob/1eae8ace228af39bd224565bac5be0a1fb7c4f25/packages/vuoro-knowledge/src/vuoro_knowledge/cli.py)
emits JSON success bodies but uses text for several errors. These observations
make it a bounded first review target; they do not establish a failing consumer.

## Information that must remain distinguishable

| Situation | Required interpretation | Disqualifying interpretation |
| --- | --- | --- |
| Operation finished; all output shown | Exact completed result, with its scope and ordering. | An omitted count is silently read as zero. |
| Operation finished; display shortened | Execution complete, display incomplete; exact total if known, returned count and a way to retrieve the omitted portion. | A preview is called the whole answer. |
| Operation stopped before completion | Execution incomplete, reason/budget, observed count or explicit lower bound, and continuation/restart semantics. | An early-stopped result gets a full-result digest or an exact final count. |
| Authorized empty result | Successful evaluation over the named authorized scope, zero matching rows. | A refusal or unavailable source is rendered as an empty list. |
| Failure or refusal | Stable machine-readable category, non-success exit, bounded explanation, and explicit retry/effect status where known. | A timeout becomes proof that no effect happened, or an authorization denial triggers an unbounded retry. |

A digest always names what it covers: full source document, selected revision,
complete query result, returned excerpt or opaque receipt. A document digest
is not the digest of its excerpt. A hash of observed rows is not proof that all
rows were observed. Declare canonicalization, ordering, duplicate/null handling,
algorithm and version before comparing digests across runs. Hash equality does
not establish freshness, permission or semantic correctness.

## Presentation, costs and authority

1. Honor explicit format choices. Keep current JSON shapes and exit behaviour
   compatible; introduce a versioned or opt-in presentation when needed.
2. Environment detection may select presentation only. It never changes the
   principal, permitted operations, confirmation rules, budget or target.
3. In machine mode keep stdout parseable. Put structured diagnostics on stderr
   under an explicit documented mode; do not mix a startup banner into JSON.
4. A cost/size estimate says what is estimated, its units and basis, and which
   parts are unknown. Do not label an estimate as actual spend.
5. An estimate printed before execution is informational. A real approval
   checkpoint requires a separate mechanism that prevents the effect until its
   existing owner authorization is satisfied.
6. Retrying a possibly committed operation requires the same business operation
   identity and owner reconciliation. A new transport request ID is not a new
   business operation and must not imply permission to duplicate its effects.

## Discriminating checks for an implementation change

| Check | Evidence to retain |
| --- | --- |
| A 25-row fixture with a 10-row display limit | Total, returned count and explicit incomplete display agree; a fresh full read yields the complete result. |
| An execution budget reached before the fixture is exhausted | Output names incomplete execution; no complete-result digest or exact final count is claimed. |
| Empty result, missing object and denied access | Three distinct outcomes, with no sensitive payload in diagnostics. |
| Human invocation, detected agent and explicit format flag | Same authorization and effects; explicit format wins. |
| A changed source with an otherwise identical excerpt | Source identity changes; the unchanged excerpt is not represented as current evidence. |
| Failure after a write may have committed | Unknown effect state survives the output; recovery uses owner read/reconciliation or the same durable operation key. |

Run these against the actual command boundary when changing it. Freeze the
expected behaviours before implementation. Record unsupported checks explicitly;
do not add tests that merely serialize the implementation's own output.

## Source and inference

[DuckDB's agent-mode description](https://duckdb.org/2026/10/09/agent-mode)
distinguishes shortened display from early-stopped execution, uses structured
errors and reports large-query estimates. Its experiment reports much larger
savings in returned output than in total input, with slightly more turns.
The proposed transfer here is explicit completeness and recoverability; no
cost saving for this estate is inferred from that experiment.
