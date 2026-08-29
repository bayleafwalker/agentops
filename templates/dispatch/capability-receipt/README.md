# Capability receipt

> **Lifecycle changed 2026-08-29 (v2).** `draft -> current -> superseded`; the
> `ratification` block is replaced by `established_by` (provenance and authority
> basis) plus `validity`. Establishing a receipt is not an approval step and no
> `actor_type` gates it. See `../model/README.md`, which is authoritative, and
> the v1 compatibility note there. v1 files still validate. v1

A capability receipt records a before/after capability delta at a natural
project boundary. It is not a work log, a numerical score, a project
justification, or an automatically publishable claim. If work completed but no
reliable capability changed, there is no receipt to write.

The normative semantic contract is enforced by
`../scripts/validate_capability_receipts.py`. The dependency-free Python
validator is authoritative for lifecycle, provenance, and lineage constraints.
`capability-receipt.schema.json` mirrors the structure and selected conditions
for editor support, but it is not the semantic authority. Private receipts
belong outside repositories:

```text
/projects/dev/_artifacts/<repo-id>/capability/receipts/<receipt-id>.json
```

`publication: private` is metadata, not access control. Never commit a private
receipt body to a public repository. Back up `_artifacts/` alongside the
workspace repositories.

## What a receipt captures

`before` and `after` state what changed in reliable capability, not which tasks
ran. `locus` distinguishes capability that is embodied, delegated, governed,
or institutionalised. The remaining fields record evidence, dependencies,
counterfactual cost, transfer, changed belief, displaced work, and a future
observation that would weaken the claim.

Every boundary, evidence, or expectation pointer is a structured exact
reference within the named source system:

```json
{
  "kind": "git-commit",
  "source": "repo:example",
  "revision": "0123456789abcdef0123456789abcdef01234567"
}
```

`source` identifies the originating system and object. `revision` is
kind-specific; the validator accepts only these exact forms:

| `kind` | Required `revision` |
| --- | --- |
| `git-commit` | Lowercase full 40- or 64-character Git object ID |
| `sprint-event` | `event:<positive integer>` |
| `artifact`, `verification-result` | `sha256:<lowercase content SHA-256>` |
| `document`, `release` | A lowercase full Git object ID or `sha256:<lowercase content SHA-256>` |

Branches and mutable aliases such as `main`, `HEAD`, and `latest` are not
provenance. A sprint-close boundary has this exact source shape (with the
owning project and sprint id) and names the exact local close event separately:

```json
{
  "kind": "sprint-event",
  "source": "sprintctl:<project>:sprint:<id>",
  "revision": "event:<positive integer>"
}
```

`sprint-event` is a deliberately local reference, not a content-bound one.
`event:<id>` identifies a row in the named Sprintctl database; it is not a
digest and is not guaranteed to survive database migration, event deletion,
or resequencing. A receipt that uses it depends on preserving that database,
event, and source mapping. Record this dependency explicitly in the receipt,
and do not treat the receipt as independently durable if the event can no
longer be resolved. The validator checks the reference shape only; it does not
prove that the event exists or still denotes the original content.

`expectation_ref` is optional because contemporaneous expectations do not
always exist. Do not invent one after the fact. Record every material gap in
`unknowns`, including why the evidence cannot currently answer it. An empty
`unknowns` array is an assertion that no material unknown was identified, not a
prompt to manufacture certainty.

## Lifecycle and authority

1. Confirm that a release, substantial sprint close, killed experiment, or
   major operating change is a real capability boundary.
2. Gather exact refs to contemporaneous expectations, sprint events,
   decisions, commits, ADRs, and verification results.
3. Write `status: draft`, keep publication `private`, and choose an id that
   starts with the exact project id plus a dot, such as
   `<project>.<date>.<boundary>`. Validate the exact bytes:

   ```bash
   python /projects/dev/agentops/templates/dispatch/scripts/validate_capability_receipts.py \
     /projects/dev/_artifacts/<repo-id>/capability/receipts/<receipt-id>.json \
     --expected-project <repo-id>
   ```

4. Record only `receipt_id`, `receipt_path`, and the validator's
   `receipt_sha256` in the owning sprint event. Never copy a private receipt
   body into sprint state.
5. Establish the successor under whatever authority actually applies. A
   `current` or `superseded` receipt carries `established_by` with the actor,
   the `actor_type` that acted (`human`, `agent` or `automation`), the time, an
   `authority_basis`, and an immutable `decision_ref` to the decision record.
   An `authority_basis` of `owner-reserved` marks a change only the owner may
   make -- that is a property of the change, not a queue the receipt waits in.
   All of these are declared assertions: neither the format nor the validator
   authenticates identity, authority, or the referenced record's existence, and
   successful validation is not proof that the named actor acted.
6. Give every successor a new receipt id and path. Create that path with
   exclusive, non-overwriting semantics and fail if it already exists. Never
   truncate an existing receipt or rename a file over it. This is a required
   writer workflow; the JSON Schema, validator, and ordinary filesystem state
   cannot prove after the fact that exclusive creation occurred.
7. Make `supersedes` name the exact predecessor id and SHA-256 digest, then
   validate the predecessor and successor together (or validate their common
   directory). Record the successor's digest. Never overwrite or delete the
   predecessor.

The validator accepts receipt files or directories, can require their project
identity with `--expected-project`, and prints only a path and SHA-256 digest
for each valid file. Every `supersedes` target must be present in the complete
validation input. The validator resolves its id, checks the digest against the
predecessor's exact bytes, requires the same project, rejects duplicate ids and
lineage cycles, and emits no partial success output.

Establishment does not by itself authorize publication. Both `candidate` and
`published` require a `current` or `superseded` successor containing the
procedural human-attestation assertions, an external `decision_ref`, and a
resolved `supersedes` link. Validator success proves only that those assertions
and links satisfy the contract; it is not identity proof. Corrections and
lifecycle changes are append-only too: write a new file and point its
`supersedes` reference at the exact prior id and digest. A corrected private
draft may use the link without a establishment assertion; it remains ineligible
for publication.

Do not add numerical scores. Precision belongs in exact evidence with explicit
durability limits,
explicit unknowns, dependencies, counterfactual, and disconfirmation
condition.
