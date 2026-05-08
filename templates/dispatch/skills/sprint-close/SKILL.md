---
name: sprint-close
description: Use at the end of a sprint to run the full close-out sequence: verify the close gate, snapshot sprint state, extract and review knowledge candidates, and mark the sprint closed.
---

## Goal

Encode the full sprint close-out sequence so steps are not repeated ad-hoc across sessions. Produces a confirmed close gate, a committed snapshot, reviewed knowledge candidates, and a closed sprint record.

## Inputs

- The sprint ID to close (confirm with `sprintctl sprint list` if uncertain).
- A loaded project DB via `.envrc` or exported `SPRINTCTL_DB` and `KCTL_DB`.
- Confirmation that all items intended for this sprint are in `done` or explicitly deferred.

## Steps

1. **Run the repo's sprint-close gate.** Use the verification commands from the repo's dispatch manifest or overlay (e.g., targeted tests, contract checks). Report pass/fail. If the gate fails, diagnose and fix before continuing. Do not close a sprint on a failing gate.

2. **Confirm sprint item health.**
   ```bash
   sprintctl maintain check --sprint-id <id>
   ```
   Review stale, blocked, or unclaimed items. Decide whether to defer, cancel, or carry forward before proceeding.

3. **Close the sprint in sprintctl.**
   ```bash
   sprintctl sprint status --id <id> --status closed
   ```
   If a final status comment is needed, add it as an event first:
   ```bash
   sprintctl event add --sprint-id <id> --type decision --actor <actor> \
     --payload '{"summary":"<close rationale>","detail":"<what was deferred and why>"}'
   ```

4. **Refresh the sprint snapshot.** Run `sprint-snapshot` to commit the final state. Use a standalone `chore:` commit.

5. **Extract knowledge.** Run `kctl-extract`. Key steps:
   ```bash
   kctl extract --sprint-id <id>
   kctl review list --kind all
   ```
   Review all candidates before completing.

6. **Verify clean state.**
   ```bash
   kctl status --sprint-id <id> --kind all
   ```

## Output Contract

- Sprint close gate passes before close-out proceeds.
- All sprint items are in `done`, `cancelled`, or explicitly deferred with a recorded reason.
- Final snapshot committed.
- All knowledge candidates reviewed (approved or rejected).
- Sprint status is `closed` in `sprintctl`.

## Do Not

- Do not skip the close gate.
- Do not close the sprint with `candidate` knowledge entries still unreviewed.
- Do not carry implementation work into close-out commits.
