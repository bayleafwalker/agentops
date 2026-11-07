# Handoff 2026-09-30-value-routing-dispatch.v1

<!-- Rendered from the canonical JSON beside this file. Do not hand-edit:
     `agentops handoff validate` and `ack` read the JSON, never this. -->

**Objective.** Keep running the value-routing dispatch workflow (agentops .claude/workflows/vuoro-dispatch-build.js) on real sprint items and fix what each run exposes. The pipeline is route -> refine/oracle (Opus 5.5) -> build (Sonnet 5.5) -> independent verify -> up to 2 repairs -> park (git revert) -> publish verified work (push main, or a PR when main refuses the push or protected paths change) -> close (delivery-checked). The operator is not escalated to by default. Near-term: land #2565, close #2566/#2565/#2559, settle the sprintctl lifecycle batch (#2539/#2540/#2543), then #2563 (run-owned branches) and #2562 (deterministic publication preflight).

**Next action.** In the attended session rooted in /projects/dev/agentops: re-dispatch #2565 (adopt fb901e2, push true) and take its PR through independent review, 'hand-pass:' prefix, merge commit; re-dispatch #2565 and #2559 to close; remove the temporary Edit allow rule. Then merge origin/main into local sprintctl main and re-dispatch #2543 (code_repo sprintctl, push true); then #2541 and #2542; then #2540 refinement, #2563, #2562, #2564.

## Predecessor

- harness: claude-code
- session: 3f826724-c04f-4aa6-b30c-945a6723b9e8
- model: claude-opus-5-5
- context used: unknown%
- transcript: unknown
- origin: `workstation:/projects/dev/agentops/docs/dispatch/handoffs/2026-09-30-value-routing-dispatch.v1.json` (authoritative copy; an ack from another host goes through it)

Read-only after transfer: once a successor acks, the predecessor makes no
edits and takes no external actions. It stays consultable.

## Constraints

