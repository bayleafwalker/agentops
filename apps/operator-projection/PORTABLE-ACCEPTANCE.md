# Portable acceptance explanation contract (v1)

`operator-acceptance-presentation/v1` is a pure, bounded projection of the
existing `operator-reconstruction/v1` report. Agentops owns it beside P1; it
does not read an owner, authenticate a caller, write a Decision, evaluate
acceptance, or authorize an effect. The ordinary `reconstruct` CLI and its
existing JSON/text output do not change. A future Vuoro transport must perform
its own current caller, repository, and work-read authorization before invoking
this projection. A supplied report cannot prove owner provenance or freshness.

The JSON DTO has exactly: schema, source_schema, derived, authorizes_effects,
repo_id, intent_id, status, provenance, links, missing, and sources. It copies
P1's eight link statuses in P1 order (`observed`, `missing`, `conflict`), its
aggregate status (`complete`, `incomplete`, `conflict`), and the ordered missing
link names. It validates these fixed fields and refuses an inconsistent report;
it does not recompute P1's joins or acceptance decision. `provenance` preserves
P1's source mode but always says authentication and current authorization are
`unknown`. Source rows contain only the fixed operation, read status and a
strict UTC observation time or null; a timestamp is not owner event time.

Observed link facts are a small allowlist: intent ID/revision/item/state;
Release digest; exact Release binding digest; the fixed caveat that claim
history is item-scoped; canonical intent digest and base commit; protected
evidence digest; acceptance's bound intent revision/digest; and applied commit
SHA. Missing/conflicting links carry only their status. Acceptance identity
and policy revision remain explicitly `unknown` until an owner contract says
which identifiers are safe to disclose. P1's raw principal, Release acceptance
contract, lease/outcome histories, verifier receipt, URL, free text, raw-source
digest, and arbitrary error/reason strings never enter this DTO or its text.
The exact canonical intent digest is a deliberate authorized disclosure for
the requested artifact identity; no additional raw-content hash is emitted.

The text renderer consumes only this DTO and prints fixed labels, the same
link statuses, safe facts, explicit missing names and the unknown authority
state. Both functions reject malformed or overlong fields with a generic
error. Neither output is a bearer token, a current authorization proof, a
complete owner history, independently attested verification, or a resulting
repository-byte proof. Real Claude/ChatGPT rendering and hosted transport
remain gated by agentops#2635 and the corresponding authorized deployment.

This contract follows [P1](../../docs/runbooks/operator-reconstruction.md),
TS-1/5/16/17 in the [target state](../../docs/plans/2026-09-17-target-state.md),
and the [offline bundle's separate integrity/authority rule](BUNDLE.md).
