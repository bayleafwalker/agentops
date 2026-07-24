# Next-Session Dispatch — Clean-Room × #1164 Workpath

Prepared: 2026-07-24. Context: the clean-room migration-safety gate is closed
(no migration; Vuoro retains authority), the strategic buy/adapt/fork
assessment is open at Stage 2, and the cross-repo backlog is filed. Full
rationale: [clean-room-1164-cross-repo-backlog.md](clean-room-1164-cross-repo-backlog.md).

## Session 1 (next): make the record durable and the gates legible

Repo: agentops, then sprintctl. No cluster access needed.

1. **agentops #1227 — commit the clean-room record.** The decision readout,
   strategic assessment, Stage-1 source analysis, fork map, both new lane run
   directories, and the fork-map schema are sitting uncommitted. Commit them
   (leave `docs/plans/evidence-needed.md` unstaged), plus the two new plan
   docs (`clean-room-1164-cross-repo-backlog.md`, this file). Verify
   decision-readout links resolve.
2. **sprintctl #1218 — gate-evidence ledger for #1164.** Build the per-gate
   table from the backlog doc's section 2 with concrete evidence links
   (#1163 dogfood record, #1193/#1194/#1195 verification evidence, #1194
   legacy-command inventory vs current catalog). Attach it as a ref on
   #1164. Expected finding: the open rows are exactly #1219/#1220 (sprintctl),
   #1222/#1223 (vuoro), #1225/#1226 (appservice).

Exit state: clean assessment worktree; #1164 shows the ledger ref; remaining
gate gaps each name an owning item.

## Session 2: close the recovery row

Repo: sprintctl. **#1219 — export/recovery rehearsal.** Export from the
served remote authority, restore into recovery SQLite, verify parity,
document the operator procedure. This is the hard prerequisite for removal —
it replaces the split backend's fallback role. Pair with **#1220**
(old-client fail-closed guidance; the stale uv-tool 0.2.0 install with its
`schema-version-mismatch` error is the ready-made test subject) if time
allows.

## Session 3+: deployment evidence, then the capstone

- appservice **#1225/#1226** (migration job + role split + DDL denial;
  credential sweep) and vuoro **#1222/#1223** (four-domain evidence;
  promotion evidence) — cluster-facing, can run in either order.
- When all ledger rows are green: **#1221** operator gate decision event on
  #1164, then **#1164 itself** — remove split-backend/remote-client bootstrap
  code, rerun full suite and catalog parity, update migration docs, and
  capture the removal diff (modules/lines) for the Stage-4 baseline.

## Session 5 (next): finish #1220, start vuoro #1245, then devbox-agent, then #1221

Prepared 2026-07-24 (session 4 handoff). Session 4 closed #1225, #1223, and
#1222 live (not just documented — see sprintctl `docs/plans/1164-gate-evidence-ledger.md`
rows 6/10/8, vuoro `docs/plans/1223-production-promotion-record.md` and
`docs/plans/1222-dev-four-domain-evidence.md`) and flipped the `sprintctl`
repo's own workstation `.envrc` to served mode (verified live).

**Do not report or treat #1164/track=projection-cutover as released.** It is
not. "Released and in production use for workstation and development
box(es)" requires all of the following, none of which session 4 completed:

1. **vuoro #1245 — make `work_store.repo_id` a per-request parameter**
   (`packages/vuoro-service/src/vuoro_service/composition.py:261` currently
   hardcodes it once at process start from `VUORO_WORK_REPOSITORY_ID`).
   This is real feature work, not a config change — `vuoro-shared` today can
   only ever serve the `sprintctl` repo tenant. It blocks: the other 7
   workstation repos (`agentops`, `box`, `actionq`, `aligned-equity`,
   `_orchestration`, `homelab-analytics`, `scribectl`) ever using served
   mode, and devbox-agent using anything but the `sprintctl` repo.
2. **Devbox-agent — untouched as of session 4.** No SSH, no inventory of its
   repo clones/credential files/`.envrc` state, no served-mode verification.
   Per `AGENTS.md`, devbox-agent has no cluster/kubectl/Talos reach, but
   served mode needs none of that — only HTTPS to the Vuoro endpoint and a
   credential file at `~/.config/vuoro/credentials/` (workstation's
   equivalent lives at `~/.config/vuoro/credentials/vuoro-shared-workstation`;
   devbox-agent likely needs its own, per the `devbox-agent-vuoro-shared.json`
   profile already in
   `agentops/templates/dispatch/environment-record/profiles/` — check
   whether that profile's `credential_ref` file actually exists on
   devbox-agent before assuming it's ready). Start here: `ssh devbox-agent`,
   check its `sprintctl` repo clone's `.envrc`/`.sprintctl/backend.json`,
   confirm the credential file, then repeat session 4's served-mode flip
   (marker to `served`, `SPRINTCTL_VUORO_PROFILE` to the devbox-agent
   profile) and verify with `sprintctl doctor` + a real `item show`.
3. **sprintctl #1220** — partial evidence only (doctor fail-closed on schema
   mismatch confirmed, event #1433). Still needs denied-**write** evidence
   from a stale install on every remote entry point, plus the documented
   upgrade path in migration docs.
4. **sprintctl #1221** — the actual release decision. Record only once
   #1245, the devbox-agent replication, and #1220 are all genuinely green —
   not before. This is the terminal event that #1164's own removal work
   (dead remote-client bootstrap code, full suite, catalog parity, migration
   docs) depends on.

Sequencing note: #1245 is the long pole (real service code + tests + a
redeploy of `vuoro-shared`) and blocks both the other-7-repos work and most
of devbox-agent's usefulness beyond the `sprintctl` repo. Doing devbox-agent's
`sprintctl`-repo-only inventory/flip first is still worthwhile and unblocked
today — it doesn't need #1245.

