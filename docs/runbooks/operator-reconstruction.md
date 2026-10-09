# Effect reconstruction

`operator-projection reconstruct` is the reading surface for MI-1/P1
(served agentops item 2612; target TS-17). It reads owner records and renders
every observed, missing or conflicting link. It authorizes no effect, stores no
work state and changes no owner record or deployment.

```sh
operator-projection --profile profile.yaml reconstruct \
  --repo-id agentops --intent-id effect_example
```

The profile has the existing operator-projection profile shape:
`authority_url` and a `file:` `credential_ref`. The command uses only
`work.effect.get-v1`, `work.read.release`, `work.read.item-decisions` and
`work.lease.read-v1`. Each must be read-semantics in the fetched catalog. The
front-page generator's separate read allowlist is unchanged. This source adds
no credential, grant, catalog operation or public effect-apply capability.
Unavailable or denied owner reads remain visible gaps; there is no local DB
fallback. An unavailable effect read prevents guessing the item's other links.

For a supplied local capture:

```sh
operator-projection reconstruct --snapshot owner-reads.json --text
```

The capture schema is `operator-reconstruction-capture/v1`, with `repo_id`,
`intent_id` and `results` keyed by the four allowed operation names. Each result
has `status` (`observed` or `unavailable`), exact request `arguments`, an optional
`observed_at`, and the unchanged owner `value` for an observed response. The
effect request uses `intent_id`; the remaining reads use its `item_id`. A
supplied capture cannot declare itself authenticated live evidence. Input bytes
are never rewritten. Result digests bind supplied response content; they do not
authenticate who supplied it or attest execution.

## What the report establishes

The eight links are always present: intent, current work release, release-to-intent
binding, attempts/claims, artifact, verification evidence, acceptance and receipt.
The artifact domain is explicitly `sprintctl-effect-intent/v1`: the canonical
proposal content and its unified-diff byte digest. It is not a Release digest,
Git commit hash, built artifact digest or proof of resulting repository bytes.
The canonical digest uses the published owner's frozen versioned fields, and the
projection recomputes it before displaying an acceptance binding.

An acceptance must name that exact intent ID, revision and recomputed digest.
A changed diff cannot reuse its acceptance or application receipt. The
acceptor/policy and applier/commit come from owner records; labels and ordinary
work Decisions cannot supply effect authority. An operator acceptor's absent
policy revision stays null. Item claim histories are displayed as item histories;
not every attempt is necessarily the effect's run. No advisory reservation is
promoted to a lease.

## Protected owner bindings and acceptance boundary

Sprintctl 0.13.1 records an explicit work-release digest and an owner-frozen
protected verification receipt on an accepted intent. Reconstruction compares
that digest with the current Release and independently validates the receipt's
intent ID, revision, canonical content digest, raw UTF-8 diff digest, Release,
verifier/acceptor identity, evidence digest and bounded revisioned passed checks.
The chain-entry digest is displayed as an owner assertion; the projection does
not independently fetch or authenticate the original evidence chain entry.

Legacy records without these fields remain **missing**. Item ID association and
ordinary work Decisions cannot replace them. A changed current Release or
malformed protected receipt renders verification, acceptance and any application
receipt as conflicting. A removed application receipt remains an explicit
missing link. The supplied capture's provenance remains unauthenticated even
when all links are consistent; `complete` describes the observed record links,
not independent attestation of check execution or resulting repository bytes.

An owner response with mismatched repository, intent, item or request bindings
refuses the whole projection. A stale content/acceptance/receipt binding renders
`conflict`. Source reads can observe different moments; this is not an atomic
cross-operation snapshot. The command returns 0 for a successfully computed
report, including `incomplete` or `conflict`, and 2 for malformed input or an
unsupported capture. Consumers must inspect the report status; exit 0 is not
acceptance.

Source validation alone does not satisfy full item 2612 or MI-1 Track B.
Resulting-artifact verification and the real cross-harness receipt chain still
require runtime evidence. No served website or package deployment is claimed
by landing this source.

## Historical first increment (2026-10-06)

The first increment preceded the protected owner contract and always left
Release/verifier bindings missing. That limitation is superseded by the field
validation described above; its original runtime probe remains historical.

The app's locked-dependency test command covers adversarial stale-diff,
cross-repository/item/request, missing-receipt, duplicate-field and catalog-write
histories. Reconstruction initially had a separate 240-code-line ceiling; the front-page
generator retains its 880-line ceiling. An authorized read-only probe against
`vuoro-shared` returned `incomplete` with all eight links missing because its
effect read was unavailable. This is evidence of the refusal path, not a real
accepted effect or receipt chain. Probe output is session-local and is not
promoted into durable execution evidence.

The protected-binding increment raises only the reconstruction ceiling to 300
code lines to cover receipt validation. Tests recompute outer receipt hashes
after semantic mutations, so an invalid raw digest, verifier, Release or check
cannot be rejected merely because its old hash differs.
