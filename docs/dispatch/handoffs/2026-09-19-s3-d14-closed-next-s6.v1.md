# Handoff 2026-09-19-s3-d14-closed-next-s6.v1

<!-- Rendered from the canonical JSON beside this file. Do not hand-edit:
     `agentops handoff validate` and `ack` read the JSON, never this. -->

**Objective.** Start S6 of the agentops target state (session binding records instruction and skill digests; cost per release; ledger handoff checkpoints replace handoff/v1 files), which S3 unblocked, while carrying the dated Object-Lock checks in agentops#2428 and the sprint 559 lane backlog. Supersedes handoffs 2026-09-18-d14-closed-next-d9-d10 and 2026-09-18-s3-pr1-pr2-live-pr3-pr5-next (both tracks closed 2026-09-19).

**Next action.** cd /projects/dev/agentops && export SPRINTCTL_BACKEND=served SPRINTCTL_VUORO_PROFILE=/projects/dev/agentops/environment-record/profiles/workstation-vuoro-shared.json && sprintctl --repo-id agentops --allow-markerless-nonlocal item show --id 2428 ; if it is on/after 2026-09-20 05:00 UTC run its check 1, then read the S6 section of docs/plans/2026-09-17-target-state.md and plan S6

## Predecessor

- harness: claude-code
- session: 30fa9ea6-78ef-4970-aa07-7a72f62f5cea
- model: claude-opus-5[1m]
- context used: unknown%
- transcript: unknown
- origin: `workstation:/projects/dev/agentops/docs/dispatch/handoffs/2026-09-19-s3-d14-closed-next-s6.v1.json` (authoritative copy; an ack from another host goes through it)

Read-only after transfer: once a successor acks, the predecessor makes no
edits and takes no external actions. It stays consultable.

## Constraints

