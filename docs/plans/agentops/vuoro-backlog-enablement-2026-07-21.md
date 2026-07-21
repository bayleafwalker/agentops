---
doc_id: vuoro-backlog-enablement-2026-07-21
status: approved
approved_at: 2026-07-21
approved_by: operator
governing_decision: vuoro-served-substrate
---

# Vuoro served-substrate backlog enablement

This is the registration and sequencing ledger for the operator-ratified
[`vuoro-served-substrate-plan.md`](vuoro-served-substrate-plan.md). Live
sprintctl state remains authoritative for item status, priority, refs, and
dependencies; this note makes owner placement and cross-repository gates
reviewable from Git.

## Registered work

| Owner | Items | Outcome | Priority / posture |
| --- | --- | --- | --- |
| agentops / future `vuoro` | #1185–#1189 | public repo, contracts, four-domain composition, packaging, appservice runtime handoff | P1; build after recorded dependencies, with #1189 planning-gated on appservice inspection |
| agentops governance | #1190–#1192 | environment injection, ratification validation, marked DR reconciliation | P2/P3; #1192 parked behind the catalog foundation |
| agentops existing | #1173, #1174 | catalog-mediated proposal execution and independent session dogfood evidence | P2; existing #1173 → #1174 dependency retained |
| sprintctl | #1193–#1195 | deployment migrations, work application core/catalog, endpoint/identity cutover | P1; #1193 and #1194 both block #1195 |
| sprintctl retirement | #1164 | retire transitional backend/client paths | P3; #1195 and existing #1163 evidence block it |
| actionq | #1196–#1198 | deployment migrations, execution adapter, external-runtime boundary | P1/P3; #1197 blocks parked #1198 |
| kctl | #1199, #1200 | central review schema and knowledge adapter | P1; #1199 blocks #1200 |
| auditctl | #1201, #1202 | central ingest schema and audit adapter | P1; #1201 blocks #1202 |

## Classification decisions

- Existing sprintctl #1163 remains done and is the capability-distribution
  exhibit; it is not reopened.
- Existing sprintctl #912 remains historical local migration-safety scope;
  shared-authority migration is #1193.
- Existing agentops #1174 remains session-mechanization evidence and no longer
  claims to be the capability-catalog promotion gate.
- Appservice work is coordinated by #1189 until its repository and live
  backlog are available. The owner-local appservice records must be created
  only after that inspection and linked back without duplicating #1189.
- Windmill is not adopted. #1198 records the single-queue boundary and stays
  parked until an external runtime is selected.

## Cross-repository critical path

```text
#1185 public repo
  -> #1186 contracts
  -> domain migrations/adapters (#1193/#1194, #1196/#1197,
                                 #1199/#1200, #1201/#1202)
  -> #1187 four-domain composition
  -> #1188 packaging
  -> #1189 isolated vuoro-dev + production promotion
  -> #1195 workstation endpoint/identity cutover
  -> #1164 legacy retirement
```

Environment injection (#1190) follows the identity/catalog contract.
Ratification validation (#1191) can build independently at P2. Marked recovery
(#1192) follows the invocation contract and domain compatibility work.

## Registration quality

Every new item has:

- a native priority;
- an owner, rationale, scope, non-scope, verification, and rollback statement;
- the ratified canonical decision and owner-local alignment as document refs
  where an owner-local note exists;
- an explicit dispatch-build, dispatch-plan, or parked decision note;
- native dependency edges for dependencies within the same repository scope.

Cross-repository dependencies are stated in item descriptions and this ledger
because sprintctl dependency edges are repository-scoped.
