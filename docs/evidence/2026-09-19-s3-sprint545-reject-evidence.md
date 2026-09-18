# S3 evidence: vuoro sprint 545 items closed without being built

**Purpose.** This is the evidence digest for the 26 `reject` decisions that S3 records against
vuoro sprint 545 (dossier §11 S3: "the 26 done-but-never-built items re-marked `reject`").
The decisions cite this file's sha256.

**Finding (PLAN.md D2, 2026-09-12).** The VUORO-CP companion set in sprint 545 was bulk-closed
on 2026-08-22 at 15:07Z. The daemons, types and ledgers those items describe do not exist in
any package. `done` then meant "no longer being worked on"; sprintctl had no `rejected`
outcome (#2240, absorbed by S3).

**Re-verified 2026-09-19.** The search ran over the `/projects/dev` source tree: `*.py`,
`*.go`, `*.rs`, `*.ts` and `*.toml` files, excluding `.git`, `node_modules`, `.venv`,
`_artifacts`, `docs/` and `tests/`. Source files matching each name:

| Name | Source files |
|---|---|
| `runnerd` | 0 |
| `PolicyInput` | 0 |
| `CredentialCatalog` | 0 |
| `GrantLedger` | 0 |

**Items.** These are the 26 items in vuoro sprint 545 that are `done`, were last updated in the
2026-08-22T15:07Z window, and are legacy with no resolution. The list was read through served
`work.read.items` on 2026-09-19. The reject script aborts unless the live list matches this one
exactly.

| Item | Last updated | Title |
|---|---|---|
| 2163 | 2026-08-22T15:07:30.961871Z | [VUORO-CP] CTL-003 — Implement host, session, incarnation, run, and work-path APIs |
| 2165 | 2026-08-22T15:07:32.257441Z | [VUORO-CP] CTL-005 — Implement durable event ingest and watermarks |
| 2168 | 2026-08-22T15:07:33.614388Z | [VUORO-CP] RUN-001 — Create vuoro-runnerd service shell |
| 2169 | 2026-08-22T15:07:34.995206Z | [VUORO-CP] RUN-002 — Implement runner identity and registration |
| 2170 | 2026-08-22T15:07:36.642761Z | [VUORO-CP] RUN-003 — Implement pull-based claim and lease renewal |
| 2171 | 2026-08-22T15:07:38.065336Z | [VUORO-CP] RUN-004 — Implement runner outbox and disconnected mode |
| 2172 | 2026-08-22T15:07:39.354720Z | [VUORO-CP] RUN-005 — Implement workspace/worktree adapter |
| 2173 | 2026-08-22T15:07:40.652237Z | [VUORO-CP] RUN-006 — Implement adopt, attach, detach, and handoff UX |
| 2174 | 2026-08-22T15:07:41.833734Z | [VUORO-CP] RUN-007 — Package runner for workstation and devbox |
| 2175 | 2026-08-22T15:07:43.251058Z | [VUORO-CP] ACP-001 — Define Vuoro Runner/v1 harness contract |
| 2176 | 2026-08-22T15:07:44.581041Z | [VUORO-CP] ACP-002 — Implement first local ACP adapter |
| 2177 | 2026-08-22T15:07:46.045911Z | [VUORO-CP] ACP-003 — Implement durable ACP update sink |
| 2178 | 2026-08-22T15:07:47.580020Z | [VUORO-CP] ACP-004 — Implement resume, cancellation, and uncertain-turn rules |
| 2179 | 2026-08-22T15:07:49.151981Z | [VUORO-CP] ACP-005 — Cut over one real runner profile |
| 2180 | 2026-08-22T15:07:50.545925Z | [VUORO-CP] ACP-006 — Prove second harness and retire PTY fallback |
| 2182 | 2026-08-22T15:07:51.980857Z | [VUORO-CP] CRED-001 — Define CredentialCatalog/v1 |
| 2183 | 2026-08-22T15:07:53.544919Z | [VUORO-CP] CRED-002 — Define credential ticket and actor binding |
| 2185 | 2026-08-22T15:07:54.869676Z | [VUORO-CP] CRED-004 — Integrate runner credential retrieval and injection |
| 2187 | 2026-08-22T15:07:56.181193Z | [VUORO-CP] CRED-006 — Implement Vuoro grant ledger above broker delivery |
| 2188 | 2026-08-22T15:07:57.859972Z | [VUORO-CP] CRED-007 — Implement payload-bound EffectDescriptor/v1 |
| 2189 | 2026-08-22T15:07:59.177462Z | [VUORO-CP] CRED-008 — Correlate credential, grant, policy, and evidence audit |
| 2191 | 2026-08-22T15:08:00.611230Z | [VUORO-CP] POL-001 — Define PolicyInput/v1 and PolicyDecision/v1 |
| 2197 | 2026-08-22T15:08:01.936685Z | [VUORO-CP] AUT-001 — Implement work_path domain and lineage |
| 2201 | 2026-08-22T15:08:03.374462Z | [VUORO-CP] AUT-005 — Implement portable handoff and successor sessions |
| 2204 | 2026-08-22T15:08:04.675776Z | [VUORO-CP] OPS-001 — Implement health, metrics, and operator status |
| 2206 | 2026-08-22T15:08:05.977344Z | [VUORO-CP] OPS-003 — Implement version report card and compatibility gates |
