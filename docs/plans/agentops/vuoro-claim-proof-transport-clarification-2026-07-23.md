---
doc_id: vuoro-claim-proof-transport-clarification-2026-07-23
status: approved-implementation-clarification
approved_at: 2026-07-23
approved_by: operator
scope: sprintctl-item-1195-group-a
governing_decision: docs/plans/agentops/vuoro-served-substrate-plan.md
---

# Vuoro claim-proof transport clarification

This companion records the operator-approved implementation clarification for
Group A of Sprintctl item **#1195**: served claim heartbeat, handoff, and
release. It does not rewrite or supersede the ratified
[`vuoro-served-substrate-plan.md`](vuoro-served-substrate-plan.md), authorize a
production deployment, or transfer domain ownership from Sprintctl.

## Verified mismatch

The shipped `work.claim.arbitrate` application accepts an immutable
authority-command record and resolves its digest-bound proof through an
injected credential resolver. The current Vuoro composition does not inject
that resolver, protocol-v1 invocation has no transient-proof channel, and the
transport client sends only the identity bearer credential plus catalog
arguments.

The client also lacks enough non-secret authority context to construct a
canonical claim command without database access. It needs the authenticated
actor, repository authority UUID, current non-secret claim snapshot, and
current claim basis revision. These values must not be guessed from profile
names, advisory CLI actor flags, cached claim output, or proof hashes.

Finally, the existing authority-command claim path is not yet complete legacy
parity:

- `claim.renew` does not apply heartbeat metadata such as runtime session,
  branch, worktree, commit, PR, hostname, and PID;
- accepted authority handoff does not emit the existing non-secret
  coordination evidence carried by a legacy handoff; and
- proofless `--allow-legacy-adopt` has no appropriately privileged served
  authority boundary.

## Approved transport contract

Vuoro must expose a generic transient-credential channel outside catalog
operation `arguments`. The concrete wire contract is a versioned
`invocation/v2` envelope on `POST /api/invoke/v2`; the existing
`invocation/v1` endpoint remains available for compatible proofless
invocations and older clients.

`invocation/v2` adds one optional `transient_credentials` object whose keys are
`sha256:<64-lowercase-hex>` bindings and whose values are non-empty proof
strings. This is a transport facility, not a work-domain argument:

- the client uses v2 only when transient bindings are supplied and first
  confirms v2 support through the handshake;
- more than one binding is permitted because rotating handoff needs both the
  current and proposed proofs;
- the service passes bindings only through the in-memory invocation context;
- service composition supplies Sprintctl's credential resolver, which returns
  only bindings referenced by the validated immutable command;
- Sprintctl rehashes each supplied proof and compares it to its reference
  before arbitration;
- transient bindings are forbidden from catalogs, producer records, decisions,
  caches, request/response diagnostics, exception text, access logs, and
  telemetry; and
- unsupported v2, malformed bindings, missing references, or digest mismatch
  fail closed before an authority effect.

TLS protects the request in transit in the same way it protects the identity
bearer credential. Deployment and observability configuration must prove that
request bodies and transient invocation context are not logged.

## Approved authority-context contract

Sprintctl adds an authenticated `work.claim.context` read operation requiring
`work:claim`. Its input is a positive `claim_id`. Its non-secret result
contains:

- the resolved authenticated actor;
- Sprintctl repository ID and authority repository UUID;
- the current non-secret claim snapshot, including `work_item_id`; and
- the canonical current `claim_revision`.

The operation never returns a claim token, a proof digest not already present
in an immutable command, another identity's bearer credential, or a database
DSN. A missing or inaccessible claim fails without creating a producer record.

The served CLI uses this context and Sprintctl-owned pure construction helpers
to create the same canonical `AuthorityCommand` and `OutboxRecord` shapes as
the retained authority CLI. The local outbox remains the producer of
`origin_stream_id`, contiguous `origin_seq`, event ID, and content digest.
A race after the context read remains a normal durable `stale-basis`
rejection; the client must not rewrite or reuse that event ID with different
content.

## Proof retention and retry

Before sending a proof-bearing command, Sprintctl writes the existing
event-keyed authority credential sidecar with directory mode `0700` and file
mode `0600`. This sidecar is retry material for one immutable command, not a
served claim-recovery file and not shared authority state.

- Heartbeat and release retain the current proof only until the command reaches
  a terminal accepted or rejected decision.
- Rotating handoff retains both the old and proposed proofs; recovery exposes
  only the proposed proof.
- Transfer handoff retains only the current proof.
- An unknown transport outcome keeps the sidecar and retries the identical
  record with the identical event ID, basis revision, and idempotency key.
- A duplicate remote decision is authoritative and must not cause a second
  effect.
- Sidecars are cleared only under Sprintctl's existing terminal-decision and
  accepted-new-proof recovery rules.

Normal served `claim start` still does not write the legacy local
claim-recovery file. Served mode never opens a local or remote authority
database as a fallback.

## Claim parity requirements

Group A is not complete until these Sprintctl-owned semantics are present:

1. `claim.renew` accepts canonical claim metadata and applies non-null values
   with the same update semantics as legacy heartbeat.
2. Heartbeat output and warning behavior remain CLI-compatible while the
   authenticated actor, not an advisory actor option, authors the command.
3. Accepted handoff updates ownership and metadata, rotates or transfers proof
   exactly once, and atomically emits non-secret claim-handoff coordination
   evidence. `performed_by` is the authenticated actor; an optional note may
   be retained, but neither proof may appear in the event.
4. Rotating handoff returns or recovers the client-generated proposed proof;
   the authority response does not reveal stored proof material.
5. Release removes the claim only after valid proof arbitration and clears its
   terminal local retry sidecar.
6. `--allow-legacy-adopt` is rejected before ordinary served invocation.
   Proofless adoption requires a separately designed recovery/admin operation,
   a distinct authority such as `work:claim-recover`, and operator-owned
   deployment policy. It is not part of Group A and is not granted by the
   existing `work:claim` profiles.

The immutable accepted/rejected authority decision is the canonical remote
outcome. Legacy diagnostic events for failed direct proof attempts need not be
duplicated when the durable rejected decision carries the equivalent
non-secret reason.

## Repository ownership and build order

1. **Vuoro:** add v2 invocation contracts, handshake advertisement, client
   selection, in-memory transient context, redaction, and compatibility tests.
2. **Sprintctl application:** add `work.claim.context`, the composition
   credential resolver, shared pure command construction, renew metadata, and
   atomic handoff evidence.
3. **Sprintctl served CLI:** wire heartbeat, handoff, and release through local
   outbox/sidecar creation and the v2 invocation path. Reject proofless adoption
   before transport.
4. **Integration verification:** exercise context-to-record construction,
   current/proposed proof binding, lost-response retry, stale-basis races,
   duplicate decisions, metadata parity, handoff evidence, terminal cleanup,
   proof redaction, and the no-PostgreSQL served import graph.
5. **Deployment gate:** update the pinned Vuoro client/service artifacts and
   run the black-box cutover suite before changing profiles or revoking direct
   database access.

Vuoro remains transport and composition; Sprintctl remains the owner of claim
records, proof semantics, arbitration, retry sidecars, and CLI behavior.
Appservice remains the owner of TLS, identities, deployment logging, artifact
promotion, and recovery authority grants.

## Deferred recovery item

Before direct recovery paths can be retired, Sprintctl and appservice need an
owner-local item for authenticated proofless claim adoption. That item must
define eligibility, audit evidence, least-privilege authority, operator
approval, and replay behavior. It must not be folded into Group A or silently
inherit the broad `work:claim` grant.
