# Sprint-State Write-Surface Policy

Status: adopted 2026-07-10

This document defines which surfaces may mutate sprintctl state, and under what
guarantees. It exists so that new cockpit API routes, MCP tools, and dispatch
templates can be checked against a stated boundary instead of re-deriving it.

## The rule

**Remote clients get intents. Execution happens where the invariants can be
enforced.** No remote surface is ever handed `SPRINTCTL_URL` semantics (raw
database write access).

## Tiers

### Tier 1 — direct CLI (full write surface)

Sessions with a shell and the project env (devbox, workstation, in-cluster
pods, dispatched worktrees) use the `sprintctl` CLI directly. This is the only
tier with the full command surface. It is privileged not because of *where* it
runs but because it can run the gates: test-gated done transitions
(`pytest … && sprintctl item done-from-claim …`), claim ownership proof from
per-session env (`SPRINTCTL_INSTANCE_ID`, `SPRINTCTL_RUNTIME_SESSION_ID`), and
direnv-scoped configuration.

### Tier 2a — mediated API writes (server-validatable transitions only)

The cockpit may expose a write route for a transition **only if** every
invariant of that transition can be checked server-side, with no dependency on
working-tree evidence. Each such route must:

1. Enforce the same transition rules as the CLI (`SPRINT_TRANSITIONS`,
   `VALID_TRANSITIONS` in sprintctl `db.py`) — parity, not a superset.
2. Record the mutation in the sprintctl `event` ledger with a truthful `actor`
   (`operator:cockpit`, `mcp:agent-cockpit`, …) so API writes carry the same
   provenance as CLI writes.
3. Pass write auth (below).

Current allowlist:

| Route | Transition | Why it qualifies |
|-------|-----------|------------------|
| `POST /cockpit/api/sprints/activate` | sprint `planned -> active`, kind -> `active_sprint` | Pure state transition; no working-tree evidence involved |
| `POST /cockpit/api/dispatch` | enqueue actionq action | Doesn't mutate sprint state; hands an intent to Tier 1 |
| `POST /cockpit/api/dispatcher/pause` | dispatcher pause file | Operational toggle, not sprint state |

Explicitly **not** eligible for API routes: `item done-from-claim`, claim
start/heartbeat/handoff/release, anything whose correctness depends on tests,
review artifacts, or claim-token possession. These stay Tier 1, reachable
remotely only via dispatch.

### Tier 2b — dispatched writes (evidence-gated transitions)

Remote clients that need an evidence-gated mutation dispatch an actionq action.
The dispatched agent runs in a worktree with the full env and executes the CLI
itself, so the gate travels with the write. This is the sanctioned remote write
path for everything not on the 2a allowlist.

### Tier 3 — reads

Cockpit read routes (`repos`, `sprints`, `takeup`, `claims`, `events`,
`audit`, …). No auth beyond network posture today.

## Write auth

- `COCKPIT_WRITE_TOKEN` (env, from a k8s secret) enables enforcement. All
  Tier 2a routes then require `Authorization: Bearer <token>` or
  `x-cockpit-write-token: <token>` (compared timing-safe; see
  `apps/web/lib/cockpit/auth.js`).
- Unset token = legacy-open for the browser routes (rollout compatibility),
  but the MCP endpoint is **disabled** until a token is configured — new
  surfaces do not inherit the legacy-open default.
- The browser UI reads the token from `localStorage["cockpit_write_token"]`
  and attaches it to write calls. Set it once per browser via devtools:
  `localStorage.setItem("cockpit_write_token", "<token>")`.
- Rotation = update the k8s secret and re-set the browser/localStorage and MCP
  client credentials. Single-operator scope; no per-user identity is claimed.

## MCP endpoint

`POST /cockpit/api/mcp` is a stateless streamable-HTTP MCP server for
claude.ai-style clients. It is a **protocol adapter over this policy**, not a
second sprintctl client:

- read tools (`list_repos`, `list_sprints`, `list_events`, `list_claims`) →
  Tier 3 lib functions;
- `activate_sprint` → the Tier 2a allowlist;
- `dispatch_action` → Tier 2b.

Adding an MCP tool that mutates sprint state requires the same justification
as adding a 2a route. If it can't be validated server-side, it must be a
dispatch template instead.

## Related

- `docs/plans/agentops/` — cockpit workstream plans
- sprintctl `docs/guides/remote-mode.md` — backend/claim semantics
- actionq session read contract — session identity joins
