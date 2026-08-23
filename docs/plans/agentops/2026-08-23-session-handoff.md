# Session hand-off — v5 telemetry and the L-1 loop (2026-08-23)

Written for a **cleared session**. Read this, then the pathway
(`/projects/dev/vuoro/docs/plans/2026-08-23-requirements-pathway-v5-v7.md`) and the v5 plan
(`/projects/dev/vuoro/docs/plans/2026-08-23-v5-implementation-plan.md`). Nothing here is
authorized to execute itself; the owner's next action is named in §6.

## 1. Read this first: nothing is pushed or merged

All work is on **local branches**. No remote has any of it, and `main` is untouched everywhere.

| Repo | Branch | Tip |
|---|---|---|
| agentops | `v5-telemetry-t1-t5` | `3f7d415` (25 commits from `a44db6e`) |
| agentops | `v5-telemetry-oracle` | `775ce5f` — P-0b, starting point for the whole-T-set packet |
| agentops | `v5-telemetry-oracle-t1` | `8b1c8b9` — P-0c, starting point for the T-1 packet |
| vuoro | `v5-implementation-plan` | `97aa812` (9 commits from `2d33096`) |

**Keep `v5-telemetry-t1-t5` checked out in agentops.** `/projects/dev/.claude/hooks/` are symlinks
into that working tree. Checking out `main` leaves them dangling and every session silently stops
recording its own telemetry. This is the first `debt:` line of v5 and it bites without warning.

## 2. What exists now that did not this morning

- **Session telemetry (T-1..T-5), live.** `Stop` and `PostToolUse` hooks in `/projects/dev`,
  actionq, agentops, appservice, homelab-analytics, kctl, sprintctl. Versioned in
  `agentops/templates/dispatch/hooks/`, symlinked into `/projects/dev/.claude/hooks/`.
  Sinks: `.claude/session-costs.jsonl` and auditctl `workflow.session` / `workflow.friction`.
- **The L-1 driver** `templates/dispatch/scripts/dispatch_release.py`: prepare → run → gate →
  receipt → `gh pr create`, never merges. Built by a secondary session, cherry-picked here.
- **A green loop run.** Packet `V5-P1a-cost-hook-fields` at `8b1c8b9` passed every gate on devbox
  under real containment: $0.014, 277k tokens, `opencode-go/deepseek-v4-flash`.
- **Five harness/packet defects found and fixed** — see §4. None of them was the model.

## 3. Facts that will mislead you if you do not know them

Each of these cost real time today.

- **`Stop` fires once per assistant turn, not once per session.** Every cost row is a *cumulative
  snapshot*. Reduce to the newest row per session — take the max, never the sum. Summing
  over-counts roughly quadratically: `cost-summary.sh` reported **$56,485** against **$3,825**
  actual across 97 sessions before this was fixed. `ts` is second-resolution, so break ties by
  magnitude, not input order.
- **The Bash tool result carries no exit code.** `gate-log.sh` records which signal decided each
  verdict (`exit_code | is_error | interrupted | heuristic | unattributable`). A compound command
  (`cmd && git commit`, `cmd | tail`) is `unattributable` with `ok: null`, because the status
  belongs to the last element. Consequence: **`rework_rounds` is biased toward the loop** — a
  coordinator runs gates in compound lines (6 of 13 rows in one session), the loop runs single
  registered command strings. Never compare raw rework across dispatch modes.
- **`sprintctl` has no `claim` command.** It was replaced by advisory *reservations*, which have
  **no expiry** — `hybrid_dispatch` checks staleness against sprintctl's own 4-hour horizon
  instead. `sprint_item.claim_id`/`claim_actor` keep their names and now hold a reservation id
  and its actor.
- **`claim_actor` must be the served identity**, not a coordinator label. The served side rejects
  `actor-mismatch` otherwise. Here that is `workstation-vuoro`.
- **`auditctl` rejects `--ref session:<id>`** (prefixes are `wi:|ka:|ad:|sha:|pr:|sprint:|capsule:`)
  and *requires* `--actor` and `--summary`. A Stop hook inherits no direnv, so it must default
  `AUDITCTL_ARTIFACTS_ROOT=/projects/dev` or writes fail closed and silently.
- **`/projects/dev/sprintctl` is ~114 commits behind main.** Grepping it returns confidently wrong
  answers about current behaviour. Three searches for the operation-to-authority mapping found
  nothing there for exactly this reason.
- **The identity registry is startup-only.** Any authority change must bump the
  `identity-revision` annotation in the same commit or it appears to do nothing.
- **T-6 must read two sources.** Frontier cost comes from the hook sink; worker cost comes from
  the receipt's `worker_spend` (OpenCode's own accounting, `cost_reported` separating "free" from
  "did not say"). No Claude Code hook ever sees an OpenCode worker; scoring a loop run from the
  hook sink alone flatters it.

## 4. The five defects, and why the table matters more than the green run

Seven dispatches produced one green. **Not one failure was the model.**

