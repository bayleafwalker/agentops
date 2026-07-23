# Lane B / Current Vuoro — Component Preflight

This is a reproducibility preflight, not a full Lane B run. All sources were
clean at the locked revisions recorded in `manifest.yaml`; no source file or
production service was changed.

## Claim and resume component contract

Command:

```sh
/tmp/vuoro-clean-room-lane-b-venv/bin/python -m pytest -q \
  /projects/dev/sprintctl/tests/test_claims.py \
  /projects/dev/sprintctl/tests/test_session_resume.py \
  -k 'transition_blocked_without_claim_proof or transition_allowed_with_claim_proof or explicit_handoff_success_rotates_token or lost_proof_can_be_explicitly_adopted_but_invalid_proof_is_rejected or session_resume'
```

Result: **13 passed, 56 deselected** in `0.11s`. The selected contract coverage
includes proof-required status mutation, proof rotation on handoff, lost-proof
adoption/rejection behavior, and session-resume rendering.

## Served transport component contract

Command:

```sh
/projects/dev/vuoro/.venv/bin/python -m pytest -q -p no:cacheprovider \
  /projects/dev/vuoro/tests/test_invocation_v2_transport.py \
  /projects/dev/vuoro/packages/vuoro-service/tests/test_invoke_v2.py \
  /projects/dev/vuoro/packages/vuoro-service/tests/test_app.py
```

Result: **29 passed** in `0.29s`. This is focused transport/service-component
coverage only; it is not live proof that the current multi-machine deployment
satisfies every R6 acceptance clause.

## Limits

No ten-actor fixture, crash/recovery injection, duplicate completion, dormant
clock, operational-cost capture, or reduced profile was run here. Therefore no
hard-gate or per-lane result sheet may be populated from this preflight.
