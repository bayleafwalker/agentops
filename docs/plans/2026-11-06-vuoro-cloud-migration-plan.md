# vuoro-cloud migration plan

Status: plan only; no vuoro-cloud change is made or authorized by this document.
Facts were read from vuoro-cloud `origin/main` (153f47d, 2026-11-06). The local
vuoro-cloud checkout was 164 commits behind and was not used. Real vuoro-cloud
PRs live on Forgejo, which this workspace could not query; re-diff `migrations/`
on every open Forgejo PR head before acting on this plan.

## Observed state

- Control-plane schema: ordered SQL files `migrations/NNN_name.sql`, 001 through
  034 on `origin/main` (no 016). PostgreSQL only; tests use a disposable PG16
  (`tests/conftest.py`, CI PG16). There is no SQLite or dual-engine path in
  vuoro-cloud itself.
- Runner: `scripts/migrate.py` records names in `schema_migrations` and applies
  each unapplied file in sorted order with one `execute` per file. It has no
  advisory lock, checksum, down path or written transaction policy.
- Apply path: k8s Job `apps/control/migration-job.yaml` (digest-pinned image,
  `vuoro_control_owner`, `backoffLimit: 6`). Not run at app startup.
- Tenant schemas: separate controller flow (`Reconciler.migrate_tenant`,
  MAINTENANCE -> MIGRATING -> READY or ROLLBACK_REQUIRED), documented in
  `18-MULTITENANT-VERSIONING-AND-MIGRATION.md`. No automatic rollback runner;
  deep tenant-schema verification is deferred.
- Guards: `tests/test_migration_order.py` and `tests/fixtures/reviewed_migrations/`.
- Release: signed `v0.1.0-poc.N` tag plus image digest through
  `promote-deployment.yaml`; Flux GitOps; staging contract in plans 2645/2646.
- Recent migrations (020-025, 029-034) are mostly role grants.

Unknown, and not to be guessed: any `material-v2` migration or fencing contract
(no document found; search was not exhaustive); physical recoverability after
restore (`physical_recoverability=unknown`); behaviour of unreleased Forgejo PRs.

## Principles

1. Forward-only. A released control migration is never edited or reordered. The
   frozen copies under `tests/fixtures/reviewed_migrations/` already express
   this; make it a written policy.
2. Expand, then contract, in separate releases. A release may add columns,
   tables, grants or nullable fields; code that stops using a thing ships in a
   later release than the one that stops writing it; removal ships a release
   after that. No migration drops or rewrites data in the same release that
   first stops depending on it.
3. A schema change is a deployment change: it needs an image bump in the
   migration Job, so it travels the existing signed promotion path. Nothing in
   this plan bypasses `promote-deployment.yaml` or staging admission.
4. Rollback means roll the application back to the previous digest while the
   expanded schema stays. If that is unsafe for a change, the change is not
   expand-only and needs its own reviewed procedure before it is released.
5. Unknown stays unknown. A migration that cannot state its rollback boundary
   or its restore effect is held, not defaulted.

## Work packages

Every package is a vuoro-cloud change except P0. Each is independently
reviewable. Integration owner for vuoro-cloud `main` is whoever the Codex lane
declares; agentops does not write there.

### P0. This plan and the intent check (agentops)

Confirm the principles against the vuoro-cloud architecture documents
(`18-MULTITENANT-VERSIONING-AND-MIGRATION.md`, the 2026-10-10 and 2026-10-12
ownership and settlement plans). If any conflicts with them, the architecture
document wins and this plan is corrected, not the reverse.

### P1. Written migration policy (docs only)

Add the principles above to vuoro-cloud as a policy document and link it from
`18-...`. Include a per-change checklist: rollback boundary, restore effect,
role grants touched, tenant-schema impact, image bump needed.

### P2. Runner hardening

Changes to `scripts/migrate.py`, each with a disposable-PG test:

- take a PostgreSQL advisory lock so two Jobs cannot interleave;
- store a content checksum per applied file and refuse to run if an applied
  file's bytes changed;
- fail closed on a name gap or duplicate number in the directory (extends
  `test_migration_order.py`);
- state the transaction rule: one file, one transaction, unless a file declares
  an explicit exception such as `CREATE INDEX CONCURRENTLY`, which gets its own
  file and review.

Existing deployments have no checksum rows. Backfill them in a first migration
that records current file digests without re-running anything, and verify
against a restored copy before release.

### P3. Number-collision control

Parallel branches can claim the same number (a stale branch already carries a
second `031_`). Add a CI check that fails when a PR introduces a number already
on its base or on another open PR head, and rule that new migrations take the
next free number at merge time, not branch time.

### P4. Migration rehearsal

CI job that applies all migrations to an empty PG16 and to a restored snapshot
of the previous released schema, runs the application test suite against both,
and records the result in the release report card. This proves upgrade from the
previous release only; it does not prove arbitrary old-version upgrade.

### P5. Tenant-schema migration evidence

Close the deferred items in `18-...`: deep tenant-schema verification after
`MIGRATING`, and a tested ROLLBACK_REQUIRED procedure (still manual, but
scripted and rehearsed). Make `fleet_converged()` non-permissive when no
`runtime_instance` rows exist, or document why it must be. Live mixed-generation
and Talos proof remain operator actions and are not claimed here.

### P6. Restore and retire-dump interaction

For each migration class state its effect on the retire dump (`pg_dump` through
`age` to public recipients) and on restore qualification. Do not design
`material-v2` restore fencing here; record it as unproven until its owner
document exists, and make P1's checklist require that statement.

### P7. Release path integration

Add the migration digest and checksum set to the release gate and report card,
so a promoted tag shows which migrations it contains. Staging admission already
requires physical evidence beyond a merged pin; migrations ride that rule.

## Ordering

P0 -> P1 -> {P2, P3} -> P4 -> {P5, P6} -> P7. P1 is documentation and can land
first. P2 and P3 touch different files and can run in parallel. P5 and P6 are
blocked on owner decisions only where noted; otherwise they are buildable from
source.

## Overlap and risks

- A Codex session is landing vuoro-cloud and Sovite PRs. None of the newest
  branches seen touch `migrations/`, `scripts/migrate.py`, `db.py` or
  `db_roles.py`, but that was checked on GitHub mirror branches only. Before any
  package starts, re-diff those paths on Forgejo and coordinate numbering with
  the declared integration owner.
- Checksum backfill (P2) touches every live control database. It needs a
  rehearsal against a restored copy and an operator-run step; it is not
  authorized by this plan.
- No package claims production readiness. Each is source work whose acceptance
  is a passing disposable-PG test; deployment evidence is separate.

## Not in this plan

Changes to Sovite, the Codex lane's open PRs, `material-v2`, the retire age key
(operator-held), deployment of any migration, or edits to released migrations.
