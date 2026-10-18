# EC-01 source increment 2: programme interfaces and Elisa consumer

This additive source extract covers three programme owners—Aligned Equity, Browser Workbench, and Scribectl—and the remaining public Home Assistant consumer `ha-elisa-kotiakku`. It builds on the [initial census](2026-10-18-estate-source-interface-census.md), the [first-consumer extraction](2026-10-18-estate-first-consumer-contracts.md), and the four-owner source inventory. It does not replace prior snapshots or duplicate the already-recorded Browser Workbench Python↔Rust worker protocol.

The JSON companion pins every repository to an exact full Git commit and every inspected path to a SHA-256 of the Git object at that revision. All four repositories were confirmed `PUBLIC` through canonical GitHub metadata on 2026-10-18. The Browser Workbench checkout was dirty, so the inventory uses only its committed object at the reported public `main` SHA. Scribectl's checkout was behind public `main`; its source was read from an isolated clone pinned to the canonical-main SHA.

## Source interfaces found

Aligned Equity exposes a Python package of record validators and JSON Schema contracts for source-ledger and decision-output records. The checked schemas use JSON Schema draft 2020-12 and disallow additional fields. The source also declares an optional Homelab Analytics adapter module whose hooks are no-ops in the inspected revision. This does not prove that the adapter is installed or invoked.

Browser Workbench adds a distinct local command/file boundary: `browser-workbench` accepts `browser-workbench.run/v1` run-spec JSON and produces `browser-workbench.result/v1` envelopes. The CLI declares `run`, `capabilities`, `probe`, `compare`, and `corpus` commands, result status/exit-code mappings, and file paths for artifacts. The prior extraction already covers the separate Python↔Rust native worker protocol; this increment links to that record instead of restating it.

Scribectl declares a local CLI over Markdown notes with YAML frontmatter and wikilinks. Its context pack includes a truncated SHA-256 receipt; ratification candidates use a checkbox/target/provenance line grammar, and the source documents the writer's checkbox as the verdict authority. The local persistence boundary is vault files; this source review does not access a configured vault or invoke commands.

`ha-elisa-kotiakku` declares a Home Assistant config flow and a `GET https://residential.gridle.com/api/public/measurements` client authenticated with an `x-api-key` header. The manifest source version is 1.4.1, the coordinator polls at five-minute intervals, the client timeout is 30 seconds, and 429 handling uses the response's `Retry-After` hint to delay a later coordinator update. Home Assistant Store objects persist energy, economics, and analytics state. This is source behavior only; no key, Home Assistant installation, or API was queried.

## Limits

The extract does not establish current runtime consumers, installed versions, effective principals, configured deployment targets, traffic, operational retention, compatibility windows, cutover/rollback, shim lifetime, or interface disposition. No live service, private source, credential, environment file, production vault, browser backend, Home Assistant installation, or owner API was read or called. These records are source discovery, not runtime qualification or contract selection; EC-01 remains partial.

Verify source hashes locally with the shared checker, supplying all four checkouts. The Scribectl source path may be a clean public-main clone at the exact recorded commit:

```bash
python scripts/check_ec01_owner_source_interfaces.py docs/architecture/2026-10-18-estate-owner-source-increment-2.json \
  --repo=aligned-equity=/path/to/aligned-equity \
  --repo=browser-workbench=/path/to/browser-workbench \
  --repo=scribectl=/path/to/scribectl \
  --repo=ha-elisa-kotiakku=/path/to/ha-elisa-kotiakku
```
