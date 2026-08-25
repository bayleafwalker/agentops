# Handover: Vuoro served-substrate completion dispatch

- Cut: `2026-07-22T13:53:06+03:00`
- Requested boundary: stop cleanly before sprintctl #1193's disposable-PostgreSQL gate
- Secret handling: no claim token or database credential is recorded here
- Current claim state: sprintctl sprint #407 and item #1193 both have zero active claims

This document is the restart packet for a fresh-context session. The current
session intentionally stopped at the boundary below. Do not infer completion
from the clean branch: #1193 and #1194 still require their accountable build
and independent-verification gates before publication.

## Outcome already published

The prerequisite batch was rebuilt from clean sprintctl remote ancestry,
independently verified, published, and closed without publishing the unrelated
local sprintctl commits `abcd38c` or `ca1830c`.

Authoritative sprintctl remote `main` is:

```text
5ddc55dbf80d4b79c03f3c89700ccf378f8adeca
```

Published commits after the former remote base `142d5cc`:

```text
03d3ec0  fix(db): retry busy WAL initialization                 #1210
db08cc6  test: make gate independent of disk and clock          #1209
ff35ace  docs(protocol): define local SQLite initialization     #1210 contract
c22bef2  fix(outbox): retry busy WAL initialization             #1208
a778462  test(outbox): make migration evidence exact            #1208
aa747d9  test(protocol): record prerequisite WAL verification
5ddc55d  test(outbox): trace WAL initialization anchors
```

Closed live items:

- #1210 — primary SQLite WAL initialization retry
- #1209 — filesystem/clock-independent mandatory test harness
- #1208 — local outbox WAL initialization retry

The final independent gates established:

- #1210: 32 eight-opener histories plus all retry/fail-fast/cleanup cases.
- #1209: the five repaired cases passed five consecutive runs; both affected
  modules passed.
- #1208: 32 concurrent legacy histories, 12 retry/classification/cleanup
  selectors, and 41 authority/durability outbox tests.
- Full published-state suite: `1016 passed, 85 skipped, 0 failed`; every skip
  was a PostgreSQL integration test with intentionally unset
  `SPRINTCTL_TEST_PG_URL`.
- The last evidence-only correction added the actual WAL retry symbols
  `_is_busy_or_locked`, `open_outbox`, and `_initialize_schema_after_wal` to
  the #1208 verification context. It was independently confirmed before push.

No claim from these items remains active, and their private proof files were
retired after close.

## Exact current #1193/#1194 build state

Use this worktree; do not rebuild from canonical local `main`:

```text
worktree: /projects/dev/_worktrees/sprintctl-1193-clean-20260722
branch:   dispatch/sprintctl-1193-clean-20260722
base:     5ddc55dbf80d4b79c03f3c89700ccf378f8adeca
head:     855ba466706e59009006bd2bbc8b0d712d839cec
status:   clean, unpushed, no active claim
```

The clean five-commit stack is:

```text
377a750d7b6dba3f64a077415e50606e33fc668c  #1193 migration compatibility
de72dd0db78ee5d60b2623d9015e9ba3048b6552  #1194 work adapter/catalog
10b1da2ec212d41d8ba0177ab708ef1b6525cc22  #1194 authority identity fix
b4e038e052065d0e8c34a640db6f31b5e8a69ac5  manifest pyproject scope
855ba466706e59009006bd2bbc8b0d712d839cec  #1193 repository-local cursors
```

Important reconstruction facts:

- The supplied long SHA for the manifest commit was invalid. The source object
  actually used was
  `e931501da8e9f6dc25f98165fcb72b8d181ceef2`.
- `4c9d2e1` conflicted in `sprintctl/pg.py`. The resolution retained the
  published origin ref enum and did not import the unrelated local
  `validation-command`/command-ref behavior from `ca1830c`.
- The #1209 hunks in `tests/test_perf.py` and
  `tests/test_projection_reads.py` were omitted as already-published identical
  changes. Their final blobs equal both the intended `1af5fe3` result and
  remote `main`.
- `aabf072`, `abcd38c`, and `ca1830c` are not ancestors.
- #1194 implementation is present in this same branch, but #1194 still needs a
  separate accountable claim/build-evidence context after #1193's build
  context finishes.

Completed on this clean stack:

```text
123 passed, 0 skipped in 82.17s
```

That targeted non-PostgreSQL gate covered bootstrap, projection, sync,
authority, pilot, application, remote-schema, doctor, schema, and performance
contracts with `uv run --extra dev --extra remote`.

Not yet run:

- #1193's focused disposable-PostgreSQL Depth-2 histories.
- The whole PostgreSQL module with cleanup/residue evidence.
- The final remote-extra full suite on this served stack.
- Fresh #1193 result/evidence commit at rebased implementation SHA.
- Separate #1194 build evidence, real Vuoro integration, and fresh verifier.
- Publication or closure of #1193/#1194.

## Next-session sequence

1. Re-read `/projects/dev/AGENTS.md`, sprintctl `AGENTS.md`, the dispatch
   manifest/overlay, and the canonical dispatch-build,
   code-change-verification, verify-state-protocols,
   reconcile-project-contracts, and item-done skills.
2. Confirm the clean worktree above still has HEAD `855ba466`, no changes, and
   remote `main` still descends from/equal `5ddc55d`.
3. From canonical cwd `/projects/dev/sprintctl`, claim live item #1193. Store
   its proof mode `0600` outside the repository and never print token-bearing
   JSON.