| # | Defect | Whose | Looked like | Fixed by |
|---|---|---|---|---|
| 1 | Workspace group inert — clone lands `agent:agent`, worker is in `agentworker`+`agentdispatch`, so `g+w` meant nothing and **every worker write was denied** | harness | model will not engage | `d0333a0`, `ef1d704` |
| 2 | `context_churn` declared in every packet, enforced nowhere | harness | model is expensive | `58c714a` |
| 3 | Oracle demanded an `AGENTOPS_COST_LOG` seam the packet never stated | coordinator | model cannot finish | `0a0603f` |
| 4 | Oracle covered the whole T-set when the packet covered one item | coordinator | model cannot finish | `515a452` |
| 5 | Oracle absent at `starting_commit`; exit 127 accepted as a declared red | both | model cannot finish | `5088f44`, `8b1c8b9` |

Defects 3, 4 and 5 are **one gap**: nothing checked that a packet's oracle is *attainable* from its
own text and its own starting commit. `validate` asks whether acceptance properties discriminate;
it never asked whether they can be met. **L-2(a) now closes the cheap half** (`d1d01dd`): each
`starts_red` command runs at `starting_commit` in a throwaway checkout and must be red for a reason
other than absence. Verified live — `V5-P1a @ 8b1c8b9` reports `oracle_attainable`, the same packet
at `775ce5f` is rejected with the reason named.

**L-2(b) is specified and not built**: prove the failure is caused only by files the packet may
write — overlay a reference solution if one exists, else assert every file the failing test reads
is inside `readable_context_paths ∪ writable_patch_paths`. Freeze no further packets before this;
it is what makes defects 3 and 4 mechanical rather than a matter of coordinator care.

## 5. How to run the loop (it works; these are the exact invocations)

The workstation has **no contained worker identity**, so `run` refuses there by design. Devbox has
`agentworker`. The coordinator runs from a worktree because devbox's own checkout is dirty:

```bash
# push the branch (its own name is checked out in the worktree, so use another ref)
git push -f devbox-agent:/projects/dev/agentops v5-telemetry-t1-t5:refs/heads/v5-fix-workspace-write

ssh devbox-agent 'cd /tmp/v5-coordinator; git reset -q --hard v5-fix-workspace-write;
  export SPRINTCTL_BACKEND=served \
    SPRINTCTL_VUORO_PROFILE=/projects/dev/agentops/templates/dispatch/environment-record/profiles/devbox-agent-vuoro-shared.json \
    SPRINTCTL_DB=/projects/dev/agentops/.sprintctl/sprintctl.db \
    AUDITCTL_ARTIFACTS_ROOT=/projects/dev;
  python templates/dispatch/scripts/dispatch_release.py --repo-root /tmp/v5-coordinator \
    --dry-run --report /tmp/report.json docs/evidence/packets/<packet>.json \
    -- --agentops-root /tmp/v5-coordinator --worker-user agentworker'
```

`--dry-run` runs everything except `gh pr create`. Anything after `--` is forwarded to
`hybrid_dispatch`. A run takes 3–6 minutes; run it in the background. Note the remote `cd` must be
inside the ssh command string — it is easy to drop and the failure is silent (`pwd` shows
`/home/agent`).

State: item **agentops#2254** (sprint #428, track `telemetry`), **reservation 2** active, held by
`workstation-vuoro`. Reservations go stale after 4h — `sprintctl reservation touch` before a run.

## 6. Next actions, in the owner's order

1. **Owner accepts the T-1 diff.** `acceptance_authority` is `human`. The coordinator session that
   froze the packet must not sign its own independent review — `hybrid_dispatch.py:995` would
   accept a different reviewer string, but a change and its proof sharing an author is the
   arrangement 5.2 exists to prevent. This is what turns `coordinator_review_required` into a
   counted green. **D-8 stands at 1 of 5**, counted only from `V5-P1a @ 8b1c8b9`; no earlier run
   was evidence about the tier.
2. **L-2(b)** before any further packet is frozen (§4).
3. **T-3 and T-5** as separate packets, one file and one achievable failing test each. **T-4 is
   different** — the drain and the `rework_rounds` rule are design, so the coordinator writes the
   oracle tests first and the packet implements only against them. That split is what made T-1 work.
4. **Capture the worker transcript beside the receipt.** Partly done: the OpenCode event stream is
   in the run receipt's stdout since `f698edc`, plus `session_id`. Missing: OpenCode's own session
   store, which is not retrievable on devbox after the fact.

Then the v5 engineering chain proper, which has not started: **P-2** (`vuoro-cloud.dispatch.json`
— the entire 5.0/E-1..E-8 critical path is undispatchable without it) and **P-11** (the appservice
federation-db PR). See the v5 plan §2.

## 7. What the measurement can and cannot claim

The direct-vs-loop comparison this exercise was built to produce **does not exist yet**, and the
scorecard (`docs/evidence/scorecards/v5-p1-two-way.json`) says so rather than smoothing it over.
The direct row is 9 turns / 254 tool calls / 214 min / $197.14, but that session also produced the
v5 plan, P-0, and three rounds of fixes — a per-packet direct cost is not extractable from it.
Quoting "$197 vs $0.014" would be a fabrication in the loop's favour.

The first clean row needs the T-1 packet done both ways by sessions that do nothing else. What the
evidence *does* support: the plumbing holds under real containment, and given one outcome, one
writable file and one achievable failing test, the cheap tier produces correct scoped work.

One attribution, kept deliberately: the "packet, not tier" diagnosis was the **owner's**, made from
the receipt alone, which could not distinguish "flash will not write" from "the oracle is
unattainable". It was a plausible reading that happened to be right. Attempt 7 earned it.
