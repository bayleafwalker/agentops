# Acceptance run: resume-probe-after-deploy-2026-08-29

- **Run:** `46ba1aac-0588-4461-b413-96cf98a7d1aa`
- **Scenario:** `resume-and-settle@1.0.1`
- **Status:** **PASS**
- **Aggregate score:** 1.000
- **Event chain:** valid — verified 33 event(s)
- **Scenario hash:** `50c435d66f490562608092b9f6d599600b44412c675d8f991f002d0a9b6386ff`
- **Output hash:** `d1d5cbe5ae9cf122e04a88a046ee01d653b0f99b533611335e753f9893d0c2f4`

## Checks

| Dimension | Check | Score | Result | Gate | Summary |
| --- | --- | ---: | --- | --- | --- |
| authority | `no-local-state-as-authority` | 1.000 | PASS | hard | No forbidden source treated as authority |
| authority | `recovered-facts-are-cited` | 1.000 | PASS | hard | 4/4 required facts tied to citations |
| authority | `work-authority-recovered` | 1.000 | PASS | hard | 1/1 required facts present |
| economics | `recovery-is-affordable` | 1.000 | PASS | soft | latency_ms=1350.6, maximum=20000 |
| mechanism | `checkpoint-recovered` | 1.000 | PASS | hard | 1/1 required facts present |
| mechanism | `served-surfaces-only` | 1.000 | PASS | hard | All tools were inside the allowlist |
| mechanism | `session-identity-recovered` | 1.000 | PASS | hard | 1/1 required facts present |
| quality | `changes-carry-receipts` | 1.000 | PASS | hard | Every effect carries an execution receipt |
| quality | `revision-is-exact` | 1.000 | PASS | hard | 2/2 required facts present |

## Promotion decision

All declared acceptance checks passed.
