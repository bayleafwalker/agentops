---
status: active
owner: operator-designated coordinator (default-assigned 2026-11-07)
last_verified: 2026-11-07
---

# Silent-drop check: decided work not visible in Oct-Nov plans

The 2026-11-07 landscape alignment review found decisions that no October or
November plan carries. It could not tell whether they were dropped or simply
tracked somewhere it did not read. This page checks each one against served
sprintctl.

Method: a read-only `sprintctl item list --project . --json` from the agentops
repo (served backend), run 2026-11-07 and returning 909 items. The titles and
descriptions were searched with the patterns listed. Re-run this check before
calling an item dropped, or before adding a new item for something already
tracked.

| Candidate | Source decision | Tracker state 2026-11-07 | Verdict | Verification method | Owner |
|---|---|---|---|---|---|
| Local harnesses move to vuoro.cloud as primary endpoint after E2 | #255 Q1 (2026-09-27) | agentops#2536 **pending**, last updated 2026-09-27 | tracked, not scheduled: no Oct-Nov plan or programme sequences it | `sprintctl item show --id 2536 --json`; it is scheduled once a programme or the [plan register](REGISTER.md) names it | operator-designated coordinator (default-assigned 2026-11-07) |
| `credctl accept`, then auto-accept for boring classes with `forge_comment_pr` as canary | #255 Q4 | agentops#2535 **active** (updated 2026-10-18). Its description carries the auto-accept step and the canary, gated on the audit prerequisite | tracked inside #2535; the auto-accept step has no separate item | check that #2535's acceptance names the canary; split it into its own item when #2535 closes | cred-broker (default-assigned 2026-11-07) |
| "Last successful authoritative event age" as a hard health metric | #255 Q6 | agentops#2533 **done**, resolution accepted (2026-09-28) | delivered per tracker; whether the metric is still emitted and alerted on was not observed | confirm the metric is live in the estate status or alerting config. A missing producer is a repair item, not a new decision | operator-designated coordinator (default-assigned 2026-11-07) |
| Docs and knowledge library owner (successor for the knowledge-base prose store) | estate plan EE-07; kctl retired | no open item matches "knowledge library", "docs library" or "knowledge base" | **not tracked**: open verification item | decide whether the rendered prose layer (`knowledge-base` concepts and domains) moves to Vuoro workspace and `vuoro-knowledge` or stays a separate corpus; record that as an item under EE-07. The knowledge-base repo is recorded as held/dormant, not retired | operator-designated coordinator (default-assigned 2026-11-07) |
| blocker12-canary retirement path | vuoro-cloud admin slices | agentops#2584 **pending** names reclassifying blocker12's owner (`vuoro-cli admin principal reclassify`) as a precondition; no item names retiring the canary itself | partly tracked: the precondition is tracked, the retirement path is not | read vuoro-cloud `IMPLEMENTATION-STATUS.md` blocker 12 on canonical main; add a retirement item only if the canary is meant to end, otherwise record it as held | vuoro-cloud (default-assigned 2026-11-07) |

None of these is a new decision. Each row either points at an existing tracked
item or names the one verification that would settle it. Nothing here retires
a tool.
