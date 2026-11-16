# Resident memory implementation

The implementation is opt-in. Nothing installs a timer, starts a resident,
provides a model credential or changes a host configuration by being merged.

## Components

| Owner | Implementation | Responsibility |
|---|---|---|
| AgentOps | `scripts/resident_memory/`, `scripts/resident_memory_cli.py` | Source snapshots, current heads/tombstones, ingestion receipts, scoped read facade |
| AgentOps | `scripts/resident_context.py` | Exact bounded context packets and current-source recheck |
| AgentOps | `hooks/session-note-start.sh`, `hooks/session-note-stop.sh` | Opt-in semantic handover notes; existing structured handoff is unchanged |
| AgentOps | `scripts/resident_evolution.py` | Receipt-bound candidate pointer metadata; no OS activation |
| lanectl | `lanectl resident` | Qualified bounded episodes, duplicate wake handling, process cleanup and recovery fencing |
| lanectl | `resident_native`, `resident_gateway`, `resident_systemd` and NixOS module | Concrete native Go/local routes, separate credential service and isolated executor composition |
| Hindsight downstream | `hindsight-extensions/resident/` | Tenant identity, exact bank grants, strict tag scopes and separate internal maintenance grants |
| Hindsight downstream | coding-agent `managedContext` | Only facade `memory_search`; no independent injection, retention or raw engine tools |

The memory SQLite database is an integration receipt/source store. It is not a
replacement task tracker or canonical knowledge service. Exact selected learned
text is retained because rerunning inference does not reproduce prior memory.

Use [resident execution paths](resident-execution-paths.md) for the devbox and
isolated-workstation profiles, on-demand local generation and pinned CPU
embedding deployment. Source availability does not establish host activation.

## Protected policy

Provision this through the host owner. Generate real random reader and facade
credentials; the zero hash below is deliberately unusable. Keep state and the
upstream credential outside the resident writable tree and enforce different
service identities. This example uses no real secret or target-host identity.

```json
{
  "schema": "resident-memory-policy/v1",
  "state_dir": "/var/lib/resident-memory",
  "upstream_url": "http://127.0.0.1:8888",
  "upstream_token_file": "/run/credentials/resident-memory/hindsight-token",
  "max_source_bytes": 65536,
  "max_result_bytes": 32768,
  "max_request_bytes": 8192,
  "scopes": [{
    "id": "story", "bank": "resident-story", "resident": "r01",
    "project": "story", "branch": "main",
    "source_root": "/srv/resident/story",
    "source_paths": ["canon.md", "rumours.md", "episodes/*.json"]
  }],
  "principals": [{
    "id": "story-reader",
    "token_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
    "scopes": ["story"]
  }]
}
```

Source paths are exact relative paths or filename-only patterns under explicitly
named directories. Traversal, hidden paths and symlinks in any component are
refused. Collection files such as episode notes should have immutable unique
names. A changing canon file has one logical source identity and new revisions.
Source content and source kind both participate in revision identity.

Hindsight must grant the facade retain/recall and operation-status access to the
same bank and exact three scope tags. It must not expose its API directly to the
resident. Its `resident/README.md`, policy example and environment template define
the server/worker side. Keep extraction/consolidation and worker grants separate.

The facade is a small single-request loopback service, with bounded request and
response bodies. Put it behind the qualified host transport for other namespaces;
do not bind it to all interfaces as a shortcut. It is not a hardened public server.

## Capture and ingest

Run as the trusted importer, using the protected policy path:

```sh
python scripts/resident_memory_cli.py --policy /etc/resident/memory.json \
  capture --scope story --path canon.md --kind canon
python scripts/resident_memory_cli.py --policy /etc/resident/memory.json \
  ingest --source SOURCE_ID_FROM_CAPTURE
python scripts/resident_memory_cli.py --policy /etc/resident/memory.json \
  reconcile --operation OPERATION_UUID_FROM_INGEST
python scripts/resident_memory_cli.py --policy /etc/resident/memory.json \
  status --scope story
```

Capture commits bytes and current-head metadata before ingestion. Ingestion
commits the exact payload and deterministic upstream UUID before network dispatch.
`submitted` means queued acknowledgement; `retained` requires operation completion.
Consolidation is reported separately as `not-observed` in this initial adapter.
There is no automatic consolidation tick or retry loop.

A repeated ingest polls its existing operation. Lost acknowledgements reconcile
against that operation ID. If the engine has pruned its receipt, the state remains
`unknown`; this adapter will not create fresh work based on a missing receipt.
Failed/cancelled operations also require explicit operator repair. Never delete
the integration ledger to force a retry.

The importer is deliberately separate from the model's tools. A model cannot
assign `canon`, change bank/source paths or forge source provenance through the
HTTP endpoint. Capture only authored source and accepted episode notes; do not
capture an injected memory packet as a new observation.

## Read and build a fresh context

```sh
python scripts/resident_memory_cli.py --policy /etc/resident/memory.json \
  serve --port 8791
```

The only HTTP operation is `POST /v1/search`, with bearer reader authentication:

```json
{"scope_id":"story","query":"What remains unresolved in this story?"}
```

There is no caller-supplied bank, tag filter, upstream URL, source path, admin
operation or write endpoint. Results include advisory entries, source references,
semantic source-kind labels, omissions, explicit outage state and ingestion lag.
Observation lineage must resolve completely. Untagged/foreign facts, stale files,
unretained sources and incomplete source-fact maps are omitted.

Configure the downstream coding-agent adapter:

