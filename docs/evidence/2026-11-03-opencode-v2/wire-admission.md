# Dormant prompt admission wire qualification

The [probe](wire-admission-probe.py) imported transport SHA-256
`78c627e98b989fd69f119c9d34d50f33b336bc7057e0daadf0759ee86c19a25a`
and exercised the pinned OpenCode 2.0.32 server in an isolated, no-egress
namespace with synthetic credentials and a loopback fake provider. The
[sanitized result](wire-admission-result.json) records observations.

The client's submission sent `{id, text}` and received the matching user
acknowledgement. Its observer found a separately queued synthetic input in the
inbox while inference was held, and then in the transcript after drain; both
observations preserved the ID, session and text digest. The observer followed
pagination through the empty terminal page. The client's submission uses the
server's default delivery; the probe used the API directly to create the
queued case. It did not establish restart guarantees or client retry safety.

Unit tests cover lost responses, conflict, malformed acknowledgements, missing
and repeated pages, and empty projections. Removing the digest comparison made
the conflict test fail. This is admission evidence only, not execution outcome,
product acceptance or authority to launch. These methods remain disconnected
from the adapter runtime.
