# Test Context Packet v1

Status: adopted for semantic-verification work

A test context packet is a small, versioned, data-only description of a
protocol test. It gives plans, executable tests, bounded models, and recorded
concurrent histories the same stable identity without duplicating production
transition code or exposing credentials.

Packets belong with the repository that owns the state they describe. Agentops
owns the contract and schema only. A packet is not a generic test compiler: an
owning repository may add a narrowly scoped reader when it has a real model or
test consumer.

## Canonical schema

`templates/dispatch/schemas/test-context.schema.json` is the sole normative
machine-readable schema. Every packet uses `schema_version = test-context/v1`.
The dependency-free repository gate validates its stable minimum without
requiring a JSON Schema package:

```bash
python /projects/dev/agentops/templates/dispatch/scripts/validate_verification_artifacts.py --root .
```

The v0 draft has been retired. New repositories and migrations must not create
`test-context/v0` packets.

## Shape

| Field | Rule |
|---|---|
| `schema_version` | Exactly `test-context/v1`. |
| `id` | Stable repository-qualified identifier, retained in every expansion. |
| `owner_repo` | Repository that owns the modeled state and executable test. |
| `subject` | The bounded state object, not a UI or broad product name. |
| `contract_ref` | Stable document id plus content or Git revision. |
| `source_of_truth` | Store or artifact whose state is authoritative. |
| `depth` | Verification depth from 0 through 3. |
| `backends` | One or more storage backends exercised by the packet. |
| `actors` | Named logical actors; never credentials or claim tokens. |
| `initial_state` | Assertions describing the start state. |
| `operations` | Data-only operation grammar and synchronization points. |
| `consistency` | Claimed target and object; linearizability requires a history-aware oracle. |
| `invariants` | Named safety properties with finite counterexamples. |
| `faults` | Named fault boundaries, if any. |
| `oracles` | The checks that decide pass/fail. |
| `implementation_anchors` | Source-level anchors to the owner implementation. |
| `expansions` | Intended derived artifacts. |

## Required discipline

- Packets, generated histories, fixtures, and model traces must never contain
  claim tokens, database URLs, API keys, or other secrets.
- A final-state query alone is not a linearizability oracle. Concurrent
  packets record `invoke`, `ok`, `fail`, or `info` events with process,
  operation, timestamps, and a non-secret attempt or epoch identifier.
- A semantic document maps every transition and invariant to an implementation
  anchor and at least one executable test. A model that does not map to the
  shipped protocol is not evidence for the protocol.
- `faults` state the durable observations and safe recovery action. A caller
  that loses a response has an unknown outcome until an oracle resolves it.

## Expansion ownership

| Expansion | Owner responsibility |
|---|---|
| Semantic document | States, transitions, preconditions, postconditions, and mapping table. |
| PlusCal/TLC | Bounded actors, items, time, and selected invariants. |
| Stateful test | Reference state, operation grammar, and database assertions. |
| Concurrent history | Deterministic synchronization and a history-aware oracle. |
| Fault scenario | Named injection point, durable observations, recovery, and retry rule. |

Initial packets live in the repositories that own the modeled state. Agentops
does not carry placeholder packets pretending to exercise consumer behavior.
