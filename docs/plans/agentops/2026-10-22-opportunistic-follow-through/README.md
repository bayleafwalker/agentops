# Agent interface and outcome follow-through

22 October 2026. Status: **source assessment and reusable qualification artifacts**.
These files turn the opportunistic scan into work that current owners can use.
They do not declare new operating policy, close work items, change a public API,
or claim an installed outcome.

The [current target state](../../2026-09-17-target-state.md), the
[estate evolution plan](../2026-10-17-estate-evolution-plan.md) and the
[selected contract stack](../../../architecture/2026-10-21-ec00-contract-stack-adr.md)
remain authoritative. In particular, measure actual producers before declaring
a new contract, keep service schemas generated from TypeSpec, and retain one
domain owner and one state path.

## Delivered artifacts

| Artifact | Ready use | Owner and limit |
| --- | --- | --- |
| [Agent output review](agent-output.md) | Review one existing CLI against explicit completeness, error and cost semantics; record actual consumer failures before extending its interface. | CLI owner implements any change. This is a review profile, not a second wire schema or an estate-wide default switch. |
| [Outcome measurement](outcome-measurement.md) and [blank observation companion](outcome-observations.template.json) | Predeclare a task population and independent requirements; attach semantic-check, use and escaped-defect observations to existing experiment evidence. | Vuoro evidence retains experiment/run composition; the relevant owner retains acceptance. The companion is authoring material, not an accepted ExperimentRecord. |
| [Knowledge reuse cases](knowledge-reuse.md) | Qualify changed inputs, unavailable sources and permission changes at their actual owner boundaries. | Git documentation remains with `vuoro-knowledge`; workspace membership and publication remain with `vuoro-workspace`. Derived-cache cases are conditional requirements, not a claim that such a cache exists. |
| [MCP compatibility follow-through](mcp-compatibility.md) | Reuse current conformance and actual-client evidence; exercise retry semantics without inventing a transport migration. | Vuoro owns protocol behaviour; record owners own durable idempotency; Cloud owns its endpoint and hosted-client evidence. |

## Source findings that change the scan's recommendation

The inspected Agentops source is
[`645edcfbf1f40623f2f1f747069a685b44ffe43c`](https://github.com/bayleafwalker/agentops/commit/645edcfbf1f40623f2f1f747069a685b44ffe43c).
The inspected Vuoro source is
[`1eae8ace228af39bd224565bac5be0a1fb7c4f25`](https://github.com/bayleafwalker/vuoro/commit/1eae8ace228af39bd224565bac5be0a1fb7c4f25).
These are source snapshots; deployment, current client access and runtime
qualification were not observed while assembling this packet.

- MCP `2026-07-28` discovery/no-handshake calls and legacy initialization
  compatibility are already described and implemented in Vuoro's MCP edge.
  Its durable write-key contract already exists. The useful work is regression
  and actual-client qualification, not a new migration plan.
- `vuoro-evidence` already supplies `ExperimentRecord`, including a bound
  population, missing cases, capture, composition and burden. Agentops already
  supplies the read-only `cost_per_release.py` join. Use those; do not introduce
  another measurement store or acceptance writer.
- `vuoro-knowledge get` already reports truncation and a source digest; search
  already reports total matches. Review what each value identifies before
  adding another output envelope. Its current error paths include human text,
  so structured error handling is a concrete owner-local candidate if an
  observed consumer needs it.
- Retired Kctl, Outctl and the cockpit are not implementation destinations.
  No model router, training programme or external qualification product is
  implied by these artifacts.

## Smallest useful next application

Use one real workflow already being exercised by the estate contract rewrite.
Bind its source, released composition, client version, requirements and task
population before gathering results. Apply the output review to its actual
commands, preserve current wire compatibility, and report internal acceptance
beside independently checked requirements and observed use. Missing information
stays unknown. If the review finds no consumer failure, retain the existing
interface and record that finding.

The packet adds no work queue. Reconcile it with existing owner work before
creating implementation items. A document landed in Git is a source delivery;
runtime adoption and a measured useful outcome need their own evidence.