Full memory: `project_1164_session3_gate_status.md` in the agentops-memory
store (despite the filename, current as of session 4).

## Parallel clocks to start early (cheap, time-gated)

- agentops **#1231** — seed S-DORMANT; the fourteen-day horizon cannot be
  compressed, so seed it in Session 1 if convenient.
- agentops **#1232** — resume observations accrue only at real resume
  boundaries; record the pre-pause state at the end of every session per
  `evidence-needed.md`.

## After the capstone: the decisive strategic experiment

agentops **#1228** (Stage-4 sheet + bespoke baseline, incorporating the
post-#1164 removal diff) then **#1229** (Stage-2 fork/projection vertical
slice, fresh locked run, effort-budgeted). Constraints that survive every
session: frozen R1–R8/H8 unchanged; no strategic work grants authority; the
strategic track never gates #1164.

## Session 6: finish #1220 deploy, close #1221, file the served-catalog gap

Prepared 2026-07-24 (session 5 handoff). Session 5 landed real code:

- **devbox-agent fully replicated** — reconciled its diverged `sprintctl`
  clone (2 real unpushed commits recovered as PostgreSQL schema version 4,
  see sprintctl PR #2), reinstalled the `uv tool` with `remote,served`
  extras, fixed `.envrc` to support host-local `.envrc.local` overrides
  (sprintctl PR merged directly to main), and verified `sprintctl doctor` +
  a live `item show` work over served mode via plain `direnv`. Its
  `agentops` clone was also diverged but confirmed to hold zero unique
  commits (all duplicates already on `origin/main`) and was reset cleanly.
- **vuoro #1245 code landed** — sprintctl PR #3 and vuoro PR #1 (both
  merged, CI green): `WorkApplication.invoke()` now resolves `repo_id` from
  `context.identity.repo_id` per call instead of the fixed
  `VUORO_WORK_REPOSITORY_ID` bound at process start; `Identity` gained a
  `repo_id` field; `load_identities` requires it on any `work:`-authority
  identity. **This is NOT yet released** — releasing requires: build+publish
  a new sprintctl adapter wheel, update its SHA256 pin in the vuoro-shared
  composition manifest, add `repo_id` to each production identity-registry
  entry, and redeploy `vuoro-shared`. All four are deployment actions
  against a live production service, deliberately not done this session.
- **sprintctl #1220 write-denial evidence recorded** — see sprintctl
  `docs/plans/1164-gate-evidence-ledger.md`, "#1220 stale-install
  fail-closed record": doctor + representative write commands all denied
  before any DB mutation, against a disposable PostgreSQL stuck at schema
  version 1. Migration upgrade path was already documented in an earlier
  session's PR.

**Session 6 should do, in order:**

1. **Redeploy vuoro-shared** (the #1245 deployment follow-up above) — needs
   appservice/kubernetes access and an explicit go-ahead; this is the last
   step that actually unblocks the other 7 workstation repos and
   devbox-agent's non-sprintctl repos from served mode.
2. **sprintctl #1221** — record the operator gate decision event on #1164,
   once #1245 is genuinely deployed (not just merged) and #1220 is closed.
3. **Served-catalog gap (finalizer action, filed not fixed)** — see
   sprintctl `docs/plans/1164-gate-evidence-ledger.md`, "Follow-up finding:
   served catalog gap for item metadata writes". `sprintctl item add`,
   `item note`, and `item ref add` are not in `vuoro_adapter.
   WORK_OPERATION_CONTRACTS` and fail under plain `SPRINTCTL_BACKEND=served`
   (no direct DSN) with `could not connect to postgres from SPRINTCTL_URL:
   'NoneType' object has no attribute 'encode'`. Inventory every CLI write
   command missing a served operation, decide the operation set, and extend
   the catalog + `WorkApplication` to close it — independent of #1245.

## Dispatch hints

- `sprintctl next-work --sprint-id 407` (sprintctl repo) and
  `--sprint-id 428` (agentops repo) surface the ready items; #1229 stays
  blocked until #1227 and #1228 are done — that is intentional.
- The workstation `sprintctl doctor` schema-version-mismatch is expected
  from the stale 0.2.0 uv-tool install; it is #1220's test subject, not a
  regression to fix on sight.
