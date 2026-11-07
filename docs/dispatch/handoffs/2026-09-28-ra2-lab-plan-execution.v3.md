# Handoff 2026-09-28-ra2-lab-plan-execution.v3

<!-- Rendered from the canonical JSON beside this file. Do not hand-edit:
     `agentops handoff validate` and `ack` read the JSON, never this. -->

**Objective.** Execute the operator-approved planner plan for the Bindery RA2 program: land the channel startup-crash retry, the agent seat's build path (place_building by type, own-production events, build_order routine) proven in a live stage-2 lab run, the pre-registered SeenAttackForceRatio experiment and the pre-registered short-rationale LLM shadow rerun, then the oracle Allied divergence study.

**Next action.** gh pr view 19 -R bayleafwalker/bindery-ra2-adapter --json state,headRefOid,mergeStateStatus && gh pr view 18 -R bayleafwalker/bindery-ra2-adapter --json state,headRefOid && ls /projects/dev/_wt/sim-prereg/docs/results/2026-09-29-seen-ratio/ /projects/dev/_wt/llm-prereg/docs/results/2026-09-29-llm-shadow-short-rationale/ ; then work the unresolved list in order.

## Predecessor

- harness: claude-code
- session: 78afae49-36a2-422b-8478-1c13363193c6
- model: claude-opus-5-5
- context used: 65.0%
- transcript: unknown
- origin: `workstation:/projects/dev/agentops/docs/dispatch/handoffs/2026-09-28-ra2-lab-plan-execution.v3.json` (authoritative copy; an ack from another host goes through it)

Read-only after transfer: once a successor acks, the predecessor makes no
edits and takes no external actions. It stays consultable.

## Constraints