- sprintctl (now 0.6.0 on the workstation) only works as: cd /projects/dev/agentops; export SPRINTCTL_BACKEND=served SPRINTCTL_VUORO_PROFILE=/projects/dev/agentops/environment-record/profiles/workstation-vuoro-shared.json; sprintctl --repo-id agentops --allow-markerless-nonlocal ... Close items with `item decide --kind accept --rationale ...`, not a bare status done.
- Owner-approved on green CI without asking: commits, merges, release tags, image publishes and appservice rollouts for the S-path; appservice merges need a maintenance-lane note (sprintctl event on sprint 559 or the item) before merging.
- Every work schema step: independent review agent (rolling-window replay of the previous release's writes on the new schema), rehearsal of the migration Job with the real image on a copy of rehearsal13_pristine (local PG16 at 127.0.0.1:55432, data dir /tmp/claude-1000/-projects-dev--projects-vuoro-dispatch-ready/e37c1794-c7f2-49e0-a192-c3840d7ee920/scratchpad/pg/data; start with `pg_ctl ... -o "-p 55432 -k ''"` because the socket path is too long), a fresh vuoro-shared pgdump, then ONE appservice PR carrying the migration Job and the image (old pods refuse schema-too-new on restart).
- Release chain scripts: /projects/dev/_artifacts/agentops/session-notes/2026-09-19-s3-scripts (sprintctl_release.sh, vuoro_repin.sh, vuoro_release.sh, appservice_roll.sh with job_edit_vNN.sh hook, wait_pr.sh). After a repin, update vuoro scripts/validate_released_work_adapter.py and validate_released_catalog_composition.py constants; compute them from the released wheels installed --no-deps like CI and diff specs against the previous wheel first. vuoro_release.sh output can be swallowed by pipes: verify PR/tag/digest yourself.
- Do appservice work in a private clone, never by switching branches in the shared /projects/dev/appservice checkout. Network commands need the sandbox disabled. KUBECONFIG=/projects/dev/appservice/clusters/.kube/config.
- Hooks block Secret-value reads and decryption commands. For S3 API work use a one-off Job in namespace forgejo (label app.kubernetes.io/name=cnpg-pgdump-age for egress, secretKeyRef forgejo-cnpg-backup-s3 ACCESS_KEY_ID/SECRET_ACCESS_KEY, amazon/aws-cli, endpoint https://hel1.your-objectstorage.com); never create pods in cnpg-dump-drill (agent-free by design).
- When the auto-mode classifier blocks a harmless edit, give the operator the one-line `!` command and a permission rule in the same reply; the operator considers routing trivial edits through them theatre.
- tests/test_perf.py sweep_stale_reservations_under_100ms fails locally on main too; in CI re-run the failed job, never skip it.

## Decisions

- **S3 complete and live 2026-09-19: sprintctl 0.5.1 (PR3 #69) then 0.6.0 (PR4 #70 trailer harvest + PR5 #72 unbound/legacy re-mark, work schema 16); vuoro-service 0.1.67/0.1.68 (vuoro #92 #93); appservice #1688 #1689; the 26 vuoro sprint-545 rejects recorded (decisions 3-28)** — Owner-adopted S3 plan; independent review GO, rehearsal 15->16 in 0.7s, recovery point vuoro-postgres-vuoro-20260919T063546Z.dump.age; sprint 559 note #3017.
- **PR4 harvest is gated on the server advertising release.commit-observed in work.batch.apply's catalog input schema; a newer client against an older server skips the harvest without advancing its cursor** — The outbox is one contiguous stream; a rejected record would wedge every later record.
- **agentops#2413 (D9/D10) closed accepted** — Operator decision #2907 replaced negative merge tests with CI guards; public-exposure-guard and backup-coverage-guard run in mise run validate. Policy text updated in appservice #1691.
- **CNPG dumps moved to appservice-pgdump-locked (Object Lock COMPLIANCE 14d, versioning, deletion protection, lifecycle NoncurrentVersionExpiration 1d) in appservice #1690; the daily drill gained a lock-check container** — Planner review (#2408 note #2989): a separate Hetzner project/key is theatre while agents hold cluster-admin and dumps are age-encrypted; immutability is what changes outcomes. Deleting a locked version was proven refused.
- **RCLONE_CONFIG=/notfound in dump and drill jobs (appservice #1687)** — Silences the per-call missing-config NOTICE; verified 0 notices live.

## Rejected

- **Separate Hetzner project + dedicated key for the dumps** — No change in any threat scenario except other shared-key workloads deleting; Object Lock covers that and more.
- **Cloud routines (/schedule) for the dated backup checks** — Cloud agents have only a git checkout: no kubeconfig, no Hetzner key, no sprintctl profile. Use sprintctl item #2428 (or a systemd user timer running claude -p, not built).
- **Negative self-merge/promote tests for D10** — Dropped by operator decision #2907 (approval theatre).
- **Filtering unsupported observation types at outbox send time** — Ingest rejects sequence gaps; filtering would wedge sync. Gate at enqueue on the server capability instead.

## Repo state

Digest definition: v2 (see the handoffs README).

| path | branch | head | dirty | unpushed | diff_sha256 |
|---|---|---|---|---|---|
| `/projects/dev/agentops` | main | `08101016f54f` | yes | 0 | `6601dcd6958c859d…` |
| `/projects/dev/sprintctl` | main | `7e86e2335f4f` | no | 0 | `e3b0c44298fc1c14…` |
| `/projects/dev/vuoro` | main | `d779a41b7e5b` | no | 0 | `e3b0c44298fc1c14…` |
| `/projects/dev/appservice` | main | `750dabf6c15b` | no | 0 | `e3b0c44298fc1c14…` |

**Running:**

- Nothing of this session's is running. Local PG16 rehearsal server stopped (data kept). vuoro-shared: vuoro-service 0.1.68, work schema 16.
- Session-only cron in session 30fa9ea6 fires 2026-09-20 08:17 Helsinki for #2428 check 1 if that session is still open.

## Unresolved

- agentops#2428 dated checks: 2026-09-20 drill restore + lock-check PASS; on/after 2026-10-03 remove appservice-storage/backups/pgdump-age/ once the locked bucket holds >=14 days per DB; on/after 2026-10-05 confirm noncurrent versions actually expire (_preflight/ empty) and usage nears ~95 GB.
- S3 follow-ups (reviewer, low): the decision-like event-type block is an app-level denylist (unicode/synonym bypasses; not a resolution hole); raw-SQL revise decision on a done item and settable sprintctl.legacy_import setting are pre-existing; `reserve` still accepts done items; `legacy_remarked` also counts pre-S3 open items later closed by decision (#2413) — label semantics, raise in S6.
- S6 not started: design from agentops docs/plans/2026-09-17-target-state.md (TS-3, TS-11, S6). S4 needs its stop/restart gate and a 90-day read-only soak; S5 needs S4 (retires the actionq-pg LB); S7 needs a post-S3 truth audit; S8 needs S5.
- Lane backlog: #2394 (Langfuse WP5) active; pending #2393 #2395-#2399 #2407 #2414 #2417. Quarterly B2 restore drill ~mid-December; B2 retention and a second dump copy deferred until it passes.
- Another session's worktree /tmp/claude-1000/-projects-dev--projects-vuoro-dispatch-ready/*/scratchpad/sprintctl-pr4 has the deleted branch s3-trailer-harvest checked out (stale, clean); leave it to its owner.
- backup-observability/app/status.html still describes the Barman-era layout (pre-existing, cosmetic).

## Evidence

- sprintctl: `agentops sprint 559 notes #2985-#2990 #3017 #3018; #2413 decision 2; #2408 notes #2986 #2989`
- sprintctl: `agentops#2428 (dated Object-Lock checks)`
- artifact: `sprintctl PRs #69 #70 #72, releases v0.5.1 v0.6.0`
- artifact: `vuoro PRs #92 #93, tags vuoro-service-v0.1.67 v0.1.68`
- artifact: `appservice PRs #1687 #1688 #1689 #1690 #1691`
- artifact: `agentops PR #181 (item-done skill uses item decide)`
- artifact: `appservice docs/backups-cnpg.md (Object Lock bucket section)`
- session: `30fa9ea6-78ef-4970-aa07-7a72f62f5cea`

## sprintctl bundle

- none (sprintctl unavailable or produced no bundle)

## Successor

- session: 6f973773-6764-4c90-be85-542b0eb9553b
- acknowledged: 2026-09-20T19:45:57Z
