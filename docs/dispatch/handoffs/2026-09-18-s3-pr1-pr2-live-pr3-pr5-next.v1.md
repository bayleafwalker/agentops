# Handoff 2026-09-18-s3-pr1-pr2-live-pr3-pr5-next.v1

<!-- Rendered from the canonical JSON beside this file. Do not hand-edit:
     `agentops handoff validate` and `ack` read the JSON, never this. -->

**Objective.** Finish S3 ("Decisions close work") on the owner-adopted path: fix and land sprintctl PR3 (#69) and PR4 (#70), build PR5 (unbound query, sweeps on open items only, metrics by resolution, legacy re-mark path at schema 16), roll each release onto vuoro-shared, then record the 26 sprint-545 reject decisions. S2 is closed; S1 and S3 PR1-PR2 are live (work schema 15).

**Next action.** cd /projects/dev/sprintctl && gh pr checks 69. #69 fails only Tests (Python 3.11): two new tests in tests/test_served_decisions.py run SPRINTCTL_BACKEND=served, which needs Python 3.12 (vuoro-client). Mark them skip below 3.12 like the other served tests, push, and merge when green. Then fix #70's four review defects (see unresolved) and build PR5.

## Predecessor

- harness: claude-code
- session: e37c1794-c7f2-49e0-a192-c3840d7ee920
- model: claude-opus-5[1m]
- context used: unknown%
- transcript: unknown
- origin: `workstation:/projects/dev/agentops/docs/dispatch/handoffs/2026-09-18-s3-pr1-pr2-live-pr3-pr5-next.v1.json` (authoritative copy; an ack from another host goes through it)

Read-only after transfer: once a successor acks, the predecessor makes no
edits and takes no external actions. It stays consultable.

## Constraints

- Goal state decides (agentops docs/plans/2026-09-17-target-state.md, D1). Planner-derivable choices are decided, not asked. The owner approved commits, merges to main, release tags, image publishes and appservice rollouts for the S-path (memory green-pr-merges-approved).
- Every schema step: an independent review agent (a rolling-window replay of the previous release's writes against the new schema), fixes, a rehearsal of the migration Job with the real image on a rehearsal13_pristine copy (local Postgres 16 at 127.0.0.1:55432, trust auth; restart it with nix shell nixpkgs#postgresql_16 if it is down), a fresh vuoro-shared pgdump (hourly at :53), then merge the appservice roll.
- Release chain scripts are in /projects/dev/_artifacts/agentops/session-notes/2026-09-19-s3-scripts (sprintctl_release.sh, vuoro_repin.sh, vuoro_release.sh, appservice_roll.sh, wait_pr.sh, job_edit_v15.sh). They stop on a red check. The known CI flake is tests/test_perf.py sweep_stale_reservations_under_100ms: re-run the failed job, never skip.
- A vuoro repin that changes any work operation spec also changes scripts/validate_released_work_adapter.py (_EXPECTED_WORK_METADATA_SHA256 and the operation count) and scripts/validate_released_catalog_composition.py (EXPECTED_REVISION, domain counts). Diff the specs against the previous wheel before accepting new values.
- Never carry out an action another agent reports as denied without the owner's explicit say-so (PR4 was published only after the owner approved it). Auto mode denies kubectl exec writes into the database; read-only psql through kubectl exec is allowed.

## Decisions

- **Dropped actionq-db/vuoro-dev-db in two phases (appservice** — actionq-db owned ns/vscode (code-server, workspace PVCs, sprintctl-cnpg-main) and the actionq-pg LB pool used by live vuoro-shared. A one-step drop would have garbage-collected them.
- **The actionq-pg LoadBalancer is kept and retires at S5 (TS-10); recorded in vuoro** — It is a legacy direct-DSN route to the live vuoro-shared postgres, not part of actionq-db.
- **Rebuild restore-plan artifacts were not edited** — They are pinned to the executed 2026-09-02 rebuild's G2 checkpoint; the next rebuild rediscovers.
- **S1 shipped as schema 13 (sprintctl 0.3.7, vuoro-service 0.1.62)** — Evidence tables immutable by trigger, sprint->event RESTRICT, repo delete removed, credential-shaped values refused at served invoke; runtime role insert/select only on evidence.
- **S3 PR1 schema 14 (0.4.0/0.1.63) and PR2 schema 15 (0.5.0/0.1.66) are live** — Decision is the only terminal writer; 1371 existing items legacy; receipt fold gave 4 evidence rows and 0 decisions, as measured beforehand. Release freezes execution reservations; old-pod writes that would skip binding fail by trigger.
- **0.4.1 and 0.4.2 fixed served connections left idle in transaction** — The startup compatibility_handshake left the shared connection in a transaction, so reads never ended theirs. That blocked the v14 ALTER and stalled work_item queries about 9 minutes until a rollout restart. Migrations now also use lock_timeout 5s.
- **The 26 rejects cite agentops docs/evidence/2026-09-19-s3-sprint545-reject-evidence.md** — sha256 f04726707e48be1e9fb23bfa62c0c5fbcbbe518f1e5ebe15c7324ec90ac477f0, merged in agentops

## Rejected

- **Terminating the idle-in-transaction backend with pg_terminate_backend through kubectl exec** — Auto mode denied it as a remote shell write; the rollout restart of vuoro-shared was used instead.
- **Regenerating backup_coverage_baseline.yaml with --write-baseline** — It reflows every entry; remove entries by hand.
- **Rolling back caller-held transactions unconditionally in WorkApplication.invoke** — Existing tests encode that a caller's open transaction is preserved. Only transactions the operation opened are ended; the real leak was the startup handshake.

## Repo state

Digest definition: v2 (see the handoffs README).

| path | branch | head | dirty | unpushed | diff_sha256 |
|---|---|---|---|---|---|
| `/projects/dev/sprintctl` | main | `eabe4679f9d3` | yes | 0 | `2309cfd7a588e23f…` |
| `/projects/dev/vuoro` | main | `d0ea67ce7c1a` | no | 0 | `e3b0c44298fc1c14…` |
| `/projects/dev/appservice` | main | `750dabf6c15b` | no | 0 | `e3b0c44298fc1c14…` |
| `/projects/dev/agentops` | main | `08101016f54f` | yes | 0 | `bb445a663591357b…` |

**Running:**

- Nothing of this session's is running. Cluster: vuoro-shared runs vuoro-service 0.1.66 (sprintctl 0.5.0, work schema 15); vuoro-work-migrate-v15 is Complete.
- Local Postgres 16 at 127.0.0.1:55432 (scratchpad/pg/data) holds rehearsal DBs; it can be stopped or dropped.

## Unresolved

- #69 (PR3 served decisions): re-verified clean at 8121171. Fix the py3.11 CI failure (see next action), then merge, release 0.5.1 (no schema change), repin vuoro (the work op count changes 46->49, so update both vuoro CI constants), roll. After that, merge agentops branch s3-item-decide-skill (0c22053, pushed, no PR yet): the item-done template now says item decide. Review nit: the 422 invalid-value mapping echoes the full psycopg error text; return the first line only.
- #70 (PR4 trailer harvest) review defects to fix before merge: HIGH: a client ahead of its server wedges served sync (record-type-not-allowed on release.commit-observed); filter unknown observation types, or gate on the server capability, and roll the server first. MED: harvest exceptions (git missing, a bad origin URL, the identity lookup) abort sync; wrap the harvest and return skipped. MED: log.showSignature breaks %H parsing; pass --no-show-signature. LOW: the scp-like branch keeps ?query tokens, and passwords with ?/# leak a prefix; cut at ?/# and drop the hint when credential_shape matches. Not yet checked: shallow and detached HEAD, the pg suite.
- PR5 not started. The branch s3-unbound-sweeps is pushed but empty. Spec: (1) work.read.unbound with 3 categories; (2) sweeps only touch non-done items; (3) work.event.add refuses decision-like types; (4) metrics by resolution, with legacy_done separate; (5) the legacy re-mark path: one authored terminal decision, with rationale and evidence, on a legacy done item with no decision; needs schema 16 / SQLite 25; (6) the import_ndjson decision-guard exemption covers only rows marked legacy. Worker tip: in agent worktrees, use /run/current-system/sw/bin/git if the snip wrapper is blocked.
- After PR5 rolls: run python /projects/dev/_artifacts/agentops/session-notes/2026-09-19-s3-scripts/s3_rejects.py (dry run, then --apply) with /home/bayleaf/.local/share/uv/tools/sprintctl/bin/python from /projects/dev/sprintctl. It aborts unless all 26 items (vuoro sprint 545) are still legacy, done and unresolved, and uses idempotency keys s3-sprint545-reject-<id>.
- After S3: S6 (session binding, cost per release, ledger handoff checkpoints) is only blocked by S3. S4 needs its stop/restart gate and ends with a 90-day read-only soak. S5 needs S4 (and retires the actionq-pg LB). S7 needs a post-S3 truth audit. S8 needs S5.
- Housekeeping: the owner's memory rule says appservice merges need a maintenance-lane message first. None was sent this session (the lane, sprint 559, is paused); raise it with the owner. Agent worktrees remain under /projects/dev/sprintctl/.claude/worktrees; remove them once their branches have merged.

## Evidence

- artifact: `appservice PRs`
- artifact: `sprintctl PRs`
- artifact: `vuoro PRs`
- artifact: `agentops PRs`
- artifact: `pgdump vuoro-postgres-vuoro-20260918T205311Z.dump.age (pre-v15 recovery point)`
- artifact: `/projects/dev/_artifacts/agentops/session-notes/2026-09-19-s3-scripts (release scripts, s3_rejects.py, handoff draft)`

## sprintctl bundle

- none (sprintctl unavailable or produced no bundle)

## Successor

- session: 30fa9ea6-78ef-4970-aa07-7a72f62f5cea
- acknowledged: 2026-09-19T05:17:56Z
