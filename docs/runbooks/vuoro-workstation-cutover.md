---
doc_id: vuoro-workstation-cutover
status: current-runbook
revision: 5
scope: sprintctl-item-1195
---

# Vuoro served-work cutover

This runbook is the execution contract for sprintctl item **#1195**. It moves
normal workstation and `devbox-vm` work operations from direct PostgreSQL to
the durable `vuoro-shared` production-class service. It is deliberately a gate, not
permission to change production, expose a database, or print a credential.

`vuoro-dev` has a separate purpose: it is an ephemeral environment for
development-build tests and UX validation. It is not the shared authority for
normal development work, must not be selected by a repository `.envrc`, and
must not be used as evidence for retiring the shared database path. The
`vuoro-shared` profiles below select the persistent primary authority.

The current canonical non-secret inputs for normal shared work are:

- `templates/dispatch/environment-record/workstation-linux.vuoro-shared.json`;
- `templates/dispatch/environment-record/devbox-vm.vuoro-shared.json`; and
- the matching files under `templates/dispatch/environment-record/profiles/`.

Validate them before selecting the shared authority:

```bash
python templates/dispatch/scripts/validate_vuoro_profiles.py \
  --environment templates/dispatch/environment-record/workstation-linux.vuoro-shared.json \
  --profile templates/dispatch/environment-record/profiles/workstation-vuoro-shared.json

python templates/dispatch/scripts/validate_vuoro_profiles.py \
  --environment templates/dispatch/environment-record/devbox-vm.vuoro-shared.json \
  --profile templates/dispatch/environment-record/profiles/devbox-agent-vuoro-shared.json
```

The validator rejects a production target, a non-HTTPS endpoint, token-bearing
or URL-bearing credential references, authority drift, and an accidental
profile/environment pairing. It does not contact a service or read a secret.

## Preconditions

Do not change a workstation `.envrc`, revoke database access, or remove the
`sprintctl-pg` LoadBalancer until every item below is green. In particular,
there must be a separately deployed durable `vuoro-shared` production-class
environment and shared-work profiles; `vuoro-dev` cannot satisfy this gate.

1. The exact deployed `vuoro-shared` image exposes a compatible handshake,
   catalog, and the complete sprintctl work catalog. Record its image digest,
   catalog revision, and handshake response without credentials.
2. Sprintctl has a tested `served` backend. It consumes only
   `SPRINTCTL_VUORO_PROFILE`; `SPRINTCTL_URL` must be rejected in that mode and
   importing the served path must not import `sprintctl.pg`, `psycopg`, or a
   migration module.
3. The local checkout of `vuoro-client` is pinned to the release used by the
   endpoint. `vuoro-client` currently requires Python 3.12 or later, so the
   served Sprintctl install must use a compatible interpreter even though local
   SQLite recovery can retain its broader interpreter support.
4. Appservice has issued one `vuoro-shared` identity for the workstation and
   one for `agent@devbox`; each has exactly the authorities in its corresponding
   profile. The encrypted `vuoro-identities` registry must bind both identities
   to `vuoro-shared`. The ephemeral `vuoro-dev` identities are distinct and
   cannot address `vuoro-shared`.
5. A black-box parity run has exercised each catalog operation and its error
   mapping: reads, claim start/arbitration, lifecycle arbitration, evidence,
   ordered batches, project reads/batches, and cutover evidence. Claims and
   lifecycle retries must retain immutable-command idempotency. Group A claim
   arbitration must also satisfy
   [`vuoro-claim-proof-transport-clarification-2026-07-23.md`](../plans/agentops/vuoro-claim-proof-transport-clarification-2026-07-23.md).
6. The kctl remote adapter has either a served read composition or an explicit,
   verified local-only mode. It must not silently retain a direct Sprintctl
   database connection after the profile migration.

The direct database CLI paths (`remote-schema`, `migrate-to-remote`, remote
doctor probes, and PostgreSQL administration) remain deployment/recovery-only.
They must require an explicit administrative/recovery invocation and are not a
fallback for a failed served request.

## Sprintctl implementation gate

The owner implementation must make these boundaries mechanically observable:

