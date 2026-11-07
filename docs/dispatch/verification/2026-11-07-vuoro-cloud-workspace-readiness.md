---
status: reference
owner: operator-designated coordinator (default-assigned 2026-11-07)
last_verified: 2026-11-07
---

# vuoro.cloud workspace readiness: what is live, what blocks "migrate all work" (2026-11-07)

Observation record plus a staged recommendation. It changes no code and no
cluster state. Labels: **[fact]** observed or read in a named source;
**[inference]** my reading of facts; **[unknown]** not established.

## 1. What is live for the operator's workspace today

Source: admin plane through `vuoro-cli` (read-only), 2026-11-07 about 14:40Z.

- **[fact]** `kotona` (`01M3ABJS1QW0Q6BNDCHP0DDTYF`, owner `github:29043838`)
  is READY/READY on runtime `91f61cea5b32` (`vuoro-service` 0.1.94), tenant
  schema 3, generation 14 observed, `maintenance_mode` no, `read_only` no. It
  is live and writable, not held. Last tenant migration 2 to 3 passed
  2026-10-12. Latest backup observation: `restored`, 2026-09-25.
- **[fact]** Cluster: node `vuoro-cloud-poc` Ready, Flux
  `v0.1.0-poc.81@sha1:0733b42`, control, control-admin, gateway and tenant
  controller ready on image prefix `sha256:e2c6b8d2` (poc.81); controller 1/1.
- **[fact]** Four test workspaces are held by design (maintenance yes,
  read-only yes, operation generation 0, so no engage operation exists):
  `blocker12-canary` (orphaned), `isolation-proof` (schema 2),
  `g2-gen71-canary`, `g3-gen72-canary`. The estate gate reads `holds` only
  because of them (`scripts/estate_status.py`; vuoro-cloud
  `rollout/status` `maintenance_workspaces`).
- **[fact]** vuoro-cloud `config/compatibility.json` has
  `release_ready: false`, pins `sprintctl` 0.18.0 and `tenant_schema` 2..3.
- **[inference]** The operator workspace works as a hosted tenant; nothing in
  the observation says it is the workstation's work store, and it is not (see
  section 2).

## 2. What "migrating all work" means, and where it stands

- **[fact]** Decision Q1(b), 2026-09-27
  (`docs/architecture/2026-09-27-agentic-ecosystem-and-split-horizon.md` §6):
  local harnesses move to vuoro.cloud as the primary endpoint after the
  vuoro-client Authorization fix and E2; a PAT is transitional; **no
  dual-write**; precondition: a workstation Vuoro profile with reviewed
  `production_endpoint_denied` semantics. §7 adds one named cutover with the
  record family to store mapping checked before and after. §3.3 "Transition":
  until the cutover each record family has exactly one authoritative store;
  `vuoro-shared` is authoritative for work items, and any vuoro.cloud work
  catalog is a read-only copy.
- **[fact]** Existing verification page
  (`2026-11-07-landscape-unverified-items.md` §1): two of the three
  preconditions are met (Authorization fix vuoro 553d807; E2 agentops#2466
  done 2026-09-27). The third is not: `environment-record/profiles/` holds
  five profiles, all targeting `vuoro-shared`, all with
  `production_endpoint_denied: false`; none targets vuoro.cloud. The
  workstation runs `SPRINTCTL_BACKEND=served` on `workstation-vuoro-shared`.
  The move has not started.
- **[fact]** agentops#2536 (the cutover item) is `pending`, unchanged since
  2026-09-27; its description does not mention the mapping check; no Oct-Nov
  plan names it (`docs/plans/silent-drop-check.md`). I could not resolve
  `#2536` as a GitHub issue; it is a sprintctl item (`sprintctl item show
  --id 2536`), which I did not run here. [unknown] whether its text changed
  after the page above was written.
- **[fact]** Related items in the same page: #2537 (outage-epoch state
  machine, Q3) not started; #2535 (digest-bound `credctl accept`) active;
  admin items #2583 to #2587 (retire pipeline 2.3, 2.4, R, public operator
  OIDC, freeze step-up) 5 pending, 3 done.
- **[fact]** vuoro-cloud `IMPLEMENTATION-STATUS.md`: physical/WAL recovery
  qualification open; a live backup/restore and notification-delivery proof
  gate open ("blocker 6"); external onboarding, home-unavailable Forgejo
  recovery and synthetic canary open (blockers 6, 7, 11); tenant catalog and
  ledger-version verification have source only, live-cluster proof open;
  version skew: `vuoro` main carries `vuoro-service` 0.1.104 needing work
  schema 31 and Sprintctl 0.28.0, while this cluster pins 0.1.94 and
  Sprintctl 0.18.0. The local `sprintctl --version` on this workstation
  reports 0.20.0. [inference] local client, hosted tenant and `vuoro-shared`
  work schemas are not the same version, so a mapping and a schema check are
  required before any record-family move.
- **[fact]** vuoro-cloud `docs/IMPLEMENTATION-MATRIX.md` lists "higher-blast-radius
  proof" columns that are still open (external two-user onboarding, released
  Actionq operations, synthetic canary and real backup/restore evidence).

## 3. Blockers, derived from the evidence

