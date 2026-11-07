# Handoff 2026-10-01-value-routing-dispatch.v1

<!-- Rendered from the canonical JSON beside this file. Do not hand-edit:
     `agentops handoff validate` and `ack` read the JSON, never this. -->

**Objective.** Keep running the value-routing dispatch workflow (agentops .claude/workflows/vuoro-dispatch-build.js) on real sprint items and fix what each run exposes. The pipeline is route -> refine/oracle (Opus 5.5) -> build (Sonnet 5.5) -> independent verify -> up to 2 repairs -> park (git revert) -> publish verified work (push main, or a PR when main refuses the push or protected paths change; publication is now preflighted and confirmed by scripts/dispatch_publish_check.py) -> close (delivery-checked). The operator is not escalated to by default. Near-term: rebuild and land #2563 (run-owned branches) in MANUAL mode, close it, remove the temporary Edit rule, then work the follow-ups (#2597, #2578, #2579, #2570, #2567-#2569, #2564 note 4099).

**Next action.** Ask the operator to switch to manual mode (shift+tab) for the #2563 build, then dispatch #2563 by name: Workflow({name: 'vuoro-dispatch-build', args: {items: [{repo: 'agentops', item_id: 2563, unit: 'run-owned-branch', description: <restore via reverting reverts 5ae747e and 39519fb or re-applying 297e51f/9269e3c on current main; resolve conflicts with #2562 per the builder's steps in wf_028d9fe0-0df; apply ONLY the oracle repair authorized in note 4110>}], push: true}}). After the build stage the operator may return to auto. Then: independent review of its PR, 'hand-pass:' prefix, merge commit, close dispatch, remove the temporary Edit allow rule.

## Predecessor

- harness: claude-code
- session: 9b66e044-305d-480c-9340-f088ea1da661
- model: claude-opus-5-5
- context used: unknown%
- transcript: unknown
- origin: `workstation:/projects/dev/agentops/docs/dispatch/handoffs/2026-10-01-value-routing-dispatch.v1.json` (authoritative copy; an ack from another host goes through it)

Read-only after transfer: once a successor acks, the predecessor makes no
edits and takes no external actions. It stays consultable.

## Constraints

