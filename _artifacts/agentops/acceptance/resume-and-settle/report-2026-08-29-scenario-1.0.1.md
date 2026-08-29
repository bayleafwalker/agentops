# Acceptance run: resume-probe-2026-08-29-r2

- **Run:** `15f82e69-6656-4aaa-8552-420cedf8e6a2`
- **Scenario:** `resume-and-settle@1.0.1`
- **Status:** **FAIL**
- **Aggregate score:** 0.722
- **Event chain:** valid — verified 22 event(s)
- **Scenario hash:** `50c435d66f490562608092b9f6d599600b44412c675d8f991f002d0a9b6386ff`
- **Output hash:** `d5673d0cdbea941e58e1ee697e08331af046bb64bf8cbe78a2583701903876f0`

## Checks

| Dimension | Check | Score | Result | Gate | Summary |
| --- | --- | ---: | --- | --- | --- |
| authority | `no-local-state-as-authority` | 1.000 | PASS | hard | No forbidden source treated as authority |
| authority | `recovered-facts-are-cited` | 0.500 | FAIL | hard | 2/4 required facts tied to citations |
| authority | `work-authority-recovered` | 1.000 | PASS | hard | 1/1 required facts present |
| economics | `recovery-is-affordable` | 1.000 | PASS | soft | latency_ms=1438.8, maximum=20000 |
| mechanism | `checkpoint-recovered` | 0.000 | FAIL | hard | 0/1 required facts present |
| mechanism | `served-surfaces-only` | 1.000 | PASS | hard | All tools were inside the allowlist |
| mechanism | `session-identity-recovered` | 1.000 | PASS | hard | 1/1 required facts present |
| quality | `changes-carry-receipts` | 1.000 | PASS | hard | Every effect carries an execution receipt |
| quality | `revision-is-exact` | 0.000 | FAIL | hard | 0/2 required facts present |

## Promotion decision

Promotion is blocked by hard-gate failures:

- `recovered-facts-are-cited` — 2/4 required facts tied to citations
- `checkpoint-recovered` — 0/1 required facts present
- `revision-is-exact` — 0/2 required facts present
