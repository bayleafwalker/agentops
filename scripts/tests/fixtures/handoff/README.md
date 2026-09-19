# Fixtures for agentops#2101 (handoff tracker precedence)

Three static handoffs, one per acceptance clause, meant to be run with
`python scripts/handoff.py validate <fixture> --no-tree-check` from the
worktree these were committed in. `--no-tree-check` skips only the
`diff_sha256` comparison (its existing, unchanged meaning); it does not skip
the evidence-ref or tracker-watermark checks this item adds.

These three are pinned to this checkout's own path (`state.repos[0].path`) so
`repo path does not exist` / `head does not resolve` never fire on a path that
happens not to exist elsewhere -- a real repo, not a stand-in, is required for
those two checks regardless of `--no-tree-check`. The pytest suite
(`scripts/tests/test_handoff.py`) is what actually proves the behaviour
portably, building disposable repos under `tmp_path`; these three are for the
`handoff validate <fixture>` command line, not for CI.

- `no-refs.json` -- no item ids, no evidence: validates unchanged.
  ```
  python scripts/handoff.py validate scripts/tests/fixtures/handoff/no-refs.json --no-tree-check
  ```
- `missing-evidence.json` -- one `evidence[]` ref naming a file that does not
  exist: refused.
  ```
  python scripts/handoff.py validate scripts/tests/fixtures/handoff/missing-evidence.json --no-tree-check
  ```
- `closed-item.json` -- `state.tracker_watermark` names item `9999` as open at
  `status_revision: 1`; `fake-sprintctl/sprintctl` answers `item show --id
  9999` as `done` at `status_revision: 7`, so validating with it on `PATH`
  refuses, naming the item and both revisions. Without a `sprintctl` on
  `PATH` at all, the same command validates clean -- absent sprintctl skips
  the re-check, it does not fail it.
  ```
  PATH="$PWD/scripts/tests/fixtures/handoff/fake-sprintctl:$PATH" \
    python scripts/handoff.py validate scripts/tests/fixtures/handoff/closed-item.json --no-tree-check
  ```