- Nothing waits on the operator by default. Refine and decide from documented direction and record the decision on the item (note type decision). Raise to the operator only for their own authority (credentials, spending, irreversible production changes) or a real permission denial, with exact steps. Once the operator has approved a batch, carry it through; on a classifier denial say so in one line and retry right after the operator grants it.
- Router advice is advisory. Never drop scope silently: move it to a named follow-up with a 'build: scope moved' or 'refinement: intent moved' note. The verifier checks every move.
- Workflows use claude-sonnet-5-5 and claude-opus-5-5. Haiku 4.5 is clerical only.
- Every PR gets an independent review (a fresh Opus agent, not the builder or verifier) posted on the PR before merge. Land on main through a PR with a merge commit, never squash, so the verified SHAs stay intact for the close stage's delivery check. For protected paths (.claude/**, *.dispatch.json, sprintctl's .github/workflows/ci.yml), the workflow opens the PR; add the 'hand-pass:' title prefix only after the review approves (agentops' protected-paths check reads it; sprintctl has no title gate). If the review requests changes, post it, do not merge, and re-dispatch a fix run.
- Do not close sprint items by hand. They close only through the workflow's verified close stage, which requires the commits to be on origin/main. After a PR merges, dispatch a close-only unit.
- sprintctl 0.10.0 uses the served backend. /projects/dev/agentops/.claude/settings.local.json now sets env SPRINTCTL_BACKEND=served and SPRINTCTL_VUORO_PROFILE=/projects/dev/agentops/environment-record/profiles/workstation-vuoro-shared.json, so plain `sprintctl` works in every agent shell (this fixed the recurring 'verifier could not read the item'). Notes: `sprintctl item note --id N --type update|decision --summary --detail`. Served mode rejects --expected-revision on item status (merged guidance in #2562).
- Run the workflow by NAME from a session rooted in /projects/dev/agentops: Workflow({name: 'vuoro-dispatch-build', args: {...}}) with args as a JSON object. The allow rules Skill(vuoro-dispatch-build) and Workflow(vuoro-dispatch-build) pre-approve it; a scriptPath launch hits a dialog that cannot show the ~89k-char script and offers deny only. Named lookup follows the shell cwd: cd back to /projects/dev/agentops before launching.
- Items take an optional code_repo (vuoro, sprintctl, appservice) alongside the tracker repo. For appservice items push must be false: pushing appservice main deploys through Flux.
- agentops main is protected (enforce_admins, required checks append-only-shards, protected-paths, scripts-tests, templates-dispatch-allowlist). sprintctl main is not protected: the workflow fast-forward pushes verified work there unless protected paths change (then a PR).
- The shared local main of each repo can carry other sessions' unpushed commits. Never discard them. Before touching another session's commits, confirm by patch-id that they are on origin, and keep a backup ref. Fast-forward local main to origin after each merge (git merge --ff-only origin/main).
- The auto-mode classifier denies edits to .claude/workflows/vuoro-dispatch-build.js as Self-Modification even with the Edit allow rule (wf_028d9fe0-0df). Builds that edit the workflow file need manual mode. Never work around a denial (no Bash/python edits, no doing the denied edit yourself or via another agent).
- Run git commands for different repos sequentially, never as parallel Bash calls.
- Run the workflow from an ATTENDED session (CLAUDE_CODE_SESSION_ATTENDED=1); bg sessions trip the bg-isolation guard until #2563 lands.
- Temporary settings rule: settings.local.json permissions.allow contains "Edit(/projects/dev/agentops/.claude/workflows/vuoro-dispatch-build.js)" (operator-approved 2026-09-30 for #2562/#2563). Remove it once #2563 is merged and closed. The Skill/Workflow allow rules and the env block stay.
- When an adopted earlier commit set is part of a unit, tell the builder to report the unit base before the first adopted commit; listing adopted commits outside the unit range makes the verifier return issues_found (wf_49b1b9fa-cfc).
- Frozen oracles: a unit may not edit its own oracle. When an oracle contradicts documented behaviour, record a decision note authorizing exactly one named assertion repair, and tell the verifier to check it (as notes 4110 and 4123 did).

## Decisions

- **#2565 delivered via PR #292 (merge dfe53ca); #2565 and #2559 closed (wf_effd2118-99a).** — oracleBlock now substitutes the hex-validated unit head; independent review approved, 72 tests pass and the new test fails on old code.
- **#2543 closed: local sprintctl main merged origin/main as f108052 (real merge, kept 20c4828 and 9a0b8e8), then re-dispatched and pushed (wf_68ade337-220).** — The prior verdict was issues_found only because the manifest lacked fix 44def31.
- **#2541 (effect-intent lifecycle, schema 19) and #2542 (shared idempotency ledger) closed; pushed to sprintctl main 7851601 (wf_290f8453-ea5).** — Verified in clean worktrees; vuoro halves moved to #2567/#2569, release and remote migration to #2568.
- **#2540 closed by decision: a report on a stale lease nobody took over stays refused as lease-expired under INV-L1; the holder reactivates the same lease (Case B) and re-reports. Doc 629ab31; vuoro Case B moved to #2570.** — Refinement settled the contract-vs-INV-L1 question (note 4051); landed via sprintctl PR #113 (merge 33b39d4).
- **#2564 closed (pg-disposable cumulative cleanup evidence, pinned PG16, -k 30s, CI parity, sweep) via sprintctl PR #113.** — Independent review approved; two low findings recorded on #2564 note 4099.
- **#2562 closed: deterministic publication preflight/confirm (scripts/dispatch_publish_check.py) merged via PR #298 (merge 0636b80) after PR #297 review REQUEST_CHANGES.** — Re-review reproduced and confirmed fixes for non-ASCII paths, merge-commit hits, PR-action-with-main-pushed, and the protection floor (.claude/**, **/*.dispatch.json for every repo, note 4123).
- **Session env now sets SPRINTCTL_BACKEND/SPRINTCTL_VUORO_PROFILE in agentops settings.local.json.** — Stage prompts call plain sprintctl --json; without the env every verifier fell back to the refused local backend.
- **#2563 oracle repair authorized (note 4110): require route events only for repos with an untiered unit in test_each_repo_builds_in_a_run_worktree_cut_from_origin_main; keep all run-worktree assertions.** — Explicit-tier units skip routing by design; the frozen oracle contradicted documented behaviour.

## Rejected

- **Merging PR #297 as built** — Independent review reproduced protected-path misses (non-ASCII, merge commits) and a PR confirm that passed with main also pushed.
- **Doing #2563's denied workflow edits myself or through another agent in auto mode** — The classifier denied them as Self-Modification; that would pursue a denied outcome. Use manual mode.
- **Launching the workflow by scriptPath in manual mode** — The approval dialog cannot show the 89k-char script and offers deny only; launch by name with the Workflow(vuoro-dispatch-build) allow rule.
- **Treating the 'Merge Without Review' security warning on wf_290f8453-ea5 publish as a breach** — The agent fast-forward pushed verified commits to unprotected sprintctl main (designed behaviour, operator-approved); no protected path was touched (checked by hand).

## Repo state

Digest definition: v5 (see the handoffs README).

| path | branch | head | dirty | unpushed | diff_sha256 |
|---|---|---|---|---|---|
| `/projects/dev/agentops` | main | `11b93f19794c` | yes | 2 | `daf15f5bd05681a2…` |
| `/projects/dev/sprintctl` | main | `33b39d422adc` | no | 0 | `e3b0c44298fc1c14…` |
| `/projects/dev/vuoro` | main | `90b45193f04f` | yes | 0 | `30f045b3e9a2ce5d…` |
| `/projects/dev/appservice` | main | `995d4ae9e06a` | no | 0 | `e3b0c44298fc1c14…` |

## Unresolved

- #2563: parked twice. First attempt failed only on the oracle subtest (now authorized for repair, note 4110). Second attempt (wf_028d9fe0-0df) was blocked by the classifier mid-conflict-resolution and parked: local agentops main is ahead 2 with 01db168 (reapplied oracle) and its revert 11b93f1, which net to zero. The builder's steps to finish: resolve 6 conflict hunks in vuoro-dispatch-build.js keeping the workspace/branch helpers plus itemReadCommand and STATUS_REVISION_RULE; publishPrompt(repo, tip, commits, itemIds, protectedHits, workspace) and its caller; apply the ~1688 routes repair; run targeted tests. Needs manual mode.
- #2597 (follow-ups to the publish preflight): preflight JSON is relayed by an LLM (digest or in-code re-derivation); PR-action main check fails open when remote main is not local or ls-remote fails (note 4128); compute the publish BRANCH in code and skip publication when the range is net-zero (note 4149; PR #299 was a stray).
- #2578 (fail-fast on dispatch-readonly) and #2579 (retire dispatch/run-* branches): moved from #2563.
- #2570 (vuoro lease.py Case B), #2567 (vuoro half of #2541), #2568 (sprintctl 0.11.0 release, remote schema 19 migration, capability grants: the migration and grants are operator-side), #2569 (vuoro half of #2542).
- #2564 note 4099: sweep can rm -rf a live cluster across PID namespaces; sweep unit test scans real /tmp.
- #2554 holds #2525's moved cross-repo parts.
- Operator-only: #2550 (Hetzner key, plus the three-wiring detail in note 3887); #2551 (create the Alloy SOPS secret, then `kubectl -n loki rollout restart ds/alloy-canary`); #2552 after those.
- Hygiene, by explicit allowlist only: agentops backup/local-main-pre-288 and parked/run-877359d1-2548; appservice wip/run-e879ba4c-langfuse and wip/2395-langfuse-credentials (confirm with patch-id). Not done this session.

## Evidence

- session: `9b66e044-305d-480c-9340-f088ea1da661`
- artifact: `docs/dispatch/handoffs/2026-09-30-value-routing-dispatch.v1.json`
- artifact: `scripts/dispatch_publish_check.py`
- sprintctl: `agentops#2563`
- sprintctl: `agentops#2597`
- sprintctl: `agentops#2562`
- sprintctl: `agentops#2564`
- sprintctl: `agentops#2570`
- sprintctl: `agentops#2578`
- sprintctl: `agentops#2579`

## sprintctl bundle

- `/projects/dev/agentops/docs/dispatch/handoffs/2026-10-01-value-routing-dispatch.v1.sprintctl-bundle.json` (sha256 `08c333864285fa7e…`)

## Successor

- session: 01a15d5d-7e52-77d3-95ec-0ea33036c90d
- acknowledged: 2026-10-21T08:51:41Z
