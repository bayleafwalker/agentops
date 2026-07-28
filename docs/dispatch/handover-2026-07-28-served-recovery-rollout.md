# Handover — served recovery and dispatch rollout, 2026-07-28

## Current state

The interrupted enablement sweep left exactly one candidate implementation
artifact: uncommitted `actionq.dispatch.json` and
`.agents/overlays/actionq.hybrid-worker.md` changes in the `actionq` checkout.
Do not commit or apply them as an enablement result yet.

The completed Vuoro pilot remains the only fully exercised hybrid repository.
Its containment result is useful, but every configured worker route remains
`available_unqualified` until the `agentworker` identity can invoke the route's
actual configured model with no override.

## Served authority recovery patch

An authority command that receives a terminal served decision was being handled
inconsistently:

- Direct served lifecycle paths call `mark_terminal_authority_decision`.
- `authority sync` removed any no-longer-needed proof sidecar but did **not**
  write that terminal receipt.

The immutable outbox record consequently remained eligible for every later
sync. A rejected earliest record could be sent repeatedly and prevent later
records on the same origin stream from advancing.

The first `sprintctl` patch did two things:

1. Classifies `authority status` as a served-safe local diagnostic. It reads
   only the producer outbox and terminal receipts, reports redacted ordered
   pending record metadata, and does not construct a database backend.
2. Marks every terminal decision returned by served `authority sync` before
   cleaning up its proof sidecar. Later sync runs skip the settled request and
   replay the next ordered record.

Live replay found a second, server-side defect: `work.batch.apply` validates
every actor before authority arbitration, so a mismatched first command aborts
the whole batch without a terminal decision or origin-cursor advance. The
follow-up `sprintctl` patch changes only batch handling: a durable authority
command with an actor/claim-agent mismatch reaches the authority ledger and is
atomically recorded as `command.rejected` with reason `actor-mismatch`. Direct
single-command operations retain their existing pre-backend fail-closed
rejection. This requires a new Sprintctl adapter wheel, a Vuoro pin/image
release, and an appservice deployment before live recovery can succeed.

Focused verification passed after both slices:

```text
uv run pytest tests/test_served_authority_sync.py \
  tests/test_served_authority_status.py tests/test_served_routes.py \
  tests/test_served_lifecycle_routes.py -q
141 passed, 17 skipped (PostgreSQL integration target unavailable in this sandbox)

python /projects/dev/agentops/templates/dispatch/scripts/
  validate_verification_artifacts.py --root .
all declared artifacts valid
```

The patch is limited to `sprintctl/cli.py`, `sprintctl/served_routes.py`,
served authority-sync tests, and the new served authority-status test. The
pre-existing `uv.lock` modification is unrelated; do not stage it with this
fix.

## Required live recovery sequence

Run this only from the workstation `sprintctl` checkout after the new adapter
wheel has been pinned, the resulting Vuoro image has been deployed, and the
client patch has been committed. It targets the existing durable producer log; do not edit
the SQLite outbox or terminal-receipt files manually.

1. Confirm the branch contains both patches, the deployed service image has
   the matching immutable Sprintctl adapter wheel, and source the checkout's
   `.envrc`.
2. Run `sprintctl authority status --json`; save only redacted metadata showing
   the earliest pending record and its origin sequence.
3. Run `sprintctl authority sync --json` once. It must replay that exact
   earliest record, record its terminal decision, and return without minting a
   replacement event.
4. Run `authority status` again, then retry the originally blocked ordinary
   operation exactly once. Capture redacted output proving the later stream
   record can now advance.
5. If the server does not return a terminal decision for the earliest record,
   stop. Do not bypass ordering or create a new event; attach the status and
   sync evidence to a sprintctl incident instead.

## 2026-07-28 live recovery incident: divergent stream history

The source and deployment recovery chain completed, but the first live replay
exposed an older authority-ledger inconsistency. The exact stream is
`f7b7bdea-6b53-4804-8986-5222dae41e38` in the `sprintctl` work repository.

- Local outbox: records `1..16` remain without local terminal receipts.
- Remote cursor: `highest_origin_seq=38`.
- Remote history: only 27 records, covering sequences `12..38`, with 27
  authority decisions; sequences `1..11` are absent.
- At the overlap (`12..16`), the remote rows have the same event IDs as the
  local records but different immutable record SHA-256 values.

The service correctly rejects replay of local sequence 1 with `expected
sequence 39, received 1`. This is no longer an ordinary retry problem:

- Writing local terminal receipts would treat divergent remote evidence as
  equivalent without a proof.
- Rewinding/seeding the remote cursor or reinserting `1..11` would change
  historical authority ordering and is not authorized by ordinary served work.

**Required next authority:** an operator-approved recovery design that names
the source of truth for the missing records and explicitly handles the
same-event/different-hash overlap. Do not retry `authority sync`, mutate the
outbox, alter `work.ingest_stream`, or create substitute events until that
decision is recorded.

### Completed release/deployment chain

- `sprintctl` `e0f785c`: `0.2.3` adapter release
  `vuoro-adapter-v1-e0f785c`, wheel SHA-256
  `394240e1c3f31f8f950d526a2a5108d42d9ff363db645ed5a9cc7481ec42c2d6`.
- `vuoro` `01406ed`, tag `vuoro-service-v0.1.18`: immutable service manifest
  digest `sha256:76e3ab2182aa56ff5ba49943baa8ecb118d42d1d0610c09ca3f3f1cdc327b801`.
- `appservice` `cf973c58`: digest deployed; Flux applied the revision and the
  `vuoro-shared` deployment reported one ready updated replica on that digest.

This session could not perform the live status/replay step because sibling
repository state is mounted read-only in the execution sandbox.

## Hybrid enablement finding: actionq

Fresh-clone proof was attempted exactly as required:

```text
git clone --no-hardlinks /projects/dev/actionq /tmp/actionq-gate.<id>
uv run --extra dev pytest <draft actionq unit subset> -q
```

It failed before collection while resolving `psycopg-binary==3.3.3`; this host
has no package DNS/egress and the required artifact was not in the temporary
uv cache. That is a real gate failure, not a test pass. Before enabling the
draft on devbox, the coordinator must provision the worker identity's exact
locked dependencies, then repeat the fresh-checkout command as the intended
worker user and retain its exit evidence. The full PostgreSQL/integration suite
remains coordinator-only regardless.

## Remaining operator/coordinator work

1. Restore and verify the reported `#2018 → #2019` dependency using the served
   dependency commands; record the accidental removal as an incident.
2. Credential `agentworker` for the configured `opencode-go` model, with its
   own spend cap; rerun containment and the no-override smoke packet.
3. Re-confirm OpenCode permissions on devbox 1.18.4. Do not use a worker's
   claimed self-verification as proof until this observation is recorded.
4. After the served recovery works live, flip only the named candidate
   repositories' host-local served configuration and verify a scoped read plus
   one authorized write on both workstation and devbox.
5. Resume repository enablement one repository at a time, retaining an
   explicit coordinator-only disposition wherever no cold deterministic gate
   can be proven. Infrastructure repositories remain intentionally excluded.
