# M2c live qualification runner

`scripts/qualify_inbox_m2c.py` is a narrowly scoped tool for qualifying the
installed inbox adapter against disposable live owner records. It does not
change `host_adapter.py`, the production CLI or the system service. It is a
qualification harness, not a deployment or runtime-enablement command.

## What it can do

The default paths are inert. `--help` prints arguments only, and
`offline-check` exercises the fault-wrapper and path-guard mechanics without
opening a network connection, loading an adapter module, reading credentials,
or calling an owner or harness. The offline checks use synthetic objects and
are explicitly not live qualification evidence.

The `execute` subcommand requires an explicit `--execute` flag and performs
exactly one adapter tick. It dynamically imports the provided immutable
installed adapter file only after checking that it is under `/nix/store`, is a
regular root-owned non-writable file, and matches the required
`--expected-adapter-sha256`. It refuses to use a different source build merely
because the file has a Nix store path. Hosts whose installed store files are
not root-owned cannot use this runner as written; do not relax this check to
admit an editable checkout.

The runner constructs the adapter's real `VuoroOwner` and `OpenCodeServe`
implementations. A named checkpoint raises a one-shot `BaseException` through
the actual adapter at a supported checkpoint. The optional caller-boundary
owner faults also call the actual owner: duplicate-read mode makes two actual
reads with identical arguments and accepts only identical results; the
result-linked mode lets the owner commit and return the real receipt, then
discards that response before the adapter sees it. These mechanisms create no
fake owner response or owner record. Offline mechanics tests do not establish
that a live owner behaves this way.

## Required isolation

Execution must happen in a separately reviewed protected systemd unit using
the protected adapter identity and its normal file, network and process
containment. The runner does not verify its own code or the unit's confinement:
the qualification script itself and its interpreter must also come from the
reviewed immutable package, with the script's exact bytes and SHA-256 verified
before use. Do not execute a Git checkout copy in the protected unit. The runner
is not permission to widen the production unit. The unit must pass its exact
immutable `/nix/store` adapter path and independently
verified SHA-256 using `--adapter-path` and `--expected-adapter-sha256`, a
root-owned trusted test policy, the protected profile, and the OpenCode password
only as a systemd `LoadCredential`. It must not put a credential value in argv,
environment overrides, test files, captured output or logs. For the inspected
agentops `e8d1d73653230d1df052631e3b2218ad9da2ef0e` source, the candidate
`scripts/host_adapter.py` file digest is
`32b4f0365aaabbb61c59ee7b04114ecb312edd0335f2ef414db9c3141d61955a`. This is
not proof that an installed Nix store file contains those bytes; calculate and
review the installed path's hash before execution. Any later source candidate
requires a new reviewed digest.

The test policy has to allow exactly one disposable repository and one known
sender principal, supplied as `--scope-repo` and `--scope-sender`. Root
pre-creates one private direct-child state directory
per history below `/var/lib/agentops-m2c-qualification`; the directory belongs
to the protected adapter UID and has no session-readable, writable or
traversable access. The production adapter state directory is never accepted.
Each restart history reuses only its own qualification directory.

First run the empty-state qualification once with no test messages available;
that invocation registers the test instance, performs its empty inbox read and
then reports its fresh instance ID. Capture the report before creating or
sending a message. Also read and record the ordinary production instance ID;
the IDs must differ. Every qualification message must explicitly set
`recipient.instance_id` to the test instance; untargeted messages are forbidden.
The owner read operation selects messages for the calling principal whose
recipient instance is either absent or equals the requested instance. Thus a
different production instance cannot receive or refuse a message targeted to
the test instance. Keep the ordinary protected adapter unit held during each
failure-injection window as an additional single-consumer safeguard. After
resuming it, verify its state has no test message and the test message has no
receipt written by the production instance.

The first invocation reports the test instance only after its empty tick. Send
the targeted message only after capturing that ID. For every subsequent
invocation, include the production instance ID as `--production-instance-id`
so the runner refuses reuse. Use separate fault-specific invocations and keep
the ordinary protected adapter unit held throughout fault histories. The
dedicated `--state-id` names exactly one precreated directory beneath
`/var/lib/agentops-m2c-qualification`; reuse it only to resume that same
scenario. Do not copy production SQLite state into it.

The sender should use only the exact repo and recipient already authorized by
the root-owned test policy. Create separate disposable items and runs per
history. A sender-retry test reuses the same message ID and identical canonical
envelope; it must never mint a second ID or change the payload after an
uncertain response. Reconcile all results from owner message status, receipts,
run records, delegated-operation evidence and harness session IDs. Never use
session transcripts as the authority record.

The qualification operation in the first success history is the supported
run-scoped session-note write with its stable same-key idempotency key. A
session note is append-only; owner deduplication and read-after-write
reconciliation protect retries, but do not make the effect reversible.
Reservations are advisory and may overlap. Test them by observing both active
reservations and the owner's conflict projection, not by expecting one to be
refused. Use the separate owner lifecycle compare-and-set path for stale item
revision checks; a session note itself does not bind an item revision.

## Evidence limits

This tool has not been run against a live owner or harness by virtue of its
source tests. A green offline check, source unit test, disposable test database,
or mock client cannot establish the M2c live exit condition. Before any live
history, an independent reviewer must check the installed bytes against the
candidate digest, protected unit UID/sandbox, policy and environment hashes,
exact instance targeting, dedicated state directory and operation-specific
owner scope. Preserve the receipts and owner records for each deliberately
induced failure. Report only the specific histories actually reconstructed.

The workstation Nix store may expose a file owned by its Nix daemon UID rather
than UID 0. This runner intentionally refuses that case. Whether the protected
qualification host provides an acceptable root-owned immutable package is a
separate preflight and remains unverified here.
