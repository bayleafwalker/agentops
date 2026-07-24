# Workflow Artifact: process-quality lessons from a live production deploy

- **Date:** 2026-07-24
- **Source session note(s):** `.agents/sessions/2026-07-24-projection-cutover-1245-live-deploy.md`
- **Workflow(s) used:** single-agent direct execution (no dispatch/subagent
  pipeline) across sprintctl, vuoro, appservice, agentops.
- **Repos touched:** sprintctl, vuoro, appservice, agentops.
- **kctl tracking:** sprintctl item #1291 (sprint 428, `agentops` repo_id;
  renumbered from #1246 after a backfill), events #1566–#1573, #2068,
  #2069, #2070. First 8 events were extracted into the kctl review
  pipeline earlier this session; #2068–#2070 (the concurrency-race
  incident, the scope-creep lesson, and the effort-routing gap, all added
  later the same session) are recorded but **not yet extracted** — `kctl
  extract --sprint-id 428` currently fails with `invalid backend
  marker backend='served'. Expected 'local' or 'remote'.` once `agentops`
  itself moved to served mode. Root cause suspected but not yet confirmed:
  `kctl`'s uv-tool install pins its own separate copy of `sprintctl` as a
  local directory dependency (`/home/bayleaf/.local/share/uv/tools/kctl/
  uv-receipt.toml`), which may simply be stale relative to sprintctl's
  current served-mode-aware backend code. See the follow-up list below.

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

## Scope and effort-routing observations

Two further observations surfaced only on later reflection, not in the
moment they occurred, which is itself notable — both were about the
session's own shape rather than about a specific technical defect:

- **Scope crept well past the opening framing, without a dedicated
  checkpoint** (lesson-learned, event #2069). What began as "continue
  orchestration for track=projection-cutover" grew to include cross-repo
  git archaeology, a new served-catalog operation, a wire-protocol change,
  and a live production deployment with schema migration and secret edits.
  Every individual step got an `AskUserQuestion` confirmation, but nothing
  ever asked "does the *overall* scope this has grown into still match
  what you signed up for" as a question distinct from "ok to take this one
  next step." Per-step confirmation discipline does not substitute for a
  periodic scope-divergence checkpoint on long sessions.
- **No mechanism escalated effort/model tier as the risk profile rose**
  (risk-accepted, event #2070). The session ran at a low reasoning-effort
  tier throughout, fixed at the start based on the initial low-stakes
  framing, even after the actual work became live production Kubernetes
  administration, SOPS secret editing, and a real schema migration with
  incident response. Nothing — neither the harness nor the agent's own
  behavior — re-evaluated the tier as the work's blast radius grew. This
  is the same shape of gap as the scope-creep item above (a fixed initial
  assessment that nothing revisits as reality diverges from it), but about
  *capability allocation* rather than *user awareness*.

## Recurring across sessions (not just this one)

Cross-referencing prior-session memory on this same `#1164`/served-mode
effort surfaces the same handful of gap *shapes* recurring, not just
isolated incidents:

- **Ambient/stale config silently overriding intent** recurs across at
  least three sessions: session 3 needed a hand-fix for `backend.json`'s
  marker and `SPRINTCTL_VUORO_PROFILE` pointer confusion; this session hit
  it as a persistent shell-profile `SPRINTCTL_BACKEND`/`SPRINTCTL_URL`
  export (event #1571); and it recurred *again*, live, while writing this
  very artifact — `sprintctl item show` failed with `SPRINTCTL_BACKEND=served
  cannot be combined with SPRINTCTL_URL` from the same stale profile
  export, requiring another explicit `unset` mid-task. Three
  independent occurrences of the same root shape across different
  sessions is a strong signal this needs a structural fix (e.g. the
  ambient exports removed from the shell profile now that served mode is
  the default), not another one-off `unset`.
- **New capability ships without updating every dependent
  verifier/consumer in lockstep**: the CI Python-3.11 leg silently broke
  for ~15 hours across 7+ commits when served mode shipped
  ([[feedback-verify-real-ci-not-just-local-pytest]]); `doctor`'s
  served-mode catalog probe silently drifted out of sync with newly-wired
  routes in the same effort
  ([[project-vuoro-served-backend-1195]]); and this session's own
  in-progress `kctl extract` failure (above) is the same shape a third
  time — a client tool with its own bundled/pinned copy of `sprintctl`
  not updated when `served` became a valid backend value. Worth treating
  as a named category of risk ("client/verifier staleness relative to a
  server-side capability change") rather than three unrelated bugs.
- **Self-imposed scope restriction from a misread signal**: a past session
  ([[feedback-dispatch-harness-not-access-control]]) treated a repo's
  declared `default_harness` as a hard boundary rather than a routing
  preference, deferring work that should have been done directly. This
  session's effort-tier gap (above) is a related shape — an operating
  parameter (harness choice there, effort tier here) that nothing
  re-examines against the actual task once initial framing sets it.
- **Goal-completion claims have repeatedly needed correction across
  sessions**: session 4's own memory record
  ([[project-1164-session3-gate-status]]) explicitly warns future sessions
  not to infer "released and in production" from a narrower "ledger row
  closed" signal, because that exact conflation happened and had to be
  walked back. Worth keeping in mind when this session's own "released"
  framing (see the source session note) is picked up next — verify the
  full goal statement's scope again rather than trusting the last
  session's closing tone.

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
- **`kctl extract` doesn't understand the `served` backend marker**
  (surfaced, not yet filed as its own item): blocks extracting events
  #2068–#2070 into the kctl review pipeline. Suspected stale
  directory-pinned `sprintctl` dependency inside `kctl`'s own uv-tool
  install; a `uv tool install --reinstall kctl` retry is the first thing
  to try, and if that doesn't resolve it, `kctl`'s own backend-resolution
  code likely needs a small patch to accept `served` alongside
  `local`/`remote`. Same category as the CI-leg and doctor-probe staleness
  incidents above — not yet fixed this session.
- **Scope-divergence checkpoint gap** (lesson-learned, event #2069): no
  process currently prompts an explicit "here is everything this session
  has grown to include, still good?" checkpoint distinct from per-step
  confirmations. Not yet implemented as any concrete tooling change; named
  here as a candidate for future harness/agent-guidance work.
- **No effort/model-tier escalation signal** (risk-accepted, event #2070):
  no mechanism ties effort-tier selection to in-session risk signals
  (production credentials touched, live cluster mutation, schema/data
  migration). Named as a candidate for harness development, not
  implemented this session.
