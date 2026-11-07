# Outcome closeout records

One `outcome-closeout-record/v1` JSON per delegated outcome under the
[active dogfood practice](../model-routing.md#active-dogfood-practice-2026-11-04)
([schema](../../../schemas/outcome-closeout-record.v1.schema.json)). Copy
[TEMPLATE.json](TEMPLATE.json) to `<closed_on>-<outcome_id>.json` in the same
change as the closeout.

It joins the fields the practice says to assess (observed route, coordinator
effort, elapsed time, review findings, repairs, cost) into one record per
attempt. Every measurement has a `basis` of `measured`, `estimate` or
`unknown`; leave a value `null` rather than guess. Set
`review.same_tier_as_worker` honestly: a review on the worker's own tier does
not support a comparative-quality claim.

This is a record, not infrastructure: no producer, hook or service reads it.
`scripts/tests/test_outcome_closeout_records.py` validates every file here
against the schema.

| Record | Outcome |
|---|---|
| [2026-11-04-outcome-routing-pr485.json](2026-11-04-outcome-routing-pr485.json) | routing practice guidance (backfilled; effort and elapsed unknown) |
