# Historical audit attribution query

This derived query supplies repository attribution for known misfiled records
without editing authored shards, SQLite indexes, producer identity or event
payloads. `attributed_repo_id` is an observation for reporting. It supplies no
capability, membership, grant or owner authority. Original `resolved_context`,
payload digest and producer stream/sequence remain unchanged in the event.

Agentops #2592 describes September 28–30, 2026 records using an earlier approximate
count. The current bounded investigation found 1,399 unique IDs across two event
types: `workflow.session` and `dispatch.exit`. Historical explicit worktree
creation commands and paired successful replies resolve 30 aliases, alongside
two canonical checkouts. No attribution rule guesses from a project-name prefix.
The private witnesses and full mapping stay on the capture host.

The checked-in overlay selects **1,017 committed records**: 810 attributed to
vuoro-cloud and 207 to Vuoro. It contains only event IDs, canonical repository
names, byte fingerprints, line positions and recorded Git/source identifiers.
It contains no paths, commands, session identifiers or private witness payloads.
The remaining **382 records** belong to an uncommitted September 30 tail and are
absent from this public overlay. Source commits/blobs name recorded provenance;
the query verifies supplied bytes, not Git ancestry or signing authority.

## Ordinary consumer command

Run from an agentops checkout. Supply physical paths explicitly; the overlay does
not locate stores, follow aliases or resolve host paths:

```sh
python scripts/query_audit_attribution.py \
  --overlay docs/evidence/audit-attribution/2026-09-28-through-30.committed.json \
  --source agentops-2026-09-28-committed=_artifacts/agentops/audit/events-2026-09-28.ndjson \
  --source agentops-2026-09-29-committed=_artifacts/agentops/audit/events-2026-09-29.ndjson \
  --source agentops-2026-09-30-committed=_artifacts/agentops/audit/events-2026-09-30.ndjson
```

Default output is a JSON count/coverage receipt. `--events` adds parsed original
events and their separate attribution; those events may contain sensitive data.
Repeat `--source SOURCE_ID=PATH` to verify another physical copy. Identical records
count once. Conflicting bytes or source repository identities fail closed.
No output is emitted before all snapshots and mapped identities pass validation.
Errors return exit 2 and `status=cannot-determine` on stderr.

A source binds an exact newline-terminated byte prefix, its length, SHA256 and
line count. Later append extensions remain untouched and are reported as unparsed
bytes beyond the frozen snapshot. They never silently enter the result. Exact
mapped event ID, source identity, line and raw-line SHA256 must all match.
Unmapped events retain their original source repository for this report; their
project spelling cannot supply attribution. Duplicate mapping identities,
unknown fields, absent mappings, changed bytes and missing source copies refuse
success. An overlay digest covers its entire canonical sorted JSON body except
the digest field; it binds content, and is not a signature or authorization.

The protected host overlay can be supplied as a second `--overlay`, together with
its explicitly supplied source. It must bind the complete frozen tail snapshot,
name the already supplied committed prefix, and begin at the following line.
It cannot rewrite or replace that prefix. The full investigation result is
**1,082 cloud and 317 Vuoro records**, only when that protected overlay is used.
The public command truthfully reports `coverage=committed-only`.

## Source and integration boundaries

The current source snapshots are:

| Day | Committed lines | Selected committed IDs | Selected protected-tail IDs |
| --- | ---: | ---: | ---: |
| September 28 | 925 | 491 | 0 |
| September 29 | 1,357 | 465 | 0 |
| September 30 | 173 | 61 | 382 |

The frozen September 30 host snapshot has 864 lines; the 691 tail lines contain
382 selected events. None of those raw tail bytes or IDs is committed here.
The exact full sorted, newline-terminated ID-set SHA256 is
`31140c79e271bef3e5f4fa7653b4bd614c8e621f77c61bbb13cede697255324a`.

Existing `auditctl list` reads the owner's SQLite index and has no attribution
join. An ordinary list adapter would be a distinct reviewed owner change; this
script is the current consumer entrypoint. `check_producers` intentionally counts
SQLite and shard loci separately, so its producer-census semantics are unchanged.
`cost_per_release` uses session-cost JSONL and Sprintctl exports rather than this
shard corpus.

Future S4 import must bind the same overlay revision and original source bytes in
its explicit import manifest and proposed `source_binding`. Preserve committed
blob provenance separately from frozen uncommitted-tail provenance; preserve
original digest domains and the historical producer namespace. The new native
run-evidence carrier is not a legacy-import carrier. No actual legacy-import
protocol, S4 import integration, import/rebuild or item #2592 acceptance is claimed
by this query. This bounded source can support those later owner gates.
