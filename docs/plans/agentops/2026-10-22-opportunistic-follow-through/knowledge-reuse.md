# Knowledge reuse: owner-mapped regression cases

Status: qualification cases, 22 October 2026. This artifact identifies what to
exercise and which owner is responsible. It contains no runtime pass results.

## Current boundary

[`vuoro-knowledge`](https://github.com/bayleafwalker/vuoro/blob/1eae8ace228af39bd224565bac5be0a1fb7c4f25/packages/vuoro-knowledge/README.md)
resolves Git-authored documents from supplied checkouts. Its current CLI can
read only what the caller can read on disk; it is not a multi-principal source
permission service. It binds source identities in a context manifest, and
`recheck` identifies changes requiring review. Existing tests cover dirty
sources, exact historical revision retrieval, changed governing documents and
tampered manifests.

[`vuoro-workspace`](https://github.com/bayleafwalker/vuoro/blob/1eae8ace228af39bd224565bac5be0a1fb7c4f25/packages/vuoro-workspace/README.md)
owns workspace membership, knowledge/artifact revisions and publication state.
It may cite repository documents; it does not mirror or author their truth.
Neither ownership statement establishes a shared analytical-memory cache or
complete column-level lineage. Retired Kctl is not the destination for this work.

## Cases for the current owners

| ID | Setup and change | Required observation | Owner / existing anchor |
| --- | --- | --- | --- |
| KR-1 | Bind a Git source; change a governing section before work resumes. | `recheck` reports refresh/review needed and identifies the changed source. Preserve the original manifest as historical evidence. | `vuoro-knowledge`; `test_cli_resolve_and_recheck` in `test_retrieval_and_binding.py`. |
| KR-2 | Retrieve a bounded section, then change another governing part of its full source. | Source revision/digest and applicability notices remain visible; unchanged excerpt bytes must not imply unchanged governing evidence. | `vuoro-knowledge`; exact-revision and bounded-get tests are relevant but do not by themselves establish this combined scenario. |
| KR-3 | A mandatory source becomes unavailable or no longer applicable. | Consumption names unavailable mandatory context and preserves the blocked/unknown condition; it is not an empty successful answer or a permission grant. | `vuoro-knowledge`; consumption-policy tests and resolver. |
| KR-4 | A workspace reader loses membership after previously retrieving an artifact. | A fresh owner read enforces current membership; an old receipt does not confer current access. Retained historical evidence remains subject to its own access policy. | `vuoro-workspace`; membership and retrieval owner boundary. Requires its own execution receipt. |
| KR-5 | A published workspace item has a superseding or withdrawn revision. | Read/resolve reports the requested revision and current publication meaning without silently rewriting the old version. | `vuoro-workspace`; revision/publication owner boundary. |
| KR-6 | A manifest's selected sources or governing claims are edited after binding. | Tampered binding is refused rather than re-hashed into apparently authentic evidence. | `vuoro-knowledge`; `test_tampered_manifest_is_refused`. |

Test-name references above identify inspected source, not tests executed by this
packet. Run affected owner tests and retain exact source/artifact/environment
provenance when implementing or qualifying a change.

## Conditional cases before introducing shared derived-result reuse

Only activate these when an actual consumer and cache boundary exist. A new
derived cache would need its own owner and an evidenced reason under TS-12.

| ID | Change | Acceptance condition |
| --- | --- | --- |
| DR-1 | A result depends on two sources; access to either source is revoked. | Re-evaluate all transitive dependencies under the current caller. Do not serve the old result on the strength of the other source or the result's own label. |
| DR-2 | A formula, semantic definition or transformation changes while source bytes do not. | The dependency identity includes the transformation/definition revision; identify affected derived claims as stale or requiring recomputation. |
| DR-3 | A derivation is incomplete or contains an opaque upstream result. | Mark lineage incomplete; deny reuse that requires complete authorization rather than assuming the missing dependencies are public. |
| DR-4 | Two same-named indicators use different definitions. | Preserve distinct identities and show a conflict; name equality does not reconcile semantics. |
| DR-5 | An invalidated value remains in historical audit material. | Preserve authorized historical evidence while preventing it from being served as current reusable knowledge. Invalidation is not silent deletion of provenance. |
| DR-6 | A refusal path includes source names, hashes or snippets. | Check that diagnostics do not reveal information the caller may not receive; preserve a bounded refusal and an owner-private evidence reference. |

Record the expected affected set from an independently reviewed dependency
fixture before evaluating the implementation. Compare both false negatives
(unsafe reuse) and false positives (unnecessary invalidation). Do not call
column-level enforcement proven when the fixture only has document-level edges.

[Lineage-Aware Memory Governance](https://arxiv.org/abs/2610.07258) supplies a
useful conditional argument: the reuse decision needs the complete derivation
and source authorization. Its nine real-agent round trips are a feasibility
demonstration, not production evidence. The cases above are an application to
the estate's actual ownership boundaries, not adoption of the paper's system.
