---
name: task-pickup
description: Use when choosing the next sprintctl task to execute. Consult live state first and reserve work before editing when overlap is possible.
---

## Goal

Choose one executable item from live sprintctl state without duplicating work, silently interrupting an existing reservation, or treating stale docs as the execution queue.

## Inputs

- A loaded project DB environment via `.envrc` or exported `SPRINTCTL_DB`.
- The current actor and a stable `session_id` for this session.
- The repository's active-sprint and backlog policy.

## Steps

1. Inspect live state before choosing anything:
   ```bash
   sprintctl sprint list --active --json
   sprintctl sprint list --include-backlog --json
   ```
2. If no active sprint exists, select an eligible backlog sprint or create/promote one only under the repository's sprint policy. Do not invent a replacement sprint from an old snapshot when a live backlog already exists.
3. For the selected sprint, inspect existing reservations first:
   ```bash
   sprintctl reservation list --all --json
   ```
   If an active reservation belongs to the current session, delegate recovery to `sprint-resume` rather than selecting new work.
4. Otherwise, ask sprintctl for an explainable candidate set:
   ```bash
   sprintctl next-work --sprint-id <sprint-id> --json --explain
   ```
5. `next-work` orders ready candidates by the native priority field (`item add --priority N`, `item priority --id N --set N`; 1 = highest, unprioritized last), falling back to the legacy `[pN] ` title prefix when no native priority is set. Trust its order; refine only when two candidates tie.
6. Read the chosen item's details, refs, and dependencies before reserving it. Resolve a blocking dependency or choose another ready item instead of reserving around it.
7. Reserve the item for this session and retain the returned reservation `id`:
   ```bash
   sprintctl reservation reserve --item-id <item-id> --actor <actor> \
     --session-id <session-id> --json
   ```
   A reservation carries no secret, so there is nothing to store securely and
   nothing to lose. Reserving never fails because somebody else got there
   first: the response carries `conflict`, `conflicting_reservations`, and
   `conflict_severity`, so read it and coordinate. Two active `execution`
   reservations are reported as a `warning`; `execution` beside
   `verification` or `observation` is ordinary. Use `--role execution` when
   you are doing the work, `verification` when reviewing or testing it, and
   `observation` when watching or orchestrating it.
8. Continue through `sprint-resume` for the implementation lifecycle.

## Output contract

- One selected item is traceable to live `next-work` output or an explicit repository-approved promotion decision.
- The item's priority is visible in the `PRI` column of `item list` and `next-work` (native `priority` field, or legacy `[pN] ` title prefix as fallback).
- Active work is covered by an active `execution` reservation held by the current session, and any overlap reported at reserve time was read and acted on.
- Any inability to choose safely is reported as a blocker with the relevant reservation, dependency, or sprint state.

## Do not

- Do not choose work from a committed snapshot or plan before inspecting live sprintctl state.
- Do not treat a reservation as an enforced lock, or expect the database to keep others out. Nothing is enforced: several sessions may hold active reservations on one item, and `reserve` records the overlap rather than refusing it. Ownership is a coordination signal, not a permission check.
- Do not use append-only note tags as a priority queue; `next-work` does not order by them.
- Do not `--interrupt-existing` on an item another session is actively working on. Coexisting is allowed and is usually the right move: register your reservation, read the conflict, and talk to the other session. A takeover is proof-free and always succeeds, which is exactly why it needs a human-visible reason: prefer `reservation reassign` for a planned handover, and treat `--interrupt-existing` as an operator-visible interruption of the other session.
- Do not edit implementation files before the item is reserved when parallel overlap is possible.
