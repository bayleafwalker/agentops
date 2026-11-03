# Dormant terminal observation qualification

The [probe](probe.py) imported transport SHA-256
`50c61fc5a35f1de4f9f04c747311bddfa38b6c574011c4a1e79291afa6a4cd4a`
and exercised OpenCode 2.0.32 using temporary HOME/XDG, synthetic credentials
and a loopback fake provider in a no-egress namespace. The [sanitized
result](result.json) records the cases and observed outputs.

Stable single-input success, provider failure and interruption produced the
corresponding terminal observations. A held request was active. An interrupted
session with a pending queued input returned unknown; a queue in another session
did not affect the observed session. The unit tests also force changed bindings,
unexpected user attachments, assistant-model mismatch, changing histories,
queued inputs and cursor failure.

Each candidate observation uses two complete ascending transcript reads,
binding checks, activity checks and inbox readbacks. The server's cursors are
not snapshot-isolated, and multiple queued inputs can share an idle event. Two
consistent reads bound what was observed; they do not establish atomic
exclusion, causality in arbitrary sessions, or owner acceptance. The method is
not connected to the adapter runtime. Before integration, retain a terminal
record identity and interval digest for downstream evidence.
