# Reviewed maintenance envelopes

## Decision

For controlled maintenance that temporarily removes the normal served
authority, use a reviewed exact-plan-bound `maintenance-envelope/v1`. Prepare
the envelope, every activation commit, every independent review, and every
publication receipt while normal authority is healthy. The envelope expires
and permits only its exact ordered commits, operations, paths, and commands
whose exact argument vectors are content-bound by a command-registry artifact.

Plan 1 is the selected operating path. Activation validation takes an explicit
trusted evaluation time and exact next step; structural validation alone never
authorizes execution. At migration start there must be zero dependent
implementation sessions and zero active normal claims, with observations and
immutable evidence/receipt references no more than five minutes old. A failed predicate, changed base, stale review,
expired window, missing receipt, unexpected job/image/schema/backup state, or
any other plan drift aborts the window.

## Ownership and authority

- AgentOps owns the reusable schema, normative validator, examples, and
  verification guidance. It owns no runtime decision or cluster authority.
- Sprintctl owns any future maintenance capability lifecycle and work-state
  decisions.
- Vuoro may expose a released Sprintctl capability but remains transport and
  composition only.
- The deployment repository owns GitOps, backups, migrations, rollback, and
  reconciliation under separate operator authorization.
- Audit evidence records commands, effects, JIT bindings, reviews,
  publications, start gates, aborts, and reconciliation outcomes.

Recovery mode does not fill the authority gap. Its observations and requested
commands can be exported and later presented to the owning arbiter, but they
cannot grant, claim, approve, publish, reconcile, advance, or bind the plan.

## Frozen and just-in-time fields

Repository URLs and bases, candidate commits, step order and dependencies,
operator decision, operations, paths, commands, reviews, verification refs,
window, abort policy, and audit requirements are immutable before activation.
Only the unique backup name, live backup UID, and drain boundary timestamp may
be bound just in time. Each has a bounded source-specific pattern, in-window
observed value, immutable source evidence, binding receipt, and an exact step
at which activation validation first requires it. Earlier steps may omit the
binding; that step and every later step must retain the validated binding, and
its receipt time cannot exceed the pre-reviewed `bind_by` deadline for that
target step. Neither observation nor binding may postdate evaluation. Each
step also carries its
independent review, executable verification, and publication receipt.

## Abort and reconciliation

Before migration, restore the reviewed pre-migration state. After migration,
use the UID-attested backup or a separately reviewed forward fix. Never delete
ledger rows, edit a released migration, substitute an unreviewed commit, or
treat a recovery request as authority.

Reconciliation is append-only and incident-correlated. It records accepted,
rejected, duplicate, expired, aborted, and incomplete outcomes; exports
content-addressed evidence; redacts credentials, claim tokens, and capability
secrets; and requires independent review. Validator success proves contract
shape and deterministic binding, not that an operator acted or that any
external receipt exists.
