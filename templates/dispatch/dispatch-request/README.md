# Canonical dispatch request

`dispatch-request.v2.schema.json` is the one transport-neutral request contract
for a new dispatch. It is distinct from the repository dispatch manifest and
from ActionQ's lifecycle resources.

## v2 rules

- `action_type` is required and currently closed to `scope-iterate`; it chooses
  the coordinator handler, not the requested result.
- `output_expectation` is required and is the closed durable requested outcome:
  `plan`, `audit-event`, `draft-work-items`, `sprint-proposal`,
  `implementation`, or `review`.
- Every schema property is required. Nullable values are explicit `null`:
  `sprint_id`, `work_item_id`, `model`, and `dispatch_group_id`. There are no
  v2 defaults. Producers must send `[]` for no refs and `""` for an empty
  prompt.
- Unknown fields fail validation. Consumers must not silently drop them.
- `kind` is absent from v2. A v1 adapter may accept it only as the deterministic
  compatibility alias listed below, then emits a v2 object without `kind`.
- An ActionQ enqueue must retain the entire normalized v2 object immutably,
  return an opaque `request_ref`, and bind it to `request_sha256` computed over
  the canonical serialized snapshot. A transport that cannot provide this
  persistence is not a v2 enqueue path.

### v1 compatibility alias

Only an explicitly declared `contract_version: "v1"` request may contain
`kind`. It maps as follows and rejects a conflicting supplied expectation:

| v1 `kind` | v2 `output_expectation` |
| --- | --- |
| `implement` | `implementation` |
| `review`, `test` | `review` |
| `investigate`, `document` | `plan` |

`custom` has no deterministic v2 meaning and is rejected. A missing contract
version is treated as v1 only during the documented migration window; new
producers must send v2.

## Projections

| Surface | Declared subset | Excluded / constraint |
| --- | --- | --- |
| Cockpit HTTP | v2 producer fields except `requested_by`; cockpit injects its authenticated operator identity | No queue lifecycle, attempts, sessions, claims, artifacts, or evidence. |
| MCP `dispatch_action` | Same producer subset as cockpit HTTP, with `additionalProperties: false` | No `kind`, no caller-provided `requested_by`, and no ActionQ persistence internals. |
| `actionctl` | Operator lifecycle/action views only | Not a v2 cockpit enqueue fallback until it returns the complete immutable snapshot `request_ref` and `request_sha256`. |

No projection may silently discard an accepted request field.

The fixture matrix in `fixtures/` is the canonical acceptance/rejection corpus
for schema, cockpit normalization, MCP input, and owner transport adapters.
