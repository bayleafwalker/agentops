# Lane 0 / `td` — Initial Control Observations

Run: `2026-07-23-lane-0-td`  
Participant: `td version v0.51.3-0.20260718194829-b739b10255e7`  
Source: `b739b10255e71f39ef7490ef0177e556db5b285c`

All commands ran in the disposable fixture named in `fixture-lock.yaml`. No
network service, production credential, or project repository was used.

## Recorded commands and results

1. `td dep add td-ab3936 td-679ead` reported that `guarded-mutation` depends
   on `bootstrap`.
2. With `bootstrap` still `open`,
   `TD_CONTEXT_ID=actor-blocked td start td-ab3936 --json` returned
   `"action": "started"` and `"status": "in_progress"`. The follow-up
   `td deps td-ab3936 --json` still listed `td-679ead`. This is recorded, not
   prevented, dependency handling.
3. `TD_CONTEXT_ID=actor-a td start td-7399ae --json` set
   `implementer_session` to `ses_87f5cd`. A second
   `TD_CONTEXT_ID=actor-b td start td-7399ae --json` exited `0` with no proof
   prompt, challenge, or authority result. A follow-up `td show` retained only
   the first session identifier. The interface exposes neither a proof nor a
   proof-gated mutation operation, so this does not meet R2 regardless of the
   second command's no-op behavior.
4. `TD_CONTEXT_ID=actor-handoff td handoff td-b4088f --done "fixture
   established" --remaining "cold actor must continue" --decision "keep state
   in td" --uncertain "no proof authority" --json` returned a handoff with all
   four structured fields. `TD_CONTEXT_ID=actor-resume td usage --new-session
   --json` then listed ready work. This is a same-session-age structure probe,
   not a qualifying cold-resume or conflict-detection result.

## Reproduction

Build the pinned source using the command in `candidate-lock.yaml`, create the
fixture state in `fixture-lock.yaml`, then run the commands above in order. The
issue IDs are generated per fixture; substitute the IDs created in the new run.
