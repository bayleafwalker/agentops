# Acceptance run: bindery-core-ERM-WIDE-fixture-wave-v11

- **Run:** `aad7ff07-f6d1-4ab0-835d-46fe5805027e`
- **Scenario:** `dispatch-cycle@1.1.0`
- **Evaluation harness:** revision 1
- **Status:** **PASS**
- **Aggregate score:** 1.000
- **Event chain:** valid — verified 44 event(s)
- **Scenario hash:** `707ba2bef8bfabe9c22f2496f8076caeeb350fc338d0a26f05015d5b25ba8ced`
- **Output hash:** `27f9895bfba8c3c81929821d38fe11a488217f89d58e0d42d3598f028996b534`

## Checks

| Dimension | Check | Scorer | Score | Result | Gate | Summary |
| --- | --- | --- | ---: | --- | --- | --- |
| authority | `containment-held` | `required_fact_coverage@1` | 1.000 | PASS | hard | 2/2 required facts present |
| authority | `every-arm-is-attributable` | `required_fact_citations@1` | 1.000 | PASS | hard | 3/3 required facts tied to citations |
| authority | `no-local-only-authority` | `forbidden_authority_absence@1` | 1.000 | PASS | hard | No forbidden source treated as authority |
| economics | `spend-was-reported` | `max_cost@1` | 1.000 | PASS | soft | cost_usd=0, maximum=25 |
| mechanism | `cycle-is-complete` | `required_fact_coverage@1` | 1.000 | PASS | hard | 3/3 required facts present |
| mechanism | `cycle-runs-in-order` | `required_tool_order@1` | 1.000 | PASS | hard | Matched 3/3 required ordered tools |
| mechanism | `substrate-operations-only` | `allowed_tools_only@1` | 1.000 | PASS | hard | All tools were inside the allowlist |
| quality | `refusal-cost-no-inference` | `required_fact_coverage@1` | 1.000 | PASS | hard | 2/2 required facts present |
| quality | `the-merge-carries-a-receipt` | `effect_receipts@1` | 1.000 | PASS | hard | Every effect carries an execution receipt |

## Promotion decision

All declared acceptance checks passed.
