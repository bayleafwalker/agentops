# EC-01 owner source interfaces: four-owner increment

This additive inventory records concrete source declarations for `cred-broker`, `datacluster-template` (owner `datacluster`), `acceptance-lab`, and `homelab-analytics`. It supplements the existing source census and first-consumer extraction; it does not alter their historical counts or claim completeness.

Every record is pinned to a full Git commit and SHA-256 hashes of the exact inspected files. The checker re-reads Git objects from supplied local repositories, so it checks committed source rather than a dirty worktree. Visibility is a dated canonical GitHub metadata observation; it is not proof that a particular source commit is the current default branch.

## Source findings

The broker declares a versioned HTTPS/JSON service with broker, approval, session, protected-intent, and protected-effect readout routes. Its client makes bounded calls without automatic retries; its protected-intent documentation specifically prohibits retrying an ambiguous POST. The service source distinguishes ordinary broker paths from private protected routes. The consuming principals and actual deployed catalog remain unknown.

Datacluster’s committed template declares Spark Operator `SparkApplication` resources using `sparkoperator.k8s.io/v1beta2`, Spark 3.5.0, Avro landing/curated records, and retry defaults in the YAML. The Terraform source declares a Hetzner/Talos provisioning boundary and sensitive inputs/outputs. These are template declarations, not evidence of a live cluster, instantiated resources, or a configured state backend.

Acceptance Lab declares a local `acceptlab` CLI and SQLite event store. Source describes an append-only event chain and rebuildable projections; scenario/candidate schemas carry a version value. It does not declare a network protocol in the inspected files. File location, backup/retention and downstream consumers remain unknown.

Homelab Analytics declares a FastAPI surface, an MCP JSON-RPC stdio server, and worker command entry points. MCP source pins protocol revision `2025-06-18`; selected routes include agent catalog/index, auth session, schedule retry, and Home Assistant ingest/action proposal. Route policy code declares authorization decisions. The selected retry route accepts only completed or failed dispatches. This source inspection does not establish deployed callers, credentials, backing store, or the effective runtime version.

## Unresolved inventory fields

For all four owners, configured consumers, runtime version/catalog, actual traffic, effective credentials and principals, deployment target, compatibility window, cutover, rollback, shim expiry, and per-interface disposition remain unknown unless a source file states a local implementation detail. No private repository, credential, environment file, runtime service, or production API was read. No canonical IDL or generated projection is proposed here. Source evidence is not owner attestation or runtime qualification; EC-01 remains partial.

Run `python scripts/check_ec01_owner_source_interfaces.py docs/architecture/2026-10-18-estate-owner-source-interfaces.json --repo cred-broker=/path/to/cred-broker --repo datacluster-template=/path/to/datacluster-template --repo acceptance-lab=/path/to/acceptance-lab --repo homelab-analytics=/path/to/homelab-analytics` to verify exact Git source pins. This command is local and makes no network calls.
