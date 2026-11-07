# Handoff 2026-09-25-ra2-strategic-bot.v2

<!-- Rendered from the canonical JSON beside this file. Do not hand-edit:
     `agentops handoff validate` and `ack` read the JSON, never this. -->

**Objective.** Implement the operator's RA2/YR strategic-bot proposal (docs/architecture/strategic-bot-proposal.md) as the strongest, fully hardened package: adversarially review and fix it, add independent opponents, measure and tune strength, close every completeness gap, run a final tournament, then land it on main via PR.

**Next action.** cd /projects/dev/_wt/bindery-ra2-bot && git pull --ff-only && git log --oneline -1 (expect 2321cb6). Read /projects/dev/_artifacts/ra2-strategic-bot-harden.workflow.js, update its session-specific paths (SCRATCH, and the claude-api skill path if the bundled-skills dir changed), and launch it with the Workflow tool's script parameter (ultracode). When it completes, verify the results, push, and open a PR from feat/strategic-bot to main with gh.

## Predecessor

- harness: claude-code
- session: d1025803-9737-4395-ab2d-56ff517810c7
- model: claude-opus-5-5
- context used: unknown%
- transcript: unknown
- origin: `workstation:/projects/dev/agentops/docs/dispatch/handoffs/2026-09-25-ra2-strategic-bot.v2.json` (authoritative copy; an ack from another host goes through it)

Read-only after transfer: once a successor acks, the predecessor makes no
edits and takes no external actions. It stays consultable.

## Constraints

- Operator opted into ultracode: run substantive work through the Workflow tool (multi-agent), with adversarial verification.
- Work in worktree /projects/dev/_wt/bindery-ra2-bot on branch feat/strategic-bot (pushed to origin). Do not work in the main checkout /projects/dev/bindery-ra2-adapter.
- dotnet is not on PATH: use `nix shell nixpkgs#dotnet-sdk_8 -c dotnet ...` with the Bash dangerouslyDisableSandbox parameter set to true (network restore; pre-approved by the forge-sandbox hook policy).
- No proprietary game files in the repo (ci/verify-no-assets.ps1). The rules fixture is hand-authored and approximate; an operator rulesmd.ini is imported from outside the repo.
- No Anthropic credential on this host (no ANTHROPIC_API_KEY, no ant CLI, cred-broker is forge-only). LLM arms run with --llm-fake; never claim live-LLM results.
- Model tiering: Sonnet for bulk fan-out agents, the session model (Opus) for review, verification, integration and judgment.
- Workflow worktree isolation creates worktrees from the main checkout (which is at main 82b4e62), so every isolated agent must `git reset --hard <feat/strategic-bot sha>` first. One agent in run 1 got a worktree whose hook refused git subcommands; the integrator implemented that package itself.

## Decisions

- **The bot lives in bindery-ra2-adapter as the net8.0 projects src/Bindery.Ra2.Bot, .Sim and .Claude, tools/Bindery.Ra2.Bot.Arena and tests/Bindery.Ra2.Bot.Tests.** — The repo already owns the RA2 telemetry seam (ra2yrcpp). The bot is engine-agnostic so it builds and tests on Linux.
- **One optional strategic LLM (claude-opus-5, low effort) that only selects and parameterises validated playbooks. The 'fast LLM' exists only as the llm+fast arm (Haiku, parameter changes only).** — The proposal's verdict: keep the AI layered, but don't make the LLM layers the default.
- **A deterministic region-level simulator is the development and evaluation environment; the retail RA2 path goes through the ra2yrcpp telemetry and command-envelope seams (bindery.ra2.bot-observation/v1, bindery.ra2.bot-command/v1).** — The native command RPC belongs to the ra2yrcpp fork. The simulator gives observe, act, reset, replay and logging offline.
- **The contracts in src/Bindery.Ra2.Bot/Contracts are fixed; the integrator made small changes (BotJson named floats and RegionId dictionary keys, ObservationFrame.OreRemaining, BeliefSnapshot.OreLastSeen).** — Parallel packages needed a single source of truth; the changes answered verified package requests.
- **Implementation run 1 (wf_e565269f-d90) done: 29 commits; bot tests 354 passed and 1 skipped (live-LLM smoke) of 355; adapter tests 66/66; 0 warnings. Arena selector: 34/45 training, 19/30 held-out wins.** — Baseline for the hardening pass; details in the integrator report and docs/architecture/strategic-bot.md.

## Rejected

- **Running the hardening workflow while the operator's machine sleeps** — Stopped cleanly (wv2jvguaf / wf_41e2b9e0-ced) before any commit. Workflow resume only works within the same session, so re-launch it fresh; do not try resumeFromRunId.
- **Evaluating only against BotRuntime-pinned opponents** — Self-referential: planner changes move both sides. The hardening script adds an independent ai-* opponent that shares no planner code.
- **Tuning or choosing defaults on held-out maps** — Contaminates the held-out split. The integrator touched held-out maps once while choosing a selector default and re-checked on training maps only; keep held-out for final evaluation.

## Repo state

Digest definition: v4 (see the handoffs README).

| path | branch | head | dirty | unpushed | diff_sha256 |
|---|---|---|---|---|---|
| `/projects/dev/_wt/bindery-ra2-bot` | feat/strategic-bot | `2321cb68eb06` | no | 0 | `e3b0c44298fc1c14…` |

## Unresolved

- Live LLM arms need a credential: the operator runs `export ANTHROPIC_API_KEY=...` (or installs ant and runs `ant auth login`), then the arena with --arms llm,llm+fast without --llm-fake.
- Whether to merge the PR to main once CI is green: AGENTS.md says branches land on main. Open the PR, watch CI in a background task, and merge when green unless the operator objects.

## Evidence

- artifact: `/projects/dev/_artifacts/ra2-strategic-bot-harden.workflow.js`
- artifact: `/projects/dev/_wt/bindery-ra2-bot/docs/architecture/strategic-bot.md`
- artifact: `/projects/dev/_wt/bindery-ra2-bot/docs/architecture/strategic-bot-proposal.md`
- artifact: `/tmp/claude-1000/-projects-dev/d1025803-9737-4395-ab2d-56ff517810c7/tasks/wtl6m1wwh.output`
- session: `d1025803-9737-4395-ab2d-56ff517810c7`

## sprintctl bundle

- none (sprintctl unavailable or produced no bundle)

## Successor

- session: 78fca569-75ab-48b7-89eb-b3f8e360e1c0
- acknowledged: 2026-09-26T06:14:58Z