| Concern | Required served behavior |
| --- | --- |
| Backend selection | Accept `SPRINTCTL_BACKEND=served`; require `SPRINTCTL_VUORO_PROFILE`; reject a set `SPRINTCTL_URL`. |
| Profile | Parse the validated JSON profile, use the endpoint and expected environment exactly as recorded, and resolve only its `file:` credential reference. |
| Dependencies | Put `vuoro-client` in a `served` extra; the normal served import graph contains no PostgreSQL driver, DSN parser, DDL, or migration code. |
| Transport | Use `AsyncVuoroClient.handshake()`, catalog discovery, and schema-driven invocation. Keep catalog revision, basis revision, and idempotency keys intact. Proof-bearing commands use negotiated `invocation/v2`; proofless v1 compatibility remains explicit. |
| Claim proof | Carry digest-bound proof bytes only in v2 transient credentials, outside catalog arguments. Support both current and proposed proofs for rotating handoff and prove the bytes never enter logs, records, decisions, caches, or errors. |
| Claim context | Resolve authenticated actor, authority repository UUID, non-secret claim state, and claim revision through `work.claim.context`; never guess them or open a database from the client. |
| Claim parity | Heartbeat applies metadata, handoff emits non-secret coordination evidence atomically, retry reuses the immutable record, and release clears terminal retry material. |
| CLI parity | Route every ordinary work command through the catalog mapping in `docs/reference/vuoro-work-adapter.md`; do not add a direct SQL compatibility branch. |
| Recovery | Local SQLite is selected only by explicit `local`/recovery configuration. Legacy claim-recovery files remain local-only and are never written by served mode. Mode-0600 event-keyed authority sidecars may retain proof only for immutable-command retry and proposed-proof recovery. Ordinary served mode rejects `--allow-legacy-adopt`; proofless adoption requires a separate recovery authority. |
| Diagnostics | `sprintctl doctor` in served mode performs handshake/catalog diagnostics only. Database migration/administration commands fail closed unless explicitly invoked in deployment/recovery mode. |

The current public `vuoro-client` distribution intentionally supplies the
transport object, not a filesystem profile loader. Sprintctl therefore owns the
small `file:` reference resolver. It must expand only `~/` for the effective
user, require a regular mode-0600 file owned by that user, strip one trailing
newline, reject empty content, and never render the reference's contents in
errors or diagnostics.

## Group A claim arbitration gate

The approved proof, context, parity, retry, and recovery boundaries are
normative in
[`vuoro-claim-proof-transport-clarification-2026-07-23.md`](../plans/agentops/vuoro-claim-proof-transport-clarification-2026-07-23.md).
Do not wire served heartbeat, handoff, or release by:

- putting raw proofs in catalog operation arguments or immutable records;
- treating the identity bearer credential, actor label, proof digest, or
  current database row as a substitute for possession of the claim proof;
- deriving command actor or basis revision from an advisory CLI option;
- adding a direct PostgreSQL preflight;
- retrying an unknown outcome with a new event ID; or
- allowing `--allow-legacy-adopt` under an ordinary `work:claim` identity.

The black-box gate must include a rotating handoff carrying two transient
bindings, a lost-response identical retry, a stale-basis rejection, heartbeat
metadata parity, atomic handoff evidence, release cleanup, proof-redaction
inspection, and an explicit ordinary-served rejection of proofless adoption.

## Identity and environment boundary

Appservice owns the encrypted `vuoro-identities` secret. Create unique opaque
production tokens through the approved secret workflow; write each token only
to the profile's mode-0600 credential file on its named host. Do not put a
token in Git, `.envrc`, a shell history, a sprint note, or a command argument.

The following registry entries use these principals and exactly the nine
profile authorities, but are ephemeral-validation identities only:

| Credential file | Actor | Bound environment |
| --- | --- | --- |
| `~/.config/vuoro/credentials/vuoro-shared-workstation` | `workstation-vuoro` | `vuoro-shared` |
| `/home/agent/.config/vuoro/credentials/vuoro-shared-agent` | `devbox-agent-vuoro` | `vuoro-shared` |

Vuoro rejects an identity whose environment differs from the deployment before
calling an adapter. The negative proof is mandatory: using either development
credential against an operator-supplied production endpoint for a read-only
catalog operation returns `environment-mismatch` (or `identity-required` if
production has no matching resolver) and produces no domain record. Record the
HTTP status and stable error code, never the token or endpoint credentials.

## Workstation

Do not execute this cutover against the current `vuoro-dev` profiles. First
create and validate the persistent production environment record and
workstation `vuoro-shared` profile through the owner workflow; substitute that
profile in every command below.

1. Check out the released Vuoro source at the deployment-pinned revision and
   install the transport-only client and the served Sprintctl extra with Python
   3.12+; confirm the resolved dependency graph has no `psycopg`.
2. Install the workstation `vuoro-shared` credential at the file path in its
shared profile with directory and file permissions `0700` and
   `0600`. Its path is a reference, not a shell variable containing a secret.
