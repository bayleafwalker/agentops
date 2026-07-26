# Handover: served-mode UX continuation

- Cut: `2026-07-26T09:38:31+03:00`
- Goal: make served mode safe and usable across workstation and devbox-agent.
- Scope boundary: source/configuration work is published; Vuoro release and
  appservice deployment remain separately authorized operator work.
- Secret handling: no database URL, credential, or claim proof is recorded.
- Live state: this session did not mutate a cluster, Flux, a live backlog,
  claims, outboxes, or recovery state.

## Published state

`sprintctl/main` is at `ac83121` and equals `origin/main`.

| Commit | Delivered source behavior |
| --- | --- |
| `dd5255a` | Served `event add`, `item add`, and basic `sprint show`; catalog and doctor routes; server-authenticated event actor. |
| `635a8e9` | Removes direct-backend rollback wiring from Sprintctl's committed environment. |
| `6ca0548` | Marker-less remote/served calls fail closed unless an explicit repo scope and invocation-only opt-in corroborate them; no global bypass. |
| `809165b` | `item show --id repo#id`, scope-conflict rejection, and redacted resolved context. |
| `749e757` | Doctor reports `backend-uncorroborated` as its own finding. |
| `3e57df4`, `7511450`, `02fac70`, `ac83121` | Scoped `repo#id` inputs for item status, served creation/read paths, item management, and claim create/start. |
| `a16e311` | Agent and doc-ref guidance requires `repo#id` on shared state. |

Related committed cutover configuration is on the owning repositories:

- `agentops` `e0f4da1`; `box` `9dc7a49`; `homelab-analytics` `032659a`;
  `scribectl` `51e7d60`.
- The selected-repository static gate passed for `agentops`, `actionq`, `box`,
  `homelab-analytics`, `scribectl`, and `sprintctl`.
- `_orchestration` is absent and `aligned-equity` remains on its user-owned
  branch; do not call the full workspace gate clean or edit that branch.

`agentops/main` is at `973682e` before this handoff commit. Its implementation
plan includes G/I/U served-readiness tracks in `9af951d`; upstream
`973682e` also refreshes the architecture-plan set.

## Evidence already captured

- Sprintctl focused suites passed while implementing the units: 111
  backend/served-route tests; 37 doctor/backend tests; 54 refs tests; 50 deps
  tests; 23 claim CLI tests; plus focused scoped-reference tests.
- `python /projects/dev/agentops/templates/dispatch/scripts/validate_verification_artifacts.py --root .`
  passed in Sprintctl.
- A broad suite was started more than once but entered an unrelated
  long-running I/O/integration segment; it was deliberately terminated. Do
  not represent the full suite as passing. Re-run it in a fresh session, with
  a foreground timeout and an explicit report of any skipped integration
  tests.

## Remaining source work

The UX plan remains incomplete. Continue in small, independently tested
commits; do not turn the checked-in partial behavior into a completion claim.

1. Finish `repo#id` parsing for remaining relevant item/claim/event/sprint
   arguments, including optional item targets and commands which render
   self-referential instructions. Preserve IDs that are genuinely local to a
   command (for example, a ref or dependency row ID) rather than pretending
   they are repository references.
2. Extend resolved-context reporting beyond `item show`: success, not-found,
   and empty output must name repository, source, backend, and a
   credential-redacted target without breaking established JSON contracts.
3. Make the preflight/taxonomy complete: doctor needs the remaining SF2-b/SF3
   diagnostics, and remote tombstone (`superseded_marker`) detection must be
   read-only and tested only against a disposable fixture.
4. Preserve unchanged local behavior. A marker without `repo_id` is not a
   non-local identity. Daemon/service environments need a committed marker or
   explicit per-invocation identity; never add a persistent allowlist.
5. Update status/evidence in `docs/plans/vuoro-ux-robustness-plan.md` only
   when a requirement has direct tests. Keep its D2--D8/D-new-1 acceptance
   criteria as the authoritative audit checklist.

## Next-agent session guidance

1. Start in `/projects/dev/sprintctl`; read `/projects/dev/AGENTS.md`,
   `sprintctl/AGENTS.md`, and
   `docs/plans/vuoro-ux-robustness-plan.md`. Fetch before trusting branch
   state.
2. Preserve untracked local files, especially `.claude/settings.local.json`
   in Sprintctl and the two older untracked Agentops handoffs. Do not reset or
   clean worktrees to remove them.
3. Work one bounded UX behavior at a time. Use `uv run --extra served pytest`
   on directly affected tests, `git diff --check`, and the verification
   artifact gate before each commit. Commit/push each independently passing
   unit to `main`.
4. If a broad test run stalls, stop only the test process started for that
   run, record the exact command and partial output, then run affected files
   sequentially. Never treat a killed run as evidence of success.
5. Do not perform database writes, claim mutations, wheel publishing, Vuoro
   pin changes, kubectl, Flux, or appservice reconciliation without the
   operator's separate authorization.

## Release and deployment handoff (operator-owned)

The deployed Vuoro work adapter is still behind the published Sprintctl
operations. After source UX work reaches its acceptance audit, an authorized
operator must:

1. release Vuoro/client-service artifacts containing `work.read.events`,
   `work.event.add`, `work.item.create`, and `work.read.sprint`;
2. update the consuming Vuoro/Sprintctl pin and deploy through Appservice;
3. verify doctor/catalog and real served reads/writes from both workstation
   and devbox-agent, including marker-less refusal and an explicitly scoped
   allowed invocation; and
4. report source, configuration, released-adapter, and deployed-runtime
   evidence separately.

The goal is not complete until that independently authorized runtime evidence
exists.
