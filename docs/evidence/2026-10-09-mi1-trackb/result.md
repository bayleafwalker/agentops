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
   `missing`; if present but the Release read was not supplied it stays
   `missing`; if different, or not 64 lowercase hex, it is `conflict`.
5. **Protected verification.** `acceptance.verification` must have exactly the
   proof keys and a receipt of schema
   `sprintctl-protected-artifact-verification/v1` that repeats the intent ID,
   revision, canonical digest and release digest. Its `artifact` must be
   `{domain: utf8-unified-diff/v1, digest: "sha256:" + hex SHA-256 of the UTF-8 diff bytes}`.
   The proof's own `run_id` and `item_id` are only checked as non-empty text;
   they are not compared with the intent's `run_id` or `item_id`.
   It needs 1 to 64 uniquely named checks, each `status: passed` with a
   `sha256:` revision. `verifier_principal` must equal the acceptor, and
   `evidence_digest` must equal the SHA-256 of the canonical receipt body.
   `entry_digest` is shown as an owner assertion and is not re-fetched.
6. **Application receipt.** `intent.application` with `applier_principal`,
   `applied_at`, `commit_sha` (40 or 64 lowercase hex), only if `state` is
   `applied` and the acceptance link is observed. It does not require the
   protected verification or Release binding to be observed on its own, only
   that they not be in conflict.

Not authorizing: work Decisions (`work.read.item-decisions`), leases and claim
histories (`work.lease.read-v1`), labels, aliases, provider verdicts. Decision
IDs are listed but `verification_evidence` stays `missing` without the
protected proof.

## How a changed diff invalidates approval

Approval is bound by value, not by name. If `unified_diff` changes, the
recomputed digest changes, so:

- if the stored `canonical_intent_digest` was not updated, `artifact` is
  `conflict`, and an existing acceptance is also `conflict` (the acceptance
  check requires `digest == intent["canonical_intent_digest"]`);
- if it was updated but the acceptance still carries the old digest, the
  acceptance check `acceptance.canonical_intent_digest != digest` fails and
  `acceptance` is `conflict`;
- if a protected proof is present, it repeats the digest and the raw diff
  digest, so `_valid_proof` fails (or the acceptance is not observed) and
  `verification_evidence` is `conflict`; with no proof it stays `missing`;
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

## Independent documentation completion verdict (native successor)

Date: 2026-10-09. This replaces the predecessor's "UNFINISHED" section.

- Verdict: **DOCUMENTATION CHECK COMPLETE (bounded)**. The prose claims were
  checked against source, corrected below, and the app's locked suite passed.
  This covers only this document. It is not MI-1, Track B (2617), P1 (2612) or
  protected-authority proof, and carries no effect authority. Passing tests do
  not show the claims are exhaustively correct; they were checked by reading.
- Source commit at check: `02408686bf8ba3fa29c15eac6dd293fc9ca3bf3f` (`git rev-parse HEAD`;
  branch `feat/mi1-trackb-native-20261009`). Predecessor read `5b1061c`, its
  parent. I did not diff the app source between them, so unchanged source is
  assumed, not verified.
- Artifact digest initially read: `5ace0fda87c9f125efd634c00f11cc56ee2b8e5bb8a8bc7797c9190de191f5bb`,
  computed as `git show HEAD:docs/evidence/2026-10-09-mi1-trackb/result.md | sha256sum`
  and equal to the expected value. (I edited the file via Read/Edit before
  computing it, so this is the committed original, not a first-read hash.)
- Successor run ID: none. No Vuoro run was registered or fabricated by me.
- Harness: `claude-code` build `2.1.289` (`claude --version`, run after the
  edits). Note it differs from the predecessor's `2.1.295`. Model: the session
  was told it is `claude-sonnet-5-5`; not independently verifiable.
- Checked by reading: `reconstruction.py`, `reconstruction_cli.py`, `sources.py`
  (read allowlist and read-semantics refusal), `docs/runbooks/operator-reconstruction.md`,
  test names in `tests/test_reconstruction.py` (the four test families named
  above exist).
- Errors found and corrected: (1) an un-updated stored digest also conflicts an
  existing acceptance, not only `artifact`; (2) `verification_evidence` conflicts
  only when a proof is present, otherwise it stays `missing`; (3) the receipt
  artifact digest is `sha256:`-prefixed; (4) the Release binding has extra
  missing and malformed-digest cases; (5) the proof's `run_id`/`item_id` are not
  compared to the intent; (6) application-receipt and `commit_sha` conditions
  made precise. Other statements matched source.
- Tests actually executed (the first attempt was denied; these ran after a
  narrower allowance):
  `uv sync --extra dev --locked --project apps/operator-projection` (installed 24
  packages) and `uv run --project apps/operator-projection --extra dev pytest -q apps/operator-projection`.
  Result, run twice: **155 passed, 15 skipped**, no failures. Skip reasons were
  not captured (`-rs` printed no reasons). This was run from the repository
  root with `--project`, not from inside the app directory as CI does. The CLI
  was not run. The "I did not run the test suite" statement above describes the
  predecessor only.
- Side effect: `uv sync` rewrote two tracked files,
  `apps/operator-projection/src/operator_projection.egg-info/PKG-INFO` and
  `SOURCES.txt`. A revert was denied, so they remain modified. They are not part
  of this task's scope and must not be captured with the result.
- Remaining unknowns: why 15 tests skipped; CI-equivalent behaviour from the app
  directory; whether a real accepted effect with `release_digest` and
  `acceptance.verification` exists; the Sprintctl version in service; whether
  `run_id` should be bound by acceptance; whether `origin/main` equalled
  `5b1061c` at the predecessor's start; the serving model; any Vuoro run record.
