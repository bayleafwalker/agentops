# OpenCode 2.0.32 terminal, interruption, and queue evidence

This is a disposable API observation against the pinned OpenCode 2.0.32 binary. The probe runs on `devbox-agent` under Bubblewrap with networking unshared. It uses a temporary HOME/XDG data root, synthetic local auth, and a loopback-only fake provider. It reads no real provider credentials or config, records no generated password, and makes no production requests.

Run `probe.py` over SSH to `devbox-agent` on stdin, inside `bwrap --unshare-net --ro-bind / / --tmpfs /tmp --dev /dev --proc /proc --clearenv`, with a system PATH. Capture stdout as `result.json`. The script embeds the pinned binary path and checks the returned version is exactly `2.0.32`.

## Observations

- OpenAPI lists `POST /api/session/{sessionID}/interrupt` and `DELETE /api/session/{sessionID}/inbox/{inboxID}`. It lists no session-status GET endpoint.
- Interrupt of a held prompt returns `200 {"interrupted":true}`. Transcript evidence is an assistant with `finish: error` and `error.type: aborted`, followed by an idle record with `outcome: interrupted`. The idle record has a different ID from the prompt. The prompt ID does match its user transcript row. This probe establishes no prompt-to-idle correlation.
- With a queued successor, interrupt leaves the successor in the inbox immediately and after waiting; that input is absent from transcript. Interrupt acknowledgement is not queue cancellation.
- Explicit queue deletion whose response is dropped: the proxy observes upstream `204` with an empty body, while the client gets `RemoteDisconnected`. Inbox readback no longer contains the queued ID; after the active turn drains, it is absent from transcript and fake-provider calls.
- Negative control: deleting session B's inbox ID through session A returns `204`, while the item remains in B's inbox. A `204` alone does not prove the intended item was removed.
- Repeated same-ID/same-text queue submission leaves one inbox row. Same-ID/different-text also gets `200`, but the acknowledgement retains the original text. Two distinct queued inputs drain in order, each with its assistant response, followed by one `succeeded` idle. A foreign session's queued input is isolated to its own inbox and transcript.
- A no-route prompt is acknowledged with `200`; terminal evidence is an idle with `outcome: failed` and `error.type: provider.no-route`. No assistant transcript row was observed.
- Eighteen synthetic turns yield 54 transcript rows. A single default GET response contains 50 rows; explicit `limit=50` pagination returns 50, 4, then 0 rows. The oldest prompt falls on page 2. All 54 message IDs and the session survive restarting the server against the same temporary data root.

The JSON distinguishes the default one-response count (`first_response_*_count`) from the full paginated count (`paged_*_count`). These findings apply only to the pinned build and disposable fixture; they do not assert general API guarantees.

## Assertion negative control

To demonstrate the version guard fails, make a temporary copy of `probe.py`, change its expected version literal from `2.0.32` to `2.0.31`, run that copy with the same isolated command, and require nonzero exit with `AssertionError: pinned server version mismatch`. Do not edit the retained fixture for this control. This intentionally falsifies a specific observed invariant; it is separate from the wrong-session deletion negative control above.
