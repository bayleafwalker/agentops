# MI-1 Track B hosted predecessor handoff: exact-artifact reconstruction

Cohort `mi1-trackb-20261009`. This is a bounded **documentation** handoff from a
hosted Claude Code session. It is not the completion of MI-1, of Track B
(served item 2617) or of P1 (item 2612). It carries no effect authority.

## Run identity

- Vuoro-Run: unavailable (tools not listed)
- The session had no Vuoro connector record tools (`register_run`,
  `append_evidence`, `write_session_note`, or any `mcp__Vuoro__*` tool). A
  tool search for `vuoro` and `register_run` returned no match. No run was
  registered, no report evidence was appended and no session note was written.
  No native credential was used to simulate registration.
- Harness: `claude-code`, build `2.1.295` (output of `claude --version`).
- Model configured for the session: `claude-sonnet-5-5`. The serving model was
  not independently verified; `get_session` was not called.
- Source HEAD read: `5b1061c6fdf5eeb9bdec10fd2ef8223426ba3d25` (equal to
  `origin/main` at start of the session).
- Artifact SHA256 of this file: in the PR body (a file cannot contain its own
  digest).
- Instruction digest: none computed. The instructions were a one-off task
  prompt, not a versioned prompt file, so no honest `instruction_digest` exists.

## Source read

- `apps/operator-projection/src/operator_projection/reconstruction.py`
  (`reconstruct`, `collect`, `intent_digest`, `_valid_proof`)
- `apps/operator-projection/src/operator_projection/reconstruction_cli.py`
- `apps/operator-projection/src/operator_projection/sources.py` (read allowlist)
- `docs/runbooks/operator-reconstruction.md`
- Test names in `apps/operator-projection/tests/test_reconstruction.py`

I did **not** run the test suite or the CLI.

## Which owner fields authorize an effect

The reconstruction authorizes nothing: every report has
`authorizes_effects: false`. It shows whether the owner's records bind an
effect to an exact artifact. The fields it reads from the effect intent
(`work.effect.get-v1`):

1. **Identity and content.** `intent_id`, `revision`, `state`, `run_id`, and the
   six content fields `item_id`, `repository`, `base_commit`, `title`,
   `rationale`, `unified_diff`.
2. **Recorded digest.** `canonical_intent_digest`. The projection recomputes
   SHA-256 over canonical JSON (sorted keys, compact separators, UTF-8) of
   `{"schema": "sprintctl-effect-intent/v1"} + the six content fields`, and
   compares. A mismatch marks `artifact` as `conflict`.
3. **Acceptance.** `intent.acceptance` must have the same `intent_id`, the same
   `intent_revision`, and a `canonical_intent_digest` equal to the *recomputed*
   digest. It needs a non-empty `acceptor_principal` and `accepted_at`, and the
   intent `state` must be `accepted` or `applied`. `acceptor_policy_version` is
   displayed but not validated (it may be null).
4. **Release binding.** `intent.release_digest` (64 hex) must equal the current
   `release.release_digest` from `work.read.release`. If absent the link stays
   `missing`; if different it is `conflict`.
5. **Protected verification.** `acceptance.verification` must have exactly the
   proof keys and a receipt of schema
   `sprintctl-protected-artifact-verification/v1` that repeats the intent ID,
   revision, canonical digest and release digest. Its `artifact` must be
   `{domain: utf8-unified-diff/v1, digest: sha256 of the UTF-8 diff bytes}`.
   It needs 1 to 64 uniquely named checks, each `status: passed` with a
   `sha256:` revision. `verifier_principal` must equal the acceptor, and
   `evidence_digest` must equal the SHA-256 of the canonical receipt body.
   `entry_digest` is shown as an owner assertion and is not re-fetched.
6. **Application receipt.** `intent.application` with `applier_principal`,
   `applied_at`, `commit_sha` (40 or 64 hex), only if `state` is `applied` and
   the acceptance link is observed.

Not authorizing: work Decisions (`work.read.item-decisions`), leases and claim
histories (`work.lease.read-v1`), labels, aliases, provider verdicts. Decision
IDs are listed but `verification_evidence` stays `missing` without the
protected proof.

## How a changed diff invalidates approval

Approval is bound by value, not by name. If `unified_diff` changes, the
recomputed digest changes, so:

- if the stored `canonical_intent_digest` was not updated, `artifact` is
  `conflict`;
- if it was updated but the acceptance still carries the old digest, the
  acceptance check `acceptance.canonical_intent_digest != digest` fails and
  `acceptance` is `conflict`;
- the protected receipt repeats the digest and the raw diff digest, so
  `_valid_proof` fails and `verification_evidence` is `conflict`;
- an application receipt then becomes `conflict` too, because it requires an
  observed acceptance.

The digest covers more than the diff: a change to `base_commit`, `title`,
`rationale`, `repository` or `item_id` also invalidates approval. `revision`
and `state` are *not* in the digest; revision is bound separately by
`acceptance.intent_revision`. `run_id` is bound by neither, so it is not
protected by the digest.

## What a native successor must validate before applying this document

1. Re-derive the claims above from source at a current HEAD; this document
   describes `5b1061c` only.
2. Run the app's locked test suite and the relevant tests (stale-diff,
   cross-repository/item/request, missing-receipt, duplicate-field).
3. Confirm the report status. `complete` means the observed record links are
   consistent. It does not mean checks ran, the resulting repository bytes
   match, or the capture is authentic. A supplied capture is unauthenticated.
4. Obtain the intent through a live owner read with a catalog showing the four
   operations as read-semantics, not from a capture, before treating the
   links as observed owner state.
5. Confirm the protected owner, not this document or a public client, applies
   any effect. Exit code 0 from the CLI is not acceptance.
6. Check that this PR's artifact digest matches the file you are reading.

## Unknown observations

- Whether any Vuoro run record exists for this session: none was registered.
- Whether the sprintctl owner version in service still emits the fields
  described (runbook cites Sprintctl 0.13.1). Not checked.
- Whether `release_digest` and `acceptance.verification` exist on any real
  intent. No real accepted effect was read in this session.
- Whether the test suite passes at this HEAD. Not run.
- Whether `run_id` should be bound by acceptance. Observed unbound; whether
  that is intended is unknown.
- The serving model and the harness environment's provenance beyond the
  values above.

## Successor task: UNFINISHED

A native successor must independently check every statement above against
source, correct any error in this file, and replace the verdict below.

- Completion verdict: **NOT COMPLETE** (no independent check has been done)
- Successor run ID: _unset_
- Errors found and corrected: _unset_
- Date and source HEAD of the check: _unset_