| # | Blocker | Basis | Applies to |
|---|---|---|---|
| B1 | No workstation vuoro.cloud profile; `production_endpoint_denied` semantics unreviewed | Q1 precondition; five profiles all point at vuoro-shared [fact] | any local harness move |
| B2 | No named cutover and no record family to store mapping, before/after checks, or rollback; #2536 pending, unscheduled | §7; #2536 [fact] | moving all work |
| B3 | Work-schema and client-version skew between workstation (Sprintctl 0.20.0), tenant pin (0.18.0) and vuoro main (0.28.0) | compatibility.json, STATUS [fact]; effect on data is [inference] | moving work records |
| B4 | Recovery not qualified: latest backup observation is 2026-09-25 `restored`; WAL/physical recovery qualification and live restore proof open | STATUS [fact]; "6 weeks stale" is a date comparison | trusting vuoro.cloud as the only store |
| B5 | Long-lived PAT is transitional; the local identity/token flow does not exist | Q1 amendment [fact] | durable credentials on agent hosts |
| B6 | Outage semantics (#2537) not started; `vuoro-shared` fallback role depends on it | §3.3 [fact] | removing vuoro-shared as the write path |
| B7 | `release_ready: false`; external onboarding and synthetic canary open | compatibility.json, STATUS [fact] | public or multi-user use, not personal use |
| B8 | Held test workspaces make the estate gate read `holds` | observation [fact] | rollouts that require all tenants migrated or unheld |

Not a blocker **[inference]**: the cluster, controller, gateway or the
operator workspace itself. They are healthy by the observation.

## 4. Personal-use profile (proposal)

Idea: a lower, named qualification bar for the operator plus their own test
workspaces, distinct from `release_ready` for external users.

- **[inference]** B7 and parts of B4 matter much less for one trusted
  operator who also owns the host: no external onboarding, no abuse
  surface, one human to notice and repair. B1, B2, B3, B5 and B6 do not
  shrink, since they protect the operator's own data.
- Proposed bar, to be reviewed and named before use: (a) B1 to B3 done;
  (b) a restore drill on `kotona` newer than the cutover rehearsal;
  (c) PAT use explicitly time-bounded; (d) `vuoro-shared` kept as the
  documented fallback until B6 exists; (e) `release_ready` stays `false`.
- Risk: a personal-use pass must not be read as `release_ready` or as
  permission for other users; label it in the gate output.

## 5. Estate gate semantics for held test workspaces (proposal, no code change)

Today any entry in `maintenance_workspaces` makes the gate `holds`
(`held.tenants_in_maintenance`, `CLOUD_HOLDS`). The route serves
`{id, state, maintenance_mode, active_migration_id, since}` with no slug, no
hold reason and no test flag.

Proposal: treat a hold as non-blocking only when it is on a reviewed
allowlist of workspace ids kept in Git (id, reason, reviewer, date), and
print the allowlisted holds as `held-by-design` in the gate detail instead
of dropping them. Anything not on the list still blocks.

Risks: (1) the allowlist can go stale, so a real hold on a listed id would
be hidden; mitigate by requiring `maintenance_mode` and `read_only` to match
the recorded values. (2) A rollout that requires all tenants migrated would
then proceed past `isolation-proof` on schema 2; the fleet-convergence gate
in vuoro-cloud must still count it, or the workspace must be retired first.
(3) The server holds `is_test`, but the estate report cannot see it; an
allowlist in agentops duplicates that fact. Alternative: serve `is_test` and
a hold reason in `rollout/status` (a vuoro-cloud change). Retirement of the
four workspaces (`docs/runbooks/operator-workspace-status.md` in
vuoro-cloud) removes the question without any semantic change.

## 6. Staged recommendation

| Stage | Work item | Acceptance check |
|---|---|---|
| S0 (now) | This page and the vuoro-cloud status corrections merged; estate gate detail names held workspaces (state, mode, since) | `agentops estate status` shows ids with state and `since`; vuoro-cloud STATUS has no stale "held since 2026-10-13" text |
| S1 | Decide the four test workspaces: leave, or retire via plan flow (operator decision) | Gate no longer reads `holds`, or the allowlist proposal is reviewed and recorded |
| S2 | Draft the record family to store mapping and the cutover plan under `docs/plans` (register entry); fold into #2536 | Plan names every family, its current store, its target, and a before/after count check; plan register passes |
| S3 | Add a `workstation-vuoro-cloud` profile with `production_endpoint_denied` reviewed; read-only first (`work:read`) | Profile passes the environment-record checks; a read through it returns `kotona` data; no write authority granted |
| S4 | Resolve skew: pick the tenant runtime and Sprintctl pair, run composition qualification and tenant migration on a test workspace | `scripts/qualify_composition.py` passes; test workspace migrates and rolls back; `release_ready` unchanged |
| S5 | Fresh restore drill on `kotona`; record a new backup observation | Observation newer than the cutover rehearsal, status `restored` |
| S6 | Rehearse the cutover on a copy of one record family, then cut over families one at a time with before/after counts; no dual-write | Counts equal before and after; rollback tested; `vuoro-shared` remains fallback |
| S7 | Outage-epoch state machine (#2537) before removing the vuoro-shared write path | Epoch tests pass; DEGRADED LOCAL and RECOVERY exercised |

## 7. Estate report gap

**[fact]** agentops `scripts/estate_status.py` previously printed only
workspace ids for `held.tenants_in_maintenance`. The rollout route already
serves `state`, `maintenance_mode` and `since`, so the report now prints them
with each id (this PR). The route serves no slug, no hold reason and no test
flag; the report cannot print them until vuoro-cloud adds them
(field shape: `docs/runbooks/estate-status.md` here, vuoro-cloud `docs/runbooks/operator-actions.md`).
