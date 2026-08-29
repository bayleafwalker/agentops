# Acceptance run: resume-probe-after-deploy-repinned

- **Run:** `e7876b67-5cbd-42a1-9941-e5e11ec28fd8`
- **Scenario:** `resume-and-settle@1.0.1`
- **Evaluation harness:** revision 1
- **Status:** **PASS**
- **Aggregate score:** 1.000
- **Event chain:** valid — verified 55 event(s)
- **Scenario hash:** `50c435d66f490562608092b9f6d599600b44412c675d8f991f002d0a9b6386ff`
- **Output hash:** `d1d5cbe5ae9cf122e04a88a046ee01d653b0f99b533611335e753f9893d0c2f4`

## Checks

| Dimension | Check | Scorer | Score | Result | Gate | Summary |
| --- | --- | --- | ---: | --- | --- | --- |
| authority | `no-local-state-as-authority` | `forbidden_authority_absence@1` | 1.000 | PASS | hard | No forbidden source treated as authority |
| authority | `recovered-facts-are-cited` | `required_fact_citations@1` | 1.000 | PASS | hard | 4/4 required facts tied to citations |
| authority | `work-authority-recovered` | `required_fact_coverage@1` | 1.000 | PASS | hard | 1/1 required facts present |
| economics | `recovery-is-affordable` | `max_latency@1` | 1.000 | PASS | soft | latency_ms=1350.6, maximum=20000 |
| mechanism | `checkpoint-recovered` | `required_fact_coverage@1` | 1.000 | PASS | hard | 1/1 required facts present |
| mechanism | `served-surfaces-only` | `allowed_tools_only@1` | 1.000 | PASS | hard | All tools were inside the allowlist |
| mechanism | `session-identity-recovered` | `required_fact_coverage@1` | 1.000 | PASS | hard | 1/1 required facts present |
| quality | `changes-carry-receipts` | `effect_receipts@1` | 1.000 | PASS | hard | Every effect carries an execution receipt |
| quality | `revision-is-exact` | `required_fact_coverage@1` | 1.000 | PASS | hard | 2/2 required facts present |

## Promotion decision

All declared acceptance checks passed.
