# Handoff: close Vuoro blind-agent workflow parity

- Target environment: `devbox-agent`
- Start repository: `/projects/dev/agentops`
- Current deployed service: `vuoro-service-v0.1.5`
- Appservice revision: `ba841bd5`
- Runtime digest: `sha256:8f5f8d1b68f29e13e68597fab57caa4d1e9942753ad52958c4b2f5e601d9d87d`
- Evidence source: `.agents/sessions/2026-07-26-served-mode-ux-continuation-handoff.md`

## Current verdict

Vuoro is healthy and the deployed Sprintctl work adapter supports the core
happy path: catalog/doctor, sprint and event reads, item creation, event
creation, next-work, item show/note/status, sprint status, and claim
start/heartbeat/handoff/release. Both workstation and devbox-agent passed real
served reads, writes, marker-less refusal, and explicit scoped invocation.

Do **not** claim complete remote-mode parity or blind-agent readiness yet.
A newly dropped agent following the checked-in guidance cannot consistently
orient, inspect conflicts and refs, resume, or produce a tracker handoff:

- `usage --context` falls through to the direct PostgreSQL path in served
  mode; scoped sprint input is integer-only.
- `item list`, `item ref list`, and `claim list-sprint` fall through to the
  direct path and currently fail with the misleading `psycopg is not
  installed` message.
- `handoff --sprint-id` is integer-only and is not served-backed.
- `next-work --explain` explicitly has no served equivalent.
- `sprint list --project` and `sprint show --detail` explicitly have no
  served equivalents.
- Item-ref writes/removal, dependency inspection/mutation, and claim
  list/show/resume/recovery have no established served parity.
- Kctl served extraction works, but its `maintain.check` preflight diagnostic
  is explicitly unsupported.
- The canonical `task-pickup` and project guidance still instruct agents to
  run several of the unsupported commands above.
- The Vuoro repository itself still has a `remote` backend marker. It was
  deliberately excluded from the earlier workstation cutover, so a blind
  agent in `/projects/dev/vuoro` does not have the same served-ready contract
  as one in Agentops.
- `actionq-daemon.service` was inactive on devbox-agent during this assessment.
  This is not a Vuoro service failure, but unattended orchestration readiness
  must not be inferred from interactive Sprintctl success.

The failures are fail-visible—there is no observed silent local fallback—but
several messages incorrectly suggest installing the remote extra. Agent UX is
therefore safer, not yet clear or complete.

## Next orchestration goal

Make a blind agent dropped into any opted-in repository, specifically
Agentops and Vuoro, able to complete the whole governed loop using only served
authority:

`orient -> inspect backlog/conflicts/refs -> choose -> claim/resume -> iterate
with notes/refs/deps -> create follow-up work -> finish/release -> hand off`

The goal is complete only when:

1. Every command prescribed by `AGENTS.md`, `task-pickup`, `sprint-resume`,
   and `item-done` either has a served catalog route with direct tests or is
   removed/replaced in guidance by an equivalent served workflow.
2. At minimum, served mode supports `usage --context`, `item list`, item ref
   add/list/remove, dependency add/list/remove, claim list/list-sprint/show/
   resume, and tracker `handoff`; all repository/sprint/item inputs accept
   `repo#id` where ambiguity exists.
3. `next-work --explain`, project-wide orientation, sprint detail, kctl
   preflight, and claim recovery receive explicit decisions: implement a
   catalog aggregate, provide an honest served composition, or remove them
   from the blind-agent contract. No direct-store emulation.
4. Every unsupported served command fails before store creation with one
   stable `served-operation-unavailable`-class error and actionable guidance;
   none emits `psycopg is not installed`, opens SQLite/Postgres, or suggests
   switching back to `remote`.
5. Vuoro repository backlog state is deliberately migrated/backfilled and
   both workstation and devbox clones select a validated served profile and
   `served` marker. Preserve recovery-only direct tooling separately.
6. The currently pinned production image is revalidated across all four
   domains—work, execution, knowledge, and audit—with accepted and rejected
   black-box calls. Catalog presence alone is not functional evidence.
7. A disposable two-agent rehearsal on devbox proves one agent can create and
   shape an item with refs/deps, a second can discover and claim it, the first
   sees the conflict, ownership can hand off/resume, the worker can finish and
   release, and a fresh session can reconstruct state from the served handoff.
8. Static guidance checks and the selected-repository cutover validator pass
   for the declared repository set. Real workstation and devbox-agent smoke
   runs use the same commands a blind agent is told to use.

## Priority order

1. **P0 — inventory and fail-closed guard.** Build a command-by-command matrix
   from the guidance and CLI; stop every unserved command before `_get_store`.
   This removes misleading direct-backend failures immediately.
2. **P0 — blind-agent read/resume surface.** Implement context, item/ref/dep,
   claim inspection/resume, and tracker handoff reads first. Without these,
   safe pickup and recovery are impossible.
3. **P0 — shaping writes.** Add item-ref and dependency mutations so a served
   agent can create a legitimately governed backlog item, not only a title.
4. **P1 — decision-support aggregates.** Resolve `next-work --explain`,
   project sprint listing/context, sprint detail, and kctl preflight.
5. **P1 — Vuoro repo cutover and guidance reconciliation.** Make Agentops and
   Vuoro behave identically for a blind session, then update canonical skills.
6. **P1 — four-domain and two-agent acceptance.** Release/deploy only after
   independent verification; capture source, artifact, configuration, and
   runtime evidence separately.

## Devbox start

Preserve all untracked files. Fetch before trusting status. The Agentops
checkout currently has two pre-existing untracked session handoffs and
Sprintctl has `.claude/settings.local.json`.

Use invocation-scoped settings until the blocked local direnv files have been
reviewed; do not persistently trust them implicitly:

```bash
cd /projects/dev/agentops
env -u SPRINTCTL_URL \
  SPRINTCTL_BACKEND=served \
  SPRINTCTL_VUORO_PROFILE=/projects/dev/agentops/templates/dispatch/environment-record/profiles/devbox-agent-vuoro-shared.json \
  sprintctl doctor --json
```

First implementation artifact: a checked-in parity matrix mapping every
guidance-prescribed command to `served`, `explicitly unsupported`, or
`recovery-only`, with a failing CLI test for each P0 gap. Do not start by
adding one-off routes without this inventory.

No release, Appservice, Flux, cluster, credential, direct-database, or daemon
mutation is authorized by this handoff. Obtain separate operator authority
after source acceptance.