- Operator approved deployment, mutations, push and merge to main, the planner's recommendations, and the WER LocalDumps key on both guests; merge only reviewed (independent reviewer agent), CI-green PRs; gh pr merge --merge --match-head-commit <sha>.
- Never force-push (this session broke that once on #13's branch with --force-with-lease; use follow-up commits). Never git stash (shared stack).
- bindery-ra2-adapter, ra2yrcpp, ra2yrproto: GitHub bayleafwalker/* canonical; always pass -R bayleafwalker/<repo> to gh (forks default to shmocz upstream).
- Never touch /projects/dev/bindery-ra2-adapter's working tree; worktrees under /projects/dev/_wt/ only.
- dotnet only via `nix shell nixpkgs#dotnet-sdk_8 -c dotnet ...` with the sandbox disabled; TreatWarningsAsErrors; every fix a test seen to FAIL then PASS; never weaken tests; quote raw dotnet test totals (Adapter and Bot, Release) in commits/PRs.
- Lab guests only via deploy/ra2-lab (ra2-vm-exec/push/pull) and the on-demand task \Bindery\BinderyLabRun; no other tasks/services/Run keys/autologon; nothing from the lab published off the host; tokens never printed.
- Experiments: pre-registration committed and pushed before any run; one run, no retuning; no tuning on held-out data; bulk LLM work only on the local endpoint http://127.0.0.1:8020/v1 model worker-fast.
- Fork DLL must be built with upstream's docker MinGW toolchain (shmocz/ra2yrcpp image built locally, not pushed); never the nix GCC15/mcfgthread build (quits on frame 0).

## Decisions

- **Stage 1 unattended: the two AI houses are allied (SpawnAiParticipant.Team -> [MultiN_Alliances]); adapter #7** — Unallied AI fought each other for 40 min and never approached idle player-a (decoded capture); allied, player-a is defeated and the match ends itself (runs 20260928-104926/114735/121424-s1).
- **Stage 2 works: ObjectTypeClass.id (ra2yrproto#2 f777d59, ra2yrcpp#4 7ac3641) and orders resolved on the seat's client by stable unique_id (adapter #10)** — Display names vs rules ids blocked the MCV routine; object addresses differ between clients (0x18fb8700 vs 0x18d87758, same uid 1070755). Seat deployed MCV in runs 120014, 124923 and the 6-run series.
- **Startup crash is inside DDRAW.dll (DDrawCompat 0.5.4) at offset 0x1C104 on both clients** — Located via the same-boot 32-bit module list of a live gamemd (SysWOW64 PowerShell, (Get-Process gamemd).Modules); faulting insn is a prologue push in a helper with 1158 callers => deep recursion. ~2/20 fork-DLL launches, 0/~18 stock. DDrawCompat.ini sets CpuAffinity=1.
- **Planner plan adopted (operator pre-approved): Q4 retry once in ChannelRunner, Q5 place_building by type on the seat's client, Q6 own-production events + BuildOrderRoutineController + spiral placement, Q1 pre-registered Seen 0.8 vs 1.0 decided on training cells, Q2 traced divergence after Q1, Q3 one short-rationale rerun then close the line if it fails** — Planner report in this session; DDrawCompat version/ini left unchanged because it would change the golden appliance.
- **Oracle gap explained, ratio not changed (adapter #16)** — Oracle always uses SeenAttackForceRatio 0.8 on exact enemy value; 40 seeds: selector 356 vs oracle 337/480, paired Allied 46 vs 1; changing it from held-out data would be held-out tuning.
- **LLM shadow pass (pre-registered) failed only N3 (0.119); Parameters tier stays** — Recorded in adapter #11; rerun under a new pre-registration is item Q3.

## Rejected

- **Changing the AI handicap to fix stage 1** — SpawnMatchPlan records 2026-08-25 measurement: 2 is aggressive, 0 passive; the cause was the missing alliance.
- **nix GCC 15 + mcfgthread cross-build of the fork DLL** — Game quits on frame 0 with nothing recorded; upstream docker toolchain build of the same commit plays full matches.
- **Treating Syringe exit code 3 as an abort** — 3 is the normal QuickExit code; a crash shows an NTSTATUS 0xC....... exit (now notable, #12).
- **ra2-vm-push through one virsh stdin session for all files** — 8 s vs ~1 s per 5 MB; stdin path is opt-in --secret for tokens/settings only (#17).
- **qemu-img snapshot before the WER registry change** — Unsafe on a disk in use by the running guest; the change is a single reversible key (revert: ra2-vm-exec <dom> 'Remove-Item -Recurse "HKLM:\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps"').
- **Resolving the crash offset as 0xC104 assuming 64K-aligned bases** — Wrong: the true module offset is 0x1C104 (base 0x72EE0000); use the same-boot module list.
- **Upgrading DDrawCompat or editing DDrawCompat.ini now** — Changes the golden appliance and breaks comparability; planner defers any fix to a fork-side A/B after a crash is captured with log and dump.

## Repo state

Digest definition: v4 (see the handoffs README).

| path | branch | head | dirty | unpushed | diff_sha256 |
|---|---|---|---|---|---|
| `/projects/dev/_wt/ra2-channel-live` | feat/lab-keep-ddrawcompat-log | `89e6649b46cb` | no | 0 | `e3b0c44298fc1c14…` |
| `/projects/dev/_wt/channel-retry` | plan/channel-retry | `33b847b10cac` | no | 0 | `e3b0c44298fc1c14…` |
| `/projects/dev/_wt/seat-build` | plan/seat-build | `5410068fd900` | no | 0 | `e3b0c44298fc1c14…` |
| `/projects/dev/_wt/ra2yrcpp-docker` | feat/object-type-id | `c629c5157a47` | no | 0 | `e3b0c44298fc1c14…` |

**Running:**

- Seen-ratio arena runs: /projects/dev/_wt/sim-prereg/docs/results/2026-09-29-seen-ratio/run.sh (6 parallel runs + analysis, started 17:31, ~3 h under load; branch plan/sim-prereg, pre-registration b343615 pushed before the run; the worktree gets untracked results).
- LLM short-rationale rerun: /projects/dev/_wt/llm-prereg/docs/results/2026-09-29-llm-shadow-short-rationale/run.sh (started ~17:50, 7/24 matches at 18:10; branch plan/llm-prereg a60af92; worktree gets untracked results).
- Lab VMs bindery-ra2-client-{a,b} running under qemu:///session, restored to stock ra2yrcpp; WER LocalDumps set for gamemd.exe on both (revert: ra2-vm-exec <dom> 'Remove-Item -Recurse "HKLM:\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps"').
- Lab payload in RA2_LAB_HOME=/projects/bindery-vm/lab-kit-2026-09-27/lab built at adapter 18f0aa5 with the docker fork DLL; RA2_LAB_TUNNEL=/mnt/arch-home/bayleaf/Bindery/tunnel/run-private-tunnel.sh.

## Unresolved

- PR #18 (feat/lab-keep-ddrawcompat-log, worktree /projects/dev/_wt/ra2-channel-live): review found nothing blocking; before merge fix the README so it states the WER LocalDumps key is a manual guest step and gives the exact command (New-Item/New-ItemProperty under HKLM:\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps\gamemd.exe: DumpFolder C:\Bindery\dumps, DumpType 2, DumpCount 5); then CI, merge.
- PR #19 (plan/channel-retry, worktree /projects/dev/_wt/channel-retry, head 33b847b): review findings fixed in 33b847b (per-attempt evidence folders, drain before retry, report counts matches); needs a short re-review of 33b847b + CI, then merge.
- Branch plan/seat-build (worktree /projects/dev/_wt/seat-build; dbdcf9d place_building by type, 2120d90 own-production events, 5410068 build_order routine; pushed, no PR): open PR, independent review, CI, merge; then rebuild the payload (deploy/ra2-lab/build-payload.sh --fork-dir /projects/dev/_wt/ra2yrcpp-docker/cbuild/mingw-w64-i686-Release/pkg/bin) and prove it live: lab-run.sh --stage 2 with the agent seat routine build_order (render() in deploy/ra2-lab/lab-run.sh hard-codes routine deploy_mcv: make it selectable) — acceptance: trace shows produce -> completed -> place and a created own building for GAPOWR, GAPILE, GAREFN with 0 refused-by-house errors. Worker's noted gaps: retry timer only fires on the next observation; Ra2Normalizer lacks the two production events; docs/channel-settings.example.json still deploy_mcv; PlayerView never drops destroyed own buildings.
- LLM short-rationale rerun running (see running): when done, record the Outcome in docs/experiments/2026-09-29-llm-shadow-short-rationale-preregistration.md by the fixed criteria (any failure closes the Full-vocabulary line for worker-fast), compress decision logs like docs/results/2026-09-28-llm-shadow-t3 (tar.xz + sha256, verify metrics reproduce), commit on plan/llm-prereg (a60af92 already has the prompt change + pre-registration), PR, review, merge.
- Seen-ratio experiment running (see running): when done read docs/results/2026-09-29-seen-ratio/{T,H1,H2}-analysis.txt, apply C1-C4 exactly as pre-registered in docs/experiments/2026-09-29-seen-attack-ratio-preregistration.md (C3: set default 1.0 in src/Bindery.Ra2.Bot/Operations/OperationalOptions.cs and run both test suites only if C1, C2, C4 pass), write the Outcome, compress results.json files, PR, review, merge.
- Then planner item Q2: commit docs/experiments/2026-09-29-oracle-allied-divergence-preregistration.md and docs/experiments/oracle_divergence.py BEFORE reading traces; run --arms selector,selector-oracle --maps heldout --opponents ai-horde:easy,ai-horde:medium,ai-horde:hard,ai-armor:easy,ai-armor:medium,ai-armor:hard --seeds 40 --benchmark contested --knob SeenAttackForceRatio=1.0 --trace <dir>; gate: stop if Allied paired split not significant at HEAD; primary cause = >=50% of selector-only pairs and >=2x its rate among oracle-only pairs.
- Startup crash (DDrawCompat, ~10% of fork-DLL launches): after #18 is merged keep an eye on ddrawcompat-client-*.log and dumps-client-*.txt in crashed runs; planner's follow-up is a pre-registered fork A/B deferring ra2yrcpp's service-thread start to the first game frame (>=60 launches per arm).
- sprintctl #2110: not found in 9 scopes; untraceable - drop unless the operator names its repo.

## Evidence

- session: `78afae49-36a2-422b-8478-1c13363193c6`
- artifact: `/projects/dev/agentops/docs/dispatch/handoffs/2026-09-27-ra2-channel-live-lab.v2.json`
- artifact: `/projects/dev/_wt/ra2-channel-live/deploy/ra2-lab/README.md`
- artifact: `/projects/dev/_wt/sim-prereg/docs/experiments/2026-09-29-seen-attack-ratio-preregistration.md`
- artifact: `/projects/dev/_wt/llm-prereg/docs/experiments/2026-09-29-llm-shadow-short-rationale-preregistration.md`
- artifact: `/projects/bindery-vm/lab-kit-2026-09-27/lab/runs/20260928-171841-s2/lab-run.log`
- artifact: `/home/bayleaf/.claude/jobs/78afae49/tmp/series/summary.txt`

## sprintctl bundle

- none (sprintctl unavailable or produced no bundle)

## Successor

- session: 88d19952-9d8b-42e7-822a-e07f2c97795e
- acknowledged: 2026-09-28T15:11:52Z
