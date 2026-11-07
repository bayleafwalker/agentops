# Handoff 2026-09-29-value-routing-dispatch.v2

<!-- Rendered from the canonical JSON beside this file. Do not hand-edit:
     `agentops handoff validate` and `ack` read the JSON, never this. -->

**Objective.** Keep running the value-routing dispatch workflow (agentops .claude/workflows/vuoro-dispatch-build.js) on real sprint items and fix what each run exposes. The pipeline is route -> refine/oracle (Opus 5.5) -> build (Sonnet 5.5) -> independent verify -> up to 2 repairs -> park (git revert) -> publish verified work (push main, or a PR when main refuses the push or protected paths change) -> close (delivery-checked). The operator is not escalated to by default. Near-term: land #2565, close #2566/#2565/#2559, settle the sprintctl lifecycle batch (#2539/#2540/#2543), then #2563 (run-owned branches) and #2562 (deterministic publication preflight).

**Next action.** In a new session rooted in /projects/dev/agentops (so the dispatch-readonly agent type loads), first check that `git -C /projects/dev/agentops status -sb` shows main == origin/main apart from the audit shard, and that `git -C /projects/dev/sprintctl log --oneline origin/main..main` lists only 20c4828 and 9a0b8e8 (it is also 1 behind, the sprintctl#111 merge; leave that). Then run Workflow({scriptPath: '/projects/dev/agentops/.claude/workflows/vuoro-dispatch-build.js', args: {items: [{repo: 'agentops', item_id: 2566, unit: 'readonly-stages'}, {repo: 'agentops', item_id: 2565, unit: 'oracle-intact-unit-head'}], push: true}}). #2566 is already delivered in #289 and only needs its close. #2565 is a new build the operator approved (edits .claude/workflows/vuoro-dispatch-build.js). The workflow will open a PR for #2565. Get an independent review on it, add the 'hand-pass:' prefix after approval, merge with a merge commit, then re-dispatch #2565 and #2559 (push true) to close them. Next, land the sprintctl manifest verification-command fix through a PR, and re-dispatch #2543 (code_repo sprintctl, push true); the builder should adopt 20c4828 and 9a0b8e8. After that: #2540 refinement, then #2563, #2562, #2564.

## Predecessor

- harness: claude
- session: 670479d6-ab6e-406f-bc84-647f5afb44e2
- model: claude-opus-5-5
- context used: unknown%
- transcript: unknown
- origin: `workstation:/projects/dev/agentops/docs/dispatch/handoffs/2026-09-29-value-routing-dispatch.v2.json` (authoritative copy; an ack from another host goes through it)

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

## Rejected

- **Treating the harness's Auto-Mode Bypass warning on a route agent (wf_409c1d1b-7f8) as a breach** — Its transcript showed reads only. The later real route-agent write is handled by #2566.
- **Fixing the #2394 appservice work by cherry-picking onto a fresh branch** — New SHAs would fail the close stage's delivery check. Point the PR branch at the verified commits instead.
- **Hand-applying the route agent's half-made #2565 edit** — It was unreviewed and its test never asserted the concrete SHA. #2565 is rebuilt through the workflow.

## Repo state

Digest definition: v5 (see the handoffs README).

| path | branch | head | dirty | unpushed | diff_sha256 |
|---|---|---|---|---|---|
| `/projects/dev/agentops` | main | `a56a20d50b17` | yes | 0 | `daf15f5bd05681a2…` |
| `/projects/dev/sprintctl` | main | `9a0b8e8a5cb0` | no | 2 | `e3b0c44298fc1c14…` |
| `/projects/dev/vuoro` | main | `90b45193f04f` | yes | 0 | `30f045b3e9a2ce5d…` |
| `/projects/dev/appservice` | main | `995d4ae9e06a` | no | 0 | `e3b0c44298fc1c14…` |

## Unresolved

- #2565 (the oracle_intact diff should target the unit head, not origin HEAD) is pending and its reservation is released. The operator approved dispatching it. #2559 (verifier hygiene) is delivered on main but went back to pending only because of the #2565 bug. Re-dispatch it after #2565 lands.
- #2566 (read-only stages) is delivered in #289 (0f8328f, e57481a) and pending close. Its close run failed only because this session could not load the new agent type.
- Sprintctl lifecycle batch (wf_5918838a-8d6): #2539 closed as delivered. #2540 is parked: its code is sound, but part (2), evaluating a report on a stale lease, was dropped without a move note. Refinement must decide between the contract point on agentops#253 and INV-L1 (note 4000). #2543 is inconclusive only because the verifier returned no structured evidence. Its commits 20c4828 and 9a0b8e8 sit unpublished on the local sprintctl main (note 4001). The fix for sprintctl.dispatch.json's first verification command (it needs `uv run --extra dev pytest`) was reverted along with #2540 and must land on its own through a PR, since the manifest is a protected path. sprintctl#111, the net-empty commit plus revert of the #2540 park, is merged (d6f6d56, independent review approved); local sprintctl main is ahead 2 (the #2543 commits) and behind 1 (that merge commit), so the next #2543 publish will take the PR fallback on non-fast-forward, which is expected; do not rebase.
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

## sprintctl bundle

- `/projects/dev/agentops/docs/dispatch/handoffs/2026-09-29-value-routing-dispatch.v2.sprintctl-bundle.json` (sha256 `a2444c85d71f9398…`)

## Successor

- session: 3f826724-c04f-4aa6-b30c-945a6723b9e8
- acknowledged: 2026-09-30T15:58:17Z
