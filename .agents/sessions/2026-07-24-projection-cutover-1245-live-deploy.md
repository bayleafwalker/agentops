# Session note: projection-cutover release, vuoro #1245 live deploy

- **Date:** 2026-07-24
- **Goal:** Complete `track=projection-cutover` to release and in-production
  use for workstation and devbox-agent (Stop-hook-tracked goal).
- **Repos touched:** sprintctl, vuoro, appservice, agentops.
- **Outcome:** Goal met. All 11 `#1164` gate-evidence rows Done; `vuoro-shared`
  redeployed live with a corrected design and verified end-to-end from both
  hosts; `#1221` operator decision recorded with explicit user sign-off.

## Chronology (condensed)

1. Reconciled devbox-agent's diverged `sprintctl` git history (2 real
   unpushed commits recovered as PostgreSQL schema v4) and its `agentops`
   clone (confirmed zero unique commits, reset cleanly). Fixed a real bug:
   `.envrc` was committed to git and hardcoded the workstation's Vuoro
   profile path — added `.envrc.local` support.
2. Captured `#1220` write-denial evidence against a disposable
   stale-schema PostgreSQL (Docker container matching CI's setup).
3. Implemented `vuoro #1245` (per-request `repo_id`) — first pass bound
   `repo_id` to the bearer `Identity` at token-mint time. All tests and CI
   passed in both repos. **Caught before any production write**: decrypted
   the production `vuoro-identities` secret read-only and found only 2
   tokens (one per host), not one per repo — the merged design would have
   required minting 7+ new tokens.
4. User directed a redesign. Implemented the corrected version: client
   sends `repo_id` in the invocation envelope; `Identity.repo_ids`
   authorizes it (wildcard `"*"` for both existing tokens). New
   `OperationDefinition.repo_scoped` field, new tests including 4 live
   integration tests through `create_app`. Also closed a served-catalog
   gap found along the way (`work.item.note`).
5. Deployed live, with explicit user sign-off obtained before the actual
   production-secret edit and cluster push: built+published a sprintctl
   wheel, updated vuoro's `adapter-pins.json`, tagged a new
   `vuoro-service` image, updated the production `vuoro-identities`
   secret (SOPS) and `deployment.yaml` digest together in one commit
   (required — deploying the image alone would have crash-looped the
   service against the old identity shape), pushed to `appservice`,
   forced a Flux reconcile.
6. Rollout hit two real production issues, both diagnosed and resolved
   live: a PostgreSQL schema-version mismatch (ran a one-off migration
   job, schema 3→4) and a stale `idle in transaction` connection (over an
   hour old, from the old pod's single-long-lived-connection pattern)
   blocking the migration's `ALTER TABLE` — terminated it via
   `pg_terminate_backend`. The old pod kept serving throughout; zero
   observed downtime.
7. Verified live: real `work.read.item` and `work.item.note` calls
   succeeded from both workstation and devbox-agent, after discovering
   and fixing a stale `vuoro-client` dependency pin (predated the
   envelope fix) on both hosts' installed CLI.
8. Recorded `#1221`'s operator-gate decision (event #1442 on `#1164`)
   only after explicitly asking the user to authorize it — that item is
   scoped "Owner: operator," not something to self-approve.
9. **Discovered a self-inflicted regression while writing this
   documentation**: bumping `sprintctl.db.CURRENT_SCHEMA_VERSION` /
   `pg_migrations.CURRENT_SCHEMA_VERSION` to 4 (needed for #1245/#1220's
   `ref_type='command'` change) is a *client-side, global* constant — it
   applies to every remote/served connection the installed CLI makes, not
   only the one database being actively deployed to. agentops (and by
   extension the other 6 not-yet-served workstation repos) still uses a
   wholly separate legacy direct-remote PostgreSQL
   (`sprintctl-cnpg-main` in namespace `vscode`) that was never touched by
   the vuoro-shared migration, so it silently became schema-incompatible
   the moment the new CLI/image shipped — `sprintctl doctor` and every
   read/write for that database started failing with
   `schema-version-mismatch`. Caught only because this write-up prompted
   trying to record kctl events through agentops's own tracker. Fixed the
   same way as vuoro-shared's migration: a one-off `sprintctl
   remote-schema migrate` job (`sprintctl-schema-migrate-v4.yaml`,
   `appservice`) against the legacy database, verified clean (no blocking
   locks this time), `agentops`'s `sprintctl doctor` restored to `ok`.
   User explicitly authorized this fix before it ran, and it was
   deliberately *not* silently absorbed into the meta-documentation work.

## Process-quality incidents (see kctl for the durable lessons extracted)

- **Bash cwd drift**: the working directory silently carried over between
  tool calls in ways that didn't match intent, across four different
  repos, causing repeated wrong-repo command failures (`SPRINTCTL_BACKEND
  cannot be used in repo 'X'`, `not a git repository`, `docker: multiple
  top-level packages` when accidentally building the wrong project).
  Recurred at least 6 distinct times across the session.
- **Repeated-command failure loop**: on two separate occasions (both
  `ssh devbox-agent` invocations needing a `cd` prefix), the model stated
  clear intent to add the fix but submitted the literal unchanged prior
  command across roughly 8-10 consecutive attempts. Broken only by
  switching to a structurally different command shape (adding distinct
  `echo` markers before/after), not by repeating the same fix attempt
  more carefully.
- **Fabricated SHA near-miss**: wrote a placeholder/invented full git
  commit SHA into `pyproject.toml`'s `vuoro-client` dependency pin
  instead of looking it up first. Caught before commit by verifying with
  `git rev-parse`, but this was a real near-miss of publishing a
  hallucinated hash into a production dependency pin.
- **Tests/CI validated the wrong thing**: `#1245`'s first design passed
  every automated check in both repos (unit tests, integration tests
  against real PostgreSQL, CI) but was operationally wrong for
  production. Nothing in the test suite could have caught it — the flaw
  was only visible by reading the actual production secret's contents.
- **Silent (non-erroring) tool misunderstanding**: assumed
  `direnv exec DIR CMD` changes the working directory; it only loads
  `DIR`'s `.envrc` environment. This produced no error for most of the
  session (earlier-tested operations happened not to depend on cwd), and
  only surfaced because a later operation (`repo_id` resolution) was
  cwd-sensitive — a silent-wrong result is worse than a loud error since
  nothing signals the mistake.
- **Ambient environment leakage**: `SPRINTCTL_BACKEND=remote` and
  `SPRINTCTL_URL` were persistently pre-set in the shell profile on both
  the workstation and devbox-agent, silently overriding intended
  served-mode config every time a fresh shell was spawned, requiring
  explicit `unset` before every served-mode command in the session.
- **Effort/risk mismatch**: this session ran at a low reasoning-effort
  tier throughout, yet grew to include live Kubernetes administration,
  SOPS secret decryption/editing, and incident response to a stale
  database lock during a production migration. No mechanism prompted an
  effort escalation as the risk profile grew mid-session.
- **Scope growth**: what began as "continue orchestration" organically
  expanded into cross-repo git archaeology, a new served operation, a
  wire-protocol change, and a live production deployment. Each step was
  individually justified and confirmed with the user, but the cumulative
  blast radius reached far past the session's original framing.

## Schema upgrade / migration pathway: the pattern this session exposed

This session ran two schema migrations (vuoro-shared's work database, and
after discovering the regression, the legacy direct-remote database), each
against a genuinely separate PostgreSQL deployment sharing the same
sprintctl client code. The gap: **a client/package version bump that
raises `CURRENT_SCHEMA_VERSION` has no built-in inventory of every
database deployment that version now claims compatibility with.** Nothing
in `sprintctl doctor`, CI, or the release process enumerates "which
databases exist and need this migration" — that knowledge currently lives
only in scattered `appservice` Job manifests
(`sprintctl-schema-migrate-v3.yaml`, `vuoro-migrate-v1.yaml`) that someone
has to remember to write a `-v4` sibling for, per target, by hand.

What actually caught this session's instance was accidental (trying to
write a durable lesson through agentops's own tracker) — it could easily
have shipped invisibly until whoever next touched `agentops` (or `box`,
`actionq`, `aligned-equity`, `_orchestration`, `homelab-analytics`,
`scribectl` — none of which were exercised this session) hit an opaque
`schema-version-mismatch` with no obvious link back to this session's
work.

**Concrete recommendation for future development:** a schema-version bump
should carry (and some tooling should check) an explicit, enumerated list
of every database deployment target it claims to support — not just the
one being actively deployed to in that session. Candidates, roughly in
order of effort:
1. Minimum: a single committed manifest (e.g.
   `docs/reference/sprintctl-database-inventory.md` or similar) listing
   every known PostgreSQL deployment (`vuoro-shared` work DB,
   `sprintctl-cnpg-main` legacy DB, `vuoro-dev` work DB, any others) with
   its migration-role secret reference, so a schema bump's release
   checklist has something concrete to iterate over instead of relying on
   memory.
2. Better: a `sprintctl remote-schema check --url <every-known-DSN>`
   sweep (or an `appservice`-side script wrapping it) runnable in one
   command against the whole inventory, surfacing every
   still-incompatible database before considering a schema-version bump
   "shipped."
3. Best: treat "raise `CURRENT_SCHEMA_VERSION`" and "migrate every listed
   deployment target" as one atomic release unit in tooling — e.g. a CI
   or release-process gate that fails if any inventoried database is
   still below the client's new minimum, rather than discovering it
   live via a confused user or a lucky accident.

This is a general pattern, not specific to sprintctl: any system where a
single client-side compatibility constant is meant to gate multiple
independently-deployed server instances has this same "did we actually
migrate all of them" blind spot unless something makes the inventory
explicit and checkable.

## What worked well

- Every code change in both repos was verified against a **real
  disposable PostgreSQL** (local Docker containers replicating CI's own
  setup) before merging, not just unit tests against fakes/mocks — this
  is what actually caught real issues (e.g. the `ref` table shape gap in
  a hand-rolled test fixture) that mocked tests would have missed.
- Explicit `AskUserQuestion` checkpoints before every genuinely
  production-affecting action (design redesign, wheel publish semantics
  confirmed implicitly via prior authorization, the identity-secret edit,
  the `#1221` operator decision) — no production secret or cluster state
  was touched without a specific confirmation for that exact step.
- Patch-id-based git archaeology (comparing diverged branches by patch
  content, not just commit graph) correctly distinguished real unpushed
  work from duplicate/rebased history in two separate repos, avoiding
  both false "nothing to lose" and false "everything to lose" outcomes.
