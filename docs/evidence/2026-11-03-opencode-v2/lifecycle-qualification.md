# OpenCode 2.0.32: policy and lifecycle observations

The accompanying synthetic probes run the pinned devbox binary in a disposable
network namespace with a loopback fake provider, generated temporary
credentials and no external inference. They do not exercise the installed inbox,
real owner operations, or deployed containment.

The policy probe sent the same synthetic shell call under allow and deny. The
allow case executed a harmless temporary sentinel; the deny case rejected the
call even when the fake provider emitted it despite seeing no tools. Ordered
narrow rules allowed fake `sprintctl run context` and `note`, while rejecting
`publish` and a semicolon-chained command. Reversing deny/allow order removed
shell. A denied tool call could still be followed by a `succeeded` idle event;
that is a harness outcome, not proof of a successful owner effect or product
acceptance.

The message probe observed the prompt response ID on its user message, but the
terminal idle event had a different ID and no typed input reference. A queued
second input appeared in the inbox and transcript, and the drain produced one
idle event for both turns. Interruption produced an interrupted idle; a missing
model produced a failed idle; a local HTTP 503 remained retrying without a
terminal idle within the bounded observation. These are observations of this
binary and fixture, not a general exactly-once or correlation guarantee.

The shell metacharacter probe exercised each current adapter character
(`>`, `<`, `$`, backtick, `;`, `&`, `|`, `[`) in synthetic commands against
default-deny rules with narrow fake `sprintctl run context` and `note` allows.
All raw-character calls were rejected with `Permission denied: shell`; their
temporary sentinels were absent. Quoted semicolon, dollar expansion, and
backticks were also rejected. A newline chain was rejected even after an exact
newline-containing allow rule was added, but that allow control itself did not
permit the command; the reason and the independent effect of an added newline
deny rule are therefore unknown. A newline inside single quotes was allowed
and invoked fake `sprintctl`, without creating a chain sentinel. These results
cover only the tested commands and rule sets; they do not establish general
shell containment. Idle was `succeeded` after both allowed and denied calls,
so it is not an execution-success signal.

The additional fixture was copied byte-for-byte from the host-local probe
(`SHA-256 73f213fcc05ba39316b4cb579ae83ca96b6faac735587f0a99ff51947823a124`)
and rerun from this worktree on the pinned devbox binary in a no-egress
namespace. The result is sanitized JSON (`SHA-256
7fa9087182c70fb95c00a69c4db14e324c8a937f83dd95ed6f6543ed76ba69a9`). It
includes a forced false assertion control; the fixture verifies that the
assertion raises and records the failure marker. For reproduction:

```sh
ssh devbox-agent 'bwrap --unshare-net --ro-bind / / --tmpfs /tmp --dev /dev --proc /proc --clearenv --setenv PATH /run/current-system/sw/bin:/usr/bin:/bin python3 -' < docs/evidence/2026-11-03-opencode-v2/opencode-v2-shell-metachar-probe.py
```

## Fresh tool-family and restart controls

The [tool-policy probe](opencode-v2-tool-policy-probe-2026-11-03.py) and its
[sanitized result](opencode-v2-tool-policy-result-2026-11-03.json) were run
against the pinned 2.0.32 binary on devbox inside the same no-egress bubblewrap
network namespace. It uses only a loopback fake model provider, a loopback HTTP
canary, temporary HOME/XDG/project state, and generated synthetic credentials.
The script asserts the expected results and removes the temporary tree when it
exits. SHA-256 values are `b449e4f3fc413909d1d129009e9bf9e508dfdbc3c43356b048138c139f886106`
for the probe and `90d282af1e69c1c0f91978bcf9ca53c7ea971e55d8abb3a816f3df9ccd8342dc`
for the sanitized result.

With ordered wildcard deny followed by one action allow, the fake provider's
forced calls were blocked for `read`, `write`, `webfetch`, `subagent`, and
`skill`. The deny controls observed no file canary, write target, or local HTTP
request. Matching positive controls read the unique temporary canary, created
the temporary write target, fetched the loopback HTTP canary, completed one
subagent request through the fake provider, and loaded the synthetic skill
marker. The v2 permission action that exposes `write` is `edit`; the subagent
tool is named `subagent`. No real subagent provider or external endpoint was
used.

The restart control stopped and restarted the disposable server while retaining
its temporary database and XDG roots. The same session ID and exact ordered
wildcard-deny rule were returned after restart. A malicious-provider `read`
call against that recovered session remained unadvertised and rejected, and
the canary was not returned.

