# Workflow Artifact: process-quality lessons from a live production deploy

- **Date:** 2026-07-24
- **Source session note(s):** `.agents/sessions/2026-07-24-projection-cutover-1245-live-deploy.md`
- **Workflow(s) used:** single-agent direct execution (no dispatch/subagent
  pipeline) across sprintctl, vuoro, appservice, agentops.
- **Repos touched:** sprintctl, vuoro, appservice, agentops.
- **kctl tracking:** sprintctl item #1246 (sprint 428), events #1444–#1451,
  extracted as 10 durable candidates awaiting review.

## Scenario

A single long session took `track=projection-cutover` from "orchestration
handoff" to "released and verified live in production": reconciled diverged
git history in two repos, corrected a flawed service design before it
reached production, deployed it (new wheel, new image, a live PostgreSQL
schema migration, a SOPS secret edit), diagnosed and resolved a real
incident mid-rollout, and discovered + fixed a self-inflicted regression in
a separate legacy database while documenting the session. This artifact is
not about the sprintctl/vuoro product outcome (recorded elsewhere) — it is
about what the *process* of getting there revealed about agent execution
quality, worth imitating or avoiding in future sessions of similar shape
(long-running, multi-repo, production-authority work).

## Suitability assessment

Direct single-agent execution (no subagent dispatch) was the right shape
for this session: the work was tightly sequential (each step's outcome
determined the next), required accumulating live context (production
secret contents, database state, cluster health) that would have been
expensive to re-derive across dispatch boundaries, and needed a single
continuous chain of user confirmations rather than parallelizable
sub-tasks. A tiered dispatch/verify pipeline would not have fit this
shape. What it exposed instead is a set of *execution-quality* gaps
independent of the dispatch-vs-direct question — see below.

## What required rework

| Issue | First-pass outcome | What it cost to fix |
|---|---|---|
| `#1245` repo_id design | Merged, CI-green in both repos, wrong for production (identity-bound instead of client-sent) | Full redesign: wire-protocol field, `Identity` model change, client + CLI threading, retested — a second full implementation pass, caught before deploy only by manually reading the production secret |
| Legacy database schema regression | Undiscovered for the remainder of the active session | A second migration job, found only while writing this documentation, not by any planned verification step |
| `ssh` command construction (×2 incidents) | ~8-10 consecutive identical failed attempts each | Broken only by changing command *structure*, not by retrying the same fix |
| Fabricated commit SHA in `pyproject.toml` | Would have shipped a hallucinated pin if uncaught | One `git rev-parse` call once actually run |

## What was validated vs. not

- Validated with real infrastructure: PostgreSQL schema compatibility (real
  disposable containers, matching CI), the live production deploy itself
  (real cluster, real traffic continuity check via pod readiness and
  request logs), the corrected `#1245` design (4 new integration tests
  through `create_app`, plus live production calls from both hosts after
  deploy).
- **Not** validated by anything until incidentally discovered: whether a
  schema-version bump is compatible with *every* database deployment that
  depends on it, not just the one being actively worked on. No test, CI
  check, or deploy-time gate covers this — see the dedicated pathway
  writeup in the source session note.
- Not validated by anything until a human read the raw secret: whether a
  service design's assumptions (one bearer token per repo) match the
  *actual* shape of the production resource it will run against. CI green
  is not evidence of this.

## Cost summary

Not a subagent-token-tracked run; rough shape instead: ~8 merged PRs/direct
pushes across 3 code repos, 2 live PostgreSQL schema migrations, 1
production secret edit, 1 image build+deploy, multiple `AskUserQuestion`
confirmation points before every production-affecting step, and at least 3
distinct multi-attempt failure loops (cwd drift, repeated-command
construction ×2) that each cost several turns without forward progress.

## Follow-up changes named

- **Schema-migration inventory gap** (risk-accepted, event #1450): no
  committed list of every PostgreSQL deployment a schema-version bump
  needs to reach, and no automated sweep to check them all. Concrete
  options recorded in the source session note's "Schema upgrade /
  migration pathway" section, not yet implemented.
- **Ambient shell environment leakage** (risk-accepted, event #1449):
  `SPRINTCTL_BACKEND=remote`/`SPRINTCTL_URL` unconditionally exported from
  the shell profile on both the workstation and devbox-agent, now stale
  now that served mode is the intended default for migrated repos. Not
  fixed this session.
- **`direnv exec DIR CMD` does not `cd`** (lesson-learned, event #1448): a
  silent behavioral gap between assumption and reality that cost no
  errors but produced wrong results until a cwd-sensitive operation
  happened to expose it. Worth a one-line note in any onboarding/agent
  guidance doc that touches `direnv exec` usage patterns.
- **Command-construction failure loop pattern** (lesson-learned, event
  #1445): a general agent-behavior observation, not specific to this
  codebase — worth surfacing to whoever owns agent/harness development,
  since it's a signal that could be used to trigger a strategy change
  (e.g. "after N identical failed attempts, force a structurally
  different retry") rather than being purely the acting agent's
  responsibility to self-correct.
