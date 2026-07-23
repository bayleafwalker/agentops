---
doc_id: vuoro-continuation-blockers-2026-07-22
status: current-observation
observed_at: 2026-07-22
updated_at: 2026-07-23
scope: supervised-continuation-handoff
---

# Vuoro continuation blockers

This is a current-state handoff, not a new architecture decision or an
appservice implementation authorization. The ratified architecture remains
[`vuoro-served-substrate-plan.md`](vuoro-served-substrate-plan.md), and the
deployment owner handoff remains
[`vuoro-appservice-runtime-handoff.md`](vuoro-appservice-runtime-handoff.md).

## 2026-07-23 update

Item #1195 has been resumed by a separate implementation session; this
document's earlier pre-claim instructions are retained as the handoff history,
not as a direction to create a competing claim. The operator-approved Group A
contract for claim proof transport, authenticated claim context, parity, retry,
and recovery separation is now
[`vuoro-claim-proof-transport-clarification-2026-07-23.md`](vuoro-claim-proof-transport-clarification-2026-07-23.md).

## Confirmed completion

Sprintctl items **#1193** and **#1194** were published and closed at
`f750d63`. Their independent PostgreSQL and full-suite verification had
completed before publication. There are no active claims to resume.

The supervised workspace must not replace the missing Vuoro endpoint with a
workstation database connection. The local sprintctl environment currently
has no configured remote URL; that is an expected configuration boundary, not
authorization to use a direct database path.

## Blocker A: served endpoint and identity cutover (#1195)

**Owner / authority needed:** appservice source, its live owner backlog, and
an operator-authorized Vuoro endpoint and identity configuration.

Before #1195 may be claimed, the following must be available and linked to
the owner-local appservice work:

- the appservice source and current GitOps topology for a read-only
  inspection;
- a durable `vuoro-shared` endpoint with a named development environment record;
- a development identity credential reference and its least-privilege
  operation grants (never the credential value in Git or a sprint note);
- proof that the development identity cannot address production; and
- the deployment-owned migration, health, rollback, and black-box functional
  gates described in the ratified appservice handoff.

At that point, create or link the appservice owner-local records through
coordination item #1189, then claim #1195. The first implementation check is
that the client profile derives its endpoint and identity from the environment
record and has no fallback to a workstation database DSN.

## Blocker B: four-domain adapter composition (#1204, then #1205)

**Owner / authority needed:** immutable, independently verifiable adapter
inputs for `sprintctl`, `actionq`, `kctl`, and `auditctl`, or a ratified
composition manifest that pins equivalent inputs.

Each input must identify the domain, source revision, artifact location,
immutable digest, adapter/API compatibility range, and migration entrypoint.
The resulting manifest must itself be versioned and immutable. Mutable branch
names, local worktrees, or package versions without a digest are insufficient:
the Vuoro service must be reproducible and must not silently compose a changed
domain adapter.

Once all four inputs exist, #1204 can compose and compatibility-check them in
one Vuoro service process. It must retain the domain database boundaries and
prove that an adapter cannot write another domain's schema. #1205 remains
blocked until #1204 produces the composition reference that packaging can pin
into the service image and release evidence.

## Supervised resumption order

1. Make the appservice source and authorized development endpoint/identity
   configuration available; inspect before creating appservice-local backlog.
2. Record the owner-local links and deployment entry criteria under #1189;
   then take #1195 only with the new environment record in place.
3. Publish or ratify the four adapter pins; validate their digests and
   compatibility before taking #1204.
4. Use #1204's resulting composition reference to start #1205 and later the
   deployment promotion gates.

No production deployment, secret creation, direct database access, or
cross-repository claim is authorized by this note.

## Prepared #1195 resumption package

The appservice source now declares the persisted `vuoro-shared` overlay with
an isolated development authority, HTTPS route, development-only identity
registry mount, separate runtime DSNs, and migration/compatibility jobs. The
ephemeral `vuoro-dev` overlay remains available for build and UX validation.
This establishes the source-inspection prerequisite; deployment verification
and usable client credentials remain separate gates.

Agentops now provides ephemeral validation inputs in
[`templates/dispatch/environment-record/`](../../../templates/dispatch/environment-record/):

- validated workstation and devbox-vm environment records;
- separate `vuoro-shared` profiles with file credential references and the
  exact current sprintctl work authorities; and
- a dependency-free profile validator that rejects a production target,
  credential-bearing URL, authority drift, or invalid source host; and
- a final eight-repository `.envrc` scanner that refuses remaining
  `SPRINTCTL_URL`, CNPG-bootstrap, LoadBalancer, PostgreSQL URL, or remote-mode
  wiring.

[`vuoro-workstation-cutover.md`](../../runbooks/vuoro-workstation-cutover.md)
is the handoff for an unattended implementation agent. It records the real
public client boundary: `vuoro-client` is transport-only and has no generic
filesystem profile loader, while its current distribution requires Python
3.12+. Sprintctl therefore still needs the served backend/profile resolver,
catalog routing, parity evidence, and no-PostgreSQL dependency proof before
any of the eight profiles can be migrated.

The remaining authority-sensitive actions stay with their owners: appservice
must verify the durable `vuoro-shared` deployment and deliver the two baseline
identity credentials; sprintctl must implement and verify served normal
operation; kctl must select a served read path or explicitly local-only mode.
Only then may the runbook's two host gates run and database access be revoked.
The host gates require durable `vuoro-shared` records and identities; the
current `vuoro-dev` deployment remains intentionally ephemeral and is not a
normal development-work authority.
