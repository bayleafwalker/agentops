# OpenCode 2.0.32 `/api/session/active` observation

`probe.py` directly calls authenticated `GET /api/session/active` against the pinned 2.0.32 server. It does not infer this endpoint from OpenAPI. The fixture runs on `devbox-agent` inside Bubblewrap with networking unshared, temporary HOME/XDG roots, synthetic Basic auth and a loopback-only fake provider. No real provider configuration or credentials are read, and the generated password is not recorded.

The retained result removes generated session IDs while preserving the response envelope, entry count, whether an entry key matched the test session, and each record value.

## Observed values

- Before creating any session, and after creating an idle session: HTTP 200, JSON object with `data` as an empty object.
- While a fake provider request was held: HTTP 200, `data` had one key matching the test session ID, with `{ "type": "running" }` as its value.
- After interrupt was acknowledged and the terminal idle record appeared: `data` was empty.
- In a separate transient-failure case, the fake provider had returned two HTTP 503 responses before the snapshot. `data` still contained the matching session with `{ "type": "running" }`. After interrupt and terminal idle, `data` was empty.

The probe asserts these expected shapes. A separate negative control reverses the first idle-map assertion in a temporary copy; it exits nonzero with `AssertionError: idle active map unexpectedly nonempty`. The retained probe is not modified by that control.

## Limits

This is a small controlled observation on one exact build, not a guarantee about all lifecycle transitions. The route is a point-in-time snapshot: a turn may start or finish between the request and response, so callers must tolerate state changing immediately after reading it. The result cannot establish race-free absence or presence outside the observed windows.

The 503 case establishes that the session remains listed as `running` after two failed provider requests. It does not reveal retry/backoff phase: the returned type is the same as for a held ordinary request, and the endpoint carries no prompt ID, attempt count, or error detail. It therefore cannot distinguish actively retrying from a generic running state.
