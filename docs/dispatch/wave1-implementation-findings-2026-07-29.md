# Wave 1 implementation findings — 2026-07-29

## Status

The Wave 1 human decisions were ratified. Implementation proceeded in
dependency order with fresh review. No reviewed candidate was pushed,
released, deployed, or tracker-closed during this pass.

The served Sprintctl tracker was unavailable for every attempted item read, so
the work was deliberately not claimed and no claim proof or tracker state was
fabricated.

## Ratified workflow model

The durable lifecycle is:

```text
canonical dispatch intent
  -> ActionQ Action (durable enqueue root)
    -> claim / Attempt (fenced incarnation)
      -> ExecutionSession (runtime attachment after an attempt starts)
        -> CandidateResult and receipts (immutable evidence)
          -> independent review / integration
```

An enqueue returns an Action and immutable request binding; it does not create
or return an execution session. A session is a later child runtime resource.
Groups and waves remain projections over Actions.

## Reviewed implementation candidates

### AgentOps #2040

Local commits `a15e404`, `22995cf`, `1889f3f`, and `8f5ab44` add the strict
canonical v2 dispatch-request contract:

- required literal `action_type` and `output_expectation`;
- `kind` only as a deterministic v1 compatibility alias;
- explicit nullable fields and no implicit defaults/coercion;
- full normalized request schema and strict enqueue-result shape;
- cockpit/MCP validation parity; and
- a fail-closed legacy `actionctl` path until ActionQ persists a request
  snapshot/ref/digest.

Fresh review confirmed this contract. ActionQ remains responsible for proving
that the returned request digest is bound to its atomically persisted bytes.

### Auditctl / AgentOps #2064

Auditctl commits `4b2fe7a` and `8040b09` implement whole-batch typed
fail-closed rebuild behavior. Unsupported schema/class, malformed envelopes,
incompatible duplicate identity, corrupt or missing shards, and origin
discontinuity reject before import, cursor progress, source modification, or
quarantine persistence. Exact canonical duplicates are the only skips.

Fresh review confirmed the target behavior. The Auditctl full suite retains one
pre-existing stale central-evidence digest failure unrelated to these commits;
the targeted suite passed.

### Sprintctl #2026

The frozen contract series on the local branch is `dc65d5f`, `f938bc4`,
`09db1a3`, and `68a0542`. It defines the token-free
`work.claim.recover-terminal/v1` boundary, strict opaque capability references,
online fail-closed capability verification, request/capability/principal scope
binding, narrow conflict taxonomy, and pinned verification context.

The isolated server candidate in
`/tmp/sprintctl-2026-terminal-recovery` adds commits `6f2cb35`, `3884dec`, and
`bd2d214`:

- immutable PostgreSQL terminal settlement and recovery-audit records;
- verification, scope, and principal checks before ledger or claim I/O;
- ledger-first historical replay after later lineage changes;
- transaction-owned ledger/audit writes; and
- terminal-path and rollback coverage, including `item.done-from-claim`.

Fresh review confirmed the focused behavior. PostgreSQL execution remains
inconclusive because no disposable `SPRINTCTL_TEST_PG_URL` was supplied. The
server candidate is a fast-forward descendant of the contract branch; there is
no deletion conflict. It intentionally contains no served CLI route, identity
issuer configuration, deployment grant, or local fallback.

### ActionQ #2027

The isolated candidate in `/tmp/actionq-2027-action-root` contains the v2
Action-root enqueue series through `1204c5b`:

- byte-exact immutable normalized snapshots, opaque request refs, and digests;
- transactional Action/enqueue/snapshot binding and idempotent replay/conflict
  behavior;
- no ExecutionSession at enqueue;
- fail-closed trusted-provenance and repository authorization hooks;
- protected request-ref snapshot resolution;
- strict ActionQ/Vuoro input and result schemas; and
- runtime compatibility checks for the v2 relation, constraints, indexes, and
  validated PostgreSQL CHECK constraints.

Fresh review confirmed the final schema-compatibility repair. The remaining
gates are operational, not a known source defect:

1. no automatic retention/pruning is implemented in Wave 1; Action data,
   snapshots, and lifecycle events are retained for the Action lifetime;
2. direct HTTP is deny-all until Vuoro composes a real authenticated identity
   transport; and
3. the disposable PostgreSQL suite has not run on this workstation because
   `initdb` and `pg_ctl` are absent.

The candidate was published over workstation GitHub SSH and then exercised in
a clean devbox worktree with its disposable PostgreSQL harness. That run
reached the stateful suite (212 passed, 7 failed, 7 skipped). It exposed a
real migration-compatibility regression: existing deployment and adapter
fixtures still observe schema version `2` where the candidate produces `3`.
The failures cover migration retry/adoption/serialization, future-version
runtime refusal, role compatibility, and one Vuoro adapter compatibility case.
The candidate is therefore returned to implementation; no release or dev
deployment is authorized from this evidence.

### Vuoro #2031 identity prerequisite

Isolated Vuoro commit `4c3a52b` in `/tmp/vuoro-2031-identity` defines an inert,
typed identity-to-ActionQ-provenance boundary. It rejects missing/ambiguous
identity, environment mismatch, absent authority, unauthorized repository
scope, missing idempotency, and raw caller actor headers. Review confirmed it
does not activate an HTTP transport or execute work.

It cannot be composed until ActionQ publishes a compatible v2 adapter API;
the currently released ActionQ 0.1.6 wheel does not expose that API.

## Release and verification sequence

1. Publish reviewed candidates on isolated GitHub branches over SSH and run
   CI-backed disposable PostgreSQL gates.
2. Keep direct ActionQ HTTP deny-all; do not deploy the candidate merely to
   make the endpoint reachable.
3. After ActionQ PostgreSQL evidence, publish its immutable adapter wheel and
   build a Vuoro candidate image containing that exact pin.
4. Pin only `vuoro-dev` to the candidate image and run deployed development
   verification through its declared identities/backends.
5. Run the Sprintctl disposable PostgreSQL suite and independently review its
   cleanup evidence before composing terminal recovery.
6. Do not promote to `vuoro-shared` until all stateful gates, provenance,
   identity composition, and release evidence are accepted.

## Environment findings

- The Appservice `vuoro-dev` deployment is Ready and intentionally separate
  from `vuoro-shared`, but its current image predates the ActionQ v2 candidate.
  It cannot validate unshipped candidate code.
- Appservice documents a dedicated `sprintctl-test` CNPG target for destructive
  Sprintctl integration tests. It must be reached only from its authorized
  in-cluster integration workload; never from a shared or production database.
- The local GitHub CLI authentication is expired, while devbox has a valid
  GitHub token and PostgreSQL binaries. The next publication path should use
  GitHub SSH credentials without printing tokens or credentials.
