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