3. Run the shared-profile validator, then a handshake/catalog check and
the full black-box Sprintctl parity suite against `vuoro-shared`. Run the
   ephemeral suite against `vuoro-dev` separately for build/UX validation;
   it is not evidence for the production gate.
4. Only after those checks pass, replace the shared Sprintctl portion of each
   workstation project `.envrc` with:

   ```bash
   export SPRINTCTL_BACKEND=served
   export SPRINTCTL_VUORO_PROFILE=<operator-issued-vuoro-shared-profile>
   unset SPRINTCTL_URL
   ```

   `<operator-issued-vuoro-shared-profile>` is the path to the profile JSON
   itself (e.g.
   `templates/dispatch/environment-record/profiles/workstation-vuoro-shared.json`),
   **not** the path the profile's own `credential_ref` points at — those are
   two different files.

   Apply that replacement to `_orchestration`, `actionq`, `agentops`,
   `aligned-equity`, `box`, `homelab-analytics`, `scribectl`, and `sprintctl`.
   Retain `SPRINTCTL_DB` only where it is needed for explicitly selected local
   recovery; served mode must not open it.
5. Each repository also carries a local, uncommitted `.sprintctl/backend.json`
   marker (written once by an earlier `migrate-to-remote` run) that pins the
   backend mode independently of `.envrc`. `sprintctl` refuses to run in
   `served` mode unless this marker's `"backend"` field also reads `"served"`
   — flip it by hand in each repository before testing:

   ```bash
   python3 -c "
   import json
   p = '.sprintctl/backend.json'
   d = json.load(open(p))
   d['backend'] = 'served'
   json.dump(d, open(p, 'w'), indent=2)
   open(p, 'a').write('\n')
   "
   ```

   Keep the prior marker content (uncommitted) alongside the `.envrc` backup
   until all eight checks pass.
6. Start a fresh shell in each repository and prove `SPRINTCTL_URL` is unset,
   `sprintctl doctor --json` reports `served` with `credential_resolved: true`,
   and a read plus one safe dev lifecycle/claim test reaches the catalog. Keep
   the existing profiles and backend markers as uncommitted backups until all
   eight checks pass. An empty catalog under `served` mode (no sprints/items
   where `remote` mode shows real ones) is not proof of a broken profile — it
   means the production `vuoro-shared` substrate has not yet been promoted
   with this repository's data (see sprintctl #1223); do not roll `.envrc` or
   the marker forward workstation-wide until that promotion evidence exists.

   The final static check is:

   ```bash
   python /projects/dev/agentops/templates/dispatch/scripts/validate_vuoro_workstation_cutover.py \
     --root /projects/dev \
     --profile <operator-issued-vuoro-shared-profile>
   ```

## Devbox-vm

`devbox-vm` has independent worktrees, ignored state, and tool installations;
the workstation change does not propagate. Perform the same steps as user
`agent` after the workstation profile is validated:

1. Pull the required Sprintctl and Vuoro revisions into the devbox clones and
   install the served tool using Python 3.12+ under `/home/agent`.
2. Install only the named devbox `vuoro-shared` credential with mode `0600`; do
   not reuse the workstation or ephemeral identity, or a PostgreSQL URI.
3. Validate the devbox `vuoro-shared` record and profile, then run handshake,
   catalog, parity, and production-negative checks from the VM.
4. Replace the same eight devbox `.envrc` blocks with the following exact
   non-secret selection and refresh `direnv allow` in each checkout:

   ```bash
   export SPRINTCTL_BACKEND=served
   export SPRINTCTL_VUORO_PROFILE=<operator-issued-vuoro-shared-profile>
   unset SPRINTCTL_URL
   ```

5. Reinstall Sprintctl as a user tool from the devbox checkout. Confirm the
   old `[remote]` extra and `psycopg` are absent from the normal agent path.

   Run the same static check from devbox-vm with
   the devbox `vuoro-shared` profile as `--profile`; its independent worktrees
   must pass on their own.

## Final revocation and rollback

After both hosts have independently passed the complete gate, appservice may
remove workstation/devbox access to the CNPG bootstrap secret and retire the
external `sprintctl-pg` LoadBalancer. Verify from both profiles that the old
database address is unreachable and that no `.envrc` retrieves
`sprintctl-cnpg-main-app`.

Rollback is limited to restoring the previous `.envrc` from its local backup
and the approved deployment credential/network policy while the served service
remains healthy. Do not use a direct PostgreSQL path as an automatic retry or
silent fallback. Any production rollback follows the appservice owner runbook.
