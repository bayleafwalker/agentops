# Dormant OpenCode v2 interrupt client qualification

The [probe](probe.py) imported client SHA-256
`638c52496b0ca3cb7cd2f9204ddec9628e32d13615dad95f730c00b46476a5dc`
and exercised the pinned OpenCode 2.0.32 server with temporary HOME/XDG,
synthetic authentication and a loopback-only fake provider under no-egress
bwrap isolation. The [sanitized result](result.json) records the observations.

The client requested deletion of a queued input; inbox readback showed it
absent, and after drain it was absent from the transcript and fake-provider
requests. Deleting another session's ID returned HTTP 204 and an acknowledged
client result while the input remained in its owning inbox. Active interruption returned `interrupted: true`, while first and repeated idle interrupts returned `false`; a queued input remained after the terminal idle. Thus
both client methods report request acknowledgement only; callers must reconcile
the queue, activity and transcript independently and never infer completion or
cancellation from these responses. Lost-response recovery is covered by the
separate [terminal probe](../opencode-v2-terminal-interrupt-2032/README.md).

The local wire tests passed, and deliberately removing the 204 status check
made the HTTP-200 negative control fail. The methods are not connected to the
adapter runtime and do not qualify deployment or terminal correlation.
