# S4 causal intake and interruption proof

The released Sprintctl 0.15.1 carrier and Vuoro service 0.1.89 image preserve
original offline requests and recover committed operations without duplicating
owner effects. Three independent histories refuse progression after a changed
context, description revision or evidence head. This qualifies causal intake,
replay and the explicit orchestration barriers. It does not qualify the complete
[S4 absorb specification](../../plans/2026-10-03-s4-evidence-home-preparation.md):
served validity/effect-state evaluation, authenticated execution facts, real
inventory import, production writer commissioning, cutover and soak remain open.

## Executed histories

An installed-release CLI captures reservation, evidence and bound proposal while
its isolated authority is stopped. A real harmless Git commit carries the exact
previously observed Release trailer. After restart, explicit stage barriers
confirm the original full Release, normal negotiated trailer ingestion, exact
original evidence tail and authenticated proposal admission. A continuously
online clone applies the same original requests in order. Comparison preserves
item and Decision state, original admission, proposal canonical digest,
reservation state and snapshot, evidence identities, counts and producer cursors.
Only generated intent identity (mapped through its original key), receipt/activity
timestamps and measured activity age are normalized. Initial and recovered
reservation replay flags are asserted separately.

A verified local HTTPS proxy forwards each real operation, observes upstream
success, kills its own CLI child with SIGKILL and drops the committed response.
A new CLI process retries the original key for reservation, trailer batch,
evidence and bound proposal. The histories retain interrupted starts and separate
confirmed attempts. The proposal receipt is recovered byte for byte; each durable
key has exactly one owner effect. Legacy and bound proposal reuse of one key is
refused with the shared idempotency-conflict contract.

A separate synthetic lifecycle editor injects faults into three fresh clones:

- Adding a supported document reference before reservation preserves the full
  item revision but changes the frozen Release. The **explicit orchestrator
  comparison** stops dependent trailer/evidence/proposal sync. This does not
  claim that individual carrier commands enforce a dependency graph.
- Editing the description after reservation, trailer and evidence confirmation
  makes proposal admission return HTTP409 `effect-causal-stale-revision`.
- Appending the exact next evidence item makes proposal admission return HTTP409
  `effect-causal-evidence-head-mismatch`.

Each proposal refusal is repeated with original bytes/key. Durable rejected
attempts retain exact operation, code and HTTP status. Full authoritative
reservation, evidence, item and Decision rows and the evidence tail remain
unchanged across both retries; no intent or proposal idempotency receipt commits.
The original reservation receipt and recorded Release remain intact.

## Reproduce

Use Docker, OpenSSL, Nix (or PostgreSQL 16 binaries), and Python 3.12. Obtain the
six actual released wheels named in
[artifact-pins.json](../../../scripts/s4-proof/artifact-pins.json). Verify their
GitHub release attestations before installing them into an isolated environment;
install those local wheel files and their dependencies with `uv pip install` or
`pip`. Keep the original wheel files: the harness checks each wheel's pinned
SHA256 and every installed wheel member except the installation-updated RECORD.
Editable installations and missing/changed source wheels are refused. The service
container uses the pinned OCI digest; its actual composed catalog must match the
pinned revision and 78 operations.

```bash
S4_PROOF_PYTHON=/absolute/path/to/isolated-env/bin/python \
S4_PROOF_PACKET_ROOT=/absolute/path/to/private-receipts \
  timeout --foreground -k 30s 900s \
  scripts/s4-proof/s4-offline-causal-pg.sh
```

The wrapper creates only its own PostgreSQL cluster under `/tmp`, generates four
least-privilege fixture roles, applies owner migrations, and proves runtime DDL
refusal. The harness validates the wrapper-owned socket/PID/port and database
marker before accepting administration. It binds synthetic identity files and
verified ephemeral TLS into nonroot read-only local containers. No production
profile, credential, database, repository effect or identity modification is
used. Producer Git configuration and inherited profile/credential variables are
isolated. Only this attempt's named containers, children and cluster are stopped.
A hard-kill orphan requires inspection using its PID/start-time owner marker;
the runner does not sweep other clusters.

Generated bearer tokens, role passwords, DSNs and TLS private keys stay outside
Git and published receipts. Receipt packets snapshot executing source and pins,
original requests/binding, CLI results, harmless Git bundle and a SHA256 manifest.
Capture failure marks qualification incomplete and retains private scratch.
PostgreSQL fsync is disabled: this is client/service interruption evidence, not
database crash durability or production authentication qualification. The fixture
Git remote is metadata; it does not prove remote publication.

## Artifact provenance and limits

The [service composition](https://github.com/bayleafwalker/vuoro/pull/195),
[carrier](https://github.com/bayleafwalker/sprintctl/pull/136) and
[deployment](https://github.com/bayleafwalker/appservice/pull/1849) passed their
required CI and released artifact/runtime gates. Their provenance records are
separate from this disposable proof. Six-field run binding retains genuinely
nullable client/grant fields; this static fixture does not simulate authenticated
OAuth execution grants. Collector claims and effect proposals are never treated
as proof of accepted execution, grant use or non-invocation.

Earlier fixture failures remain failures: unsupported reference type returned422;
a strengthened reservation comparison initially retained the expected recovered
`replayed:true` history flag. Corrected attempts were rerun. They were harness
input/oracle errors, not owner defects. The final packet records only the exact
final source; earlier private attempt packets are retained rather than overwritten.
