---
doc_id: vuoro-served-substrate
status: ratified
ratified_at: 2026-07-21
ratified_by: operator
supersedes:
  - client-owned-shared-schema-migration
  - direct-database-client-as-target-interface
---

# Vuoro served-substrate architecture

## Decision

Vuoro centralizes the semantics of governed work, not every effect performed
on its behalf. The architectural defect to remove is substrate-owned policy
packaged as machine-local CLI artifacts: database migrations, transition and
batching rules, command availability, validation, and shared environment
knowledge currently change according to which workstation installation runs.

The target is one modular Vuoro service, a server-published operation catalog,
and a transport-only schema-driven client. Domain state and semantics remain
owned by `sprintctl`, `actionq`, `kctl`, and `auditctl`; deployment remains
owned by `appservice`.

This decision was operator-ratified on 2026-07-21. The attached owner alignment
notes translate it into repository-local boundaries without duplicating this
architecture.

## Scope model

### Substrate-scoped

These capabilities affect the meaning of work across machines and must be
served by the authority path:

- shared-database migrations and compatibility;
- claims, leases, lifecycle transitions, and acceptance gates;
- project batching and dispatch ordering;
- exposed operation definitions and validation schemas;
- project workflow variables and canonical environment metadata;
- human-only ratification constraints;
- cross-machine observation ingestion and receipts.

Network clients never migrate a shared authority database. Migrations run in a
deployment-controlled job using a domain-specific migration role. Runtime
service roles cannot execute DDL. Service startup checks schema compatibility
and fails closed; it never upgrades a schema as a side effect of serving a
request.

An explicitly local SQLite authority may continue to migrate its own local
file. This exception covers standalone use and marked disaster recovery, not a
client attached to shared authority.

### Convention-scoped

Git remains canonical for authored documents. Vuoro only promotes conventions
that repeatedly affect authoritative state. The first promotion is a
validation gate for human-only ratification: a transition to `ratified` or a
ratified supersession must carry operator identity and revision evidence.
Vuoro does not create a second canonical document store or ratification ledger
in this tranche.

### Machine-scoped

Worktrees, filesystems, builds, Docker daemon operations, image construction,
secrets, hardware, shells, and host recovery remain local. Vuoro publishes the
environment record and runbook constraints that govern those effects. A local
executor performs the effect and reports evidence; the service does not
pretend a Docker restart or worktree creation is remote-neutral.

## Product and repository shape

Create a public `bayleafwalker/vuoro` repository with two independently
packaged deliverables:

- `vuoro-client`: endpoint/identity profiles, handshake, catalog discovery,
  schema rendering, cache/watermark display, and generic invocation only;
- `vuoro-service`: the HTTP service, pinned domain adapters, compatibility
  checks, migrations, and deployment administration.

The client distribution must not contain domain cores, database drivers,
migration assets, or authority implementations. The service image may contain
all four adapters and their migration entrypoints. Updating a domain adapter
therefore changes the deployed substrate once, rather than requiring every
workstation to reinstall it.

Domain repositories publish adapter/application-core packages and retain
their schemas and semantic tests. Vuoro composes them into one process but
does not merge their databases or allow cross-domain writes.

| Module | Domain owner | Served responsibility | Preserved local responsibility |
| --- | --- | --- | --- |
| `/api/work/v1` | `sprintctl` | work, claims, lifecycle, evidence, batching | declared standalone/DR SQLite authority |
| `/api/execution/v1` | `actionq` | queue, leases, dispatch, session state | machine-local runner effects |
| `/api/knowledge/v1` | `kctl` | candidate/review workflow and publication references | Git document content and local authored projections |
| `/api/audit/v1` | `auditctl` | observation ingestion and receipts | SQLite/NDJSON capture, buffering, and rebuild |

## Service contract

The first deployment exposes:

- `GET /api/meta/v1/handshake`;
- `GET /api/catalog/v1`, with a stable revision and ETag;
- `POST /api/invoke/v1`;
- the four domain API namespaces above.

The handshake reports deployment environment, client-protocol range, catalog
revision, and per-domain API/schema compatibility. It replaces package source
string comparison as the compatibility boundary.

Each catalog operation declares:

- globally unique name and domain owner;
- input and result JSON Schemas;
- required authority;
- execution semantics;
- idempotency requirements;
- required client schema features;
- deprecation and replacement metadata.

Operation names are domain-qualified, for example
`work.pilot.cutover-evidence`. A protocol-v1 client can invoke a newly deployed
operation without reinstalling when the operation uses its supported schema
feature set. Unsupported schema features fail explicitly as a client feature
incompatibility. Catalog data can describe arguments and presentation but can
never supply executable client code or unpinned external schema references.

Invocation derives actor and environment from authenticated identity. Clients
submit the operation, input, request ID, optional basis revision, and required
idempotency key. Authority commands return a durable accepted/rejected
decision reference; proposal acceptance never implies command success.

## Per-operation transport semantics

| Class | Disconnected behaviour |
| --- | --- |
| Read/query | use a compatible cache with visible watermark, or fail |
| Observation/event | append locally and submit idempotently later |
| Claim/lease/transition | require live authority consensus |
| Acceptance/ratification | require live authority and human identity where specified |
| Local effect | execute locally under its environment record, then report evidence |

