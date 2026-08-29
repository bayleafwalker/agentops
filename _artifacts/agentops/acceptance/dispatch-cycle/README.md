# `dispatch-cycle` — recorded runs

`events.db` is the authority; the Markdown files are projections and rebuild from it.

| Run | Cycle | Scenario | Status | Score |
|---|---|---|---|---|
| `019ef52d` | `ERM-005-redaction-idempotency` | 1.0.0 | CONDITIONAL | 0.889 |
| `31e100ee` | `ERM-WIDE-fixture-wave` | 1.0.0 | FAIL | 0.889 |
| `10a5bf6a` | `ERM-005-redaction-idempotency` | 1.1.0 | CONDITIONAL | 0.889 |
| `aad7ff07` | `ERM-WIDE-fixture-wave` | 1.1.0 | **PASS** | 1.000 |

The two 1.0.0 runs are kept rather than rescored. `31e100ee` failed `cycle-runs-in-order`
because that cycle's refusal was spelled `dispatch.preflight_rejected` while the check
enumerated `dispatch.packet.rejected` — the same arm of the same cycle under a second
name. 1.1.0 names the three arms instead of the event types, which is also what makes
the scenario portable to a substrate whose events are spelled differently.

`ERM-005` stays CONDITIONAL at 1.1.0 for a real reason, not a gate defect: its receipt
carries `reported_cost_usd: 0.0` with no `cost_reported` flag, which arrived later. A
zero with nothing asserting that anything was reported is ambiguous between "it cost
nothing" and "the field defaulted", and the probe will not resolve that in its own
favour.

The assessment this evidence supports —
`docs/assessments/dispatch-cycle-substrate-vs-consumer-2026-08-29.md` — is that the
receipt, packet, gate-set, reservation and containment halves are substrate mechanisms,
while the cycle's own arm vocabulary is coordinator prose with no schema and no
producer. Across fifteen repositories with audit streams, two complete cycles exist and
both are bindery's.