```json
{
  "managedContext": true,
  "serverMode": "self-hosted",
  "apiUrl": "http://127.0.0.1:8791",
  "apiToken": "SUPPLY_READER_TOKEN_FROM_HOST",
  "managedScopeId": "story"
}
```

Managed mode disables independent roster/preamble/memory injection, seeding,
retention and skill synchronization. The single `memory_search(query)` tool calls
the facade. Missing configuration/failure does not fall back to the raw engine.

The context CLI combines trusted instructions/current work, required source bytes
and optional recalled memory:

```sh
python scripts/resident_memory_cli.py --policy /etc/resident/memory.json \
  context --scope story --instructions /etc/resident/charter.txt \
  --work /var/lib/resident-admission/current-work.json \
  --query 'Continue the current edition' --required-source CANON_SOURCE_ID \
  --output-dir /var/lib/resident-admission/contexts
```

`current-work.json` is a concrete observation from the existing work owner. The
CLI does not invent an agenda or sync state into a new tracker. A blocked packet
remains reviewable on disk and must never be launched. Required sections are
never silently truncated; mandatory overflow is an error.

Immediately before admission, recheck the sources:

```sh
python scripts/resident_memory_cli.py --policy /etc/resident/memory.json \
  recheck --scope story --context /var/lib/resident-admission/contexts/DIGEST.json \
  --generation 1
```

This emits an observation valid for 30 seconds, binding both the packet's internal
digest and its full file hash. The protected admission service installs it as a
root-protected receipt for lanectl. This CLI does not mint operating-system
protection, launch a process or grant external effects. Recheck again before any
later source-dependent effect through that effect's existing owner.

The packet's `digest` excludes its own digest field. `lanectl --context-sha256`
is the SHA-256 of the complete file, so those two values are intentionally distinct.

## Corrections

Edit and version the authored file, then capture its new revision. Even before
recapture, changed bytes make the old source unavailable for derived recall.
Retraction is immediate and monotonic in this store:

```sh
python scripts/resident_memory_cli.py --policy /etc/resident/memory.json \
  retract --source SOURCE_ID --reason 'Withdrawn by the source owner'
```

Retraction denies recapture until an explicit operator repair. It suppresses
affected raw and synthesized results but does not delete upstream learned state.
Upstream repair/reprocessing and legal deletion are separate operations. This
initial implementation has no public restore/delete/admin endpoint.

Memory labelled as rumour remains advisory rumour even if it is retrieved often.
The current exact canon belongs in `required_sources`; a memory summary never
becomes a substitute instruction or owner decision.

## Episodes and local evolution

Use lanectl's disabled example profile and commissioning runbook. Execution
requires a protected, unexpired qualification receipt tied to the precise launcher
recipe. A fresh wake ID admits new work; replaying an old wake returns its receipt.
One coordinator owns the workspace. Continuation is a proposal in the checkpoint;
the existing work/admission owner decides whether to schedule another episode.

`resident_evolution.py` prepares a compare-and-swap runtime pointer only after
the evaluator receipt binds the candidate, configuration, matched state manifest,
current protected boundary and prior pointer. Candidate evaluation cannot replace
the evaluator that judges that candidate. The module performs no service restart,
database restore, arbitrary NixOS activation or provider credential operation.

## Verification and host acceptance

```sh
uv run --no-project --with pytest --with pyyaml python -m pytest -q \
  scripts/tests/test_resident_memory.py scripts/tests/test_resident_memory_transport.py \
  scripts/tests/test_resident_context.py scripts/tests/test_resident_evolution.py \
  scripts/tests/test_session_notes.py scripts/tests/test_session_note_hooks.py
uv run --no-project --with pytest --with pyyaml python -m pytest -q scripts/tests
```

The focused three-context story is a deterministic contract test. It demonstrates
source correction, context independence and rumour labels; it is not a native
model-quality result. Actual host acceptance must still demonstrate:

- Three fresh native episodes and one bounded critic producing a finished local edition.
- No provider credential, raw engine API, database, broad forge token or supervisor
  socket access from arbitrary resident tool code.
- Every paid inference/embedding request admitted through the qualified aggregate
  gateway, including retries, failed calls and consolidation; no fallback route.
- Admission-time source checks, coordinator crash/child cleanup, duplicate wake,
  fencing, blocked source owner and denied-budget recovery.
- A matched restore drill, with post-checkpoint corrections/spend/effect receipts
  preserved before any readmission.

These are activation gates. A fixture process or a configuration boolean does not
establish them. The source implementation leaves execution disabled until the
host owner supplies the actual qualified route, limits and receipt.

## Recovery and rollback

Create the integration snapshot with SQLite's backup API (which includes WAL):

```sh
python scripts/resident_memory_cli.py --policy /etc/resident/memory.json \
  backup /protected-backup/resident-memory.sqlite3
```

Use database-native consistent PostgreSQL backup/PITR and back up Git/source files,
context/selection snapshots and lanectl receipts. Bind runtime/configuration/schema
and owner checkpoints in the recovery manifest. A portable Hindsight bank export
is useful migration evidence, not an exact replacement for an operational backup.

To roll back: deny new admissions/effects; stop and drain workers; snapshot current
state; fence the generation; restore a matched candidate/configuration/database
set in a clean environment; retain/reapply the latest correction tombstones,
spent-budget ledger, revocations and external-effect receipts; reconcile unknown
work with its owners; then requalify and readmit. Do not restore yesterday's budget
allowance or turn restored leases into new execution authority.

RPO/RTO are unmeasured until a timed restore succeeds. All source, derived text and
lineage should remain available if the semantic backend is later replaced.
