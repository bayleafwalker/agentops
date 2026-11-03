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

The compact [summary](opencode-v2-policy-message-results-2026-11-03.json) binds
both scripts and their initial sanitized results by SHA-256. The scripts assert
positive and negative observations and exercise a forced assertion failure.
Their original comments refer to host-local `_artifacts`; from this repository,
run either script by piping it over SSH into the isolated namespace:

```sh
ssh devbox-agent 'bwrap --unshare-net --ro-bind / / --tmpfs /tmp --dev /dev --proc /proc --clearenv --setenv PATH /run/current-system/sw/bin:/usr/bin:/bin python3 -' < docs/evidence/2026-11-03-opencode-v2/opencode-v2-policy-qualification-probe.py
ssh devbox-agent 'bwrap --unshare-net --ro-bind / / --tmpfs /tmp --dev /dev --proc /proc --clearenv --setenv PATH /run/current-system/sw/bin:/usr/bin:/bin python3 -' < docs/evidence/2026-11-03-opencode-v2/opencode-v2-message-shapes-probe.py
```

Committed fixtures and observations are cross-host-replicated; the live
service, original process output, and temporary generated credentials are not.
