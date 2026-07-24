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

## Dispatch hints

- `sprintctl next-work --sprint-id 407` (sprintctl repo) and
  `--sprint-id 428` (agentops repo) surface the ready items; #1229 stays
  blocked until #1227 and #1228 are done — that is intentional.
- The workstation `sprintctl doctor` schema-version-mismatch is expected
  from the stale 0.2.0 uv-tool install; it is #1220's test subject, not a
  regression to fix on sight.
