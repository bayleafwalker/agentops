# Cross-attempt comparison contract

`operator-attempt-comparison/v1` is an agentops-owned, derived reading of two
`operator-reconstruction-capture/v1` inputs. It reuses P1 validation and its four
Sprintctl owner read operations. The scope is artifact comparison and explicit
unknowns. Sprintctl alone writes Decisions and settles work; this surface has no
chooser, settlement evaluator, protected action, network call or write path.

Run `python -m operator_projection.comparison_cli --left capture-a.json --right
capture-b.json`, adding `--text` for a human-readable report. Input files remain
unchanged. Supplied captures cannot establish authenticated provenance, current
ownership or authorization, regardless of their labels or timestamps.

Known repository scope, artifact repository, item and current owner Release
must match exactly; a mismatch refuses the whole comparison. Missing bindings
remain explicit and yield a partial comparison. Each side preserves P1's exact
artifact, verification and receipt bindings, missing links and conflicts, source
result digests and explicit owner revisions. A content/Release/acceptance conflict
is shown as a stale or conflicting binding within that capture, never a terminal
work outcome. Different shared owner source snapshots are reported without
ranking them by time. Intent equality is separate from recorded run identity: two intents can belong
to one run. The recorded run relation is same, different or unknown; missing
owner run observations remain unknown and cannot establish an attempt relation. Neither completeness nor a receipt selects a candidate or implies settlement.

This resolves agentops#2621's projection ownership question: existing P1 source
reads suffice, so agentops extends its operator projection. No additional Vuoro
read composition or domain authority is introduced. It follows TS-1, TS-5 and
TS-17; offline captures remain observations, and live currentness needs a fresh
authorized owner read before any separately supported settlement operation.
