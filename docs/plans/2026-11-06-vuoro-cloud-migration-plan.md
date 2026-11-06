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
  each unapplied file in sorted order with one `execute` per file, inside one
  `psycopg.connect` block (not autocommit). All unapplied files and their
  bookkeeping rows therefore commit together at exit, unless a file issues its
  own `COMMIT`; 26 of the 33 files wrap themselves in `BEGIN; ... COMMIT;`, which
  commits the batch so far. The runner has no advisory lock, checksum, down path
  or written transaction policy, and `CREATE INDEX CONCURRENTLY` cannot run in
  any file today.
- Apply path: k8s Job `apps/control/migration-job.yaml` (digest-pinned image,
  `vuoro_control_owner`, `backoffLimit: 6`). Not run at app startup.
- Tenant schemas: separate controller flow (`Reconciler.migrate_tenant`,
  MAINTENANCE -> MIGRATING -> READY or ROLLBACK_REQUIRED), documented in
  `18-MULTITENANT-VERSIONING-AND-MIGRATION.md`. No automatic rollback runner;
  deep tenant-schema verification is deferred.
- Guards already present: `tests/test_migration_order.py` (branch migrations must
  sort after the merge-base newest) and `scripts/validate.py`
  `check_migration_names` (malformed name or duplicate prefix in the tree).
  `tests/fixtures/reviewed_migrations/` holds a single reviewed file
  (`026_controller_status_at.sql`), not a frozen set.
- Existing rollback rule: `18-MULTITENANT-VERSIONING-AND-MIGRATION.md`, "Rollback
  procedure per persisted-state change": additive-only, roll back by stopping
  writes to new columns or tables; a failed tenant migration may restore from its
  `checkpoint_ref`. Written for tenant-lifecycle migrations 004-006.
  `fleet_converged()` is permissive with no `runtime_instance` rows by documented
  choice (avoids a first-boot deadlock).
- Release: signed `v0.1.0-poc.N` tag plus image digest through
  `promote-deployment.yaml`; Flux GitOps; staging contract in plans 2645/2646.
- Migrations 020-025 and 029-034 are mostly role grants; 026-028 are not.
- A stale branch, `origin/feat/admin-2.3-retire-cli-p5`, carries a second
  `031_workspace_suffix_read_committed.sql` (main's 031 is
  `031_pat_principal_binding.sql`).

Cited from other documents and not verified here: the staging contract in plans
2645/2646, Flux behaviour, and tag-signature enforcement in the promotion
workflow. The 164-commit staleness figure is the survey's, not re-counted.

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
   expanded schema stays. This holds only if the previous release tolerates the
   expanded schema; each change states that explicitly, and if it cannot, the
   change is not expand-only and needs its own reviewed procedure (for tenant
   schemas, the existing `checkpoint_ref` restore) before release. This extends,
   not replaces, the rule already in document 18.
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

Extend the existing "Rollback procedure per persisted-state change" section of
document 18 rather than adding a competing document, and say whether that rule
now covers all control migrations or only tenant-lifecycle ones. Include a
per-change checklist: rollback boundary, restore effect,
role grants touched, tenant-schema impact, image bump needed.

### P2. Runner hardening

Changes to `scripts/migrate.py`, each with a disposable-PG test. Decide first,
as a recorded choice, who owns the transaction: the runner (one transaction per
file, files must not contain `BEGIN`/`COMMIT`, which would require rewriting 26
released files and is therefore not recommended) or the files (the runner runs
in autocommit and each file keeps its own `BEGIN; ... COMMIT;`). Recommended:
files own it, runner uses autocommit, each new file must be atomic and
idempotent (atomicity alone does not make a Job retry safe: the bookkeeping row
is inserted after the file and committed later, so an earlier committed file is
re-run if a later one fails; moving the insert into each file's transaction is a
separate change), and a file that needs
`CREATE INDEX CONCURRENTLY` omits the wrapper and is reviewed as an exception.
Changing to autocommit changes behaviour for the 7 unwrapped files (008, 009, 011, 013, 022, 024, 032) and needs
rehearsal (P4) before release.

- Take a PostgreSQL session advisory lock (`pg_advisory_lock`, not the
  transaction variant) on the single runner connection for the whole run, with a
  distinct constant key (not the `hashtext(workspace_id)` scheme of document 18)
  and a try-lock with timeout so a second Job fails fast and visibly.
- Store a content checksum per applied file and refuse to run if an applied
  file's bytes changed. Backfill is a runner step, not a migration: when the
  checksum column is NULL for an applied name, the runner records the current
  file digest once, after an operator confirms the files match what was applied.
  Define NULL handling (applied but unchecked = reported, not trusted) and the
  fresh-install path (checksum written with the row). Fix digest rules (raw
  bytes, no newline normalisation) and check `.gitattributes`.
- Gap check is baseline-aware: the missing 016 is declared in a reviewed
  allowlist, and any new gap or duplicate fails.

### P3. Number-collision control

Duplicate prefixes in the tree (`check_migration_names`) and ordering after the
merge-base (`test_migration_order.py`) are already enforced. The remaining gap is
two open branches claiming the same next number, as the stale second `031_`
shows. Mechanism: assign the number at merge time (the merge step or a required
rebase check renames or rejects), not by scanning other open PRs, which needs
Forgejo API access from CI, is racy and misfires on abandoned PRs.

### P4. Migration rehearsal

CI job that applies all migrations to an empty PG16 and to a database built by
replaying the previous release tag's migrations (no restored data, which avoids
a snapshot source and pg_dump/server version mismatch), runs the application
test suite against both, and records the result in the release report card. This proves upgrade from the
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

Depends on P2 and P4. Add the migration digest and checksum set to the release gate and report card,
so a promoted tag shows which migrations it contains. Staging admission already
requires physical evidence beyond a merged pin; migrations ride that rule.

## Ordering

P0 -> P1, with P2 and P3 independent of P1 (code and CI files only; P2 needs the
transaction-ownership decision first) -> P4 (needs P2) -> {P5, P6} -> P7 (needs
P2 and P4). P2 and P3 touch different files and can run in parallel. P5 and P6 are
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
