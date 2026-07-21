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
| agentops coordination | #1185–#1189 | public bootstrap, cross-repo mirrors, and appservice runtime handoff | P1; #1185 is blocked only on GitHub repository-creation permission, #1186–#1188 mirror owner items, and #1189 remains planning-gated on appservice inspection |
| `vuoro` owner backlog 427 | #1203–#1206 | contracts, four-domain composition, packaging, and marked recovery | P1/P3; #1203 is the owner-local chain head and #1206 remains parked |
| agentops governance | #1190–#1192 | environment injection, ratification validation, and the recovery coordination mirror | P2/P3; #1191 needs a design pass and #1192 mirrors vuoro #1206 |
| agentops existing | #1173, #1174 | catalog-mediated proposal execution and independent session dogfood evidence | P2; existing #1173 → #1174 dependency retained |
| sprintctl | #1193–#1195 | deployment migrations, work application core/catalog, endpoint/identity cutover | P1; #1193 and #1194 both block #1195 |
| sprintctl retirement | #1164 | retire transitional backend/client paths | P3; #1195 and existing #1163 evidence block it |
| actionq | #1196–#1198 | deployment migrations, execution adapter, external-runtime boundary | #1196 is independently verified, pushed, and done at `8d9eeae`; #1197 is the P1 chain head and blocks parked #1198 |
| kctl | #1199, #1200 | central review schema and knowledge adapter | P1; #1199 blocks #1200 |
| auditctl | #1201, #1202 | central ingest schema and audit adapter | #1201 is independently verified, pushed, and done at `1950e8e`; #1202 is the P1 chain head |

## Classification decisions

- Existing sprintctl #1163 remains done and is the capability-distribution
  exhibit; it is not reopened.
- Existing sprintctl #912 remains historical local migration-safety scope;
  shared-authority migration is #1193.
- Existing agentops #1174 remains session-mechanization evidence and no longer
  claims to be the capability-catalog promotion gate.
- Implementation authority moved from agentops #1186, #1187, #1188, and #1192
  to vuoro #1203, #1204, #1205, and #1206 respectively. Structured notes on
  the old records mark them as coordination mirrors; agents must not dispatch
  both sides as separate implementations.
- The local public-repository bootstrap and split distributions are committed
  in `/projects/dev/vuoro`. The public GitHub remote cannot be created by the
  current credential (`createRepository` is unavailable), so agentops project
  membership remains unpushed until that external permission gate clears.
- The rebuildable project folder moved from `/projects/dev/vuoro` to
  `/projects/dev/vuoro-project` before the public repository was initialized.
- Appservice work is coordinated by #1189 until its repository and live
  backlog are available. The owner-local appservice records must be created
  only after that inspection and linked back without duplicating #1189.
- Windmill is not adopted. #1198 records the single-queue boundary and stays
  parked until an external runtime is selected.
- Actionq #1196 shipped the deployment-owned migration, read-only
  compatibility, and runtime/migration principal boundary after four
  independent verification rounds. Its final PostgreSQL 18.4 gate passed 74
  focused and 162 full tests with zero skips.
- Auditctl #1201 shipped the central observation/receipt schema and migration
  contract while preserving local SQLite/NDJSON recovery. Its final gate
  covered stable cross-stream conflict behavior, role rotation and DDL denial,
  reproducible implementation evidence, and explicit lock ordering.

## Cross-repository critical path

```text
#1185 public remote + project publication
  -> vuoro #1203 contracts (agentops mirror #1186)
  -> domain migrations/adapters (#1193/#1194, #1196/#1197,
                                 #1199/#1200, #1201/#1202)
  -> vuoro #1204 four-domain composition (agentops mirror #1187)
  -> vuoro #1205 packaging (agentops mirror #1188)
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
