# Terminal producer identity qualification

The [portable probe](probe.py) imports the v2 client from a read-only mount and
verifies SHA-256 `4d9f05e108540ea49db62923c59696b77a3eca05333c37e2f4d6b6ed5096d1a0`.
It ran twice against pinned OpenCode 2.0.32 with synthetic credentials and a
loopback fake provider in a no-egress namespace. The [sanitized result](result.json)
contains no generated credentials.

For success, provider failure and interruption, returned session ID, prompt
ID and text digest matched the created session, submitted text and independently
paginated transcript. Terminal ID and interval digest also matched independent
reads. A queue in the observed session returned unknown after interruption;
a queue in another session did not affect a separate successful observation.
The two-read result is bounded and non-atomic; it is not owner settlement or
proof of permanent session exclusivity. The state recorder trusts its local
caller and separately checks the producer's identity against frozen bindings.

To rerun, stage the client at the hash above and mount it read-only at the path
expected by the probe inside `bwrap --unshare-net`, with temporary HOME/XDG.
No production service, owner RPC or real provider is involved.
