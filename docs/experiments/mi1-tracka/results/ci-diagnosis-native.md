# MI-1 Track A: ci-diagnosis (native path) — agent proposal

Status: proposal for a separate reviewer. Not accepted; no rubric applied. Partial where noted.

## Frozen inputs
- Ledger: `docs/experiments/mi1-tracka/cases.json` (case `ci-diagnosis`, run 36913128176, job 110540455279, source revision `343bb1bd10e575b90eb36a8cb7bbb0a9d599bbe1`).
- Log `docs/experiments/mi1-tracka/inputs/ci-failure.log`: SHA256 `edade4ac4e079c4f2eb69bac650bf0af0f34f96efd3c65accc965affe82926c6`, **matches** the ledger (checked with sha256sum in the first turn of this session, before Bash was restricted).
- Revision `343bb1b…` exists locally (checked earlier with `git cat-file -t`: `commit`).
- Source read with `git show 343bb1b…:<path>`: `scripts/check_protected_paths.py`, `.github/workflows/protected-paths.yml`, `agentops.dispatch.json`.

## Diagnosis
The job `protected-paths` failed deliberately; this is the gate working, not a broken build.

Log evidence (`ci-failure.log`):
- Checkout was the PR #301 merge ref `346dc58` (merge of `343bb1b` into base `582e8ef`).
- Command: `scripts/check_protected_paths.py --base origin/main --head 343bb1b… --title "$PR_TITLE"`.
- PR title: `fix(dispatch): isolate run workspaces and enforce native publication`.
- Output: `protected: .claude/workflows/vuoro-dispatch-build.js`, "modifies 1 protected path(s) and does not declare itself a hand-pass", exit code 1.

Source evidence at `343bb1b`:
- `agentops.dispatch.json` `hybrid.protected_paths` contains `.claude/**`, so the changed file is protected via `_matches_any` (`/**` prefix rule).
- `check_protected_paths.py` `main()`: with hits, it returns 0 only if (a) the title starts with `[hybrid]` AND the sole hit is `agentops.dispatch.json` AND the change is purely additive under `hybrid.commands`, or (b) the title (case-insensitive) starts with `hand-pass:`. Neither held: the hit was a `.claude/` file and the title had no marker. Hence exit 1.
- The workflow `.github/workflows/protected-paths.yml` triggers on `pull_request` types `opened, synchronize, reopened, edited`, so editing the title re-runs the check.

## Minimal legitimate remediation
If the edit to `.claude/workflows/vuoro-dispatch-build.js` is intended and owner-reviewed, the minimal fix is to edit the PR title to begin with `hand-pass:` (e.g. `hand-pass: fix(dispatch): isolate run workspaces and enforce native publication`). This is the declared mechanism ("Being forced to say so is the feature"), and the `edited` trigger re-evaluates it. It is a declaration of a human hand-pass, not a bypass, and should only be used if a human reviewer actually accepts the protected-path change. If the change is not intended, remove it from the PR. Do not edit the workflow, the checker or the protected list, and do not skip the check — those are themselves protected paths.

## Historical vs current policy
- Historical (at `343bb1b`): as above.
- Current worktree (branch `docs/mi1-tracka-native-ci-diagnosis`): `agentops.dispatch.json` lines 163–171 (read with Read) list the same seven `protected_paths`, and `scripts/check_protected_paths.py` and `protected-paths.yml` still reference the `hand-pass:` marker (Grep). I did **not** diff the current files against `343bb1b` (git diff was outside the allowlist), so "unchanged" is only supported for the manifest list and marker, not for the whole script.

## Remaining unknowns
- The full set of files changed in PR #301 was not examined (no `git diff`/GitHub API access); the log reports exactly one protected hit, which I take from the log only.
- Whether PR #301 was subsequently retitled, merged, or how it was resolved was not examined (no PR records read).
- Whether the `.claude/` edit was intended or owner-approved is unknown.
- I did not run `check_protected_paths.py` against the revision; the reasoning above is from reading the code and log.
- No usage, cost, wall time or operator time is recorded here; these are unmeasured, not zero.