The authority location does not make every operation remotely executable.
Offline claims remain unsupported. `work.completed` remains a bufferable fact;
`work.item.done` remains an authority transition.

## Deployable product and environment split

The public Vuoro repository publishes:

- a versioned transport-only client package;
- one immutable multi-command service OCI image;
- a Docker Compose stack for local evaluation;
- a neutral `deploy/kustomize/base` with service, probes, configuration,
  network-policy defaults, and migration Job templates.

Appservice owns concrete overlays, secrets, databases, networking, backup,
promotion, and rollback. Environment differences are configuration only; no
environment-specific catalog, migration, workflow rule, or application branch
is permitted.

Appservice first deploys a persistent isolated `vuoro-dev` runtime with its
own namespace, database authority, identities, endpoint, and retained
functional-test state. It must have no production credentials, data mounts, or
network authority. Explicit admin jobs may seed or reset it and must refuse to
run unless `environment_class=development`.

The same service image digest moves through:

1. development migration jobs and compatibility checks;
2. black-box four-domain functional tests;
3. recorded image/catalog/schema evidence;
4. production migration jobs;
5. production rollout and non-destructive smoke tests.

Local Compose may use one PostgreSQL instance with four schemas. Runtime
configuration must nevertheless accept independent domain DSNs so production
can retain separate database clusters. The Kubernetes base assumes externally
provided databases and secrets and does not require CNPG.

## Environment records

The normative shape is
[`environment-record.schema.json`](../../../templates/dispatch/environment-record/environment-record.schema.json).
Records declare environment class, roles, constraints, capabilities, runbook
references, revision, and identity bindings. They never contain credentials.
The initial records cover workstation Linux, devbox-vm, `vuoro-dev`, and
production.

Client profiles select endpoint plus an identity credential reference. The
active environment is always visible; a development identity cannot address
production. This replaces per-repo `.envrc` knowledge for Vuoro transport,
while local build tools may continue to use their own environment setup.

## Ratification validation

Git remains canonical. The first enforcement mechanism is validation, not a
new authority store. A changed document entering `ratified` or ratified
supersession must carry:

- document ID and exact revision;
- ratifier identity and timestamp;
- a verified signature from a configured human ratifier.

Agent and automation identities may author and revise drafts but fail this
gate. The reusable rule belongs in agentops; repositories opt in through their
dispatch/verification boundary.

## Recovery authority

The devbox fat client is a bootstrap and disaster-recovery escape hatch, not a
second normal authority. `vuoro recovery begin --incident <id>` creates a
separate recovery namespace. Recovery records may contain observations and
requested commands, but never normal grants, accepted decisions, or claims
that compete with an unavailable production authority.

After recovery, the service imports records idempotently, reports conflicts
against current revisions, and requires human reconciliation before an
authority transition. This avoids split brain while preserving useful outage
work.

## External execution systems

Actionq remains the only writable execution queue. If Windmill or another
runtime is introduced, actionq claims the governed action and invokes that
runtime as a backend. Vuoro stores its execution reference and material
evidence receipts. Two schedulers never independently own the same work.

Future agent infrastructure may supply identities, delegation, tool discovery,
sandboxes, scheduling, and receipts. Vuoro references those concepts only when
they change responsibility, durable work structure, evidence, or acceptance;
it does not mirror every runtime-internal subtask.

## Sequencing and gates

1. Land this decision, owner alignment notes, and owner-correct backlog.
2. Remove shared-schema migration from clients and deploy migration roles/jobs.
3. Bootstrap the public service/client repository and operation contracts.
4. Extract and compose all four domain adapters.
5. Deploy isolated `vuoro-dev`; run migration and black-box functional gates.
6. Remove workstation database credentials and cut over endpoint/identity clients.
7. Add environment injection and human-only ratification validation.
8. Retire split backend/client authority only after catalog parity and recovery evidence.
9. Add marked DR reconciliation and optional external execution backends.

Every phase is independently useful and reversible before the final removal
gate. Existing direct clients remain explicitly transitional; their historical
plans are preserved but must link here when describing target architecture.

## Acceptance invariants

- A client installed before a service release discovers a new supported
  operation without reinstalling.
- Client packages contain no shared-authority migrations or database access.
- Runtime roles cannot execute DDL; service startup never migrates.
- Development migration and reset paths cannot reach production.
- The same OCI digest is verified in development and promoted to production.
- Cross-domain adapters cannot write each other's schemas.
- Offline observations converge idempotently; authority changes require live
  decisions.
- Human-only ratification rejects agent-authored transitions.
- Recovery records cannot create competing claims or accepted decisions.

## Related decisions

- `sprintctl/docs/plans/adr-outbox-sync-model.md` remains canonical for the
  observation/command/decision split and synchronization invariants.
- [`state-event-command-matrix.md`](state-event-command-matrix.md) assigns
  current domain ownership.
- [`write-surface-policy.md`](write-surface-policy.md) governs the transitional
  cockpit and direct-client write surfaces.
- [`vuoro-appservice-runtime-handoff.md`](vuoro-appservice-runtime-handoff.md)
  translates this plan into deployment-owned work.
- [`vuoro-backlog-enablement-2026-07-21.md`](vuoro-backlog-enablement-2026-07-21.md)
  records owner-local items #1185–#1202, refinements to #1163/#1164 and
  #1173/#1174, priorities, and the cross-repository critical path.
