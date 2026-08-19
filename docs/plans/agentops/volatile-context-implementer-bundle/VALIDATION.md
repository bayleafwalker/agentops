# Validation Record

Validated on 17 August 2026.

- Python source compilation: passed
- Reference unit/integration tests: 20 passed
- HTTP projection → authoritative CAS mutation → post-mutation projection: passed
- Stale mutation with hooks bypassed: rejected
- Idempotent mutation replay: revision unchanged
- JSON artifact parsing: passed
- Example projection 7,500-byte budget check: passed
- Obvious credential-pattern scan: passed
- Demo hook round trip: passed

Run `./scripts/validate-bundle.sh` to reproduce the automated checks.
