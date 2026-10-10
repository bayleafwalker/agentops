# Portable P1 bundle contract

Agentops owns `operator-reconstruction-bundle/v1` beside its existing P1
capture/reconstruction. Vuoro may later transport the opaque bundle under
#2637. Sprintctl alone owns Decisions. This first slice exports a supplied
capture and exact UTF-8 unified-diff bytes, then verifies them entirely offline.
It adds no transport, credential, owner-signing key, trust anchor, record store,
import/recovery operation, network read or settlement writer. S8 portability
and hosted transport qualification remain separate.

```sh
python -m operator_projection.bundle_cli export --capture owner-reads.json --artifact proposal.diff > result.bundle.json
python -m operator_projection.bundle_cli verify result.bundle.json
```

Run these from the installed operator-projection package or its locked dev
environment. Export prints one self-contained JSON file; verify prints a derived
integrity/reconstruction report. Inputs are never rewritten. Exit 2 refuses
malformed, overlong or internally inconsistent bundle bytes. Exit 0 includes
valid byte integrity with P1 missing links or conflicts; it is never acceptance.

## Exact bytes and manifest

The envelope has exactly `schema`, `manifest`, `capture_utf8`, `artifact_utf8`
and `report`. The capture is carried as a JSON string so UTF-8 decoding and
re-encoding preserves the original capture's bytes, whitespace and final
newline. Its contents must be strict `operator-reconstruction-capture/v1`
JSON, validated by the existing P1 reconstruction. The separately supplied
artifact must exactly equal that capture's intent `unified_diff` UTF-8 bytes.
Other artifact kinds, binary files, source trees, resulting repository bytes
and images are outside this slice. If no owner intent/diff is supplied, export
refuses to invent the artifact. A missing application/verification link in an
otherwise supplied intent stays missing.

The strict manifest has exactly three entries, each with `domain`, `bytes`
(integer length) and lowercase `sha256`:

| Entry | Byte domain |
| --- | --- |
| capture | utf8-p1-capture/v1: exact original capture file bytes |
| artifact | utf8-unified-diff/v1: exact proposal diff bytes |
| report | canonical-operator-reconstruction/v1: P1 canonical JSON report bytes |

Verification recomputes all three lengths/hashes from the carried bytes,
checks the separate artifact against the capture, reruns existing P1 in
supplied-capture mode and compares the full derived report. This differs from
merely validating self-reported hash syntax. The manifest has no authentication:
an author can replace every byte and recompute every hash.

The entire UTF-8 bundle is limited to 4 MiB, including CLI final newline;
capture bytes to 512 KiB, artifact bytes to 256 KiB and canonical report bytes
to 1 MiB. JSON nesting is limited to 64 and values to 100,000. Duplicate keys
(including inside the carried capture), nonfinite numbers, invalid UTF-8,
escaped Unicode surrogates, unknown manifest/envelope fields and signature
extensions are refused. JSON escaping may cause an export to exceed its total
bound even when each individual input fits. No artifact path or URL from the
capture is opened; the CLI reads only its explicit input paths.

## Integrity and authority are separate

Every successful offline verification reports:

- `integrity=verified-local-bytes`;
- `owner_authority=UNKNOWN`, `owner_currentness=UNKNOWN` and
  `history_completeness=UNKNOWN`;
- `owner_provenance=unauthenticated supplied capture` and
  `authorizes_effects=false`;
- unchanged P1 consistency, missing/conflicting links and the derived report.

These unknowns remain even if every P1 link is consistent or the capture calls
itself live/signed/current. P1 `complete` means supplied link consistency;
it does not mean complete owner history, current accepted work, authenticated
owner responses, independently executed checks or verified resulting repository
bytes. A substituted stale Release may produce P1 conflicts. A stale but
self-consistent entire capture cannot be distinguished from a current one
offline and remains currentness UNKNOWN. Timestamps cannot resolve that.

No owner signature/trust contract exists here, so this CLI accepts no supposed
trusted proof or online mode. A fresh independently authenticated owner readback
belongs to a separately authorized operation; it can compare owner facts later
without turning this file into authority. Neither output permits a Decision,
effect application or secret disclosure. The caller chooses what supplied
content to export; this command preserves it and does not redact private owner
records. Actual private captures/artifacts belong in the private proof packet,
not public source/tests.

The ownership clarification for existing agentops#2620 follows TS-5/6/16/17,
[P1's owner contract](../../docs/runbooks/operator-reconstruction.md) and the
existing [cross-attempt comparison](COMPARISON.md). No duplicate item or second
P1 implementation is introduced.
