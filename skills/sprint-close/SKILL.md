---
name: sprint-close
description: Use at the end of a sprint to verify the close gate, decide whether a real capability boundary occurred, preserve evidence, and close the sprint cleanly.
---

## Goal

Encode the full sprint close-out sequence so steps are not repeated ad-hoc across sessions. Produces a confirmed close gate, an explicit capability-boundary decision, a committed snapshot, reviewed knowledge candidates, and a closed sprint record.

## Inputs

- The sprint ID to close (confirm with `sprintctl sprint list` if uncertain).
- A local/recovery project DB via `.envrc` or exported `SPRINTCTL_DB` and
  `KCTL_DB`. The maintenance and knowledge-review portions below are not yet
  a normal served blind-agent workflow; do not replace unavailable catalog
  operations with direct-store access.
- Confirmation that all items intended for this sprint are in `done` or explicitly deferred.

## Steps

1. **Run the repo's sprint-close gate.** Use the verification commands from the repo's dispatch manifest or overlay (e.g., targeted tests, contract checks). Report pass/fail. If the gate fails, diagnose and fix before continuing. Do not close a sprint on a failing gate.

2. **Confirm sprint item health.** In served mode, use the released
   `work.maintain.check` composition through `kctl preflight`; do not invoke
   the direct `maintain check` CLI. If the selected deployed profile does not
   yet contain that contract, stop for an operator-recorded health decision
   rather than opening a local/direct store or continuing with an unverified
   close.

   In local/recovery mode:

   ```bash
   sprintctl maintain check --sprint-id <id>
   ```
   Review stale, blocked, or unreserved items. Decide whether to defer or carry forward unfinished work before proceeding.

3. **Record any final close rationale.** Add it before the sprint becomes
   terminal:

   ```bash
   sprintctl event add --sprint-id <id> --type decision --actor <actor> \
     --payload '{"summary":"<close rationale>","detail":"<what was deferred and why>"}'
   ```

4. **Close the sprint and retain its local boundary reference.** Explicit close
   atomically commits the status transition and one local boundary event:

   ```bash
   sprintctl sprint status --id <id> --status closed --actor <actor> --json
   ```

   Retain `boundary_event_id` and `boundary_revision` (`event:<id>`) from the
   response. Do not draft a sprint-close receipt unless this command succeeds.
   This revision is a local database row reference, not a content digest or a
   migration-stable identity. Preserve the Sprintctl database, event, and
   source mapping; a bound receipt is not independently durable if the event is
   deleted or resequenced.

5. **Decide whether this was a capability boundary.** Use
   `capability-receipt` when the evidence supports a newly reliable, cheaper,
   or better-governed capability. The receipt must use the
   `sprint-close-boundary` event from step 4 as its boundary ref. The skill
   writes an unpublished workspace draft, validates it, and records only its
   project, project-prefixed id, path, and SHA-256 digest in sprint state. It
   stops before establishment or publication -- not because a human must sign
   it off, but because a close-out has not yet determined the authority basis
   under which the delta is established. Validator success authenticates
   nothing about the actor.

   A routine sprint may legitimately contain no capability delta. Record that
   decision without manufacturing a receipt:

   ```bash
   sprintctl event add --sprint-id <id> --type decision \
     --actor <actor> \
     --payload '{"summary":"No capability receipt for this close","detail":"<evidence-backed reason>","tags":["capability","boundary"],"evidence_event_id":<boundary_event_id>}'
   ```

6. **Refresh the sprint snapshot.** Run `sprint-snapshot` to commit the final state. Use a standalone `chore:` commit.

7. **Extract knowledge.** Run `kctl-extract` only when its required served
   knowledge composition is released, or in separately authorized
   local/recovery mode. The served preflight has an owning health-check
   contract, but Kctl candidate/review composition remains release-pending.
   Do not use `--no-preflight` or a local store to bypass it.
   Key local/recovery steps:
   ```bash
   kctl extract --sprint-id <id>
   kctl review list --kind all
   ```
   Review all candidates before completing.

8. **Verify clean state.**
   ```bash
   kctl status --sprint-id <id> --kind all
   ```

## Output Contract

- Sprint close gate passes before close-out proceeds.
- All sprint items are in `done` or explicitly deferred with a recorded reason.
- Sprint status and the local `sprint-close-boundary` event commit atomically.
- The close records either a validated capability-receipt draft or an explicit
  decision that the sprint was not a capability boundary.
- Any drafted receipt stays `draft` and private until it is established with a
  recorded `established_by` and `authority_basis`. Validator success is not
  identity proof.
- Final snapshot committed.
- All knowledge candidates reviewed (approved or rejected).
- Sprint status is `closed` in `sprintctl`.

## Do Not

- Do not skip the close gate.
- Do not draft a sprint-close receipt before the close boundary event exists.
- Do not treat task completion or sprint closure as proof of capability.
- Do not establish or publish a capability receipt under an authority basis you
  do not hold. Establishing one under delegated authority is ordinary work; if
  the delegation genuinely does not cover it, that is
  `missing-delegated-authority` and belongs in a realignment session, not in a
  queue for a person.
- Do not close the sprint with `candidate` knowledge entries still unreviewed.
- Do not carry implementation work into close-out commits.