A forced mutation changed the wildcard deny effect to allow. Under that
mutated rule, the forced `read` returned the canary and the same denial
assertion failed as expected; the probe records the caught assertion. This
demonstrates that the negative check detects this specific policy regression.
It does not validate arbitrary policy mutations.

The subsequent MCP discovery attempt is retained in the
[MCP probe](opencode-v2-mcp-discovery-probe-2026-11-03.py) and
[sanitized result](opencode-v2-mcp-discovery-result-2026-11-03.json). It
configured a synthetic local stdio server in both the temporary project config
and temporary XDG global config, with the documented `mcp.servers.localtest`
shape. The server implemented initialize, tools/list, and tools/call; its only
tool returned a synthetic marker and appended a local call record. The
`opencode mcp list` command nevertheless returned `No MCP servers configured`,
and the provider saw only built-in tools, with no `mcp__localtest__echo`. Forced
calls under deny-all and four candidate explicit allow actions all returned
`No tool named "mcp__localtest__echo" is currently available`; the server call
record remained empty. These are unknown-tool rejections, not permission
enforcement. MCP allow/deny remains untested because this binary did not
discover the configured server. The attempt does not establish whether another
configuration path or runtime provisioning mechanism would work.

These controls establish only
the listed tool calls, rules, and disposable paths on this binary. They do not
establish general filesystem, kernel, OS, external network, MCP, deployed
service, real-owner, or full adapter recovery containment. A `succeeded` idle
event remains a session drain signal and is not a tool-effect success signal.
Reproduce the probe with:

```sh
ssh devbox-agent 'bwrap --unshare-net --ro-bind / / --tmpfs /tmp --dev /dev --proc /proc --clearenv --setenv PATH /run/current-system/sw/bin:/usr/bin:/bin python3 -' < docs/evidence/2026-11-03-opencode-v2/opencode-v2-tool-policy-probe-2026-11-03.py
```

The prompt-admission fixture then measured the request/ack and projection path.
OpenAPI requires prompt `text`; omitting it returned HTTP 400 and left the
transcript IDs unchanged. A valid prompt returned HTTP 200 with
`{data:{delivery,id,payload,sessionID,time,type}}`; the default delivery was
`steer`, and its user ID/text matched the transcript. A queued prompt appeared
immediately in the inbox with the same ID/text. While the first synthetic
inference was held, that queued ID was absent from the transcript throughout a
one-second observation window; after release and drain it appeared with the
same text. The inbox was empty after drain.

Four acknowledged turns produced 12 transcript rows. Reading with `limit=2`
returned six full pages and an empty terminal page; paged IDs were unique and
their set matched the unpaged read. For response loss, a loopback proxy received
the server's HTTP 200 acknowledgement and then dropped it, so the caller saw
`RemoteDisconnected`. A client-supplied message ID was already present in the
transcript. Replaying that ID returned the original acknowledgement without a
second transcript row or provider request in the two-second observation. A
replay with the same ID but different text also returned the original text.
This demonstrates observed same-process behavior; it does not establish
deduplication durability across a server restart. Likewise, transcript
projection absence was measured only during the bounded one-second held
inference window.

The prompt fixture and sanitized result are bound by SHA-256 in the compact
summary below. Reproduce it on the isolated devbox with:

```sh
ssh devbox-agent 'bwrap --unshare-net --ro-bind / / --tmpfs /tmp --dev /dev --proc /proc --clearenv --setenv PATH /run/current-system/sw/bin:/usr/bin:/bin python3 -' < docs/evidence/2026-11-03-opencode-v2/opencode-v2-prompt-admission-probe.py
```

The compact [summary](opencode-v2-policy-message-results-2026-11-03.json) binds
the original policy/message scripts and their initial sanitized results by
SHA-256. The scripts assert positive and negative observations and exercise a
forced assertion failure.
Their original comments refer to host-local `_artifacts`; from this repository,
run each script by piping it over SSH into the isolated namespace:

```sh
ssh devbox-agent 'bwrap --unshare-net --ro-bind / / --tmpfs /tmp --dev /dev --proc /proc --clearenv --setenv PATH /run/current-system/sw/bin:/usr/bin:/bin python3 -' < docs/evidence/2026-11-03-opencode-v2/opencode-v2-policy-qualification-probe.py
ssh devbox-agent 'bwrap --unshare-net --ro-bind / / --tmpfs /tmp --dev /dev --proc /proc --clearenv --setenv PATH /run/current-system/sw/bin:/usr/bin:/bin python3 -' < docs/evidence/2026-11-03-opencode-v2/opencode-v2-message-shapes-probe.py
```

Committed fixtures and observations are cross-host-replicated; the live
service, original process output, and temporary generated credentials are not.
