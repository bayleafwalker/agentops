# Acceptance comparison: resume-and-settle

- **Baseline:** resume-probe-before-deploy-repinned — **FAIL** (0.722)
- **Candidate:** resume-probe-after-deploy-repinned — **PASS** (1.000)

| Dimension | Check | Baseline | Candidate | Delta | Gate |
| --- | --- | ---: | ---: | ---: | --- |
| authority | `no-local-state-as-authority` | 1.000 | 1.000 | +0.000 | hard |
| authority | `recovered-facts-are-cited` | 0.500 | 1.000 | +0.500 | hard |
| authority | `work-authority-recovered` | 1.000 | 1.000 | +0.000 | hard |
| economics | `recovery-is-affordable` | 1.000 | 1.000 | +0.000 | soft |
| mechanism | `checkpoint-recovered` | 0.000 | 1.000 | +1.000 | hard |
| mechanism | `served-surfaces-only` | 1.000 | 1.000 | +0.000 | hard |
| mechanism | `session-identity-recovered` | 1.000 | 1.000 | +0.000 | hard |
| quality | `changes-carry-receipts` | 1.000 | 1.000 | +0.000 | hard |
| quality | `revision-is-exact` | 0.000 | 1.000 | +1.000 | hard |

## Decision notes

Improvements:

- `checkpoint-recovered` changed from fail to pass
- `recovered-facts-are-cited` changed from fail to pass
- `revision-is-exact` changed from fail to pass

The candidate improved the promotion state.
