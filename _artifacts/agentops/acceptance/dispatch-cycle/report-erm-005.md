# Acceptance run: bindery-core-ERM-005-redaction-idempotency-v11

- **Run:** `10a5bf6a-9a7b-4f79-829f-f6fcf593a2be`
- **Scenario:** `dispatch-cycle@1.1.0`
- **Evaluation harness:** revision 1
- **Status:** **CONDITIONAL**
- **Aggregate score:** 0.889
- **Event chain:** valid — verified 44 event(s)
- **Scenario hash:** `707ba2bef8bfabe9c22f2496f8076caeeb350fc338d0a26f05015d5b25ba8ced`
- **Output hash:** `bb8082f11bdbfaa74b6ed1f30006302ffc2a690207a9a36ea2ae76c6c495262e`

## Checks

| Dimension | Check | Scorer | Score | Result | Gate | Summary |
| --- | --- | --- | ---: | --- | --- | --- |
| authority | `containment-held` | `required_fact_coverage@1` | 1.000 | PASS | hard | 2/2 required facts present |
| authority | `every-arm-is-attributable` | `required_fact_citations@1` | 1.000 | PASS | hard | 3/3 required facts tied to citations |
| authority | `no-local-only-authority` | `forbidden_authority_absence@1` | 1.000 | PASS | hard | No forbidden source treated as authority |
| economics | `spend-was-reported` | `max_cost@1` | 0.000 | FAIL | soft | Metric cost_usd was not reported |
| mechanism | `cycle-is-complete` | `required_fact_coverage@1` | 1.000 | PASS | hard | 3/3 required facts present |
| mechanism | `cycle-runs-in-order` | `required_tool_order@1` | 1.000 | PASS | hard | Matched 3/3 required ordered tools |
| mechanism | `substrate-operations-only` | `allowed_tools_only@1` | 1.000 | PASS | hard | All tools were inside the allowlist |
| quality | `refusal-cost-no-inference` | `required_fact_coverage@1` | 1.000 | PASS | hard | 2/2 required facts present |
| quality | `the-merge-carries-a-receipt` | `effect_receipts@1` | 1.000 | PASS | hard | Every effect carries an execution receipt |

## Promotion decision

No hard gate failed, but one or more soft acceptance checks require review.
