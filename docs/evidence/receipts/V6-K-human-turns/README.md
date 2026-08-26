# V6-K receipts — both attest to a superseded packet

Neither file is named `receipt.json`, so `test_packet_receipt_linkage.py` does
not pair them with the committed packet. That is deliberate and it is not an
exemption: the packet these receipts were produced against no longer exists.

## What happened

The packet was frozen with `debt` as a **string**. `task-packet.schema.json`
requires an array, so the packet was schema-invalid from the moment it was
written and should never have been dispatched. `hybrid_dispatch.py validate`
reported `packet-schema-valid` among its pre-gates and `status: fit` anyway --
its structural check is weaker than the committed schema, which is a defect in
the validator, recorded in the plan rather than fixed here.

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
  8, having spent two of them on bash calls the overlay correctly denied.
  $0.006569, 87,897 tokens.

Re-emitting either against the corrected packet would assert that the worker read
a packet it never saw, so neither was rewritten.

## What the next dispatch must do

Re-dispatch against the corrected packet and file the result as `receipt.json`.
Resolve the churn question first -- whether denied-by-policy tool calls should
count toward a mutation-free step budget is a harness question that would change
every packet, so it wants its own measurement rather than a tuning nudge.
