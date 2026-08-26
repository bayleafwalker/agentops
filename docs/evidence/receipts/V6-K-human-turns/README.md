# V6-K receipts — both attest to a superseded packet

Neither file is named `receipt.json`, so `test_packet_receipt_linkage.py` does
not pair them with the committed packet. That is deliberate and it is not an
exemption: the packet these receipts were produced against no longer exists.

## What happened

The packet was frozen with `debt` as a **string**. `task-packet.schema.json`
requires an array, so the packet was schema-invalid from the moment it was
written and should never have been dispatched. `hybrid_dispatch.py validate`
reported `packet-schema-valid` among its pre-gates and `status: fit` anyway.

That has since been fixed, and the defect was wider than this packet. Measured:
six of the eight configured pre-gate names appeared nowhere in the dispatch
scripts at all. `validate_packet` ended with `return list(policy["gates"]["pre"])`
— the policy's own list, echoed back regardless of what had been checked — and
`main` printed it in the `unfit` payload as readily as the `fit` one. The schema
checker existed the whole time, inside `tests/test_task_packet_schema.py`, where
the dispatch path could not reach it. It now lives in
`scripts/packet_schema.py`, is registered as this gate's evaluator, and every
configured gate reports what was actually observed about it — including
`not_evaluated`, for the four that are not knowable until a workspace exists.

Correcting `debt` to an array moved the packet hash, and the receipts de-linked.
That is exactly the dogfooding cost recorded as §9.1 of
`docs/plans/agentops/2026-08-26-v6k-remainder-plan.md`: `claim_id`, `attempt` and
now a schema repair are all inputs to the hash that is supposed to prove the
packet did not change.

## Why they are kept

Neither run produced accepted work, so nothing is being laundered by keeping
them, and both carry findings that are about the harness rather than the packet:

- `receipt.attempt-1-void.json` — the contained worker could not read its packet
  at all (`File not found`), because `--file` pointed into the coordinator
  checkout. $0, 0 tokens, the model never ran. Fixed by the staging hand-pass.
- `receipt.superseded-packet.json` — the staging fix held (the worker's most-read
  path is the staged packet, and `staged_packet_sha256` matched), and the worker
  was then stopped by `context_churn` at 9 mutation-free steps against a limit of
  8. $0.006569, 87,897 tokens.

  An earlier version of this file added "having spent two of them on bash calls
  the overlay correctly denied". That was wrong, and wrong in the direction this
  repository keeps failing in: a rationale recalled correctly, a reach never
  checked against the code. `churn_verdict` skips any event whose status is not
  `completed` — the comment there records V5-M9 as the run that decided it —
  `MUTATION_TOOLS` does not contain `bash`, and both denied calls carry
  `"status":"error"` in `worker-stdout.txt`. They spent no steps. All nine were
  completed non-mutation calls.

Re-emitting either against the corrected packet would assert that the worker read
a packet it never saw, so neither was rewritten.

## What the next dispatch must do

Re-dispatch against the corrected packet and file the result as `receipt.json`.

There is no churn question to resolve first. Denied calls already do not spend
the budget, and have not since V5-M9. What was actually wrong is narrower: this
packet declared `max_reasoning_steps_without_mutation: 8`, while
`context_churn_limits` defaults to 12 and its comment says in terms that "eight
steps is not enough room to orient in one before writing". The packet now
declares 12.

No global floor was introduced. A default plus a comment about one
orientation-heavy workflow does not establish a universal minimum, and the
corpus settles it: of 40 committed packets, 30 declare 20 and **10 declare 8** —
the whole V5-M/P/T series. A floor of 12 would retroactively invalidate a
quarter of them. If one is wanted it is a ratification with a migration story,
or a per-class minimum, not an inference from a comment.
