---
status: active
owner: operator-designated coordinator (default-assigned 2026-11-07)
last_verified: 2026-11-07
---

# Operator gates as work items

A step only the operator can perform is a work item, not a restriction recorded
in handoff prose. Each one is an `operator-command-package/v1` document
([schema](../../../schemas/operator-command-package.v1.schema.json)) carrying
what [/projects/dev/CLAUDE.md](/projects/dev/CLAUDE.md) requires before anything
waits on the operator: the directory, the exact commands, a verified
precondition, the expected result, what to send back, and the rollback.

`python3 scripts/check_operator_command_packages.py` validates every package
here against the schema and two cheap rules: a `ready` package has no blockers,
every precondition verified and every command exact; a `blocked` package names
what resolves each blocker, and that resolver is never just "operator" (route to
build, repair or park instead).

A package is the body an operator request carries. It grants no authority, and
it does not replace the durable operator-request lifecycle owned through Vuoro
(CL-K03, [operator actions plan](../../plans/agentops/2026-10-18-operator-actions.md)).

## Programme completion

Programmes complete at **source accepted**: merged on canonical main with
exact-head CI green and independent review recorded, against their original
acceptance criteria. Deployment is a separate gate item that references one of
the packages below. The rolling [programme status](../programmes/STATUS.md)
reports both.

## Packages

| Package | Gate | Programme | Readiness 2026-11-07 |
|---|---|---|---|
| [work31-appservice-field-execution](work31-appservice-field-execution.v1.json) | field execution | 08 integration | blocked: monitor/helper phase protocol, fresh pre31 pair |
| [vuoro-service-0-1-104-rollout](vuoro-0-1-104-rollout.v1.json) | deployment | 03 cloud product | blocked: pin PR, schema-version mapping, promotion |
| [vuoro-cloud-poc-promotion](poc-promotion.v1.json) | promotion | 03 cloud product | blocked: frozen head and digest after #353 |
| [admission-mint-signing](admission-mint-signing.v1.json) | signing | 04 requests | blocked: private transport, service identity decision |
| [vuoro-cloud-staging-rehearsal](staging-rehearsal.v1.json) | rehearsal | 02 cloud recovery, migration plan | blocked: #353, schema-version mapping |
| [vuoro-cloud-live-state-read](vuoro-cloud-live-state-read.v1.json) | deployment (read-only observation) | 03 cloud product | ready: operator tunnel up, then `kubectl get` only |

## Owners

Seams that had no named owner. Where nobody was named, the default owner is the
operator-designated coordinator role (the session the operator designates as
coordinator for the estate), marked `default-assigned 2026-11-07`. Reassign by
editing this table in a reviewed change.

| Seam | Owner | Basis |
|---|---|---|
| Release train (source slice to deployment: rollouts, promotions, Work31, migrations) | operator-designated coordinator, default-assigned 2026-11-07 | no plan owned it (landscape alignment report, 2026-11-07) |
| Tenant schema-version mapping contract | vuoro repo maintainer role, executed by the operator-designated coordinator; default-assigned 2026-11-07 | the contract is defined in the vuoro repo; vuoro-cloud consumes it (migration plan P5/P6) |
| Migration numbering integration (vuoro-cloud `migrations/`, sprintctl work schema numbers) | operator-designated coordinator as integration owner, default-assigned 2026-11-07 | concurrent Codex and Claude lanes collide on numbers; one integration owner allocates the next number before a PR opens |
| EC-00 reservation #405 (vuoro#2734) | held by another session (handoffs 2026-11-05, 2026-11-06); fallback owner operator-designated coordinator, default-assigned 2026-11-07 | do not disturb the live reservation; the fallback owner acts only after it expires or is released |
