# External-review packet v2 — sanitised public summary

**Full record:** appservice (private) `docs/2026-09-20-external-review-packet-v2.md`, issued
2026-09-20. This summary names axis outcomes only; it omits hostnames, bucket names, endpoint
URLs, credential identifiers and the specific confidentiality-gap detail the full packet's
source correction doc classes as sensitive. See agentops#2417.

## Why reissued

The prior review packet predated the four-axis status model (decision / implementation /
verification / exposure) and immutable evidence tuples (repo + commit + path + environment +
timestamp + result hash). All six prerequisite items for the reissue are `done`. A new,
independently reproducible verification became available this morning and is the trigger for
this reissue: a scheduled backup-integrity drill recorded a verified `PASS` against every
covered database.

## Outcome summary by axis

| Area | Decision | Implementation | Verification | Exposure |
|---|---|---|---|---|
| Primary database backup path | accepted | deployed | **restore-tested** (new evidence this reissue) | bounded production |
| Old backup path pending retirement | accepted for removal | deployed, removal not yet executed | untested | bounded production |
| File-tier snapshots (in-cluster) | accepted | deployed | restore-tested | bounded production |
| Encrypted-artifact snapshots | accepted | deployed | observed | bounded production |
| Offsite second copy (personal/irreplaceable files) | accepted, ratified | deployed | restore-tested | bounded production |
| Offsite second copy — database dumps | explicitly out of scope by design | absent | n/a | n/a |
| Offsite restore-drill cadence | proposed | not yet a recurring mechanism | untested | none |
| Canonical content + VM rebuild records | accepted | deployed | restore-tested (content); 2 of 4 rebuild-time estimates unmeasured | bounded production |
| Promotion/authority control | signature/approval gates on merges deliberately set aside outside one repository; automated pre-merge checks are the control | deployed as those checks | observed (no negative-test artifact found showing a check blocking a change) | bounded production |
| Runner risk acceptance | accepted (narrow, existing) | deployed | observed | bounded production |
| Orphan-resource retirement control | accepted | deployed | restore-tested (one drill) | bounded production |
| Stale internal dispatch path | accepted | **retired** | restore-tested | none |
| Evaluation-tool credential scoping | reconsidered; different compensating control chosen | n/a (evaluation tool not deployed) | untested | none |
| Audit-adoption measurement | not re-measured this cycle | unknown | untested | unknown |
| Evaluation-tool deployment (telemetry pilot) | no-go for production; disposable pilot only, gated | absent | untested | none |
| Legacy checkout retirement | out of scope this cycle | unknown | untested | unknown |

## What is still open

- Two dated follow-up checks on the primary backup path remain open (early and early-to-mid
  October); until they complete, an older, less-protected copy of the same data still exists.
- No recurring offsite restore-drill cadence exists yet — one clean-room restore has been done,
  not a repeating schedule. The next one is not yet on a fixed date.
- The audit-adoption claim ("who is actually writing to the shared ledger, and where") was not
  re-measured this cycle and stays unanswered.
- A negative test proving the promotion control actually blocks self-approval was not located.

This summary intentionally states axes and outcomes only. Anyone with access to the private
appservice repository can read the full packet and every evidence tuple behind these rows.
