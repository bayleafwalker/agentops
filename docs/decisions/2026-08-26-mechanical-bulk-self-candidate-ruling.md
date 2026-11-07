---
status: accepted
scope: dormant
decided: 2026-08-26
decided_by: owner (agentops#2100, Option C)
recorded: 2026-11-07
---

# Self-candidate ruling for the `mechanical_bulk` action class

Until 2026-11-07 this ruling lived only as prose in
`routing.action_classes.mechanical_bulk.self_candidate_ruling` of
`agentops.dispatch.json`. That file is not an authority (target-state TS-11),
so the ruling is recorded here. Removing the class from the manifest is a
protected-path change and follows in a separate hand-pass PR
(branch `feat/dispatch-manifest-reconciliation`); until then the manifest
prose duplicates this record and this record governs.

## Ruling (verbatim from the manifest)

> Owner ruling 2026-08-26 (agentops#2100, Option C), REISSUED and keyed to this action class rather than inherited from a route of the same name. Route selects execution and is transient; authority to mint a candidate without a human review record is a separate, durable decision and must be stated deliberately. This grant is made for the action class mechanical_bulk, and covers exactly the routes named in permitted_routes -- a route added later inherits nothing. It carries forward, unchanged in substance, the owner ruling of 2026-08-23 (L-3 / D-8): human approval is perpendicular to the loop -- review happens at release, architecture and style boundaries, not per mechanical packet. A green evidence gate on this class disposes candidate without a per-packet independent review record; D-8's >=5-green-first-pass-with-0-escalations rule governs which classes qualify. Reissued rather than edited so that the act of granting is visible in the record: the 2026-08-23 ruling was written about a class and applied through a route, and this closes that gap.

## Status on 2026-11-07

- **Still in force, with nothing that invokes it.** The ruling grants
  self-candidate disposition only to the `mechanical_bulk` action class and to
  the routes named in its `permitted_routes` (`mechanical_bulk`). That route
  ran through hybrid dispatch, which retired in S2 item 6 on 2026-09-17
  (AGENTS.md; [model-routing.md, "Worker Routes (retired)"](../dispatch/model-routing.md)).
  No live route reaches the class, so the exception currently disposes nothing.
- **What governs current work.** The 2026-11-04 routing practice keeps
  independent review requirements. A green evidence gate does not stand in for
  independent review on any current route.
- **Revival.** A future route that wants self-candidate disposition cites this
  record, satisfies D-8's ">=5 green first-pass with 0 escalations" rule for its
  class, and is granted by a new, dated decision. As the ruling itself says, a
  route added later inherits nothing.

Sources: [open owner decisions, 2026-08-26](../plans/agentops/2026-08-26-open-owner-decisions.md);
[mechanical-bulk boundary analysis](../plans/agentops/2026-08-25-mechanical-bulk-boundary-decision.md).
