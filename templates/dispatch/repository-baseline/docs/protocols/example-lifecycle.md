# Example lifecycle contract

Document the repository-owned source of truth, states, transitions, invariants,
retry semantics, crash windows, and recovery actions here.

| Transition | Preconditions | Durable effect | Retry rule | Verification anchor |
|---|---|---|---|---|
| `example-transition` | Replace with a bounded precondition. | Replace with the authoritative effect. | Unknown outcomes require an oracle before retry. | `src/example/store.py:transition` |

Do not claim atomicity, exclusivity, idempotency, or linearizability unless the
implementation and an appropriate oracle establish it.