- Nothing waits on the operator by default. Refine and decide from documented direction and record the decision on the item. Raise to the operator only for their own authority (credentials, spending, irreversible production changes) or a real permission denial, with exact steps.
- Router advice is advisory. Never drop scope silently: move it to a named follow-up with a 'build: scope moved' or 'refinement: intent moved' note. The verifier checks every move.
- Workflows use claude-sonnet-5-5 and claude-opus-5-5. Haiku 4.5 is clerical only.
- Every commit I author gets an independent review posted on its PR before merge. Land on main through a PR with a merge commit, never squash, so the SHAs the workflow verified stay intact for the close stage's delivery check. Then remove worktrees and branches. For protected paths (.claude/**, *.dispatch.json), the workflow opens the PR itself without a 'hand-pass:' prefix. Add the prefix only after the independent review approves.
- Do not close sprint items by hand. They close only through the workflow's verified close stage, which requires the commits to be on origin/main.
- sprintctl 0.10.0 uses the served backend. Prefix commands with `direnv exec .` in agentops, pass `--expected-revision` on status changes, and give `--reason` for pending. The served backend occasionally times out (ReadTimeout); check whether a write landed before retrying it.
- The workflow must run from a session rooted in /projects/dev/agentops. Since #289 (a56a20d), its route, verify, record and close stages use the project agent type 'dispatch-readonly' (.claude/agents/dispatch-readonly.md), and a session only loads agent types at start.
- Items take an optional code_repo (vuoro, sprintctl, appservice) alongside the tracker repo. For appservice items push must be false: pushing appservice main deploys through Flux. Land appservice work with a PR pointed at the verified commits (as #1807 did), then re-dispatch so close sees them on origin.
- agentops main is protected (enforce_admins, required checks append-only-shards and protected-paths). Direct pushes fail with GH006, and the workflow falls back to a PR.
- The shared local main of each repo can carry other sessions' unpushed commits. Never discard them. A run halts when local main moves under it (#2563). Before touching another session's commits, confirm by patch-id that they are already on origin, and keep a backup ref.
- The permission classifier may deny a builder's edit to .claude/workflows/* as self-modification. The operator approved the workflow edits for #2553, #2558-#2560, #2565 and #2566. For a new workflow-editing item, ask before dispatching, or when a denial comes back. Never work around a denial.
- Run git commands for different repos sequentially, never as parallel Bash calls. A mis-targeted parallel commit once landed vuoro audit shards on agentops main.
- Run the workflow from an ATTENDED (interactive) session rooted in /projects/dev/agentops. In a background job session (CLAUDE_CODE_SESSION_ATTENDED=0) the bg-isolation guard blocks builders from writing the shared checkout until the parent calls EnterWorktree; after EnterWorktree, the session and its workflow agents cannot touch that repo's shared checkout at all. The workflow builds on shared local main, so bg sessions cannot run it until #2563 lands.
- Temporary settings rule: /projects/dev/agentops/.claude/settings.local.json permissions.allow contains "Edit(/projects/dev/agentops/.claude/workflows/vuoro-dispatch-build.js)" (operator instruction, 2026-09-30, for #2565). Builders must edit that file with the Edit tool; Bash/python edits are denied as Self-Modification. Remove the rule once #2565 is merged.
- Queue addition (operator-approved via session dev-bf 88841e52, 2026-09-30): after #2543, dispatch agentops #2541 (M2-1 effect-intent lifecycle, work.effect.*) and #2542 (shared idempotency ledger), code_repo sprintctl, push true. They touch the same pg.py as #2543, hence the order.
- Pass workflow agents the sprintctl invocation `direnv exec . sprintctl ...` from /projects/dev/agentops: without it sprintctl refuses the local backend and the served backend lacks SPRINTCTL_VUORO_PROFILE (made wf_ed28b453-37b's verify inconclusive).

## Decisions

- **Per-item code_repo in both workflows: build #274, verify #282 (#2549).** — Most of the agentops backlog changes vuoro, sprintctl or appservice code. #2530 and #2525 (vuoro) then closed end to end.
- **Delivery-checked close (#277): an item closes only when its commits are ancestors of origin/main. Otherwise it is 'verified, undelivered' (pending, reason partial).** — #2395 had closed with push off and nothing on origin. It was later landed through appservice#1805.
- **Park refuses to revert merges or published commits (#276). The history rule forbids merge, pull and rebase during a unit.** — A park reverted a merge of origin and would have rolled vuoro-shared back from v0.1.80 to v0.1.72. Nothing was pushed.
- **PR-publish mode (#284, #2553): when main refuses the push, or protected paths change, publish pushes a dispatch/publish-<sha> branch and opens a PR. It never merges and never enables auto-merge.** — agentops main became protected (#2546). First use: #286, which carried #2558, #2559 and #2560.
- **The verified prefix publishes past an unverified unit, and refs/dispatch/verified record verified ranges. The delivery check runs for every confirmed item (#286, #2558).** — Previously one inconclusive unit stranded the whole repo, and a publish agent claiming published=true skipped the ancestor check.
- **Verifier hygiene: keep the worktree path in a shell variable, write no shared scratch files, run the manifest suite command verbatim first (#2559). Adopted oracle commits are declared, and closeout runs once per tracker (#2560).** — Parallel verifiers overwrote each other's scratch file, and verifiers ran bare pytest before the wheels existed.
- **Non-writing stages run as agent type dispatch-readonly (#289, #2566). Its definition allows only sprintctl, jev_shadow.py, git fetch origin, git update-ref under refs/dispatch/verified/, and the verifier's own worktree.** — A Haiku route agent edited the workflow file in the shared checkout mid-run, and a concurrently launched run loaded that file. The edit is saved in the session scratchpad as route-agent-2565-edits.patch and was discarded.
- **sprintctl Postgres tests now run in dispatch verification through scripts/pg-disposable-tests.sh: a throwaway PG16 from nix, with every PG* variable cleared (sprintctl#110, #2561).** — Planner finding R4: the tests always skipped locally, so sprintctl lease work was verified without its most relevant tests.
- **The vuoro manifest suite is self-contained (uv sync --all-packages --all-extras plus the four wheel builds, then pytest): vuoro#158, #159.** — #2525 was inconclusive because bare `uv run pytest` fails cold.
- **agentops main branch protection adopted with enforce_admins=true (#2546, closed).** — Operator approved it ('Sure').
- **sprintctl manifest verification fix landed as sprintctl#112 (merge c993f03, commit 44def31): first verification command gets --extra dev --extra served; catalog command names test_served_operation_surface.py and test_adapter_kit_migration.py (test_served_lifecycle_routes.py was deleted in a07f26c).** — It was reverted with the #2540 park. Independent review approved on the PR; 4/4 CI checks passed.
- **#2566 closed by the workflow (wf_e022e124-64d), delivery-checked on e57481a.** — Delivered in #289; it only needed its close.
- **#2543 fix path: merge origin/main into local sprintctl main (a real merge; keeps 20c4828 and 9a0b8e8), then re-dispatch #2543 (code_repo sprintctl, push true).** — wf_c3cdb702-6d8 found the code sound (docs 4/4, pg-disposable 530 with zero residue, full suite 1579 pass, scope move to vuoro #2472 holds) and returned issues_found only because the manifest at 9a0b8e8 still has the bare `uv run pytest` command; the fix 44def31 is only on origin. A merge keeps the verified SHAs; rebase stays forbidden.
- **#2565 built as fb901e2 on local agentops main (unpublished, ahead 1): oracleBlock substitutes the hex-validated unit head; test_saved_workflows.py asserts it.** — wf_ed28b453-37b verify: code and tests sound, range is exactly fb901e2, verdict inconclusive only because the verifier could not read the item (SPRINTCTL_VUORO_PROFILE unset). Re-dispatch #2565 to re-verify fb901e2 with sprintctl reachable; the builder should adopt fb901e2, not rebuild.

## Rejected

- **Treating the harness's Auto-Mode Bypass warning on a route agent (wf_409c1d1b-7f8) as a breach** — Its transcript showed reads only. The later real route-agent write is handled by #2566.
- **Fixing the #2394 appservice work by cherry-picking onto a fresh branch** — New SHAs would fail the close stage's delivery check. Point the PR branch at the verified commits instead.
- **Hand-applying the route agent's half-made #2565 edit** — It was unreviewed and its test never asserted the concrete SHA. #2565 is rebuilt through the workflow.
- **Having builders edit vuoro-dispatch-build.js through Bash, sed or python** — Denied as Self-Modification (wf_6434b9f3-e6f, wf_36841688-79f); the allow rule covers the Edit tool only.
- **Running the dispatch workflow from a background job session, with or without EnterWorktree** — wf_2659cc14-fc0 was blocked by the bg-isolation guard; once the parent isolated, the #2543 verifier's cleanup and the session's own git -C on the shared checkout were refused. Use an attended session.

## Repo state

Digest definition: v5 (see the handoffs README).

| path | branch | head | dirty | unpushed | diff_sha256 |
|---|---|---|---|---|---|
| `/projects/dev/agentops` | main | `fb901e24acad` | yes | 1 | `daf15f5bd05681a2…` |
| `/projects/dev/sprintctl` | main | `9a0b8e8a5cb0` | no | 2 | `e3b0c44298fc1c14…` |
| `/projects/dev/vuoro` | main | `90b45193f04f` | yes | 0 | `30f045b3e9a2ce5d…` |
| `/projects/dev/appservice` | main | `995d4ae9e06a` | no | 0 | `e3b0c44298fc1c14…` |

## Unresolved

- #2565: fb901e2 is on local agentops main, unpublished, verdict inconclusive (item unreadable). Re-dispatch #2565 with push true and tell it to adopt fb901e2; the workflow opens a PR (protected path). Independent review, then 'hand-pass:' prefix, merge with a merge commit, then re-dispatch #2565 and #2559 (push true) to close. Then remove the temporary Edit allow rule.
- #2543: pending (issues_found, manifest only). Merge origin/main into local sprintctl main (it is ahead 2, behind 3), then re-dispatch.
- #2541 and #2542 after #2543 (see constraint).
- #2540 still parked: refinement must decide between the contract point on agentops#253 and INV-L1 (note 4000).
- Fold into #2562: builder/verifier prompts must name `direnv exec . sprintctl`; a builder reported `sprintctl item status` in served mode rejects --expected-revision (check and correct constraint 6 if true).
- #2562: deterministic publication preflight (protected-path hits, push refusal, verified-ref value checks, origin_url computed in code, --expected-revision on retries). Findings are in notes 3921 and 3950.
- #2563: build on a run-owned branch or worktree instead of the shared local main. The agent-type resolution note is 3988.
- #2564: pg-disposable-tests follow-ups. Cleanup evidence per fixture, pin PG, a timeout with -k, CI parity, guide wording, and a stale-cluster sweep (one orphan cluster survived a reviewer signal test; note 3979).
- #2554 holds #2525's moved cross-repo parts (sprintctl serving, vuoro-cloud scope row, agentops runbook).
- Operator-only: #2550 (Hetzner key); #2551 (create the Alloy SOPS secret, then `kubectl -n loki rollout restart ds/alloy-canary`); #2552 after those. #2550 also needs the three-wiring detail from note 3887.
- Hygiene, by explicit allowlist only: agentops backup/local-main-pre-288 (its commits are on origin through #288, so safe to delete); agentops parked/run-877359d1-2548 (superseded by 1cf9ddf); appservice wip/run-e879ba4c-langfuse and wip/2395-langfuse-credentials (landed through #1805; confirm with patch-id). Other sessions' vuoro worktrees under /tmp/claude-1000/*/scratchpad belong to those sessions; leave them alone.

## Evidence

- session: `670479d6-ab6e-406f-bc84-647f5afb44e2`
- artifact: `docs/dispatch/workflow-topology.md`
- artifact: `.claude/agents/dispatch-readonly.md`
- sprintctl: `agentops#2559`
- sprintctl: `agentops#2562`
- sprintctl: `agentops#2563`
- sprintctl: `agentops#2564`
- sprintctl: `agentops#2565`
- sprintctl: `agentops#2566`
- sprintctl: `agentops#2539`
- sprintctl: `agentops#2540`
- sprintctl: `agentops#2543`
- session: `3f826724-c04f-4aa6-b30c-945a6723b9e8`

## sprintctl bundle

- none (sprintctl unavailable or produced no bundle)

## Successor

- session: 9b66e044-305d-480c-9340-f088ea1da661
- acknowledged: 2026-09-30T16:37:30Z
