# Fixture-only cancellation qualification

The [portable probe](probe.py) imports source from read-only `/tmp/fixture`
mounts after verifying SHA-256: host adapter
`f963419e2dcf4be2f09982d764ea99216c2f3691ee5f923b19b4d035455bf575`, v2 client
`be29305b7ec8167495eea1fa8e0bc50b6f8937815466a7dfc00260ecd6848766`, and
profile validator `110a7583802157a446fbd327acb06940916d29334a8fa8772d3fa90dd709cd56`.
It ran twice against pinned OpenCode 2.0.32 with synthetic owner/delegation,
temporary state and a loopback fake provider inside `bwrap --unshare-net`.
The [sanitized result](result.json) contains no generated credential.

For a sole running input, the fixture sent one interrupt, deliberately lost the
response, and did not resend after restart. It closed only after observing the
interrupted terminal record. A foreign queued input blocked session-wide
interrupt and remained unresolved. Observed success won a cancellation race.

**Sole queued deletion is unqualified.** A queue request on an idle session
was immediately projected into a completed transcript; inspection returned
unknown and the probe issued no DELETE. The orchestration explicitly defers queued deletion without authorizing or
sending DELETE; unit fixtures cover the low-level helper but do not establish a
real single-pending-input case. Earlier exact-binary
evidence shows a wrong-session DELETE can return 204 without deleting its true
target. Neither that response nor an empty queue proves cancellation.

To rerun, stage the exact source files above and mount them read-only under
`/tmp/fixture` in a no-egress bwrap namespace with temporary HOME/XDG. The
injected fixture must control all session writers; non-atomic observations do
not enforce that property. Repeated complete-history comparisons may defer an
interrupt indefinitely while a transcript streams. This phase is default off,
and does not qualify real Vuoro RPC, arbitrary sessions or deployed service.