4. Recreate a hermetic PostgreSQL 18.4 cluster under a new `mktemp` path. The
   working native binaries were under:

   ```text
   /nix/store/jnln5fgb9zsr408gl8ya1yrxkmfnagcj-postgresql-18.4/bin
   ```

   Use a Unix socket, a disposable database/role with the required test
   comment, and no ambient/shared DSN. The previous cluster at
   `/tmp/sprintctl-1193-clean-pg2` was fast-stopped and removed; it must not be
   reused.
5. Run #1193's focused PostgreSQL migration/concurrency histories and the full
   `tests/test_pg_integration.py` plus `tests/test_work_application_pg.py`
   surface with zero target skips. Prove cleanup/residue across all work
   tables and stop/remove the cluster even on failure.
6. Re-run artifact/manifest/docs/render/lint/compile/build/diff/ancestry gates
   and the exact foreground full suite. If the full run omits PostgreSQL by
   design, preserve the separate no-skip PostgreSQL evidence and inspect every
   remaining skip.
7. Replace the rejected/old #1193 result with a fresh exact-SHA result for the
   rebased final implementation, commit evidence separately, and leave the
   #1193 claim active for a fresh independent verifier.
8. After #1193 build context is stable, acquire a separate #1194 claim. Install
   the released Vuoro packages from:

   ```text
   /projects/dev/vuoro/packages/vuoro-client
   /projects/dev/vuoro/packages/vuoro-service
   ```

   into the isolated sprintctl environment. Run the real generic-client/service
   adapter integration, PostgreSQL application histories, identity/actor
   binding, batching, retry, and full-suite gates. Create an accurate #1194
   result packet if required by the state-protocol workflow.
9. Run fresh independent verification for #1193 and #1194 sequentially. Push
   the repo batch only after both confirm. Then close both with their own
   private claim proofs.
10. Only then take #1195, followed by Vuoro #1204 and #1205 in dependency order.

## Live dependency state

- sprintctl #1193: active, zero claims; blocked only by done #1208.
- sprintctl #1194: active, zero claims; blocked only by done #1208.
- sprintctl #1195: pending; blocked by #1193 and #1194.
- Vuoro #1204: pending. Its text requires the four released owner adapters;
  actionq, kctl, and auditctl are published, while sprintctl work remains the
  outstanding gate.
- Vuoro #1205: pending; blocked by #1204.
- agentops #1191: pending and intentionally not buildable yet. Decision event
  #1299 requires a planning/operator pass to choose the signature scheme,
  ratifier configuration, hook integration point, and transition-detection
  mechanics.

Published owner-adapter evidence relevant to #1204:

| Repository | Authoritative remote `main` | Relevant delivery |
|---|---|---|
| Vuoro | `d0254987e0d584230eeba45efbc7094f5375e93b` | protocol v1 / #1203 |
| actionq | `9327973cff9dd555d95af6bb9a547379fbd8701e` | #1197 commit `a50de53` is an ancestor |
| auditctl | `560397e8cf3e9a44a4f627b353c0dec63b34b92b` | #1202 plus SQLite startup repair |
| kctl | `57d943f4dfc4ab4489cc91ef08c9c164fa425cb2` | #1199/#1200 |
| sprintctl | `5ddc55dbf80d4b79c03f3c89700ccf378f8adeca` | prerequisites only; work adapter unpushed |
| agentops | `b7f3b2cbbac3a4ccc66b109292fdde3a3740ae54` | project/dispatch guidance current remotely |

## Workspace and tool cautions

- Canonical `/projects/dev/sprintctl` is intentionally divergent: local main
  is ahead 10/behind 7 and retains unrelated `abcd38c`, `ca1830c`, the old
  served commits/evidence, and untracked `.claude/settings.local.json`. Do not
  reset, rebase, or push it.
- Canonical `/projects/dev/agentops` is ahead 10/behind 1 with untracked
  `.auditctl/`. Preserve it. This handover file is intentionally left as a
  workspace change rather than publishing the branch's unrelated history.
- Kctl retains pre-existing generated `build/lib/**` dirt and untracked local
  tool state. Preserve it.
- Actionq local main is behind remote by two commits after fetch; remote still
  contains `a50de53` as an ancestor. Preserve its untracked local tool state.
- Several temporary sprintctl worktrees contain rejected verification attempts.
  Do not bulk-prune them during the resumed build. The authoritative worktree
  for the next action is the `/projects/dev/_worktrees/...1193...` path above.
- `/home/agent/.local/bin/sprintctl` is currently an editable v0.2.0 install
  from `/tmp/vuoro-dispatch-sprintctl-prereq-final.GWsutw`, which is clean at
  `5ddc55d`. Use it for live authority calls from canonical cwd
  `/projects/dev/sprintctl`. Do not reinstall the schema-v3 #1193 candidate
  globally while the live shared authority is still schema v1.
- `direnv exec <dir>` loads environment but does not change the process cwd.
  Explicitly set cwd for authority commands.
- Run live sprintctl authority reads sequentially. Concurrent schema-v1 client
  startup reads reproduced PostgreSQL DDL deadlocks.
- `sprintctl handoff` is not read-only: it appends a `handoff-generated` event
  and writes a file. A verifier accidentally invoked it twice; the append-only
  observations remain, while generated files were removed.
- One #1209 claim token was accidentally emitted by an unsafe nested-field
  redaction, immediately revoked, removed, and replaced. No exposed or active
  credential remains.

## Stop-state verification

- #1193 clean worktree: clean at `855ba466`.
- Disposable PostgreSQL: stopped and `/tmp/sprintctl-1193-clean-pg2` removed.
- #1193 claim: released; private proof removed.
- Sprint #407 active claims: zero.
- No #1193/#1194 commit was pushed or item closed.

