---
name: sprint-resume
description: Use when work already exists in sprintctl and the request is to continue, pick up, or resume an existing sprint item. Covers reservation checks, handover behavior, and live-state verification before repo edits.
---

## Goal

Resume an already-registered sprint item from live `sprintctl` state without duplicating work, silently interrupting another session's reservation, or losing knowledge that should flow into `kctl` later.

## Inputs

- A request to continue sprint work, pick up the next item, or resume an already-scoped brief.
- A loaded project DB environment via `.envrc` or exported `SPRINTCTL_DB`.
- The relevant sprint item, reservation, and recent event state.

## Steps

1. Confirm the work already exists in `sprintctl`. If it does not, stop and use `sprint-packet` instead.
2. Load the project DB first via `.envrc` or exported `SPRINTCTL_DB`.
3. Inspect live sprint, item, reservation, and event state before touching repo files:
   `sprintctl sprint show --json`, `sprintctl item list --sprint-id <id> --json`, `sprintctl item show --id <item-id> --json`, `sprintctl reservation list --item-id <item-id> --all --json`.
   Recovery after context loss is a plain lookup: reservations carry no secret, so there is no token to find and nothing to have lost.
4. Check reservation state:
   - If no active reservation exists, `sprintctl reservation reserve --item-id <id> --actor <actor> --session-id <session-id> --json`.
   - Record the returned reservation `id` and `session_id`. There is nothing secret to persist.
   - If the active reservation is this session's, continue. `sprintctl reservation touch --id <id> --session-id <session-id>` refreshes the activity clock; it is optional, not a lease renewal, and nothing expires for want of it.
   - If it belongs to another session, do not edit repo files. A reservation is advisory and `--override` always succeeds, so the decision is a coordination one, not a permission one: prefer `sprintctl reservation reassign` for a planned handover, and treat override as an operator-visible interruption.
   - A reservation reported `stale` has simply been inactive; that is a display heuristic, not an expiry, and it does not by itself transfer ownership.
5. Use a stable `--session-id` per live client or process start (for Codex, `CODEX_THREAD_ID` works well). It identifies the session for coordination and audit; it proves nothing and authorizes nothing. Run `sprintctl agent-protocol --json` for the canonical, machine-readable command shapes -- prefer it over any command written out in this file.
6. Move the item to `active` before implementation with `sprintctl item status --id <item-id> --status active --expected-revision <revision>`. Read the current revision from `sprintctl item show --id <item-id> --json`; the transition is a compare-and-swap and is durably rejected if the basis is stale.
7. Record structured `sprintctl` events when design choices, resolved blockers, or reusable lessons occur. Use `decision` or `lesson-learned` types with `summary`, `detail`, `tags`, and `confidence` payload keys. The bar is met when any of these occur:
   - A design choice was made between two viable options
   - A blocker was resolved by a non-obvious fix
   - A pattern emerged that applies to other items or future sprints
   - A migration or schema decision was made
   - An integration failure revealed a wrong assumption
   Log immediately — context degrades fast, and retroactive logging at sprint close produces thin candidates.
8. If work pauses or changes hands, use `sprintctl reservation reassign --id <id> --actor <next-actor> --session-id <next-session-id>` to transfer it in place, then `sprintctl handoff --output <path>` when the next session also needs broader sprint context. Keep handoff artifacts local unless a tracked artifact was explicitly requested.
9. When implementation completes, set the item done and release the reservation:
   `sprintctl item status --id <item-id> --status done --expected-revision <revision>` then `sprintctl reservation release --id <id> --actor <actor>`. These are two operations rather than one: releasing is a coordination signal, and the transition is guarded by the revision CAS rather than by ownership.
10. After material sprint-state changes, refresh the shared snapshot with `sprint-snapshot`.

## Output Contract

- Repo edits start only after live ownership is clear.
- Item status, relevant events, and snapshot state stay aligned with the actual execution state.
- Knowledge-worthy lessons are recorded while context is hot.

## Do Not

- Do not pick the next task from docs when existing item state is available in live `sprintctl`.
- Do not adopt another session's active reservation because the actor label looks familiar. Reassign or override it deliberately, or leave it alone.
- Do not look for ownership proof at all. There is none by design: a reservation records who is working on what so conflicts surface, and no sprintctl mutation checks it.
- Do not start implementation before the reservation state is clear.
- Do not wait until sprint close to log a lesson that should become an event now.
