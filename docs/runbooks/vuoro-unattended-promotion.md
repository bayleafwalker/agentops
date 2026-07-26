# Vuoro unattended-dispatch promotion gate

This runbook is the operator handoff for promoting the claim-safety changes
that follow Vuoro v0.1.9. It authorizes neither an image build nor a cluster
change; those remain owner-controlled deployment actions.

## Required source revisions

- ActionQ: `d344cc2` or a descendant. It contains ActionQ schema v2, opaque
  claim receipts, terminal settlement fencing, dual-authority supervision,
  settlement evidence, and the complete disposable cross-authority fault
  matrix.
- ActionQ dispatcher: `6436306` or a descendant. It no longer publishes the
  colliding `actionq-daemon` command.
- Vuoro: `b652c4f` or a descendant. Its service CLI exposes only operations it
  can actually perform.
- Agentops: `0e8dac8` or a descendant. Cockpit and manifest skill catalogs
  agree.

## Ordered promotion

1. Build and sign an immutable ActionQ artifact from the required revision.
   Record its digest and checksum in the Vuoro composition source; do not use a
   mutable tag.
2. In an owner-authorized foreground deployment job, run `actionctl migrate
   --json-output` with the migration role. Confirm schema version `2` and an
   empty subsequent migration result.
3. Verify the runtime role with `actionctl check-compatibility`; it must report
   `compatible: true`, observed schema version `2`, and must not hold DDL
   authority.
4. Install the ActionQ package as the sole provider of `actionq-daemon` on the
   execution host. Confirm `command -v actionq-daemon` resolves to that package
   and `actionq-dispatch` supplies only `dispatcher-once`.
5. Pin the new immutable artifact in Vuoro composition and the application
   deployment. Perform the separately authorized rollout.

## Disposable independent fault gate

Run these only against a disposable queue and sprint authority. Capture the
ActionQ event history, Sprintctl claim history, daemon state, and child PID
result for each case.

| Fault | Required result |
| --- | --- |
| ActionQ lease expires then action is swept/reclaimed | Old receipt cannot renew or settle; only the new receipt can terminally transition. |
| Sprintctl heartbeat rejects | Daemon terminates the child; no ActionQ completion is recorded. |
| ActionQ renewal rejects or response is lost | Daemon terminates the child and does not settle as success. |
| Sprintctl release fails | `settlement.pending` and `settlement.sprint_claim_release_failed` are durable; ActionQ records failure, never completion. |
| Shutdown during child execution | Child stops, session end is recorded, Sprintctl takeup/claim cleanup is attempted, and no stale receipt can settle after restart. |
| Process crash between Sprintctl release and ActionQ terminal command | Journal shows `settlement.pending` plus the Sprintctl release record; operator/recovery procedure chooses the fenced ActionQ terminal action only after inspecting both authorities. |

Do not enable unattended dispatch if any case lacks durable evidence. This gate
does not establish high availability: the current single-replica deployment
still requires a separate continuity design and failure rehearsal.
